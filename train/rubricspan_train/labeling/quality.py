# -*- coding: utf-8 -*-
"""M1-6 质量控制：对齐后处理 + 过滤 + 抽检导出 + 专家分数一致性对照。

输入 ``labels_voted.jsonl``（或首轮 ``labels_raw.jsonl``），输出：

- ``data/labeling_cache/labels_final.jsonl`` —— 对齐成功且通过质检的样本；
- ``data/processed/qc_report.json``         —— 全量质检统计（对齐成功率、
  hit_type 分布、semantic 占比、过滤明细、专家分数一致性）；
- ``data/processed/inspection_sample_5pct.md`` —— 人工抽检样本（分层 5%）。

对齐成功率的口径（M1 出口标准）：**hit 点级** aligned / hit_points > 90%，
**样本级**（全部 hit 点都对齐成功的样本 / 含 hit 的样本）同步报告。
"""
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..align.aligner import align_span
from .common import (
    DIR_LABELING_CACHE,
    DIR_PROCESSED,
    DIR_SCORING_CONFIGS,
    load_labeling_config,
    load_jsonl,
    write_jsonl,
)

LABELS_VOTED = DIR_LABELING_CACHE / "labels_voted.jsonl"
LABELS_FINAL = DIR_LABELING_CACHE / "labels_final.jsonl"


