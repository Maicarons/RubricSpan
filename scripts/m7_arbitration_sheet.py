#!/usr/bin/env python3
"""M7 · 高置信分歧人工仲裁清单生成（BC-002 处置入口）。

读取 `models/artifacts/e2e_eval.json`（全链路评估明细），按与
`m7_e2e_eval.py` 完全一致的口径重新推导逐点金标，输出"系统命中 vs 金标未标"
的分歧点清单，按置信度降序供人工抽检仲裁：
- 若人工判"系统对"→ 金标漏标，进入再打标闭环；
- 若人工判"金标对"→ 系统误命中，收集为负例/难例。

产出：docs/arbitration-sheet.md（Top N）+ data/arbitration_sheet.csv（全量）
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from m7_e2e_eval import load_answers  # noqa: E402

EVAL_JSON = ROOT / "models" / "artifacts" / "e2e_eval.json"
OUT_MD = ROOT / "docs" / "arbitration-sheet.md"
OUT_CSV = ROOT / "data" / "arbitration_sheet.csv"


def confidence(d: dict) -> float:
    return d.get("confidence") if d.get("confidence") is not None else (
        d.get("similarity") if d.get("similarity") is not None else 0.0)


def main() -> int:
    answers = {a["question_id"]: a for a in load_answers()}
    data = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    rows = []
    for rec in data["records"]:
        ans = answers.get(rec["question_id"])
        if ans is None:
            continue
        kept = ans["points"]  # 与评估时 reduced 配置同序
        for j, detail in enumerate(rec["details"]):
            if j >= len(kept):
                continue
            gold = kept[j]
            pred_hit = detail["hit_status"] != "miss"
            if not (pred_hit and gold["impossible"]):
                continue  # 只收"系统命中、金标未标"
            rows.append({
                "question_id": rec["question_id"],
                "point_text": gold["query"],
                "source": detail["source"],
                "hit_status": detail["hit_status"],
                "conf": round(confidence(detail), 4),
                "weight": detail["point_score"],
                "span": (detail.get("extracted_span") or "")[:40],
            })
    rows.sort(key=lambda r: r["conf"], reverse=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    top = rows[:50]
    lines = [
        "# 高置信分歧仲裁清单（BC-002）",
        "",
        f"> 全量 {len(rows)} 条分歧点（系统命中、金标未标），按置信度降序。",
        f"全量数据：`data/arbitration_sheet.csv`；本页展示 Top {len(top)}。",
        "判定方法：对照原答案文本（`data/processed/mrc_test.jsonl` 中对应 context），",
        "在「系统对（漏标）」与「金标对（误命中）」二选一标注。",
        "",
        "| # | 题目 | 得分点 | 来源 | 判定 | 置信 | 命中片段 |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(top, 1):
        lines.append(
            f"| {i} | {r['question_id']} | {r['point_text'][:28]} | "
            f"{r['source']} | ☐系统对 ☐金标对 | {r['conf']:.3f} | {r['span']} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"全量 {len(rows)} 条 → {OUT_CSV}")
    print(f"Top {len(top)} → {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
