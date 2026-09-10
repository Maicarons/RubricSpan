"""外部数据集导入/生成训练数据的单元测试（合成数据驱动）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubricspan_train.data.import_extra import (  # noqa: E402
    import_agieval,
    import_ceval,
    import_cmmlu,
    import_gaokao_bench,
    import_internlm_history,
    import_m3ke,
    import_reciter,
)
from rubricspan_train.data.extra_processed import (  # noqa: E402
    build_mrc_negatives,
    build_similarity_pairs,
)


def _write(tmp: Path, rel: str, rows: list[dict]) -> Path:
    fp = tmp / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return fp


def test_import_m3ke_schema(tmp_path):
    _write(tmp_path, "m3ke/data/dev/History-Arts & Humanities-High school.jsonl", [
        {"id": 0, "question": "戊戌变法的领导阶级是？", "A": "地主阶级", "B": "资产阶级维新派",
         "C": "农民阶级", "D": "无产阶级", "answer": "B"},
    ])
    rows = import_m3ke(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["source"] == "m3ke" and r["subject"] == "History" and r["stage"] == "高中"
    assert r["type"] == "choice" and r["answer_letter"] == "B"
    assert r["answer_text"] == "资产阶级维新派"


def test_import_internlm_history_strips_prefix(tmp_path):
    # 真实文件为 JSON 数组（非 jsonl），整体加载
    fp = tmp_path / "internlm-history" / "datasets" / "2022_junior_middle_history.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps([{
        "conversation": [{
            "input": "请问以下问题属于中学历史学科中的哪一个专题？北京人遗址发现石器……这表明北京人",
            "output": "中国境内人类的活动、早期国家与社会变革。", "system": "sys",
        }],
    }], ensure_ascii=False), encoding="utf-8")
    rows = import_internlm_history(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["source"] == "internlm-history" and r["type"] == "open"
    assert not r["question"].startswith("请问以下问题")
    assert "北京人" in r["question"]


def test_similarity_pairs_m3ke_dev_only(tmp_path):
    dev = {"source": "m3ke", "subject": "History", "stage": "高中", "qid": "m3ke-0",
           "type": "choice", "question": "戊戌变法的领导阶级是？", "material": "",
           "choices": {"A": "地主阶级", "B": "资产阶级维新派", "C": "农民阶级"},
           "answer_letter": "B", "answer_text": "资产阶级维新派", "explanation": "",
           "difficulty": None, "split": "dev", "note": ""}
    test_row = dict(dev, qid="m3ke-1", split="test", answer_letter=None, answer_text="")
    pairs = build_similarity_pairs([dev, test_row])
    pos = [p for p in pairs if p["score"] > 0.5]
    neg = [p for p in pairs if p["score"] <= 0.5]
    assert len(pos) == 1 and pos[0]["sentence2"] == "资产阶级维新派"
    assert len(neg) == 2  # A、C 两个错误选项
    assert all(p["split"] == "val" for p in pairs)  # dev → val


def test_similarity_pairs_history_pos_and_cross_neg(tmp_path):
    rows = [
        {"source": "internlm-history", "subject": "历史", "stage": "初中", "qid": "h-0",
         "type": "open", "question": "北京人遗址……这表明北京人", "material": "",
         "choices": None, "answer_letter": None, "answer_text": "中国境内人类的活动",
         "explanation": "", "difficulty": None, "split": "train", "note": ""},
        {"source": "internlm-history", "subject": "历史", "stage": "初中", "qid": "h-1",
         "type": "open", "question": "商鞅变法内容……", "material": "",
         "choices": None, "answer_letter": None, "answer_text": "早期国家与社会变革",
         "explanation": "", "difficulty": None, "split": "train", "note": ""},
    ]
    pairs = build_similarity_pairs(rows)
    pos = [p for p in pairs if p["score"] > 0.5]
    neg = [p for p in pairs if p["score"] <= 0.5]
    assert len(pos) == 2
    assert len(neg) >= 2  # 跨考点 hard 负例
    # 负例不得把正确考点标成负
    h0 = [p for p in neg if p["question_id"] == "EXT-internlm-history-h-0"]
    assert all(p["sentence2"] != "中国境内人类的活动" for p in h0)


def test_mrc_negatives_guard_label_in_context(tmp_path):
    rows = [
        # 考点名出现在题干中 → 应被守卫跳过（否则是假负例）
        {"source": "internlm-history", "subject": "历史", "stage": "初中", "qid": "h-0",
         "type": "open", "question": "中国境内人类的活动包括北京人遗址……", "material": "",
         "choices": None, "answer_letter": None, "answer_text": "中国境内人类的活动",
         "explanation": "", "difficulty": None, "split": "train", "note": ""},
        # 考点名不在题干中 → 合法负例
        {"source": "internlm-history", "subject": "历史", "stage": "初中", "qid": "h-1",
         "type": "open", "question": "北京人遗址发现近10万件石器……这表明北京人", "material": "",
         "choices": None, "answer_letter": None, "answer_text": "早期国家与社会变革",
         "explanation": "", "difficulty": None, "split": "train", "note": ""},
    ]
    negs = build_mrc_negatives(rows)
    assert len(negs) == 1
    assert negs[0]["is_impossible"] is True
    assert negs[0]["origin"] == "extra-internlm-history"


def test_mrc_negatives_requires_material_or_context(tmp_path):
    # 无材料且 query 过短的题不产生负例
    rows = [{"source": "m3ke", "subject": "History", "stage": "高中", "qid": "m-0",
             "type": "choice", "question": "戊戌变法领导阶级？", "material": "",
             "choices": {"A": "x", "B": "y"}, "answer_letter": "B", "answer_text": "y",
             "explanation": "", "difficulty": None, "split": "dev", "note": ""}]
    assert build_mrc_negatives(rows) == []


def test_import_gaokao_bench_parses_inline_options(tmp_path):
    """GAOKAO-Bench 客观题：内联选项解析 + 主观题答案文本。"""
    obj = tmp_path / "gaokao-bench" / "Data" / "Objective_Questions"
    obj.mkdir(parents=True)
    (obj / "2010-2022_History_MCQs.json").write_text(json.dumps({
        "keywords": "2010-2022_History_MCQs",
        "example": [{
            "year": "2010", "category": "（新课标）",
            "question": "1．（4分）下列简称源自西周封国的是（　　）\nA．河南  B．湖南  C．山东  D．广东",
            "answer": ["C"], "analysis": "鲁晋…", "index": 0, "score": 4,
        }],
    }, ensure_ascii=False), encoding="utf-8")
    subj = tmp_path / "gaokao-bench" / "Data" / "Subjective_Questions"
    subj.mkdir(parents=True)
    (subj / "2010-2022_History_Open-ended_Questions.json").write_text(json.dumps({
        "keywords": "2010-2022_History_Open-ended_Questions",
        "example": [{
            "year": "2011", "category": "（课标）", "question": "材料…问题：分析…",
            "answer": "（1）官营专卖。\n（2）促进盐业发展。", "analysis": "", "index": 0, "score": 20,
        }],
    }, ensure_ascii=False), encoding="utf-8")
    rows = import_gaokao_bench(tmp_path)
    assert len(rows) == 2
    mcq = next(r for r in rows if r["type"] == "choice")
    assert mcq["subject"] == "历史" and mcq["answer_letter"] == "C"
    assert mcq["choices"] == {"A": "河南", "B": "湖南", "C": "山东", "D": "广东"}
    sub = next(r for r in rows if r["type"] == "open")
    assert sub["answer_text"].startswith("（1）官营专卖") and sub["difficulty"] == 20


def test_import_agieval(tmp_path):
    d = tmp_path / "agieval" / "data" / "v1"
    d.mkdir(parents=True)
    (d / "gaokao-history.jsonl").write_text(json.dumps({
        "passage": "材料：分封制…", "question": "下列属于分封对象的是",
        "options": ["(A)功臣", "(B)商人", "(C)农民", "(D)工匠"], "label": "A",
        "answer": None, "other": {"source": "2015年上海历史试卷"},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = import_agieval(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["subject"] == "历史" and r["answer_letter"] == "A"
    assert r["material"].startswith("材料") and r["choices"]["D"] == "工匠"


def test_import_cmmlu(tmp_path):
    d = tmp_path / "cmmlu" / "data" / "dev"
    d.mkdir(parents=True)
    (d / "chinese_history.csv").write_text(
        ",Question,A,B,C,D,Answer\n0,思想家是谁,陆九渊,董仲舒,朱熹,孔子,A\n", encoding="utf-8")
    rows = import_cmmlu(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["subject"] == "中国历史" and r["answer_letter"] == "A"
    assert r["answer_text"] == "陆九渊"


def test_import_reciter_flattens_nested(tmp_path):
    d = tmp_path / "reciter"
    (d / "comprehensions").mkdir(parents=True)
    (d / "normal").mkdir(parents=True)
    (d / "comprehensions" / "comprehensions.json").write_text(json.dumps({
        "$schema": "x", "comprehensions": [{
            "title": "逍遥游", "source": "庄子", "content": "斥鵪腾跃起飞，$0，$1。",
            "answer": ["不过数仞而下", "翱翔蓬蒿之间"],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    (d / "normal" / "poems.json").write_text(json.dumps({
        "$schema": "x", "poems": [{
            "title": "论语", "tag": "2020", "content": [["学而时习之", "不亦说乎"], [["温故而知新", "可以为师矣"]]],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    rows = import_reciter(tmp_path)
    assert len(rows) == 2
    fill = next(r for r in rows if r["type"] == "fill")
    assert fill["answer_text"] == "不过数仞而下；翱翔蓬蒿之间"
    poem = next(r for r in rows if r["type"] == "open")
    assert "学而时习之" in poem["answer_text"] and "温故而知新" in poem["answer_text"]


def test_import_ceval(tmp_path):
    d = tmp_path / "ceval"
    (d / "dev").mkdir(parents=True)
    (d / "val").mkdir(parents=True)
    (d / "test").mkdir(parents=True)
    (d / "dev" / "middle_school_history_dev.csv").write_text(
        "id,question,A,B,C,D,answer,explanation\n"
        "0,《凡尔赛和约》内容包括,①②④,①②③,①③④,②③④,B,1.历史事实…\n",
        encoding="utf-8")
    (d / "val" / "high_school_history_val.csv").write_text(
        "id,question,A,B,C,D,answer\n"
        "0,北宋前期土地政策,自然经济,自耕农受阻,重农抑商瓦解,土地质变,B\n",
        encoding="utf-8")
    (d / "test" / "middle_school_history_test.csv").write_text(
        "id,question,A,B,C,D\n0,保密题,1,2,3,4\n", encoding="utf-8")
    rows = import_ceval(tmp_path)
    assert len(rows) == 2  # dev + val（test 无答案不入）
    hist = next(r for r in rows if r["subject"] == "初中历史")
    assert hist["answer_letter"] == "B" and hist["answer_text"] == "①②③"
    assert all(r["split"] == "train" for r in rows)
