# -*- coding: utf-8 -*-
"""M1-1 打标 / 解析 / 合成 Prompt 模板与少样本示例。

三组模板共用一条纪律：**只输出严格 JSON**。打标输出结构由
``contracts/labeling-schema.json`` 约束（流水线负责回填 ``student_answer``
原文后做 Schema 校验，模型只需输出 ``question_id`` 与 ``point_labels``）。
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# M1-1 阅卷教师打标 Prompt
# ---------------------------------------------------------------------------

LABEL_SYSTEM = (
    "你是一位经验丰富、评判客观的高考阅卷组长。你的任务是把学生答案对照得分点逐点判分。\n"
    "规则：\n"
    "1. 只输出一个 JSON 对象，不要输出任何解释、markdown 代码块或其他文本。\n"
    "2. extracted_span 必须从学生答案中**逐字连续复制**：不得改写、缩写、纠错、加省略号；"
    "未命中时输出空字符串 \"\"。\n"
    "3. hit_type 判定：\n"
    "   - exact：学生答案中出现与得分点标准表述或某个别名**字面一致**的关键词；\n"
    "   - semantic：语义等价命中——意思正确但用了不同的说法（同义词、展开解释、口语化表述）；\n"
    "   - miss：未命中，或意思明显错误。\n"
    "4. extracted_span 应选取能支撑该得分点的**最短关键片段**（一般 4~40 字），"
    "exact 时优先取命中关键词本身，semantic 时取学生的等价表述。\n"
    "5. confidence 为你对本条判断的把握（0.0~1.0）；拿不准时给低值。\n"
    "6. partial_credit：完整命中=1.0；semantic 且只答出一半要点=0.5；miss 省略该字段。\n"
    "7. rationale 用不超过 30 字说明理由（仅供人工抽检）。"
)

_LABEL_FEWSHOT_USER = (
    "【题目】（2018·全国卷）戊戌变法前后，维新派宣传变法思想的主要方式有哪些？\n"
    "【得分点】\n"
    "1. 公车上书（别名：上书请愿、联名上书）\n"
    "2. 兴民权、设议院，实行君主立宪（别名：君主立宪、设议院）\n"
    "【学生答案】康有为他们曾经组织举人一起上书皇帝请求拒绝和约，后来又办报纸、成立强学会，"
    "宣传设制度局、开议会，让老百姓也能参与政治。\n"
    "【question_id】2018-bs-41"
)

_LABEL_FEWSHOT_ASSISTANT = json.dumps(
    {
        "question_id": "2018-bs-41",
        "point_labels": [
            {
                "point_id": 1,
                "hit": True,
                "hit_type": "semantic",
                "extracted_span": "组织举人一起上书皇帝请求拒绝和约",
                "confidence": 0.9,
                "partial_credit": 1.0,
                "rationale": "上书请愿即公车上书的等价表述",
            },
            {
                "point_id": 2,
                "hit": True,
                "hit_type": "semantic",
                "extracted_span": "宣传设制度局、开议会，让老百姓也能参与政治",
                "confidence": 0.85,
                "partial_credit": 1.0,
                "rationale": "兴民权设议院的口语化等价表述",
            },
        ],
    },
    ensure_ascii=False,
)

LABEL_USER_TEMPLATE = """【题目】{question}
【得分点】
{points_block}
【学生答案】{student_answer}
【question_id】{question_id}

对学生答案逐点判分，只输出 JSON：{{"question_id": "{question_id}", "point_labels": [{{"point_id": <int>, "hit": <bool>, "hit_type": "exact|semantic|miss", "extracted_span": "<逐字复制的片段或空串>", "confidence": <0.0-1.0>, "partial_credit": <0-1，semantic 时给>, "rationale": "<简短理由>"}}]}}"""


def build_label_messages(
    question_text: str,
    points: list[dict[str, Any]],
    student_answer: str,
    question_id: str,
) -> list[dict[str, str]]:
    """组装打标消息（含少样本示例）。points 为评分配置的 points 数组。"""
    lines = []
    for p in points:
        aliases = p.get("aliases") or []
        suffix = f"（别名：{'、'.join(aliases)}）" if aliases else ""
        lines.append(f"{p['point_id']}. {p['point_text']}{suffix}")
    user = LABEL_USER_TEMPLATE.format(
        question=question_text.strip(),
        points_block="\n".join(lines),
        student_answer=student_answer.strip(),
        question_id=question_id,
    )
    return [
        {"role": "system", "content": LABEL_SYSTEM},
        {"role": "user", "content": _LABEL_FEWSHOT_USER},
        {"role": "assistant", "content": _LABEL_FEWSHOT_ASSISTANT},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 参考答案 → 评分配置（得分点拆分）
# ---------------------------------------------------------------------------

PARSE_POINTS_SYSTEM = (
    "你是命题组专家，负责把参考答案拆解为可独立判分的得分点，供阅卷系统使用。\n"
    "只输出一个 JSON 对象，不要任何其他文本。规则：\n"
    "1. point_text 为得分点的标准表述：一句话内的关键要点（关键词/短语优先），"
    "不要照抄整段参考答案；每个得分点必须可独立判断学生是否答出。\n"
    "2. 多个小问的题目：把所有小问的要点合并为一个编号连续的列表（point_id 从 1 开始）。\n"
    "3. weight 为该点分值（可为小数），全部 weight 之和必须等于题目总分。\n"
    "4. aliases 列出 2~4 个等价表述/别称/常见同义说法（不含 point_text 本身）；"
    "确实没有合理别名时给空数组。\n"
    "5. 得分点数量不超过 {max_points} 个；参考答案要点过多时合并次要小点。"
)

PARSE_POINTS_USER_TEMPLATE = """【题目（满分 {total} 分）】{question}
【参考答案】{reference}
【question_id】{question_id}

