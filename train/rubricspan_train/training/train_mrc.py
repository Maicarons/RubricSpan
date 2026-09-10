# -*- coding: utf-8 -*-
"""M2-1 / M2-2：MRC 模型微调（mengzi-bert-base）。

两阶段：

- ``bridge``（M2-1，可选加速收敛）：CMRC 2018 预训练桥接 1 epoch；
- ``main``（M2-2）：在 M1 产出的 MRC 五元组上微调 3 epoch，
  逐 epoch 在 val 上评估（loss / span-EM / 有答判定 acc），保存最优权重。

用法（train/ 目录）::

    python -m rubricspan_train.training.train_mrc --stage both
    python -m rubricspan_train.training.train_mrc --stage main   # 跳过桥接

显存不足时 ``--batch 8 --grad-accum 2``（执行计划 R5 预案）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, get_linear_schedule_with_warmup

from ..common_paths import DATA_DIR, MODELS_DIR, TRAIN_DIR
from .mrc_data import featurize, load_cmrc, load_mrc_jsonl

BACKBONE = MODELS_DIR / "backbone" / "mengzi-bert-base"
BRIDGE_DIR = MODELS_DIR / "artifacts" / "mrc" / "pytorch_bridge"
MAIN_DIR = MODELS_DIR / "artifacts" / "mrc" / "pytorch"


class FeatureDataset(Dataset):
    def __init__(self, features: list[dict]) -> None:
        self.features = features

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, i: int) -> dict:
        return self.features[i]


def collate(batch: list[dict]) -> dict:
    return {
        "input_ids": torch.tensor([b["input_ids"] for b in batch], dtype=torch.long),
        "attention_mask": torch.tensor([b["attention_mask"] for b in batch], dtype=torch.long),
        "token_type_ids": torch.tensor([b["token_type_ids"] for b in batch], dtype=torch.long),
        "start_positions": torch.tensor([b["start_positions"] for b in batch], dtype=torch.long),
        "end_positions": torch.tensor([b["end_positions"] for b in batch], dtype=torch.long),
    }


def build_features(tokenizer, examples, max_length: int, drop_truncated_positive: bool) -> list[dict]:
    """分块特征化：一次 tokenizer 批量 500 条，限制峰值内存（曾触发 OpenBLAS OOM）。"""
    import gc

    feats: list[dict] = []
    chunk = 500
    for i in range(0, len(examples), chunk):
        feats.extend(featurize(
            tokenizer, examples[i : i + chunk],
            max_length=max_length,
            drop_truncated_positive=drop_truncated_positive,
        ))
        if i % 5000 == 0:
            gc.collect()
    return feats


def _amp_dtype() -> torch.dtype:
    """bf16 仅 Ampere+（sm≥8.0）；无 CUDA 或 T4/P100 退 FP32 全精度。"""
    if not torch.cuda.is_available():
        return torch.float32
    if torch.cuda.get_device_capability() >= (8, 0):
        return torch.bfloat16
    return torch.float32


@torch.no_grad()
def evaluate(model, loader, device, amp_dtype: torch.dtype) -> dict[str, float]:
    model.eval()
    total_loss = total = 0
    span_correct = span_total = 0
    null_correct = null_total = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        if amp_dtype != torch.float32:
            with torch.autocast("cuda", dtype=amp_dtype):
                out = model(**batch)
        else:
            out = model(**batch)
        total_loss += out.loss.item()
        total += 1
        starts = batch["start_positions"]
        ends = batch["end_positions"]
        pred_s = out.start_logits.argmax(-1)
        pred_e = out.end_logits.argmax(-1)
        is_null = starts == 0
        # span 精确率：预测区间与 gold 完全一致
        exact = (pred_s == starts) & (pred_e == ends)
        span_correct += (exact & ~is_null).sum().item()
        span_total += (~is_null).sum().item()
        null_correct += (exact & is_null).sum().item()
        null_total += is_null.sum().item()
    model.train()
    return {
        "loss": total_loss / max(total, 1),
        "span_exact": span_correct / max(span_total, 1),
        "null_acc": null_correct / max(null_total, 1),
    }


def _strip_examples(examples: list, stem_map: dict[str, str], strip_fn) -> int:
    """对 origin=full 行按题干剥离 context；金标 answer 区间被整段清空的矛盾行保持原样。"""
    changed = 0
    for ex in examples:
        if ex.origin != "full" or not ex.uid:
            continue
        stem = stem_map.get(ex.uid.split("#")[0], "")
        if not stem:
            continue
        before = ex.context
        after = strip_fn(before, [stem])
        if after != before:
            if ex.answer_start >= 0 and ex.answer_end > ex.answer_start and not after[ex.answer_start:ex.answer_end + 1].strip():
                continue  # 数据矛盾：金标区间被剥离，保留原样
            ex.context = after
            changed += 1
    return changed


def train(
    stage: str,
    *,
    epochs: int,
    lr: float,
    batch: int,
    grad_accum: int,
    max_length: int,
    seed: int,
    log: dict,
    strip_stems: bool = False,
    extra_negatives: Path | None = None,
) -> None:
    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp_dtype = _amp_dtype()
    log["amp_dtype"] = str(amp_dtype)
    tok = AutoTokenizer.from_pretrained(BACKBONE, use_fast=True)

    src = BACKBONE if stage == "bridge" or not BRIDGE_DIR.exists() else BRIDGE_DIR
    model = AutoModelForQuestionAnswering.from_pretrained(src).to(device)
    log["init_from"] = str(src)

    if stage == "bridge":
        train_examples = load_cmrc(DATA_DIR / "raw" / "cmrc2018" / "data" / "cmrc2018_train.json")
        val_examples = load_cmrc(DATA_DIR / "raw" / "cmrc2018" / "data" / "cmrc2018_dev.json", limit=500)
        out_dir = BRIDGE_DIR
    else:
        # main 阶段：训练集剔除选择型得分点正例（M8，考点由选项规则负责，
        # 避免"抽字母"捷径入训）；val 保留全量以照常评估模型对选择型点的表现。
        train_examples = load_mrc_jsonl(
            DATA_DIR / "processed" / "mrc_train.jsonl", drop_option_points=True
        )
        val_examples = load_mrc_jsonl(DATA_DIR / "processed" / "mrc_val.jsonl")
        out_dir = MAIN_DIR
        if extra_negatives:
            extra = load_mrc_jsonl(extra_negatives)
            n_train = sum(1 for e in extra if e.split == "train")
            log["extra_negatives"] = {"file": str(extra_negatives), "train_rows": n_train}
            train_examples = train_examples + [e for e in extra if e.split == "train"]
            print(f"[{stage}] 外部 MRC 负例并入 train：+{n_train}（extra_mrc_negatives.jsonl）", flush=True)

    if strip_stems and stage != "bridge":
        # 训练/推理口径一致：推理侧评分入口剥离题干（CC-006），训练 context 也同源剥离；
        # 空格替代保持字符索引稳定，answer_start/end 无需重新定位。
        from .stem_strip import build_stem_map, strip_stem_spans

        stem_map = build_stem_map(DATA_DIR / "raw" / "sas-bench")
        n_train = _strip_examples(train_examples, stem_map, strip_stem_spans)
        n_val = _strip_examples(val_examples, stem_map, strip_stem_spans)
        log["strip_stems"] = {"train_changed": n_train, "val_changed": n_val}
        print(f"[{stage}] 题干剥离：train {n_train} 行、val {n_val} 行 context 被净化", flush=True)

    train_feats = build_features(tok, train_examples, max_length, drop_truncated_positive=True)
    val_feats = build_features(tok, val_examples, max_length, drop_truncated_positive=False)
    log["train_features"] = len(train_feats)
    log["val_features"] = len(val_feats)
    print(f"[{stage}] train={len(train_feats)} (from {len(train_examples)} ex) val={len(val_feats)}")

    train_loader = DataLoader(
        FeatureDataset(train_feats), batch_size=batch, shuffle=True,
        collate_fn=collate, num_workers=0, drop_last=False,
    )
    val_loader = DataLoader(FeatureDataset(val_feats), batch_size=batch * 2, shuffle=False,
                            collate_fn=collate, num_workers=0)

    steps_per_epoch = (len(train_loader) + grad_accum - 1) // grad_accum
    total_steps = steps_per_epoch * epochs
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(optim, int(0.06 * total_steps), total_steps)

    best = {"span_exact": -1.0}
    log["epochs"] = []
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        running = 0.0
        optim.zero_grad(set_to_none=True)
        for it, batch in enumerate(train_loader, 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            if amp_dtype != torch.float32:
                with torch.autocast("cuda", dtype=amp_dtype):
                    out = model(**batch)
                    loss = out.loss / grad_accum
            else:
                out = model(**batch)
                loss = out.loss / grad_accum
            loss.backward()
            running += out.loss.item()
            if it % grad_accum == 0 or it == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optim.step()
                sched.step()
                optim.zero_grad(set_to_none=True)
        metrics = evaluate(model, val_loader, device, amp_dtype)
        metrics["epoch_secs"] = round(time.time() - t0)
        metrics["train_loss"] = round(running / len(train_loader), 4)
        log["epochs"].append({f"epoch{epoch}": metrics})
        print(f"[{stage}] epoch {epoch}: {metrics}", flush=True)
        key = metrics["span_exact"] + 0.2 * metrics["null_acc"]
        if key > best["span_exact"] + 0.2 * best.get("null_acc", 0):
            best = dict(metrics)
            out_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out_dir)
            tok.save_pretrained(out_dir)
            log["best_epoch"] = epoch
            print(f"[{stage}] saved best -> {out_dir}", flush=True)
    log["best"] = best


def main(argv: list[str] | None = None) -> int:
    import os

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["bridge", "main", "both"], default="both")
    p.add_argument("--epochs", type=int, default=0, help="0 = 阶段默认（bridge 1 / main 3）")
    p.add_argument("--lr", type=float, default=0.0)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--grad-accum", type=int, default=1)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--strip-stems", action="store_true",
                   help="main 阶段对训练/验证 context 做题干剥离（与推理侧 CC-006 口径一致）")
    p.add_argument("--extra-negatives", type=Path, default=None,
                   help="外部数据集 MRC is_impossible 负例（data/processed/extra_mrc_negatives.jsonl，"
                        "仅并入 train；来源见 docs/reports/extra-datasets.md）")
    args = p.parse_args(argv)

    stages = ["bridge", "main"] if args.stage == "both" else [args.stage]
    summary: dict[str, dict] = {}
    for stage in stages:
        log: dict = {
            "stage": stage,
            "batch": args.batch,
            "grad_accum": args.grad_accum,
            "max_length": args.max_length,
            "seed": args.seed,
        }
        epochs = args.epochs or (1 if stage == "bridge" else 3)
        lr = args.lr or (3e-5 if stage == "bridge" else 2.5e-5)
        log.update({"epochs": epochs, "lr": lr})
        train(stage, epochs=epochs, lr=lr, batch=args.batch, grad_accum=args.grad_accum,
              max_length=args.max_length, seed=args.seed, log=log, strip_stems=args.strip_stems,
              extra_negatives=args.extra_negatives)
        summary[stage] = log
    out = MODELS_DIR / "artifacts" / "mrc" / "train_log.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({s: {"best": l.get("best")} for s, l in summary.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
