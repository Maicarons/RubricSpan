# -*- coding: utf-8 -*-
"""M2-3：相似度模型微调（text2vec-base-chinese + CosineSimilarityLoss）。

训练对 = M1-7 相似度句子对（label 派生 + SAS-Datasets 真实人工分 + STS-B 中文），
强化专有名词同义判别（戊戌变法 ↔ 百日维新类等价表述）。

M8 调优重训时由 ST `fit` 改为等效手写循环：ST 3.3 的 smart batching 在 8GB
FP32 下仅 ~32 对/步、15-20s/步（2 epochs 需 8-12 小时）；手写循环对每批 64 对
批量 encode（mean pooling）→ cosine-MSE → AdamW linear warmup，定期跑
EmbeddingSimilarityEvaluator 并按 val Pearson 保存最优。训练入口/超参 CLI 不变。

用法（train/ 目录）::

    python -m rubricspan_train.training.train_similarity [--epochs 2]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, InputExample
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
from torch.utils.data import DataLoader
from transformers import get_linear_schedule_with_warmup

from ..common_paths import MODELS_DIR, PROCESSED_DIR

BACKBONE = MODELS_DIR / "backbone" / "text2vec-base-chinese"
OUT_DIR = MODELS_DIR / "artifacts" / "similarity" / "pytorch"


def load_pairs(path: Path) -> list[InputExample]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            s = min(max(float(r["score"]), 0.0), 1.0)
            out.append(InputExample(texts=[r["sentence1"], r["sentence2"]], label=s))
    return out


def evaluate(evaluator, model) -> float:
    """返回 val cosine-Pearson；与 ST fit 内部同一 evaluator 口径。"""
    scores = evaluator(model)
    # ST 3.3 输出 key 形如 f"{name}_pearson_cosine"（name=val）
    return float(
        scores.get("val_pearson_cosine")
        or scores.get("cosine_pearson")
        or next((v for k, v in scores.items() if "pearson" in k), 0.0)
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--warmup", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--eval-every", type=int, default=0, help="0 = 每 1/4 epoch 评估一次")
    args = p.parse_args(argv)

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")
    model = SentenceTransformer(str(BACKBONE), device=device)
    train = load_pairs(PROCESSED_DIR / "similarity_train.jsonl")
    val = load_pairs(PROCESSED_DIR / "similarity_val.jsonl")
    print(f"train pairs={len(train)} val pairs={len(val)}")

    def encode(labels_list: list[str]) -> torch.Tensor:
        # 训练态须保留梯度：不用 model.encode（内部 no_grad），直接 tokenize + ST forward。
        feats = model.tokenizer(
            labels_list, padding=True, truncation="longest_first", max_length=128,
            return_tensors="pt",
        )
        feats = {k: v.to(device) for k, v in feats.items()}
        return model(feats)["sentence_embedding"]

    # 预计算 val 输入列表（与 ST evaluator 复用的形态）
    evaluator = EmbeddingSimilarityEvaluator(
        [ex.texts[0] for ex in val],
        [ex.texts[1] for ex in val],
        [ex.label for ex in val],
        main_similarity="cosine",
        name="val",
    )

    def pass_collate(batch):
        return batch  # list[InputExample] 原样成批，循环内自行取 texts

    loader = DataLoader(train, batch_size=args.batch, shuffle=True, collate_fn=pass_collate)
    steps_per_epoch = len(loader)
    total_steps = steps_per_epoch * args.epochs
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(
        optim, int(args.warmup * total_steps), total_steps
    )

    best_pearson = -1.0
    best_epoch, best_step = 0, 0
    eval_every = args.eval_every or max(1, steps_per_epoch // 4)
    log: dict = {
        "base_model": str(BACKBONE),
        "train_pairs": len(train),
        "val_pairs": len(val),
        "epochs": args.epochs,
        "batch": args.batch,
        "lr": args.lr,
        "loss": "CosineSimilarityLoss(MSE on cosine)",
        "seed": args.seed,
        "epochs_detail": [],
    }

    global_step = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        ep_loss = 0.0
        t0 = time.time()
        for bi, batch in enumerate(loader, 1):
            a = encode([ex.texts[0] for ex in batch])
            b = encode([ex.texts[1] for ex in batch])
            labels = torch.tensor([ex.label for ex in batch], device=device)
            cos = torch.nn.functional.cosine_similarity(a, b)
            loss = torch.nn.functional.mse_loss(cos, labels)
            optim.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            ep_loss += float(loss.item())
            global_step += 1
            if bi % 25 == 0:
                print(
                    f"  step {bi}/{steps_per_epoch} avg_loss={ep_loss / bi:.4f} "
                    f"avg={(time.time() - t0) / bi:.2f}s/step",
                    flush=True,
                )

            if bi % eval_every == 0 or bi == steps_per_epoch:
                model.eval()
                pearson = evaluate(evaluator, model)
                print(
                    f"[epoch {epoch}/{args.epochs}] step {bi}/{steps_per_epoch} "
                    f"train_loss={ep_loss / bi:.4f} val_pearson={pearson:.4f}",
                    flush=True,
                )
                if pearson > best_pearson:
                    best_pearson = pearson
                    best_epoch, best_step = epoch, bi
                    OUT_DIR.mkdir(parents=True, exist_ok=True)
                    model.save(str(OUT_DIR))
                    print(f"  -> saved best ({best_pearson:.4f}) -> {OUT_DIR}", flush=True)
                model.train()
        epoch_secs = round(time.time() - t0)
        log["epochs_detail"].append(
            {"epoch": epoch, "train_loss": round(ep_loss / steps_per_epoch, 4), "secs": epoch_secs}
        )
        print(f"[epoch {epoch}] done in {epoch_secs}s", flush=True)

    log.update({"best_pearson": best_pearson, "best_epoch": best_epoch, "best_step": best_step})
    (OUT_DIR / "train_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"saved -> {OUT_DIR} (best pearson={best_pearson:.4f} @ epoch {best_epoch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())