把参考答案拆解为得分点，只输出 JSON：{{"question_id": "{question_id}", "total_score": {total}, "points": [{{"point_id": <int>, "point_text": "<标准表述>", "weight": <分值>, "aliases": ["<等价表述>", ...]}}]}}"""


def build_parse_points_messages(
    question_text: str, reference: str, total: float, question_id: str, max_points: int = 10
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PARSE_POINTS_SYSTEM.format(max_points=max_points)},
        {
            "role": "user",
            "content": PARSE_POINTS_USER_TEMPLATE.format(
                question=question_text.strip(),
                reference=reference.strip(),
                total=total,
                question_id=question_id,
            ),
        },
    ]


# ---------------------------------------------------------------------------
# M1-2 四档合成答卷
# ---------------------------------------------------------------------------

SYNTH_SYSTEM = (
    "你要扮演真实高中生作答主观题。你的输出将被用于训练阅卷模型，因此必须像真实学生：\n"
    "- 用高中生的语言，可以口语化、有少量啰嗦或过渡句，但不要编造与题目无关的内容；\n"
    "- 不要抄录题目或材料原文；不要使用 markdown 列表符号以外的格式化记号；\n"
    "- 直接输出答案正文，不要任何前言（如“答：”可以要，但不要解释你在扮演谁）。\n"
    "只输出一个 JSON 对象：{\"answer\": \"<学生答案正文>\"}，不要其他文本。"
)

_SYNTH_TIER_SPECS: dict[str, str] = {
    "excellent": (
        "【水平：优秀（能拿约 90%~100% 的分）】\n"
        "覆盖全部得分点。要求：**至少一半得分点使用与标准表述不同的同义说法**"
        "（换词、展开解释、口语化转述），其余可用标准术语；表述准确、逻辑清楚。"
    ),
    "good": (
        "【水平：良好（约 70% 的分）】\n"
        "覆盖约 3/4 的得分点，遗漏 1~2 个次要点；已答出的点中**多数用同义说法**而非照搬标准表述；"
        "个别点表述略有含糊但意思正确。"
    ),
    "fair": (
        "【水平：及格边缘（约 50% 的分）】\n"
        "只答出一半左右得分点；答案较短、表述笼统，个别已答点只沾边（部分正确）；"
        "有一个得分点用同义说法答出。"
    ),
    "poor": (
        "【水平：不及格（约 20% 的分）】\n"
        "只答出 0~1 个得分点，或答非所问、存在明显史实/概念错误；篇幅短。"
        "允许出现真实学生常见的错误联想，但不得复述标准答案。"
    ),
}

SYNTH_USER_TEMPLATE = """{tier_spec}
【题目】{question}
【得分点（仅供你把握内容范围，禁止照抄整句标准表述）】
{points_block}
{variant_hint}
以真实高中生口吻作答本题，只输出 JSON：{{"answer": "<答案正文>"}}"""


def build_synth_messages(
    question_text: str,
    points: list[dict[str, Any]],
    tier: str,
    variant: int = 0,
) -> list[dict[str, str]]:
    lines = [f"{p['point_id']}. {p['point_text']}" for p in points]
    variant_hint = (
        "（与已有答案写法明显不同：句式、切入角度、用词都要变化，避免重复模板。）"
        if variant > 0
        else ""
    )
    user = SYNTH_USER_TEMPLATE.format(
        tier_spec=_SYNTH_TIER_SPECS[tier],
        question=question_text.strip(),
        points_block="\n".join(lines),
        variant_hint=variant_hint,
    )
    return [
        {"role": "system", "content": SYNTH_SYSTEM},
        {"role": "user", "content": user},
    ]
