# -*- coding: utf-8 -*-
"""M1-7 训练数据构建：对齐后标注 → MRC 五元组 + 相似度句子对（含固定种子划分）。

用法（仓库根目录）::

    python -m rubricspan_train.data.build

输入：
- ``data/labeling_cache/labels_final.jsonl`` —— 质检后的打标样本（M1-6 产物）
- ``data/scoring_configs/*.json``            —— 评分配置（query 与别名来源）
- ``data/raw/sas-datasets/``                 —— 真实人工分相似度补充（可选）

输出（``data/processed/``）：
- ``mrc_train/val/test.jsonl``        —— 五元组 (context, query, answer, start, end)
  附 ``is_impossible`` 负样本，占比按配置目标（≥20%，执行计划 M1-7）；
- ``similarity_train/val/test.jsonl`` —— 句子对 + 0~1 分数；
- ``dataset_stats.json``              —— 划分、种子与分布统计。

划分单位 = question_id（同题样本不跨 split，防泄漏）；种子见
``configs/data_split.yaml``。
"""
from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..labeling.common import (
    DATA_DIR,
    DIR_LABELING_CACHE,
    DIR_PROCESSED,
    TRAIN_DIR,
    load_jsonl,
    load_yaml,
    write_jsonl,
)

_SENT_SPLIT = re.compile(r"[。！？；\n，、]+")


# ---------------------------------------------------------------------------
# 划分
# ---------------------------------------------------------------------------


def split_by_question(
    question_ids: list[str], ratios: dict[str, float], seed: int
) -> dict[str, str]:
    """按题目分组划分：返回 qid → split 名。"""
    rng = random.Random(seed)
    qids = sorted(set(question_ids))
    rng.shuffle(qids)
    n = len(qids)
    n_train = int(n * ratios["train"])
    n_val = int(n * ratios["val"])
    assign: dict[str, str] = {}
    for i, qid in enumerate(qids):
        if i < n_train:
            assign[qid] = "train"
        elif i < n_train + n_val:
            assign[qid] = "val"
        else:
            assign[qid] = "test"
    return assign


# ---------------------------------------------------------------------------
# MRC 五元组
# ---------------------------------------------------------------------------


def build_mrc(records: list[dict], configs: dict[str, dict], split_of: dict[str, str]) -> list[dict]:
    """打标样本 → 五元组；负样本在 build 主流程中按目标占比抽样。"""
    pos: list[dict] = []
    neg: list[dict] = []
    for rec in records:
        labels = rec["labels"]
        qid = labels["question_id"]
        config = configs.get(qid)
        if not config:
            continue
        point_map = {p["point_id"]: p for p in config["points"]}
        context = labels["student_answer"]
        for pl in labels["point_labels"]:
            point = point_map.get(pl["point_id"])
            if point is None:
                continue
            base = {
                "id": f"{rec['sample_id']}#p{pl['point_id']}",
                "question_id": qid,
                "origin": rec["origin"],
                "context": context,
                "query": point["point_text"],
                "query_aliases": point.get("aliases", []),
                "point_weight": float(point["weight"]),
            }
            if pl["hit"] and pl.get("align"):
                a = pl["align"]
                pos.append(
                    {
                        **base,
                        "answer": context[a["start"] : a["end"]],
                        "answer_start": a["start"],
                        "answer_end": a["end"],
                        "is_impossible": False,
                        "hit_type": pl["hit_type"],
                    }
                )
            elif not pl["hit"]:
                neg.append(
                    {
                        **base,
                        "answer": "",
                        "answer_start": -1,
                        "answer_end": -1,
                        "is_impossible": True,
                        "hit_type": "miss",
                    }
                )
    out = pos + neg
    for r in out:
        r["split"] = split_of[r["question_id"]]
    return out


def subsample_negatives(records: list[dict], target_ratio: float, seed: int) -> list[dict]:
    """保持正样本全量，负样本抽样到目标占比（neg / 总量）。"""
    pos = [r for r in records if not r["is_impossible"]]
    neg = [r for r in records if r["is_impossible"]]
    if not pos or not neg:
        return pos + neg
    k = int(len(pos) * target_ratio / max(1e-9, 1 - target_ratio))
    if k >= len(neg):
        return pos + neg
    rng = random.Random(seed)
    # 按题目分层抽样，避免负样本集中在少数题
    by_q: dict[str, list[dict]] = defaultdict(list)
    for r in neg:
        by_q[r["question_id"]].append(r)
    for v in by_q.values():
        rng.shuffle(v)
    picked: list[dict] = []
    queue = list(by_q.values())
    while len(picked) < k:
        progressed = False
        for lst in queue:
            if lst and len(picked) < k:
                picked.append(lst.pop())
                progressed = True
        if not progressed:
            break
    return pos + picked


