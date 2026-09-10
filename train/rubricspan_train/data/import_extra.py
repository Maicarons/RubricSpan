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
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 来源 → 获取状态（无法自动下载的记获取方式与许可风险，见 extra_sources/README.md）
STATUS = {
    "m3ke": "已下载：OpenCSG/raw.githubusercontent 镜像（tjunlp-lab/M3KE，dev/train/test 按学科 jsonl）",
    "internlm-history": "已下载：Gitee 镜像（sanbuphy/InternLM-History，2022 中考历史 专题分类对话）",
    "gaokao-bench": "已下载：raw.githubusercontent（OpenLMLab/GAOKAO-Bench，Apache-2.0，2010-2022 高考主/客观题含参考答案）",
    "agieval": "已下载：raw.githubusercontent（ruixiangcui/AGIEval，MIT，高考各科 jsonl）",
    "cmmlu": "已下载：raw.githubusercontent（haonan-li/CMMLU，无 LICENSE 文件，学术基准惯例，67 学科知识测试）",
    "reciter": "已下载：raw.githubusercontent（Binkic/Reciter，MIT，高考古诗文默写题库）",
    "ceval": "已下载：ModelScope（OmniData/C-Eval，CC BY-NC-SA 4.0，dev/val 带答案入训、test 答案保密；模型发布许可已对齐 CC BY-NC-SA）",
    "ncr": "未下载：OpenI 仓仅元数据；数据在 Google Drive（需浏览器/授权下载）",
    "exams": "未下载：HF/TFDS 不可达；ModelScope 仅有 EXAMS-V（不同数据集）",
    "d175": "商业授权：数据堂 1.3 亿题，需购买/申请，不入训练",
    "ceamc": "未公开：GitHub 仓仅 README、论文无数据链接，需联系作者",
    "ceval": "不可用：C-Eval 为 CC BY-NC-SA 4.0（非商业），与项目 Apache-2.0 模型冲突，不入训练",
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
    """NCR：中学语文阅读理解 MCQ。数据在 Google Drive（见 extra_sources/README.md），
    本地缺文件时仅记状态；支持 `ncr/*.json` 任意文件名（train/dev/test 由文件名推断）。"""
    out = []
    d = src / "ncr"
    if not d.exists():
        return out
    for fp in sorted(d.glob("*.json")):
        stem = fp.stem.lower()
        if "train" in stem:
            split = "train"
        elif "dev" in stem or "valid" in stem:
            split = "dev"
        elif "test" in stem:
            split = "test"
        else:
            split = "train"
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
                    "difficulty": art.get("Diff"), "split": split, "note": "",
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


def import_gaokao_bench(src: Path) -> list[dict]:
    """GAOKAO-Bench（OpenLMLab，Apache-2.0）：2010-2022 高考客观题 + 主观题（含参考答案）。

    文件：Data/{Objective_Questions,Subjective_Questions}/<主题>_*.json
    记录：{year, category, question, answer, analysis, index, score}；
    客观题选项内联于 question（"A．…  B．…"），answer=["C"]；主观题 answer 为参考答案文本。
    """
    SUBJ_MAP = {
        "History": "历史", "Geography": "地理", "Political_Science": "政治",
        "Chinese": "语文", "Chinese_Language": "语文",
    }
    out = []
    n = 0
    for sub in ("Objective_Questions", "Subjective_Questions"):
        d = src / "gaokao-bench" / "Data" / sub
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.json")):
            subject = "语文"
            for k, v in SUBJ_MAP.items():
                if k in fp.stem:
                    subject = v
                    break
            data = json.loads(fp.read_text(encoding="utf-8"))
            is_obj = sub == "Objective_Questions"
            for item in data.get("example", []):
                q = (item.get("question") or "").strip()
                if not q:
                    continue
                choices = None
                ans_letter = None
                ans_text = ""
                if is_obj:
                    # 内联选项 "A．xx  B．yyy" → {A: xx, ...}；answer=["C"]
                    parts = re.split(r"\s*([A-E])．", q)
                    if len(parts) >= 3:
                        q = parts[0].strip()
                        choices = {}
                        for i in range(1, len(parts) - 1, 2):
                            choices[parts[i]] = parts[i + 1].strip()
                        ans = (item.get("answer") or [])
                        ans_letter = ans[0] if ans and ans[0] in choices else None
                        ans_text = choices.get(ans_letter, "") if ans_letter else ""
                    else:
                        ans = (item.get("answer") or [])
                        ans_letter = ans[0] if ans else None
                else:
                    ans_text = (item.get("answer") or "").strip()
                out.append({
                    "source": "gaokao-bench", "subject": subject, "stage": "高中",
                    "qid": _norm_qid("gaokao-bench", n), "type": "choice" if is_obj else "open",
                    "question": q, "material": "",
                    "choices": choices, "answer_letter": ans_letter,
                    "answer_text": ans_text,
                    "explanation": (item.get("analysis") or "").strip(),
                    "difficulty": item.get("score"), "split": "train",
                    "note": f"{item.get('year')} {item.get('category','')}".strip(),
                })
                n += 1
    return out


def import_agieval(src: Path) -> list[dict]:
    """AGIEval（MIT）：高考各科 jsonl。记录 {passage, question, options:[(A)…], label, answer}。"""
    SUBJ_MAP = {"chinese": "语文", "history": "历史", "geography": "地理", "english": "英语"}
    out = []
    n = 0
    d = src / "agieval" / "data" / "v1"
    if not d.exists():
        return out
    for fp in sorted(d.glob("gaokao-*.jsonl")):
        subject = "其他"
        for k, v in SUBJ_MAP.items():
            if fp.stem.endswith(k):
                subject = v
                break
        with fp.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                choices = {}
                for opt in r.get("options") or []:
                    m = re.match(r"\(([A-E])\)\s*(.*)", opt.strip())
                    if m:
                        choices[m.group(1)] = m.group(2).strip()
                label = (r.get("label") or "").strip() or None
                out.append({
                    "source": "agieval", "subject": subject, "stage": "高中",
                    "qid": _norm_qid("agieval", n), "type": "choice",
                    "question": (r.get("question") or "").strip(),
                    "material": (r.get("passage") or "").strip(),
                    "choices": choices or None, "answer_letter": label,
                    "answer_text": choices.get(label, "") if label and label in choices else "",
                    "explanation": "", "difficulty": None, "split": "train",
                    "note": (r.get("other") or {}).get("source", ""),
                })
                n += 1
    return out


def import_cmmlu(src: Path) -> list[dict]:
    """CMMLU（无 LICENSE，学术基准惯例）：67 学科知识测试 CSV（Question,A,B,C,D,Answer）。"""
    SUBJ_CN = {
        "chinese_history": "中国历史", "world_history": "世界历史", "chinese_literature": "中国文学",
        "ancient_chinese": "古代汉语", "modern_chinese": "现代汉语", "elementary_chinese": "小学语文",
        "high_school_geography": "高中地理", "high_school_politics": "高中政治",
        "chinese_foreign_policy": "中国外交政策", "legal_and_moral_basis": "法律与道德基础",
        "education": "教育学", "sociology": "社会学", "philosophy": "哲学",
        "marxist_theory": "马克思主义理论", "world_religions": "世界宗教", "global_facts": "全球常识",
        "ethnology": "民族学", "journalism": "新闻学", "arts": "艺术",
        "chinese_teacher_qualification": "教师资格考试",
    }
    out = []
    n = 0
    d = src / "cmmlu" / "data"
    if not d.exists():
        return out
    for split in ("dev", "test"):
        for fp in sorted((d / split).glob("*.csv")):
            subject = SUBJ_CN.get(fp.stem, fp.stem)
            stage = "小学" if "elementary" in fp.stem else ("高中" if "high_school" in fp.stem else "其他")
            with fp.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    q = (row.get("Question") or "").strip()
                    if not q:
                        continue
                    choices = {k: (row.get(k) or "").strip() for k in "ABCD" if (row.get(k) or "").strip()}
                    ans_letter = (row.get("Answer") or "").strip() or None
                    out.append({
                        "source": "cmmlu", "subject": subject, "stage": stage,
                        "qid": _norm_qid("cmmlu", n), "type": "choice",
                        "question": q, "material": "",
                        "choices": choices or None, "answer_letter": ans_letter,
                        "answer_text": choices.get(ans_letter, "") if ans_letter else "",
                        "explanation": "", "difficulty": None, "split": "train", "note": "",
                    })
                    n += 1
    return out


def import_reciter(src: Path) -> list[dict]:
    """Reciter（MIT）：高考古诗文默写题库——137 篇默写篇目 + 472 理解性默写。"""
    out = []
    n = 0
    fp = src / "reciter" / "comprehensions" / "comprehensions.json"
    if fp.exists():
        for item in json.loads(fp.read_text(encoding="utf-8")).get("comprehensions", []):
            content = (item.get("content") or "").strip()
            ans = (item.get("answer") or [])
            if not content or not ans:
                continue
            out.append({
                "source": "reciter", "subject": "语文", "stage": "高中",
                "qid": _norm_qid("reciter", n), "type": "fill",
                "question": content, "material": "",
                "choices": None, "answer_letter": None,
                "answer_text": "；".join(ans), "explanation": "",
                "difficulty": None, "split": "train",
                "note": f"{item.get('title')}（{item.get('source','')}）",
            })
            n += 1
    fp = src / "reciter" / "normal" / "poems.json"
    if fp.exists():
        def _flatten(chunk):
            # content 可能嵌套 list（诗句分组），递归展平为句子文本
            if isinstance(chunk, str):
                return chunk
            parts = []
            for c in chunk:
                s = _flatten(c)
                if s:
                    parts.append(s)
            return "，".join(parts)
        for item in json.loads(fp.read_text(encoding="utf-8")).get("poems", []):
            lines = [_flatten(chunk) for chunk in item.get("content", [])]
            text = "。".join(x for x in lines if x)
            if not text:
                continue
            out.append({
                "source": "reciter", "subject": "语文", "stage": "高中",
                "qid": _norm_qid("reciter", n), "type": "open",
                "question": f"{item.get('title')}（默写篇目）", "material": "",
                "choices": None, "answer_letter": None,
                "answer_text": text, "explanation": "",
                "difficulty": None, "split": "train",
                "note": f"{item.get('tag','')} 高考默写范围",
            })
            n += 1
    return out


def import_ceval(src: Path) -> list[dict]:
    """C-Eval（CC BY-NC-SA 4.0）：各学段知识测试 CSV（dev/val 带答案；test 答案保密不入训）。

    只取文科 12 科；dev/val 全部入 train（模型发布许可已对齐 CC BY-NC-SA）。
    """
    SUBJ_CN = {
        "art_studies": "艺术", "chinese_language_and_literature": "中国语言文学",
        "education_science": "教育科学", "high_school_chinese": "高中语文",
        "high_school_geography": "高中地理", "high_school_history": "高中历史",
        "high_school_politics": "高中政治", "law": "法学",
        "middle_school_geography": "初中地理", "middle_school_history": "初中历史",
        "middle_school_politics": "初中政治", "modern_chinese_history": "中国近现代史",
    }
    out = []
    n = 0
    d = src / "ceval"
    if not d.exists():
        return out
    for split_dir, suffix in (("dev", "dev"), ("val", "val")):
        for fp in sorted((d / split_dir).glob("*.csv")):
            stem = fp.stem.removesuffix(f"_{suffix}")
            subject = SUBJ_CN.get(stem)
            if subject is None:
                continue  # 只取文科科目
            stage = "初中" if stem.startswith("middle_school") else ("高中" if stem.startswith("high_school") else "其他")
            with fp.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    q = (row.get("question") or "").strip()
                    if not q:
                        continue
                    choices = {k: (row.get(k) or "").strip() for k in "ABCD" if (row.get(k) or "").strip()}
                    ans_letter = (row.get("answer") or "").strip() or None
                    out.append({
                        "source": "ceval", "subject": subject, "stage": stage,
                        "qid": _norm_qid("ceval", n), "type": "choice",
                        "question": q, "material": "",
                        "choices": choices or None, "answer_letter": ans_letter,
                        "answer_text": choices.get(ans_letter, "") if ans_letter else "",
                        "explanation": (row.get("explanation") or "").strip(),
                        "difficulty": None, "split": "train", "note": "C-Eval（CC BY-NC-SA 4.0）",
                    })
                    n += 1
    return out


ADAPTERS = {
    "m3ke": import_m3ke,
    "internlm-history": import_internlm_history,
    "gaokao-bench": import_gaokao_bench,
    "agieval": import_agieval,
    "cmmlu": import_cmmlu,
    "reciter": import_reciter,
    "ceval": import_ceval,
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
