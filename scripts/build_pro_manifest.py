#!/usr/bin/env python3
"""1.0-pro 预处理产物：数据清单 + 平衡性报告（供训练方案审阅与执行对照）。

扫描 data/processed/ 下主 build 与外部补充数据，输出：
- `data/processed/pro_data_manifest.json`：各文件条数 / train split 计数 / 正负比 / 负例占比；
- 控制台平衡性报告（相似度正负比、MRC is_impossible 占比提示）。

用法：python scripts/build_pro_manifest.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

FILES = [
    "mrc_train.jsonl", "mrc_val.jsonl", "mrc_test.jsonl",
    "similarity_train.jsonl", "similarity_val.jsonl", "similarity_test.jsonl",
    "extra_similarity_pairs.jsonl", "extra_mrc_negatives.jsonl",
]


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def main() -> int:
    manifest: dict = {}
    for name in FILES:
        p = PROCESSED / name
        if not p.exists():
            manifest[name] = {"error": "missing"}
            continue
        rows = load(p)
        entry = {"rows": len(rows)}
        if "split" in rows[0]:
            from collections import Counter
            entry["split"] = dict(Counter(r.get("split", "?") for r in rows))
            entry["train"] = sum(1 for r in rows if r.get("split") == "train")
        if "score" in rows[0]:
            pos = sum(1 for r in rows if r["score"] > 0.5)
            entry["pos"] = pos
            entry["neg"] = len(rows) - pos
            entry["pos_neg_ratio"] = round(pos / max(len(rows) - pos, 1), 3)
        if "is_impossible" in rows[0]:
            imp = sum(1 for r in rows if r.get("is_impossible"))
            entry["is_impossible"] = imp
            entry["impossible_ratio"] = round(imp / len(rows), 4)
        manifest[name] = entry

    (PROCESSED / "pro_data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 1.0-pro 预处理平衡性报告 ===")
    m = manifest["mrc_train.jsonl"]
    e = manifest["extra_mrc_negatives.jsonl"]
    print(f"MRC 主训练: {m['rows']}（is_impossible {m['impossible_ratio']:.0%}）")
    print(f"MRC 外部负例: {e['rows']}（train {e['train']}）")
    merged_imp = m["is_impossible"] + e["train"]
    merged = m["rows"] + e["train"]
    print(f"MRC 合并训练: {merged}，is_impossible ≈ {merged_imp}（{merged_imp/merged:.0%}）⚠️ 较旧 22% 大幅上升")
    s = manifest["similarity_train.jsonl"]
    x = manifest["extra_similarity_pairs.jsonl"]
    print(f"相似度主训练: {s['rows']}（正 {s['pos']}/负 {s['neg']}）")
    print(f"相似度外部对: {x['rows']}（train {x['train']}，正 {x['pos']}/负 {x['neg']}）")
    extra_train = [r for r in load(PROCESSED / "extra_similarity_pairs.jsonl") if r.get("split") == "train"]
    ep = sum(1 for r in extra_train if r["score"] > 0.5)
    en = len(extra_train) - ep
    tp, tn = s["pos"] + ep, s["neg"] + en
    print(f"相似度合并训练: {s['rows'] + x['train']}（正 {tp} / 负 {tn} = 1:{tn / max(tp, 1):.2f}）")
    print(f"清单已写入 {PROCESSED / 'pro_data_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
