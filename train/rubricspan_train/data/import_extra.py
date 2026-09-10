# -*- coding: utf-8 -*-
"""外部补充数据集归一化：各来源 → `data/raw/extra/{source}/normalized.jsonl` 统一 schema。

统一记录字段：

    {
      "source": "m3ke|internlm-history|ncr|exams",
      "subject": "历史|语文|地理|政治|…",
      "stage": "小学|初中|高中|大学|其他",
      "qid": "<source>-<序号>",
      "type": "choice|fill|open",
      "question": "题目/设问文本",
      "material": "阅读材料（可为空串）",
      "choices": {"A": "…", "B": "…"} | null,
      "answer_letter": "B" | null,
      "answer_text": "标准答案文本（choice 解析选项、fill/open 直接给文本）",
      "explanation": "解析（可为空串）",
      "difficulty": "…" | null,
      "split": "train|dev|test",
      "note": "获取/许可备注（缺数据时占位说明）"
    }

用途映射（详见 docs/reports/extra-datasets.md）：
- MCQ 数据 → 相似度句子对（question ↔ 正确选项正例 / 错误选项 hard 负例）；
- 带材料数据 → MRC is_impossible 负例（材料中无答案 span）。

用法（仓库根）::

    python -m rubricspan_train.data.import_extra [--src data/raw/extra_sources --out data/raw/extra]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 来源 → 获取状态（无法自动下载的记获取方式与许可风险，见 extra_sources/README.md）
STATUS = {
    "m3ke": "已下载：OpenCSG/raw.githubusercontent 镜像（tjunlp-lab/M3KE，dev/train/test 按学科 jsonl）",
    "internlm-history": "已下载：Gitee 镜像（sanbuphy/InternLM-History，2022 中考历史 专题分类对话）",
    "ncr": "未下载：OpenI 仓仅元数据；数据在 Google Drive（需浏览器/授权下载）",
    "exams": "未下载：HF/TFDS 不可达；ModelScope 仅有 EXAMS-V（不同数据集）",
    "d175": "商业授权：数据堂 1.3 亿题，需购买/申请，不入训练",
    "ceamc": "未公开：GitHub 仓仅 README、论文无数据链接，需联系作者",
}

M3KE_SPLIT_DIRS = {"dev": "dev", "train": "train", "test": "test"}
# 文件名 "Subject-Category-Stage.jsonl" → (subject, stage)
M3KE_STAGE_MAP = {
    "Primary school": "小学", "Junior high school": "初中", "High school": "高中",
    "College": "大学", "Other": "其他",
}


def _norm_qid(source: str, n: int) -> str:
    return f"{source}-{n:06d}"


def import_m3ke(src: Path) -> list[dict]:
    out = []
    n = 0
    for split, dirname in M3KE_SPLIT_DIRS.items():
        d = src / "m3ke" / "data" / dirname
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.jsonl")):
            # History-Arts & Humanities-High school.jsonl
            stem = fp.stem
            parts = [p.strip() for p in stem.split("-")]
            subject = parts[0] if parts else "其他"
            stage = "其他"
            for p in parts:
                if p in M3KE_STAGE_MAP:
                    stage = M3KE_STAGE_MAP[p]
            with fp.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    choices = {k: r[k] for k in "ABCDE" if r.get(k)}
                    ans_letter = (r.get("answer") or "").strip() or None
                    ans_text = choices.get(ans_letter, "") if ans_letter and ans_letter in choices else ""
                    out.append({
                        "source": "m3ke", "subject": subject, "stage": stage,
                        "qid": _norm_qid("m3ke", n), "type": "choice",
                        "question": r.get("question", ""), "material": "",
                        "choices": choices or None, "answer_letter": ans_letter,
                        "answer_text": ans_text, "explanation": "",
                        "difficulty": None, "split": split, "note": "",
                    })
                    n += 1
    return out


def import_internlm_history(src: Path) -> list[dict]:
    """InternLM-History：专题分类对话 → 客观分类题（question=去掉指令前缀的题干）。"""
    out = []
    n = 0
    prefix = re.compile(r"^请问以下问题属于中学历史学科中的哪一个专题？")
    for fp, split in [
        (src / "internlm-history" / "datasets" / "2022_junior_middle_history.json", "train"),
        (src / "internlm-history" / "datasets" / "2022_junior_middle_history_test.json", "test"),
    ]:
        if not fp.exists():
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        for item in data:
            for c in item.get("conversation", []):
                inp = prefix.sub("", c.get("input", "")).strip()
                if not inp:
                    continue
                out.append({
                    "source": "internlm-history", "subject": "历史", "stage": "初中",
                    "qid": _norm_qid("internlm-history", n), "type": "open",
                    "question": inp, "material": "",
                    "choices": None, "answer_letter": None,
                    "answer_text": c.get("output", ""), "explanation": "",
                    "difficulty": None, "split": split, "note": "专题分类标注",
                })
                n += 1
    return out


def import_ncr(src: Path) -> list[dict]:
    """NCR：中学语文阅读理解 MCQ。数据在 Google Drive，本地缺文件时仅记状态。"""
    out = []
    for fp in [src / "ncr" / "ncr_train.json", src / "ncr" / "ncr_dev.json", src / "ncr" / "ncr_test.json"]:
        if not fp.exists():
            continue
        n = 0
        data = json.loads(fp.read_text(encoding="utf-8"))
        for art in data:
            for q in art.get("Questions", []):
                out.append({
                    "source": "ncr", "subject": "语文", "stage": "初中",
                    "qid": _norm_qid("ncr", n), "type": "choice",
                    "question": q.get("Question", ""), "material": art.get("Content", ""),
                    "choices": {ch[0]: ch[2:].strip() for ch in q.get("Choices", []) if len(ch) >= 2},
                    "answer_letter": (q.get("Answer") or "").strip() or None,
                    "answer_text": "", "explanation": "",
                    "difficulty": art.get("Diff"), "split": fp.stem.split("_")[-1], "note": "",
                })
                n += 1
    return out


def import_exams(src: Path) -> list[dict]:
    """EXAMS：多语言考试问答（HF mhardalov/exams）。本地缺文件时仅记状态。"""
    out = []
    fp = src / "exams" / "exams_zh.jsonl"
    if not fp.exists():
        return out
    n = 0
    with fp.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            choices = r.get("choices") or {}
            ans = r.get("answer")
            ans_letter = None
            if isinstance(ans, str) and ans in choices:
                ans_letter = ans
            out.append({
                "source": "exams", "subject": r.get("subject", "其他"), "stage": "高中",
                "qid": _norm_qid("exams", n), "type": "choice",
                "question": r.get("question", ""), "material": r.get("context", ""),
                "choices": choices or None, "answer_letter": ans_letter,
                "answer_text": choices.get(ans_letter, "") if ans_letter else "",
                "explanation": "", "difficulty": None,
                "split": r.get("split", "train"), "note": "",
            })
            n += 1
    return out


ADAPTERS = {
    "m3ke": import_m3ke,
    "internlm-history": import_internlm_history,
    "ncr": import_ncr,
    "exams": import_exams,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=REPO_ROOT / "data" / "raw" / "extra_sources")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "raw" / "extra")
    args = p.parse_args(argv)

    total = 0
    summary: dict[str, dict] = {}
    for source, adapter in ADAPTERS.items():
        rows = adapter(args.src)
        if rows:
            dst = args.out / source / "normalized.jsonl"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8",
            )
            subjects = sorted({r["subject"] for r in rows})
            summary[source] = {"rows": len(rows), "subjects": subjects}
            total += len(rows)
            print(f"[{source}] {len(rows)} 条 → {dst}")
        else:
            print(f"[{source}] 无本地数据（{STATUS[source]}）")
    # 占位状态记录
    for source, note in STATUS.items():
        if source not in summary:
            summary[source] = {"rows": 0, "note": note}
    (args.out / "status.json").write_text(
        json.dumps({"total": total, "sources": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n合计 {total} 条归一化记录；状态写 {args.out / 'status.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
