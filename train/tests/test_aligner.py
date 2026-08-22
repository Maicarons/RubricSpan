# -*- coding: utf-8 -*-
"""M1-5 对齐模块单测：三种匹配策略为必测项（train/README.md 约定）。"""
from __future__ import annotations

from rubricspan_train.align.aligner import AlignResult, align_span


class TestExact:
    def test_plain_substring(self):
        res = align_span("学生认为戊戌变法促进了思想启蒙", "戊戌变法")
        assert res is not None and res.strategy == "exact"
        assert res.start == 4 and res.end == 8
        assert res.matched_text == "戊戌变法"

    def test_first_occurrence(self):
        res = align_span("甲说A，乙再说A", "A")
        assert res is not None and res.start == 2

    def test_empty_span(self):
        assert align_span("任何答案", "") is None
        assert align_span("任何答案", "   ") is None

    def test_not_found_exact_falls_through(self):
        # 无任何公共字符 → 三级策略全部失败
        assert align_span("完全不同的内容", "ABC") is None


class TestFuzzy:
    def test_punctuation_diff(self):
        answer = "他答：促进了思想启蒙，有利于社会进步。"
        span = "促进了思想启蒙 有利于社会进步"  # 模型把逗号换成空格
        res = align_span(answer, span)
        assert res is not None and res.strategy == "fuzzy"
        assert answer[res.start : res.end] == "促进了思想启蒙，有利于社会进步"

    def test_fullwidth_halfwidth(self):
        res = align_span("增长率为５０％以上", "50%")
        assert res is not None and res.strategy == "fuzzy"
        # ％ 属归一化时剔除的标点，对齐区间落在数字本体上
        assert res.matched_text == "５０"

    def test_case_insensitive(self):
        res = align_span("采用OPEC机制增产", "opec")
        assert res is not None and res.strategy == "fuzzy"


class TestLcs:
    def test_minor_rewrite(self):
        answer = "辛亥革命推翻了清王朝的专制统治"
        span = "辛亥革命推翻清朝的专制统治"  # 模型微改（王朝→朝）
        res = align_span(answer, span)
        assert res is not None and res.strategy == "lcs"
        # 对齐片段必须来自原文
        assert res.matched_text in answer
        assert len(res.matched_text) >= 2

    def test_lcs_coverage_too_low(self):
        # 覆盖率不足 60% 的碎片不接受
        assert align_span("一二三四五六七八九", "六七八九十一二三") is None

    def test_completely_different(self):
        assert align_span("经济重心南移", "政治制度变革") is None


class TestBoundaries:
    def test_span_at_answer_start(self):
        res = align_span("开议会，设制度局", "开议会")
        assert res is not None and res.start == 0

    def test_span_at_answer_end(self):
        answer = "维新派主张设制度局"
        res = align_span(answer, "设制度局")
        assert res is not None and res.end == len(answer)

    def test_long_answer_no_crash(self):
        answer = "句子。" * 500
        res = align_span(answer, "句子")
        assert res is not None