# ---------------------------------------------------------------------------
# 相似度句子对
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if len(s.strip()) >= 6]


def build_similarity_from_labels(
    records: list[dict], configs: dict[str, dict], split_of: dict[str, str]
) -> list[dict]:
    """打标结果 → 句子对。

    - exact 命中：(point_text, span, 1.0)
    - semantic 命中：(point_text, span, partial_credit)
    - miss：point_text × 学生答案句子 (0.0) —— 优先取不与任何命中 span 重叠的
      句子（真干扰句）；答案被命中片段占满时回退任意句子（对 miss 点仍是
      语义正确的负例）；
    - 别名正例：(point_text, alias, 1.0)
    """
    pairs: list[dict] = []
    for rec in records:
        labels = rec["labels"]
        qid = labels["question_id"]
        config = configs.get(qid)
        if not config:
            continue
        point_map = {p["point_id"]: p for p in config["points"]}
        hit_ranges: list[tuple[int, int]] = [
            (pl["align"]["start"], pl["align"]["end"])
            for pl in labels["point_labels"]
            if pl.get("align")
        ]
        answer = labels["student_answer"]

        def overlaps_hit(start: int, end: int) -> bool:
            return any(not (end <= s or start >= e) for s, e in hit_ranges)

        # 句级负例：非重叠干扰句优先，回退任意句
        sents = _sentences(answer)
        distractors = [
            s
            for s in sents
            if not overlaps_hit(answer.find(s), answer.find(s) + len(s))
        ]
        neg_fallback = distractors[0] if distractors else (sents[0] if sents else answer[:60])
        for pl in labels["point_labels"]:
            point = point_map.get(pl["point_id"])
            if point is None:
                continue
            base = {
                "question_id": qid,
                "origin": rec["origin"],
            }
            if pl["hit_type"] == "exact":
                pairs.append({**base, "sentence1": point["point_text"],
                              "sentence2": pl["extracted_span"], "score": 1.0,
                              "source": "label-exact"})
            elif pl["hit_type"] == "semantic":
                pairs.append({**base, "sentence1": point["point_text"],
                              "sentence2": pl["extracted_span"],
                              "score": round(float(pl.get("partial_credit", 1.0)), 2),
                              "source": "label-semantic"})
            elif pl["hit_type"] == "miss" and neg_fallback:
                pairs.append({**base, "sentence1": point["point_text"],
                              "sentence2": neg_fallback, "score": 0.0,
                              "source": "label-miss"})
            # 别名正例（每点一个，控制规模）
            for alias in point.get("aliases", [])[:1]:
                pairs.append({**base, "sentence1": point["point_text"],
                              "sentence2": alias, "score": 1.0,
                              "source": "label-alias"})
    for p in pairs:
        p["split"] = split_of[p["question_id"]]
    return pairs


def _tsv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig") as f:
        return [row for row in csv.reader(f, delimiter="\t") if row]


def load_sas_datasets_similarity(raw: Path) -> list[dict]:
    """SAS-Datasets（ADS/LE/ASAG/SR）真实人工分 → (reference, answer, score∈[0,1])。"""
    pairs: list[dict] = []

    def add(s1: str, s2: str, score: float, source: str, qid: str) -> None:
        s1, s2 = s1.strip(), s2.strip()
        if len(s1) < 4 or len(s2) < 4:
            return
        pairs.append({"sentence1": s1, "sentence2": s2,
                      "score": round(min(max(score, 0.0), 1.0), 3),
                      "source": source, "question_id": qid})

    ads = raw / "sas-datasets" / "ADS" / "all.jsonl"
    if ads.exists():
        with ads.open(encoding="utf-8") as f:
            for line in f:
                it = json.loads(line)
                try:
                    score = float(it["score"]) / 10.0
                except (TypeError, ValueError):
                    continue
                ref = it.get("reference1") or ""
                add(ref, it.get("answer", ""), score, "sas-ads", f"ADS-{it.get('q_id', 'x')}")

    le = raw / "sas-datasets" / "LE"
    if (le / "train.csv").exists():
        for row in _tsv(le / "train.csv"):
            if len(row) < 4:
                continue
            score = None
            try:
                score = float(row[3])
            except ValueError:
                try:
                    score = float(row[0]) / 100.0
                except ValueError:
                    continue
            add(row[1], row[2], score, "sas-le", f"LE-{row[1][:24]}")

    asag = raw / "sas-datasets" / "ASAG"
    if (asag / "qa_zh.csv").exists() and (asag / "train_zh.csv").exists():
        qa = {row[0]: row[2] for row in _tsv(asag / "qa_zh.csv") if len(row) >= 3}
        for row in _tsv(asag / "train_zh.csv"):
            if len(row) < 4 or row[0] not in qa:
                continue
            try:
                score = float(row[1]) / 5.0
            except ValueError:
                continue
            add(qa[row[0]], row[3], score, "sas-asag", f"ASAG-{row[0]}")

    sr = raw / "sas-datasets" / "SR" / "sentences-goldstandard.csv"
    if sr.exists():
        for row in _tsv(sr):
            if len(row) < 8:
                continue
            try:
                score = float(row[3])
            except ValueError:
                continue
            add(row[7], row[1], score, "sas-sr", f"SR-{row[0][:16]}")
    return pairs


