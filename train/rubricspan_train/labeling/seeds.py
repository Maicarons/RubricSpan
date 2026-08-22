# -*- coding: utf-8 -*-
"""SAS-Bench 种子数据加载（M1 打标输入侧）。

产出两类对象：

- **唯一题池**：SAS-Bench 中多份学生作答共享同一题目；按题目文本去重得到
  唯一题（``SeedQuestion``），每题只解析一次评分配置；
- **作答样本**（``SeedSample``）：
  - ``full``：一份答卷的全部 steps 拼接为完整学生答案（贴近真实阅卷场景，
    且有人工总分 ``manual_label`` 可作打标质量对照）；
  - ``fragment``：单条 step 片段（天然的真实"部分作答"，含得分点遗漏，
    是 MRC 负样本与 partial 命中的重要来源）。
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUBJECT_CODE = {
    "1_History_ShortAns": "HIST",
    "8_Political_ShortAns": "POL",
    "3_Geography_ShortAns": "GEO",
    "6_Chinese_ShortAns": "CHN",
}


@dataclass
class SeedQuestion:
    question_id: str
    subject: str  # 学科中文名
    question_text: str
    reference: str
    total: float
    item_ids: list[str] = field(default_factory=list)


@dataclass
class SeedSample:
    sample_id: str
    question_id: str
    student_answer: str
    origin: str  # full | fragment | synthetic
    expert_total: float | None = None  # full 答卷的人工总分（manual_label）
    expert_step_label: float | None = None  # fragment 的人工步骤分


def load_sas_bench(
    raw_dir: Path, subjects: list[str]
) -> tuple[list[SeedQuestion], list[SeedSample]]:
    """加载指定学科，返回 (唯一题池, 全部 full/fragment 样本)。"""
    questions: list[SeedQuestion] = []
    qid_by_text: dict[str, str] = {}
    qindex: dict[str, SeedQuestion] = {}
    samples: list[SeedSample] = []
    for subject_file in subjects:
        code = SUBJECT_CODE[subject_file]
        subject_name = {"HIST": "历史", "POL": "政治", "GEO": "地理", "CHN": "语文"}[code]
        path = raw_dir / "sas-bench" / f"{subject_file}.jsonl"
        seen_q = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                qtext = _norm_question(item["question"])
                qid = qid_by_text.get(qtext)
                if qid is None:
                    seen_q += 1
                    qid = f"SAS-{code}-{seen_q:03d}"
                    qid_by_text[qtext] = qid
                    sq = SeedQuestion(
                        question_id=qid,
                        subject=subject_name,
                        question_text=item["question"].strip(),
                        reference=item["reference"].strip(),
                        total=float(item["total"]),
                        item_ids=[item["id"]],
                    )
                    questions.append(sq)
                    qindex[qid] = sq
                else:
                    qindex[qid].item_ids.append(item["id"])
                steps = item.get("steps", [])
                full_answer = "\n".join(s["response"].strip() for s in steps if s["response"].strip())
                if full_answer:
                    samples.append(
                        SeedSample(
                            sample_id=f"{item['id']}#full",
                            question_id=qid,
                            student_answer=full_answer,
                            origin="full",
                            expert_total=_first_num(item.get("manual_label")),
                        )
                    )
                for k, s in enumerate(steps):
                    resp = s["response"].strip()
                    if not resp:
                        continue
                    samples.append(
                        SeedSample(
                            sample_id=f"{item['id']}#s{k}",
                            question_id=qid,
                            student_answer=resp,
                            origin="fragment",
                            expert_step_label=float(s.get("label", 0) or 0),
                        )
                    )
    return questions, samples


def sample_fragments(
    samples: list[SeedSample],
    *,
    total: int,
    miss_ratio: float,
    seed: int,
) -> list[SeedSample]:
    """按 0 分 / 有分分层抽取 fragment 样本。"""
    rng = random.Random(seed)
    fragments = [s for s in samples if s.origin == "fragment"]
    zeros = [s for s in fragments if (s.expert_step_label or 0) <= 0]
    scored = [s for s in fragments if (s.expert_step_label or 0) > 0]
    rng.shuffle(zeros)
    rng.shuffle(scored)
    n_miss = min(len(zeros), int(round(total * miss_ratio)))
    n_hit = min(len(scored), total - n_miss)
    picked = zeros[:n_miss] + scored[:n_hit]
    # 不足额时从剩余片段补齐
    if len(picked) < total:
        rest = [s for s in fragments if s not in picked]
        picked += rest[: total - len(picked)]
    return picked


def _norm_question(qtext: str) -> str:
    """题目去重键：压空白。同一题不同份卷子的排版空格差异不至于误分。"""
    return "".join(qtext.split())


def _first_num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
