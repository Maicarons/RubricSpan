#!/usr/bin/env python3
"""M7 全链路评估：经**真实 Rust 网关 HTTP API** 驱动混合评分，与 M1 金标对齐。

数据：data/processed/mrc_test.jsonl 中 origin=full 的行（真实完整学生答案 ×
逐点金标 is_impossible），按 (question_id, context) 聚合为 155 份"答案卷"；
每份只保留被测得分点（与金标同口径），专家总分 = Σ 命中点 weight。

流程：对抽样答案 → POST /api/questions → PUT /api/standard-answer（约简配置）→
POST /api/answers → POST /api/score → 汇总 point_details 计算系统级指标：
Point-Acc / 等价给分率 / ScoreCorr(Pearson) / MAE。

用法：python scripts/m7_e2e_eval.py [--sample N] [--gateway URL]
产出：models/artifacts/e2e_eval.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MRC_TEST = ROOT / "data" / "processed" / "mrc_test.jsonl"
CONFIGS = ROOT / "data" / "scoring_configs"
SAS_RAW = ROOT / "data" / "raw" / "sas-bench"
OUT_JSON = ROOT / "models" / "artifacts" / "e2e_eval.json"


def build_stems() -> dict[str, str]:
    """qid -> 该题全部来源题干（多来源以换行拼接）。

    服务端在评分前会按题干剥离答卷中重合的题干材料片段（strip_stem_spans），
    因此评测必须 POST 真实题干而非占位文本，与生产链路同构。
    """
    item2q: dict[str, str] = {}
    for fp in SAS_RAW.glob("*.jsonl"):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("id") and item.get("question"):
                    item2q[item["id"]] = item["question"].strip()
    stems: dict[str, set[str]] = defaultdict(set)
    with open(MRC_TEST, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("origin") != "full":
                continue
            q = item2q.get(row["id"].split("#")[0])
            if q:
                stems[row["question_id"]].add(q)
    return {qid: "\n".join(sorted(v)) for qid, v in stems.items()}


def _assert_safe_runtime_url(url: str) -> None:
    """仅允许 http/https 且目标为环回/私网地址（内部评测脚本，防 SSRF）。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的协议: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1") and not (
        host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.")
    ):
        raise ValueError(f"不允许的目标主机: {host!r}")


