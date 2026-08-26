# -*- coding: utf-8 -*-
"""M2-4 评估指标（纯函数，技术方案 §13）。

- EM / Token-F1：字符级（中文按字切分，去除空白与标点后比对）；
- Point-wise Accuracy：逐点"是否有答案"判定准确率；
- Score Correlation：样本级总分 Pearson（预测总分 vs 人工总分）；
- 等价命中率：semantic 正例中被判有答的比例（同义识别核心指标）。
"""
from __future__ import annotations

import string
from typing import Sequence

_PUNCT = set(string.punctuation) | {
    "，", "。", "；", "：", "、", "（", "）", "【", "】", "《", "》", "！", "？",
    "“", "”", "‘", "’", "…", "—", "·",
}


def normalize(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace() and ch not in _PUNCT)


def exact_match(pred: str, gold: str) -> int:
    return int(normalize(pred) == normalize(gold) and normalize(pred) != "")


def token_f1(pred: str, gold: str) -> float:
    p, g = normalize(pred), normalize(gold)
    if not p or not g:
        return 0.0
    common: dict[str, int] = {}
    for ch in p:
        common[ch] = common.get(ch, 0) + 1
    overlap = 0
    for ch in g:
        if common.get(ch, 0) > 0:
            common[ch] -= 1
            overlap += 1
    if overlap == 0:
        return 0.0
    precision = overlap / len(p)
    recall = overlap / len(g)
    return 2 * precision * recall / (precision + recall)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
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


def decode_span(
    start_logits: Sequence[float],
    end_logits: Sequence[float],
    ctx_token_span: tuple[int, int],
    *,
    max_span_tokens: int = 64,
    null_index: int = 0,
) -> tuple[str, float, float]:
    """从 logits 解出最优非空 span。

    返回 (span_token_range, span_logprob, null_logprob)；调用方用
    ``span_logprob - null_logprob > threshold`` 判有答，用 offsets 还原文本。
    span_token_range 为 (start, end) token 下标（含两端）；无有效 span 返回 (0,0)。
    """
    import math

    lo, hi = ctx_token_span
    if lo < 0:
        return (0, 0), -1e9, -1e9
    s_probs = _log_softmax(start_logits)
    e_probs = _log_softmax(end_logits)
    null_logprob = s_probs[null_index] + e_probs[null_index]
    best = (-1e12, (0, 0))
    for i in range(lo, hi + 1):
        for j in range(i, min(i + max_span_tokens, hi + 1)):
            score = s_probs[i] + e_probs[j]
            if score > best[0]:
                best = (score, (i, j))
    return best[1], best[0], null_logprob


def _log_softmax(xs: Sequence[float]) -> list[float]:
    import math

    m = max(xs)
    exps = [math.exp(x - m) for x in xs]
    z = sum(exps)
    return [x - m - math.log(z) for x in xs]
