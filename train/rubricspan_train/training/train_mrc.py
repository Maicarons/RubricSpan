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


@torch.no_grad()
def evaluate(model, loader, device) -> dict[str, float]:
    model.eval()
    total_loss = total = 0
    span_correct = span_total = 0
    null_correct = null_total = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
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
) -> None:
    torch.manual_seed(seed)
    device = "cuda"
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
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(**batch)
                loss = out.loss / grad_accum
            loss.backward()
            running += out.loss.item()
            if it % grad_accum == 0 or it == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optim.step()
                sched.step()
                optim.zero_grad(set_to_none=True)
        metrics = evaluate(model, val_loader, device)
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
              max_length=args.max_length, seed=args.seed, log=log)
        summary[stage] = log
    out = MODELS_DIR / "artifacts" / "mrc" / "train_log.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({s: {"best": l.get("best")} for s, l in summary.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
