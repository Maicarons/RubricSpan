# -*- coding: utf-8 -*-
"""MRC 训练数据特征化：五元组 → BERT QA features。

输入为 M1-7 产出的五元组（context/query/answer/answer_start/answer_end，
is_impossible 负样本），或 CMRC 2018 桥接数据（SQuAD 格式）。

编码约定（SQuAD v2 风格）：

- 输入序列 ``[CLS] query [SEP] context [SEP]``，max_length 截断只作用于 context；
- 正例：answer 的字符区间经 offset mapping 映射到 context token 区间；
  超出截断预算的正例在训练时丢弃（避免错负信号），评测时标记
  ``out_of_range``（模型客观无法命中，报告单列）；
- 负例：start = end = 0（指向 [CLS]，即 SQuAD2 的 null answer 约定），
  推理端以「最优非 CLS span 概率 − CLS span 概率」的差值阈值判有答。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence


@dataclass
class MrcExample:
    """一条五元组（或 CMRC 转换后的等价物）。"""
    uid: str
    query: str
    context: str
    answer: str = ""
    answer_start: int = -1
    is_impossible: bool = False
    hit_type: str = "miss"
    origin: str = ""
    question_id: str = ""
    point_weight: float = 0.0


# M8：选择型得分点（"选B得3分""断句正确项为B""第（1）题答案：C"）由
# Rust 评分引擎的选项字母规则负责，训练时剔除其**正例**（标注 span 多为单字母，
# 教模型"抽字母"捷径，造成高置信误判）；保留负例（该形式应判无答）。
OPTION_QUERY_RE = re.compile(
    r"(选\s*[A-E]|[A-E]项|答案\s*[A-E]|[A-E]正确|正确项为\s*[A-E]|"
    r"正确选项\s*[A-E]|不正确项为\s*[A-E]|[A-E]得|[A-E]为不正确)"
)


def is_option_query(query: str) -> bool:
    return bool(OPTION_QUERY_RE.search(query))


def load_mrc_jsonl(path: Path, *, drop_option_points: bool = False) -> list[MrcExample]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if (
                drop_option_points
                and not r.get("is_impossible", False)
                and is_option_query(r.get("query", ""))
            ):
                continue
            out.append(
                MrcExample(
                    uid=r["id"],
                    query=r["query"],
                    context=r["context"],
                    answer=r.get("answer", ""),
                    answer_start=int(r.get("answer_start", -1)),
                    is_impossible=bool(r.get("is_impossible", False)),
                    hit_type=r.get("hit_type", "miss"),
                    origin=r.get("origin", ""),
                    question_id=r.get("question_id", ""),
                    point_weight=float(r.get("point_weight", 0)),
                )
            )
    return out


def load_cmrc(path: Path, limit: int = 0) -> list[MrcExample]:
    """CMRC 2018 官方格式 → MrcExample（M2-1 桥接用）。

    本仓库版本为扁平列表：``[{context_id, context_text, qas, title}]``，
    ``qas[i] = {query_id, query_text, answers: [text, ...]}``（无字符起点，
    用 ``context.find`` 定位；定位失败跳过）。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    articles = data["data"] if isinstance(data, dict) else data
    out: list[MrcExample] = []
    for article in articles:
        if "paragraphs" in article:  # SQuAD 兼容格式
            paras = [(p["context"], qa) for p in article["paragraphs"] for qa in p["qas"]]
            qid_of = lambda qa: qa["id"]          # noqa: E731
            qtext_of = lambda qa: qa["question"]  # noqa: E731
            ans_of = lambda qa: (qa.get("answers") or [None])[0]  # noqa: E731
        else:
            paras = [(article["context_text"], qa) for qa in article["qas"]]
            qid_of = lambda qa: qa["query_id"]    # noqa: E731
            qtext_of = lambda qa: qa["query_text"]  # noqa: E731
            ans_of = lambda qa: (qa.get("answers") or [None])[0]  # noqa: E731
        for context, qa in paras:
            a = ans_of(qa)
            if not a:
                continue
            if isinstance(a, dict):
                text, start = a["text"], int(a.get("answer_start", -1))
            else:
                text = str(a)
                start = context.find(text)
            if not text or start < 0:
                continue
            out.append(
                MrcExample(
                    uid=qid_of(qa),
                    query=qtext_of(qa),
                    context=context,
                    answer=text,
                    answer_start=start,
                    is_impossible=False,
                    hit_type="exact",
                    origin="cmrc",
                    question_id=qid_of(qa),
                )
            )
            if limit and len(out) >= limit:
                return out
    return out


def featurize(
    tokenizer: Any,
    examples: Sequence[MrcExample],
    *,
    max_length: int = 512,
    drop_truncated_positive: bool = True,
) -> Iterator[dict]:
    """编码为模型输入 dict 流（list 化由调用方决定）。

    产出字段：input_ids / attention_mask / token_type_ids / start_positions /
    end_positions / uid / out_of_range。
    """
    queries = [e.query for e in examples]
    contexts = [e.context for e in examples]
    enc = tokenizer(
        queries,
        contexts,
        max_length=max_length,
        truncation="only_second",
        padding="max_length",
        return_offsets_mapping=True,
        return_tensors=None,
    )
    seq_ids_batch = [enc.sequence_ids(i) for i in range(len(examples))]
    for i, e in enumerate(examples):
        offsets = enc["offset_mapping"][i]
        seq_ids = seq_ids_batch[i]
        ctx_span = _context_token_span(seq_ids)
        start_pos = end_pos = 0  # 默认 null（CLS）
        out_of_range = False
        if not e.is_impossible and e.answer and 0 <= e.answer_start < len(e.context):
            ans_end_char = e.answer_start + len(e.answer)
            tok_span = _char_span_to_token_span(
                offsets, seq_ids, ctx_span, e.answer_start, ans_end_char
            )
            if tok_span is None:
                out_of_range = True
                if drop_truncated_positive:
                    continue
            else:
                start_pos, end_pos = tok_span
        yield {
            "input_ids": enc["input_ids"][i],
            "attention_mask": enc["attention_mask"][i],
            "token_type_ids": enc["token_type_ids"][i],
            "start_positions": start_pos,
            "end_positions": end_pos,
            "uid": e.uid,
            "out_of_range": out_of_range,
        }


def _context_token_span(seq_ids: list[int | None]) -> tuple[int, int]:
    """sequence_ids==1（第二个输入串，即 context）的 token 下标区间。"""
    first = last = -1
    for i, sid in enumerate(seq_ids):
        if sid == 1:
            if first < 0:
                first = i
            last = i
    return first, last


def _char_span_to_token_span(
    offsets: list[tuple[int, int]],
    seq_ids: list[int | None],
    ctx_span: tuple[int, int],
    start_char: int,
    end_char: int,
) -> tuple[int, int] | None:
    """字符区间 → token 区间；answer 完全落在 context 截断范围外返回 None。"""
    first, last = ctx_span
    if first < 0:
        return None
    tok_s = tok_e = None
    for i in range(first, last + 1):
        s, e = offsets[i]
        if s == e:  # 特殊 token
            continue
        if e > start_char and s < end_char:  # 与答案区间相交
            if tok_s is None:
                tok_s = i
            tok_e = i
    if tok_s is None:
        return None
    return tok_s, tok_e