def load_stsb_zh_similarity(raw: Path, limit: int = 4000) -> list[dict]:
    base = raw / "sas-datasets" / "stsbenchmark"
    pairs: list[dict] = []
    if not base.exists():
        return pairs
    for name in ("train_zh.csv",):
        for row in _tsv(base / name):
            if len(row) < 7:
                continue
            try:
                score = float(row[4]) / 5.0
            except ValueError:
                continue
            s1, s2 = row[5].strip(), row[6].strip()
            if len(s1) < 4 or len(s2) < 4:
                continue
            pairs.append({"sentence1": s1, "sentence2": s2,
                          "score": round(score, 3), "source": "stsb-zh",
                          "question_id": f"STSB-{row[3]}"})
    rng = random.Random(42)
    rng.shuffle(pairs)
    return pairs[:limit]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    cfg = load_yaml(TRAIN_DIR / "configs" / "data_split.yaml")
    seed = int(cfg["split"]["seed"])
    ratios = cfg["split"]["ratios"]
    records = load_jsonl(DIR_LABELING_CACHE / "labels_final.jsonl")
    if not records:
        raise SystemExit("FAIL: labels_final.jsonl empty — run quality stage first")
    configs = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (DATA_DIR / "scoring_configs").glob("SAS-*.json")
    }
    print(f"build: {len(records)} labeled samples, {len(configs)} configs")

    split_of = split_by_question(
        [r["labels"]["question_id"] for r in records], ratios, seed
    )

    # ---- MRC 五元组 ----
    mrc = build_mrc(records, configs, split_of)
    target_ratio = float(cfg.get("mrc", {}).get("negative_ratio", 0.22))
    mrc = subsample_negatives(mrc, target_ratio, seed)
    for split in ("train", "val", "test"):
        write_jsonl(DIR_PROCESSED / f"mrc_{split}.jsonl", [r for r in mrc if r["split"] == split])

    # ---- 相似度句子对 ----
    sim = build_similarity_from_labels(records, configs, split_of)
    extra = []
    if cfg.get("similarity", {}).get("include_sas_datasets", True):
        extra += load_sas_datasets_similarity(DATA_DIR / "raw")
    if cfg.get("similarity", {}).get("include_stsb_zh", True):
        extra += load_stsb_zh_similarity(DATA_DIR / "raw")
    # 外部数据只入 train（评测集保持本项目分布）
    for p in extra:
        p["split"] = "train"
    sim_all = sim + extra
    for split in ("train", "val", "test"):
        write_jsonl(
            DIR_PROCESSED / f"similarity_{split}.jsonl",
            [r for r in sim_all if r["split"] == split],
        )

    # ---- 统计 ----
    def dist(items: list[dict]) -> dict[str, Any]:
        by_split: Counter[str] = Counter(r["split"] for r in items)
        neg_ratio = (
            sum(1 for r in items if r.get("is_impossible")) / len(items) if items else 0
        )
        out: dict[str, Any] = {
            "total": len(items),
            "by_split": dict(by_split),
        }
        if any("is_impossible" in r for r in items):
            out["negative_ratio"] = round(neg_ratio, 4)
            by_origin: Counter[str] = Counter(r.get("origin", "?") for r in items)
            out["by_origin"] = dict(by_origin)
            hits = [r for r in items if not r.get("is_impossible")]
            out["hit_type"] = dict(Counter(r["hit_type"] for r in hits))
        if items and "source" in items[0]:
            out["by_source"] = dict(Counter(r["source"] for r in items))
        return out

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": {"seed": seed, "ratios": ratios,
                  "unit": "question_id",
                  "questions": {s: sum(1 for q in set(split_of) if split_of[q] == s)
                                    for s in ("train", "val", "test")}},
        "mrc": dist(mrc),
        "similarity": dist(sim_all),
        "labeled_samples_input": len(records),
    }
    DIR_PROCESSED.mkdir(parents=True, exist_ok=True)
    (DIR_PROCESSED / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats["mrc"], ensure_ascii=False))
    print(json.dumps(stats["similarity"], ensure_ascii=False))
    print("build done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