def http_json(method: str, url: str, body: dict | None = None, timeout: int = 600) -> dict:
    _assert_safe_runtime_url(url)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_answers() -> list[dict]:
    """聚合出 (question_id, context) 级答案卷及逐点金标。

    同一 (答案, 得分点) 出现**互相矛盾**的金标时（LLM 打标噪声），该点
    整体剔除——无法仲裁真值，计入只会污染指标。
    """
    by_answer: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    with open(MRC_TEST, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("origin") != "full":
                continue
            key = (row["question_id"], row["context"])
            pt = by_answer[key]
            q = row["query"]
            if q in pt:
                if pt[q]["impossible"] != bool(row["is_impossible"]):
                    pt[q]["conflict"] = True
                continue
            pt.setdefault(q, {
                "query": q,
                "aliases": list(row.get("query_aliases") or []),
                "weight": float(row["point_weight"]),
                "impossible": bool(row["is_impossible"]),
                "conflict": False,
            })
    out = []
    n_conflict = 0
    for (qid, ctx), points in sorted(by_answer.items()):
        cfg_path = CONFIGS / f"{qid}.json"
        if not cfg_path.exists():
            print(f"[warn] 缺评分配置 {qid}，跳过", flush=True)
            continue
        kept = [p for p in points.values() if not p["conflict"]]
        n_conflict += len(points) - len(kept)
        if not kept:
            continue
        expert_total = sum(p["weight"] for p in kept if not p["impossible"])
        max_total = sum(p["weight"] for p in kept)
        out.append({
            "question_id": qid, "context": ctx, "points": kept,
            "expert_total": expert_total, "max_total": max_total,
        })
    if n_conflict:
        print(f"[info] 剔除矛盾金标点 {n_conflict} 个", flush=True)
    return out


def stratified_sample(answers: list[dict], n: int) -> list[dict]:
    """按专家得分率排序后等距抽取，覆盖全分数段。"""
    ranked = sorted(answers, key=lambda a: a["expert_total"] / max(a["max_total"], 1e-9))
    if len(ranked) <= n:
        return ranked
    stride = len(ranked) / n
    return [ranked[int(i * stride)] for i in range(n)]


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (vx * vy + 1e-12)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=36)
    ap.add_argument("--gateway", default="http://127.0.0.1:8080")
    args = ap.parse_args()

    answers = load_answers()
    stems = build_stems()
    print(f"候选答案卷 {len(answers)} 份；抽样 {args.sample} 份（等距覆盖分数段）", flush=True)
    sample = stratified_sample(answers, args.sample)
    n_stem = sum(1 for a in sample if a["question_id"] in stems)
    print(f"题干剥离就绪：{n_stem}/{len(sample)} 卷有真实题干", flush=True)

    preds: list[float] = []
    golds: list[float] = []
    ratios: list[float] = []
    tp = fp = fn_ = tn = 0          # 有答判定混淆计数（点级）
    gold_hit_credit = gold_total_n = 0   # 等价给分率分母/分子
    records: list[dict] = []
    t0 = time.time()

    for i, ans in enumerate(sample):
        eq = f"EVAL-{ans['question_id']}"
        reduced = {
            "question_id": eq,
            "total_score": round(sum(p["weight"] for p in ans["points"]), 4),
            "subject": None,
            "points": [
                {"point_id": j + 1, "point_text": p["query"],
                 "weight": p["weight"], "aliases": p["aliases"]}
                for j, p in enumerate(ans["points"])
            ],
        }
        try:
            http_json("POST", f"{args.gateway}/api/questions",
                      {"question_id": eq, "content": stems.get(ans["question_id"], f"E2E 评估题 {eq}"),
                       "subject": "eval", "total_score": reduced["total_score"]})
            http_json("PUT", f"{args.gateway}/api/standard-answer", reduced)
            sub = http_json("POST", f"{args.gateway}/api/answers",
                            {"question_id": eq,
                             "submissions": [{"student_id": "e2e-eval",
                                              "answer_text": ans["context"]}]})
            aids = sub.get("answer_ids") or [
                a["answer_id"] for a in (sub.get("items") or sub.get("answers") or [])]
            aid = aids[0]
            scored = http_json("POST", f"{args.gateway}/api/score",
                               {"question_id": eq, "answer_ids": [aid]})
            result = (scored.get("results") or scored.get("items"))[0]
        except Exception as e:  # noqa: BLE001
            print(f"[{i+1}/{len(sample)}] {eq} 失败：{e}", flush=True)
            continue

        # 点级对齐：reduced 配置 point_id=j+1 与金标顺序一致
        details = {d["point_id"]: d for d in result["point_details"]}
        for j, p in enumerate(ans["points"]):
            d = details.get(j + 1)
            if d is None:
                continue
            pred_hit = d["hit_status"] != "miss"
            if pred_hit and not p["impossible"]:
                tp += 1
            elif pred_hit:
                fp += 1
            elif not p["impossible"]:
                fn_ += 1
            else:
                tn += 1
            if not p["impossible"]:
                gold_total_n += 1
                if d["point_score"] > 0:
                    gold_hit_credit += 1

        pred_total = float(result["total_score"])
        preds.append(pred_total)
        golds.append(ans["expert_total"])
        ratios.append(pred_total / max(ans["max_total"], 1e-9))
        records.append({"question_id": ans["question_id"], "pred": pred_total,
                        "gold": ans["expert_total"], "max": ans["max_total"],
                        "details": result["point_details"]})
        dt = time.time() - t0
        print(f"[{i+1}/{len(sample)}] {eq} pred={pred_total:.1f} "
              f"gold={ans['expert_total']:.1f} （累计 {dt:.0f}s）", flush=True)

    n = len(preds)
    metrics = {
        "n_answers": n,
        "point_accuracy": (tp + tn) / max(tp + tn + fp + fn_, 1),
        "equivalence_credit_rate": gold_hit_credit / max(gold_total_n, 1),
        "score_corr_pearson": pearson(preds, golds) if n >= 3 else None,
        "mae": sum(abs(p - g) for p, g in zip(preds, golds)) / max(n, 1),
        "confusion": {"tp": tp, "fp": fp, "fn": fn_, "tn": tn},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(
        {"metrics": metrics, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n==== 全链路评估结果 ====")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"明细已写入 {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
