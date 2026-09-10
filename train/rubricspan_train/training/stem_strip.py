"""题干剥离（训练侧预处理）——Rust `rubricspan_scoring::preprocess::strip_stem_spans` 的 Python 端口。

动机：MRC 训练数据的 `origin=full` 行 context 原样携带题干材料，推理侧评分入口在
评分前会剥离题干（CC-006），训练与推理口径不一致会让模型学到"从题干里抽答案"。
本模块在**数据侧**做同源剥离：空格替代（字符数不变），`answer_start`/`answer_end`
索引天然保持有效，无需重新定位。

实现与 Rust 版逐分支对齐：
- 归一化：忽略空白、中英文标点、ASCII 数字、①类注释上标；ASCII 字母折叠小写；
- 对答案归一化序列逐位置二分最长匹配：`norm[i..j]` 在题干中出现时更短的
  `norm[i..j']` 必然也出现，匹配长度对 j 单调，可安全二分；
- 重合 ≥ [`MIN_MATCH_CHARS`] 字（归一化后）的片段替换为空格。

校验方式：`train/tests/test_stem_strip.py` 与 Rust 版测试用例同源对拍。
"""

from __future__ import annotations

import json
from pathlib import Path

MIN_MATCH_CHARS = 8

_IGNORABLE_CJK = set("，。；：、！？（）【】《》「」『』“”‘’…—·～．﹒＊＃＋－／＝０１２３４５６７８９")
_IGNORABLE_CJK |= {chr(c) for c in range(ord("①"), ord("⑳") + 1)}
_IGNORABLE_CJK |= {chr(c) for c in range(ord("⑴"), ord("⑽") + 1)}
_IGNORABLE_CJK |= {chr(c) for c in range(ord("㈠"), ord("㈩") + 1)}


def is_ignorable(c: str) -> bool:
    """与 Rust 版一致：空白、中英文标点、数字、注释上标均忽略；ASCII 字母保留。"""
    if c.isspace() or c in _IGNORABLE_CJK:
        return True
    if c.isascii():
        return not c.isalnum()  # ASCII 数字/标点忽略，字母保留
    return False


def _fold(c: str) -> str:
    return c.lower() if c.isascii() else c


def normalize(text: str) -> str:
    return "".join(_fold(c) for c in text if not is_ignorable(c))


def strip_stem_spans(answer: str, stems: list[str]) -> str:
    """从答案中剥离与任一题干重合的长片段（空格替代，长度不变，索引稳定）。"""
    if not answer or not stems:
        return answer
    kept = [i for i, c in enumerate(answer) if not is_ignorable(c)]
    if len(kept) < MIN_MATCH_CHARS:
        return answer
    norm = "".join(_fold(answer[i]) for i in kept)
    stem_norms = [normalize(s) for s in stems if len(normalize(s)) >= MIN_MATCH_CHARS]
    if not stem_norms:
        return answer

    marked = [False] * len(answer)
    n = len(norm)
    i = 0
    while i < n:
        best = 0
        if n - i >= MIN_MATCH_CHARS:
            # 二分最长匹配长度：lo 恒可行（MIN-1 视为不匹配基准），hi 为剩余长度
            lo, hi = MIN_MATCH_CHARS - 1, n - i
            while lo < hi:
                mid = (lo + hi + 1) // 2  # div_ceil，与 Rust 一致
                pat = norm[i:i + mid]
                if any(pat in s for s in stem_norms):
                    lo = mid
                else:
                    hi = mid - 1
            if lo >= MIN_MATCH_CHARS:
                best = lo
        if best > 0:
            for k in kept[i:i + best]:
                marked[k] = True
            i += best
        else:
            i += 1
    if not any(marked):
        return answer
    return "".join(" " if marked[off] else c for off, c in enumerate(answer))


def build_stem_map(sas_raw_dir: Path) -> dict[str, str]:
    """SAS 原始题库 → {item_id: 题干全文}（多来源题干换行拼接，供训练行按 id 前缀查找）。"""
    item2q: dict[str, str] = {}
    for fp in sorted(sas_raw_dir.glob("*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("id") and item.get("question"):
                    item2q[item["id"]] = item["question"].strip()
    return item2q


def strip_train_jsonl(src: Path, dst: Path, stem_map: dict[str, str]) -> int:
    """把 mrc 训练/验证 jsonl 中 origin=full 行的 context 做题干剥离，写出副本。

    返回剥离发生变化的行数；`answer_start/end` 因空格替代长度不变而保持有效。
    若剥离会波及金标 answer 区间（数据矛盾），该行保持原样并计数告警。
    """
    changed = 0
    guard_skips = 0
    rows: list[dict] = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("origin") == "full" and row.get("id"):
                item_id = row["id"].split("#")[0]
                stem = stem_map.get(item_id, "")
                if stem:
                    before = row["context"]
                    after = strip_stem_spans(before, [stem])
                    if after != before:
                        # 守卫：剥离不得把金标 answer 区间整段清成空格（数据矛盾则保持原样）
                        s, e = int(row.get("answer_start", -1)), int(row.get("answer_end", -1))
                        if s >= 0 and e > s and not after[s:e + 1].strip():
                            guard_skips += 1
                        else:
                            row["context"] = after
                            changed += 1
            rows.append(row)
    dst.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return changed, guard_skips
