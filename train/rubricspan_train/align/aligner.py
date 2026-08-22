# -*- coding: utf-8 -*-
"""M1-5 对齐后处理：extracted_span → 学生答案字符级起止位置。

大模型被要求逐字复制片段，但实际输出常出现细差（多/漏一个标点、空格、
全半角差异，甚至轻微改写）。对齐按三级策略降级：

1. ``exact``    —— span 是答案的精确子串；
2. ``fuzzy``    —— 去空白/标点 + 全角转半角 + 小写化后的子串匹配，
                   通过字符映射表回投原始下标；
3. ``lcs``      —— 最长公共子串（difflib）：全部匹配块覆盖 span ≥ 60% 且最长
                   块 ≥ 2 字才接受，返回最长块对应的原文区间（容忍模型中段微改）。

返回 :class:`AlignResult`；三策略皆失败返回 ``None``（进入质检统计，不计入
对齐成功样本）。策略命中分布即“成功率统计”报告数据。
"""
from __future__ import annotations

import difflib
import string
import unicodedata
from dataclasses import dataclass

# 视为可忽略的“噪声字符”：ASCII 标点、CJK 标点、空白
_PUNCT = set(string.punctuation) | {
    "，", "。", "；", "：", "、", "（", "）", "【", "】", "《", "》", "！", "？",
    "“", "”", "‘", "’", "…", "—", "·", "『", "』", "〈", "〉", "〔", "〕",
    "％", "＋", "－", "＝", "＜", "＞", "＼", "／", "＠", "＆", "＊", "＃", "＄",
}


@dataclass
class AlignResult:
    start: int  # 学生答案中的起始下标（含）
    end: int  # 结束下标（不含）
    matched_text: str  # 实际对齐上的原文片段（可能与 span 有细差）
    strategy: str  # exact | fuzzy | lcs


def _normalize_keep_map(text: str) -> tuple[str, list[int]]:
    """归一化文本并保留 归一化下标 → 原文下标 的映射。"""
    norm_chars: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in _PUNCT:
            continue
        # 全角 ASCII → 半角；宽不换
        conv = unicodedata.normalize("NFKC", ch)
        if len(conv) != 1:  # 组合字符等罕见情况，保守丢弃
            conv = ch
        norm_chars.append(conv.lower())
        index_map.append(i)
    return "".join(norm_chars), index_map


def align_span(answer: str, span: str, *, min_lcs_coverage: float = 0.6) -> AlignResult | None:
    """把 span 对齐到 answer 的字符区间；失败返回 None。"""
    span = (span or "").strip()
    if not span:
        return None

    # 策略 1：精确子串
    idx = answer.find(span)
    if idx >= 0:
        return AlignResult(idx, idx + len(span), span, "exact")

    # 策略 2：归一化子串（容忍空白/标点/全半角差异）
    norm_answer, amap = _normalize_keep_map(answer)
    norm_span, smap = _normalize_keep_map(span)
    if norm_span:
        nidx = norm_answer.find(norm_span)
        if nidx >= 0:
            start = amap[nidx]
            last = nidx + len(norm_span) - 1
            end = amap[last] + 1
            return AlignResult(start, end, answer[start:end], "fuzzy")

    # 策略 3：最长公共子串兜底（匹配块总覆盖 span 主要内容即可，容忍中段微改）
    if not norm_answer or not norm_span:
        return None
    sm = difflib.SequenceMatcher(None, norm_answer, norm_span, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    coverage = sum(b.size for b in blocks)
    need = max(2.0, min_lcs_coverage * len(norm_span))
    if coverage < need:
        return None
    longest = max(blocks, key=lambda b: b.size)
    if longest.size < 2:
        return None
    start = amap[longest.a]
    end = amap[longest.a + longest.size - 1] + 1
    return AlignResult(start, end, answer[start:end], "lcs")


def align_batch(records: list[dict]) -> tuple[list[dict], dict[str, float]]:
    """批量对齐 hit 点标注。

    ``records`` 每条需含 ``student_answer`` 与点标注列表 ``point_labels``；
    hit=True 的点在原位追加 ``align`` 字段（AlignResult 序列化）。
    返回 (带对齐结果的 records, 统计信息)。
    """
    stats = {"hit_points": 0.0, "aligned": 0.0}
    strat: dict[str, float] = {"exact": 0.0, "fuzzy": 0.0, "lcs": 0.0}
    for rec in records:
        answer = rec["student_answer"]
        for pl in rec.get("point_labels", []):
            if not pl.get("hit"):
                continue
            stats["hit_points"] += 1
            span = pl.get("extracted_span") or ""
            res = align_span(answer, span)
            if res is None:
                pl["align"] = None
                continue
            pl["align"] = {"start": res.start, "end": res.end, "strategy": res.strategy}
            stats["aligned"] += 1
            strat[res.strategy] += 1
    stats.update(strat)
    return records, stats
