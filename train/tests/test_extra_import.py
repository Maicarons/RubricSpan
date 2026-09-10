"""外部数据集导入/生成训练数据的单元测试（合成数据驱动）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubricspan_train.data.import_extra import (  # noqa: E402
    import_internlm_history,
    import_m3ke,
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
