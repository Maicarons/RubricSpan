# -*- coding: utf-8 -*-
"""M2-4 一键评估：EM / Token-F1 / Point-wise Acc / Score Correlation / 等价命中率。

支持 PyTorch 权重与 ONNX（含 INT8）两种后端复评——同一套代码用于：
① 最终指标报告；② M2-6 一致性辅助；③ M2-7 INT8 精度损失对比。

用法（train/ 目录）::

    python -m rubricspan_train.evaluation.report                       # PyTorch 权重
    python -m rubricspan_train.evaluation.report --onnx ../models/mrc/model.onnx
    python -m rubricspan_train.evaluation.report --onnx ../models/mrc/model.int8.onnx --tag int8

产出：``models/artifacts/mrc/eval_{tag}.json``，并打印指标摘要。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..common_paths import DATA_DIR, MODELS_DIR, PROCESSED_DIR, REPO_ROOT
from . import metrics as M
from .backend import load_backend


def encode_batch(tokenizer, queries: list[str], contexts: list[str], max_length: int):
    enc = tokenizer(
        queries, contexts,
        max_length=max_length, truncation="only_second", padding="max_length",
        return_offsets_mapping=True,
    )
    seq_ids = [enc.sequence_ids(i) for i in range(len(contexts))]
    ctx_spans = []
    for sids in seq_ids:
        first = last = -1
        for i, sid in enumerate(sids):
            if sid == 1:
                if first < 0:
                    first = i
                last = i
        ctx_spans.append((first, last))
    return enc, ctx_spans


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_inference(backend, tokenizer, records: list[dict], max_length: int, batch: int = 32) -> list[dict]:
    """对五元组记录批量推理，附加预测字段。"""
    out = []
    for i in range(0, len(records), batch):
        chunk = records[i : i + batch]
        enc, ctx_spans = encode_batch(
            tokenizer,
            [r["query"] for r in chunk],
            [r["context"] for r in chunk],
            max_length,
        )
        input_ids = np.array(enc["input_ids"], dtype=np.int64)
        attention = np.array(enc["attention_mask"], dtype=np.int64)
        token_type = np.array(enc["token_type_ids"], dtype=np.int64)
        s_logits, e_logits = backend(input_ids, attention, token_type)
        for j, r in enumerate(chunk):
            span_range, span_lp, null_lp = M.decode_span(
                s_logits[j], e_logits[j], ctx_spans[j]
            )
            offsets = enc["offset_mapping"][j]
            if span_range != (0, 0):
                s_char = offsets[span_range[0]][0]
                e_char = offsets[span_range[1]][1]
                pred_text = r["context"][s_char:e_char]
            else:
                pred_text = ""
            out.append(
                {
                    **r,
                    "pred_text": pred_text,
                    "span_logprob": float(span_lp),
                    "null_logprob": float(null_lp),
                    "score_diff": float(span_lp - null_lp),
                }
            )
    return out


def tune_threshold(results: list[dict]) -> tuple[float, float]:
    """在 val 上搜有答判定阈值，最大化 point-wise accuracy。"""
    golds = np.array([0.0 if r["is_impossible"] else 1.0 for r in results])
    diffs = np.array([r["score_diff"] for r in results])
    cands = np.unique(diffs)
    if len(cands) > 2000:
        cands = np.quantile(diffs, np.linspace(0, 1, 2000))
    best_t, best_acc = 0.0, -1.0
    for t in cands:
        acc = float(np.mean((diffs > t).astype(float) == golds))
        if acc > best_acc:
            best_acc, best_t = acc, float(t)
    return best_t, best_acc


def mrc_metrics(results: list[dict], threshold: float) -> dict[str, Any]:
    preds = [r["pred_text"] if r["score_diff"] > threshold else "" for r in results]
    golds = ["" if r["is_impossible"] else r["answer"] for r in results]
    pos = [i for i, r in enumerate(results) if not r["is_impossible"]]
    em = sum(M.exact_match(preds[i], golds[i]) for i in pos) / len(pos)
    f1 = sum(M.token_f1(preds[i], golds[i]) for i in pos) / len(pos)
    gold_hit = [not r["is_impossible"] for r in results]
    pred_hit = [p != "" for p in preds]
    acc = sum(int(g == p) for g, p in zip(gold_hit, pred_hit)) / len(results)
    sem_idx = [i for i in pos if results[i].get("hit_type") == "semantic"]
    sem_hit = [pred_hit[i] for i in sem_idx]
    # M8 口径分层：exact / semantic 子集分别报告 EM / Token-F1。
    # 语义改写样本的"正确 span"不唯一（多解），混合口径 EM 天然偏严；
    # 分层便于把"抽取得准不准"（exact 子集）与"改写是否识别"（semantic）分开度量。
    def grp(hit_type: str) -> tuple[list[int], float | None, float | None]:
        idx = [i for i in pos if results[i].get("hit_type") == hit_type]
        if not idx:
            return idx, None, None
        return idx, sum(M.exact_match(preds[i], golds[i]) for i in idx) / len(idx), \
            sum(M.token_f1(preds[i], golds[i]) for i in idx) / len(idx)
    ex_idx, em_exact, f1_exact = grp("exact")
    se_idx, em_semantic, f1_semantic = grp("semantic")
    return {
        "em": round(em, 4),
        "token_f1": round(f1, 4),
        "point_accuracy": round(acc, 4),
        "has_answer_threshold": round(threshold, 4),
        "equivalence_hit_rate": round(sum(sem_hit) / len(sem_hit), 4) if sem_hit else None,
        "semantic_eval_n": len(sem_hit),
        "eval_n": len(results),
        "positives": len(pos),
        "em_exact": round(em_exact, 4) if em_exact is not None else None,
        "f1_exact": round(f1_exact, 4) if f1_exact is not None else None,
        "n_exact": len(ex_idx),
        "em_semantic": round(em_semantic, 4) if em_semantic is not None else None,
        "f1_semantic": round(f1_semantic, 4) if f1_semantic is not None else None,
        "n_semantic": len(se_idx),
    }


def score_correlation(backend, tokenizer, max_length: int, threshold: float) -> dict | None:
    """样本级总分相关性：对 full 样本的全部得分点推理（含被抽样子集外的负例）。"""
    configs = {}
    for p in (DATA_DIR / "scoring_configs").glob("SAS-*.json"):
        configs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    labels = load_jsonl(DATA_DIR / "labeling_cache" / "labels_final.jsonl")
    split_qids = {r["question_id"] for r in load_jsonl(PROCESSED_DIR / "mrc_test.jsonl")}
    recs = []
    for rec in labels:
        if rec.get("origin") != "full" or rec.get("expert_total") is None:
            continue
        if rec["labels"]["question_id"] not in split_qids:
            continue
        config = configs.get(rec["labels"]["question_id"])
        if not config:
            continue
        weight = {p["point_id"]: float(p["weight"]) for p in config["points"]}
        ptext = {p["point_id"]: p["point_text"] for p in config["points"]}
        for pl in rec["labels"]["point_labels"]:
            if pl["point_id"] not in ptext:
                continue
            recs.append(
                {
                    "uid": f'{rec["sample_id"]}#p{pl["point_id"]}',
                    "sample_id": rec["sample_id"],
                    "question_id": rec["labels"]["question_id"],
                    "query": ptext[pl["point_id"]],
                    "context": rec["labels"]["student_answer"],
                    "answer": pl.get("extracted_span", ""),
                    "is_impossible": not pl["hit"],
                    "weight": weight[pl["point_id"]],
                }
            )
    if not recs:
        return None
    results = run_inference(backend, tokenizer, recs, max_length)
    pred_total: dict[str, float] = defaultdict(float)
    gold_total: dict[str, float] = defaultdict(float)
    for r in results:
        credit = 1.0 if r["score_diff"] > threshold else 0.0
        pred_total[r["sample_id"]] += r["weight"] * credit
        gold_total[r["sample_id"]] += r["weight"] * (1.0 if not r["is_impossible"] else 0.0)
    sids = sorted(pred_total)
    xs = [pred_total[s] for s in sids]
    # 对照人工总分（manual_label）
    expert = {r["sample_id"]: r["expert_total"] for r in labels}
    ys = [float(expert[s]) for s in sids if s in expert]
    xs2 = [x for x, s in zip(xs, sids) if s in expert]
    r_pear = M.pearson(xs2, ys)
    # 与标签总分的一致性（隔离“打标质量”与“抽取质量”）
    r_label = M.pearson(xs, [gold_total[s] for s in sids])
    return {
        "n_samples": len(xs2),
        "pearson_vs_expert": round(r_pear, 4),
        "pearson_vs_label": round(r_label, 4),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", default=str(MODELS_DIR / "artifacts" / "mrc" / "pytorch"))
    p.add_argument("--onnx", default="", help="改用 ONNX 后端（M2-6/M2-7 复评）")
    p.add_argument("--tag", default="pt")
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--batch", type=int, default=32)
    args = p.parse_args(argv)

    backend, tokenizer = load_backend(args.model_dir, args.onnx)

    val = load_jsonl(PROCESSED_DIR / "mrc_val.jsonl")
    test = load_jsonl(PROCESSED_DIR / "mrc_test.jsonl")
    print(f"eval: val={len(val)} test={len(test)} backend={'onnx' if args.onnx else 'pt'}")

    val_results = run_inference(backend, tokenizer, val, args.max_length, args.batch)
    threshold, val_acc = tune_threshold(val_results)
    test_results = run_inference(backend, tokenizer, test, args.max_length, args.batch)
    report: dict[str, Any] = {"threshold": threshold, "val_point_accuracy": round(val_acc, 4)}
    report.update(mrc_metrics(test_results, threshold))
    if args.tag in ("pt", "final"):
        corr = score_correlation(backend, tokenizer, args.max_length, threshold)
        if corr:
            report["score_correlation"] = corr

    out = MODELS_DIR / "artifacts" / "mrc" / f"eval_{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
