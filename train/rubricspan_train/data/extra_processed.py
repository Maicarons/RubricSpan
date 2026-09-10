# -*- coding: utf-8 -*-
"""外部补充数据集 → 训练数据（相似度句子对 + MRC is_impossible 负例）。

输入：`data/raw/extra/*/normalized.jsonl`（import_extra 产出，统一 schema）。
输出：
- `data/processed/extra_similarity_pairs.jsonl`
- `data/processed/extra_mrc_negatives.jsonl`

设计说明（详见 docs/reports/extra-datasets.md）：
- **M3KE 是评测基准**：官方仅 dev 355 题带答案，test 20122 题答案保密——
  只取 dev 生成句子对（题干↔正确选项正例 / 题干↔错误选项 hard 负例），test 不入训练；
- **InternLM-History**：题干↔专题/考点标注为语义正例（考点表述正是兜底判分的得分点形态），
  跨考点抽样错误考点为 hard 负例；MRC 侧用"考点"作 query、整条题干材料作 context 的
  is_impossible 负例（考点名不以 span 出现在材料中）；
- 不修改主 build（data/build.py 固定种子与划分不被扰动），另立文件、训练入口显式
  opt-in（train_similarity --extra-pairs / train_mrc --extra-negatives）。

用法（train/ 目录）::

    python -m rubricspan_train.data.extra_processed [--raw ../data/raw/extra --out ../data/processed]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_EXTRA = REPO_ROOT / "data" / "raw" / "extra"
PROCESSED = REPO_ROOT / "data" / "processed"

SEED = 42
MIN_CHOICE_LEN = 2
MIN_QUESTION_LEN = 4
MAX_HISTORY_NEG_PER_Q = 2   # 跨考点 hard 负例上限/题


def load_normalized(src: Path) -> list[dict]:
    rows = []
    for fp in sorted(src.glob("*/normalized.jsonl")):
        with fp.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _split(split: str) -> str:
    return {"train": "train", "dev": "val", "test": "test"}.get(split, "train")


def build_similarity_pairs(rows: list[dict]) -> list[dict]:
    pairs = []
    rng = random.Random(SEED)
    # InternLM-History 的跨考点负例池（去重考点名）
    history_labels = sorted({r["answer_text"] for r in rows
                             if r["source"] == "internlm-history" and (r["answer_text"] or "").strip()})

    for r in rows:
        q = (r["question"] or "").strip()
        if len(q) < MIN_QUESTION_LEN:
            continue
        if r["source"] == "m3ke":
            # 仅 dev 带答案；test 无答案不入训练
            if not r.get("answer_letter"):
                continue
            choices = {k: v.strip() for k, v in (r.get("choices") or {}).items()
                       if (v or "").strip() and len(v.strip()) >= MIN_CHOICE_LEN}
            if not choices:
                continue
            pos_text = choices.get(r["answer_letter"], "")
            split = _split(r.get("split", "train"))
            qid = f"EXT-{r['source']}-{r['qid']}"
            if pos_text and len(pos_text) >= MIN_CHOICE_LEN:
                pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                              "sentence2": pos_text, "score": 1.0,
                              "source": f"extra-{r['source']}-pos", "split": split})
            for letter, text in choices.items():
                if letter == r["answer_letter"]:
                    continue
                pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                              "sentence2": text, "score": 0.0,
                              "source": f"extra-{r['source']}-neg", "split": split})
        elif r["source"] == "internlm-history":
            label = (r.get("answer_text") or "").strip()
            if not label:
                continue
            split = _split(r.get("split", "train"))
            qid = f"EXT-{r['source']}-{r['qid']}"
            pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                          "sentence2": label, "score": 1.0,
                          "source": "extra-internlm-history-pos", "split": split})
            # 跨考点 hard 负例：同一学科（历史）的其他专题名
            others = [lb for lb in history_labels if lb != label]
            for lb in rng.sample(others, min(MAX_HISTORY_NEG_PER_Q, len(others))):
                pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                              "sentence2": lb, "score": 0.0,
                              "source": "extra-internlm-history-neg", "split": split})
        elif r["type"] in ("open", "fill"):
            # 主观/默写题：题干（材料+设问）↔ 参考答案 = 语义正例（学生答案↔得分点同构）
            ans = (r.get("answer_text") or "").strip()
            if len(ans) < MIN_CHOICE_LEN or ans in q or len(q) < MIN_QUESTION_LEN:
                continue
            split = _split(r.get("split", "train"))
            qid = f"EXT-{r['source']}-{r['qid']}"
            pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                          "sentence2": ans[:300], "score": 1.0,
                          "source": f"extra-{r['source']}-pos", "split": split})
        elif r["type"] == "choice":
            # 通用客观题：题干↔正确选项正例 / 题干↔错误选项 hard 负例
            # （agieval/cmmlu/gaokao-bench 客观题；m3ke 在上方专用分支保证 dev 过滤）
            if not r.get("answer_letter") or not r.get("choices"):
                continue
            choices = {k: v.strip() for k, v in r["choices"].items()
                       if (v or "").strip() and len(v.strip()) >= MIN_CHOICE_LEN}
            if not choices:
                continue
            pos_text = choices.get(r["answer_letter"], "")
            split = _split(r.get("split", "train"))
            qid = f"EXT-{r['source']}-{r['qid']}"
            if pos_text and len(pos_text) >= MIN_CHOICE_LEN:
                pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                              "sentence2": pos_text, "score": 1.0,
                              "source": f"extra-{r['source']}-pos", "split": split})
            for letter, text in choices.items():
                if letter == r["answer_letter"]:
                    continue
                pairs.append({"question_id": qid, "origin": "extra", "sentence1": q,
                              "sentence2": text, "score": 0.0,
                              "source": f"extra-{r['source']}-neg", "split": split})
    return pairs


def build_mrc_negatives(rows: list[dict]) -> list[dict]:
    negs = []
    for r in rows:
        query = (r["question"] or "").strip()
        material = (r.get("material") or "").strip()
        if r["source"] == "internlm-history":
            # 无独立材料：题干（材料+问题）作 context，考点标注作 query（不以 span 出现）
            context, query = query, (r.get("answer_text") or "").strip()
            if not query or query in context:
                continue
        else:
            if len(material) < 10:
                continue
            context = material
        if len(query) < MIN_QUESTION_LEN or len(context) < 10:
            continue
        split = _split(r.get("split", "train"))
        negs.append({
            "id": f"extra-{r['source']}-{r['qid']}", "question_id": f"EXT-{r['source']}-{r['qid']}",
            "origin": f"extra-{r['source']}", "context": context,
            "query": query, "query_aliases": [],
            "answer": "", "answer_start": -1, "answer_end": -1,
            "is_impossible": True, "hit_type": "miss", "split": split,
            "point_weight": 0.0,
        })
    return negs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, default=RAW_EXTRA)
    p.add_argument("--out", type=Path, default=PROCESSED)
    args = p.parse_args(argv)

    rows = load_normalized(args.raw)
    pairs = build_similarity_pairs(rows)
    negs = build_mrc_negatives(rows)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "extra_similarity_pairs.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in pairs) + "\n", encoding="utf-8")
    (args.out / "extra_mrc_negatives.jsonl").write_text(
        "\n".join(json.dumps(n, ensure_ascii=False) for n in negs) + "\n", encoding="utf-8")

    from collections import Counter
    n_pos = sum(1 for p in pairs if p["score"] > 0.5)
    print(f"相似度句子对：{len(pairs)}（正例 {n_pos} / 负例 {len(pairs) - n_pos}）")
    print("  source 分布：", dict(Counter(p["source"] for p in pairs)))
    print(f"MRC is_impossible 负例：{len(negs)}")
    print("  origin 分布：", dict(Counter(n["origin"] for n in negs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