def run_quality(cfg: dict[str, Any]) -> dict[str, Any]:
    qcfg = cfg.get("quality", {})
    min_conf = float(qcfg.get("min_confidence", 0.55))
    max_span_ratio = float(qcfg.get("max_span_ratio", 0.5))
    max_invalid_ratio = float(qcfg.get("max_invalid_point_ratio", 0.34))
    inspection_ratio = float(qcfg.get("inspection_ratio", 0.05))
    seed = int(cfg.get("pipeline", {}).get("random_seed", 42))

    records = load_jsonl(LABELS_VOTED)
    if not records:
        records = load_jsonl(DIR_LABELING_CACHE / "labels_raw.jsonl")
    configs = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in DIR_SCORING_CONFIGS.glob("SAS-*.json")
    }
    print(f"quality: {len(records)} records, {len(configs)} scoring configs")

    stats: Counter[str] = Counter()
    strat: Counter[str] = Counter()
    final_records: list[dict] = []
    filters: Counter[str] = Counter()
    for rec in records:
        labels = rec["labels"]
        answer = labels["student_answer"]
        points_out: list[dict] = []
        invalid = 0
        total_points = 0
        for pl in labels["point_labels"]:
            total_points += 1
            if pl["confidence"] < min_conf:
                filters["low_confidence"] += 1
                invalid += 1
                continue
            if not pl["hit"]:
                points_out.append({**pl, "align": None})
                stats["miss_points"] += 1
                continue
            stats["hit_points"] += 1
            span = pl.get("extracted_span") or ""
            if not span:
                filters["empty_span"] += 1
                invalid += 1
                continue
            if len(span) > max_span_ratio * max(len(answer), 1):
                filters["overlong_span"] += 1
                invalid += 1
                continue
            res = align_span(answer, span)
            if res is None:
                filters["align_fail"] += 1
                invalid += 1
                continue
            stats["aligned"] += 1
            strat[res.strategy] += 1
            points_out.append(
                {
                    **pl,
                    "align": {
                        "start": res.start,
                        "end": res.end,
                        "matched_text": res.matched_text,
                        "strategy": res.strategy,
                    },
                }
            )
        stats["hit_type_exact"] += sum(1 for p in points_out if p["hit_type"] == "exact")
        stats["hit_type_semantic"] += sum(1 for p in points_out if p["hit_type"] == "semantic")
        if total_points and invalid / total_points > max_invalid_ratio:
            filters["sample_dropped_invalid_ratio"] += 1
            continue
        if not any(p["hit"] for p in points_out) and not points_out:
            filters["sample_dropped_empty"] += 1
            continue
        out_rec = dict(rec)
        out_rec["labels"] = {**labels, "point_labels": points_out}
        final_records.append(out_rec)
        stats["samples_kept"] += 1
        if any(p["hit"] for p in points_out):
            stats["samples_with_hits"] += 1
            if all(
                (p["align"] is not None) for p in points_out if p["hit"]
            ):
                stats["samples_fully_aligned"] += 1

    # ---------------- 专家分数一致性（full 样本对照 manual_label） ----------------
    agreement = _expert_agreement(final_records, configs)

    # ---------------- 5% 人工抽检导出 ----------------
    inspection_path = _export_inspection(
        final_records, configs, ratio=inspection_ratio, seed=seed
    )

    hits = stats["hit_points"] or 1
    samples_hit = stats["samples_with_hits"] or 1
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_records": len(records),
        "kept_samples": stats["samples_kept"],
        "point_alignment": {
            "hit_points": stats["hit_points"],
            "aligned": stats["aligned"],
            "success_rate": round(stats["aligned"] / hits, 4),
            "strategies": {"exact": strat["exact"], "fuzzy": strat["fuzzy"], "lcs": strat["lcs"]},
        },
        "sample_alignment": {
            "samples_with_hits": stats["samples_with_hits"],
            "samples_fully_aligned": stats["samples_fully_aligned"],
            "success_rate": round(stats["samples_fully_aligned"] / samples_hit, 4),
        },
        "hit_type_distribution": {
            "exact": stats["hit_type_exact"],
            "semantic": stats["hit_type_semantic"],
            "semantic_share_of_hits": round(
                stats["hit_type_semantic"] / max(stats["hit_type_exact"] + stats["hit_type_semantic"], 1), 4
            ),
            "miss_points": stats["miss_points"],
        },
        "filters": dict(filters),
        "expert_agreement": agreement,
        "inspection_export": str(inspection_path),
    }
    DIR_PROCESSED.mkdir(parents=True, exist_ok=True)
    (DIR_PROCESSED / "qc_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_jsonl(LABELS_FINAL, final_records)
    print(
        f"quality done: kept={stats['samples_kept']} "
        f"align(point)={report['point_alignment']['success_rate']:.1%} "
        f"align(sample)={report['sample_alignment']['success_rate']:.1%} "
        f"semantic/hits={report['hit_type_distribution']['semantic_share_of_hits']:.1%}"
    )
    if agreement:
        print(
            f"expert agreement: pearson={agreement['pearson']:.3f} "
            f"mae={agreement['mae']:.2f} n={agreement['n']}"
        )
    return report


def _predicted_total(labels: dict, config: dict) -> float:
    weight_by_id = {p["point_id"]: float(p["weight"]) for p in config["points"]}
    total = 0.0
    for pl in labels["point_labels"]:
        if not pl["hit"]:
            continue
        credit = float(pl.get("partial_credit", 1.0) or 1.0)
        total += weight_by_id.get(pl["point_id"], 0.0) * credit
    return total


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / (vx**0.5 * vy**0.5)


def _expert_agreement(records: list[dict], configs: dict[str, dict]) -> dict[str, Any]:
    """对 SAS-Bench full 样本：LLM 判分总分 vs 人工总分（manual_label）。"""
    pairs: list[tuple[float, float]] = []
    for rec in records:
        if rec.get("origin") != "full" or rec.get("expert_total") is None:
            continue
        config = configs.get(rec["labels"]["question_id"])
        if not config:
            continue
        pairs.append((_predicted_total(rec["labels"], config), float(rec["expert_total"])))
    if len(pairs) < 5:
        return {"n": len(pairs), "note": "insufficient pairs"}
    xs = [p for p, _ in pairs]
    ys = [e for _, e in pairs]
    mae = sum(abs(x - y) for x, y in pairs) / len(pairs)
    within = sum(1 for x, y in pairs if abs(x - y) <= 0.2 * max(y, 1)) / len(pairs)
    return {
        "n": len(pairs),
        "pearson": round(_pearson(xs, ys), 4),
        "mae": round(mae, 3),
        "within_20pct": round(within, 4),
    }


def _export_inspection(
    records: list[dict], configs: dict[str, dict], *, ratio: float, seed: int
) -> Path:
    """分层抽检导出：按 origin × 命中构成分层，供人工核对。"""
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        pls = rec["labels"]["point_labels"]
        has_sem = any(p["hit_type"] == "semantic" for p in pls)
        has_hit = any(p["hit"] for p in pls)
        bucket = (
            "semantic" if has_sem else ("hit" if has_hit else "all_miss")
        )
        strata.setdefault((rec["origin"], bucket), []).append(rec)
    picked: list[dict] = []
    for key, recs in sorted(strata.items()):
        rng.shuffle(recs)
        k = max(1, round(len(recs) * ratio))
        picked += [(key, r) for r in recs[:k]]
    path = DIR_PROCESSED / "inspection_sample_5pct.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# M1 人工抽检样本（5% 分层抽样）",
        "",
        f"- 导出时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 样本数：{len(picked)} / {len(records)}",
        "- 核对方法：逐点检查 hit/hit_type/extracted_span 是否可接受；",
        "  extracted_span 应为学生答案的连续原文片段；",
        "  semantic 判定要求语义等价正确。将每条样本的 OK/NG 记入文末表格。",
        "",
    ]
    for i, ((origin, bucket), rec) in enumerate(picked, 1):
        labels = rec["labels"]
        config = configs.get(labels["question_id"], {})
        points_map = {p["point_id"]: p for p in config.get("points", [])}
        lines.append(f"## {i}. {rec['sample_id']}  [{origin}/{bucket}]")
        point_texts = "\n".join(
            f"  - {pid}. {p.get('point_text', '?')}" for pid, p in sorted(points_map.items())
        )
        lines.append(f"- **得分点**：\n{point_texts}")
        lines.append(f"- **学生答案**：{labels['student_answer'][:600]}")
        for pl in labels["point_labels"]:
            pt = points_map.get(pl["point_id"], {}).get("point_text", "?")
            lines.append(
                f"  - [{pl['point_id']}] {pl['hit_type']} conf={pl['confidence']} "
                f"| {pt} → 「{pl['extracted_span']}」"
                + (f" (align@{pl['align']['strategy']})" if pl.get("align") else "")
            )
        lines.append("")
    lines += ["## 人工核对结果", "", "| # | sample_id | 结论 | 备注 |", "|---|---|---|---|"]
    for i, (_k, rec) in enumerate(picked, 1):
        lines.append(f"| {i} | {rec['sample_id']} |  |  |")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
