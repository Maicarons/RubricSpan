# -*- coding: utf-8 -*-
"""M1 构建侧单测：Schema 校验、投票、划分与负样本抽样。"""
from __future__ import annotations

import copy

import jsonschema
import pytest

from rubricspan_train.data.build import (
    build_mrc,
    build_similarity_from_labels,
    split_by_question,
    subsample_negatives,
)
from rubricspan_train.labeling.common import load_json_schema
from rubricspan_train.labeling.run import _majority_vote, _normalize_label_output
from rubricspan_train.labeling.seeds import SeedSample

SCORING_CONFIG = {
    "question_id": "SAS-TST-001",
    "total_score": 6,
    "subject": "历史",
    "points": [
        {"point_id": 1, "point_text": "公车上书", "weight": 3.0, "aliases": ["上书请愿"]},
        {"point_id": 2, "point_text": "兴民权设议院", "weight": 3.0, "aliases": ["君主立宪"]},
    ],
}


def _record():
    return {
        "sample_id": "TST_0#full",
        "origin": "full",
        "expert_total": 6,
        "labels": {
            "question_id": "SAS-TST-001",
            "student_answer": "康有为组织举人联名上书皇帝，后来又宣传设议会让百姓参与政治。",
            "point_labels": [
                {
                    "point_id": 1,
                    "hit": True,
                    "hit_type": "semantic",
                    "extracted_span": "组织举人联名上书皇帝",
                    "confidence": 0.9,
                    "partial_credit": 1.0,
                },
                {
                    "point_id": 2,
                    "hit": True,
                    "hit_type": "exact",
                    "extracted_span": "设议会",
                    "confidence": 0.95,
                    "partial_credit": 1.0,
                },
            ],
            "labeling_meta": {
                "model": "test",
                "temperature": 0.1,
                "self_consistency_votes": 1,
                "labeled_at": "2026-08-22T00:00:00+00:00",
            },
        },
    }


class TestSchemaConformance:
    def test_normalized_labels_conform_contract(self):
        sample = SeedSample(
            sample_id="TST_0#full",
            question_id="SAS-TST-001",
            student_answer="康有为组织举人联名上书。",
            origin="full",
        )
        raw = {
            "question_id": "SAS-TST-001",
            "point_labels": [
                {"point_id": 1, "hit": True, "hit_type": "semantic",
                 "extracted_span": "组织举人联名上书", "confidence": 0.9, "partial_credit": 1.0},
                {"point_id": 99, "hit": True, "hit_type": "weird", "extracted_span": "x"},
            ],
        }
        rec = _normalize_label_output(raw, sample, SCORING_CONFIG, "test-model", 0.1)
        schema = load_json_schema("labeling-schema.json")
        jsonschema.validate(rec["labels"], schema)  # 不合法定义被丢弃、缺失点补 miss
        assert [p["point_id"] for p in rec["labels"]["point_labels"]] == [1, 2]
        assert rec["labels"]["point_labels"][1]["hit_type"] == "miss"

    def test_scoring_config_contract(self):
        schema = load_json_schema("scoring-config.schema.json")
        jsonschema.validate(SCORING_CONFIG, schema)


class TestMajorityVote:
    def test_majority_overrides_minority(self):
        base = [
            {"point_id": 1, "hit": True, "hit_type": "exact",
             "extracted_span": "甲", "confidence": 0.9, "partial_credit": 1.0},
        ]
        flip = [
            {"point_id": 1, "hit": False, "hit_type": "miss",
             "extracted_span": "", "confidence": 0.8},
        ]
        same = [copy.deepcopy(base[0])]
        final, flips, agreement = _majority_vote(base, [base, flip, same])
        assert flips == 0  # 平票多数（2/3 支持 hit）不翻转
        assert final[0]["hit"] is True
        assert agreement == pytest.approx(2 / 3)

    def test_tie_falls_back_to_first_round(self):
        base = [{"point_id": 1, "hit": True, "hit_type": "semantic",
                 "extracted_span": "甲", "confidence": 0.9, "partial_credit": 1.0}]
        flip = [{"point_id": 1, "hit": False, "hit_type": "miss",
                 "extracted_span": "", "confidence": 0.7}]
        final, flips, _ = _majority_vote(base, [base, flip])
        assert flips == 0
        assert final[0]["hit_type"] == "semantic"


class TestSplit:
    def test_deterministic_and_disjoint(self):
        qids = [f"Q{i:03d}" for i in range(50)]
        a = split_by_question(qids, {"train": 0.8, "val": 0.1, "test": 0.1}, seed=42)
        b = split_by_question(qids, {"train": 0.8, "val": 0.1, "test": 0.1}, seed=42)
        assert a == b
        assert set(a) == set(qids)
        from collections import Counter

        counts = Counter(a.values())
        assert counts["train"] == 40 and counts["val"] == 5 and counts["test"] == 5


class TestMrcBuild:
    def test_five_tuple_and_alignment_consistency(self):
        rec = _record()
        # 注入对齐结果（quality 阶段产物结构）
        ans = rec["labels"]["student_answer"]
        for pl in rec["labels"]["point_labels"]:
            i = ans.find(pl["extracted_span"])
            pl["align"] = {"start": i, "end": i + len(pl["extracted_span"]), "strategy": "exact"}
        split_of = {"SAS-TST-001": "train"}
        mrc = build_mrc([rec], {"SAS-TST-001": SCORING_CONFIG}, split_of)
        assert len(mrc) == 2
        for r in mrc:
            assert r["answer"] == ans[r["answer_start"] : r["answer_end"]]
            assert r["split"] == "train"

    def test_negative_subsample_ratio(self):
        pos = [{"id": f"p{i}", "question_id": f"Q{i}", "is_impossible": False, "context": "c"}
               for i in range(800)]
        neg = [{"id": f"n{i}", "question_id": f"Q{i}", "is_impossible": True, "context": "c"}
               for i in range(2000)]
        out = subsample_negatives(pos + neg, target_ratio=0.22, seed=42)
        n_neg = sum(1 for r in out if r["is_impossible"])
        assert n_neg / len(out) == pytest.approx(0.22, abs=0.01)
        assert len([r for r in out if not r["is_impossible"]]) == 800

    def test_similarity_pairs(self):
        rec = _record()
        ans = rec["labels"]["student_answer"]
        for pl in rec["labels"]["point_labels"]:
            i = ans.find(pl["extracted_span"])
            pl["align"] = {"start": i, "end": i + len(pl["extracted_span"]), "strategy": "exact"}
        rec["labels"]["point_labels"].append(
            {"point_id": 3, "hit": False, "hit_type": "miss", "extracted_span": "",
             "confidence": 0.9, "align": None}
        )
        SCORING_CONFIG["points"].append(
            {"point_id": 3, "point_text": "创办时务报", "weight": 2, "aliases": []}
        )
        split_of = {"SAS-TST-001": "train"}
        pairs = build_similarity_from_labels([rec], {"SAS-TST-001": SCORING_CONFIG}, split_of)
        by_source = {p["source"]: p for p in pairs}
        assert by_source["label-exact"]["score"] == 1.0
        assert by_source["label-semantic"]["score"] == 1.0
        assert by_source["label-miss"]["score"] == 0.0
        alias_pairs = [p for p in pairs if p["source"] == "label-alias"]
        assert {"上书请愿", "君主立宪"} == {p["sentence2"] for p in alias_pairs}
