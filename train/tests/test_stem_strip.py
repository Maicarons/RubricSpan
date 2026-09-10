"""stem_strip 与 Rust `preprocess.rs` 测试用例同源对拍。

改 Rust 版时同步改这里（反之亦然）；两套用例逐条对应。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubricspan_train.training.stem_strip import strip_stem_spans  # noqa: E402

POEM_STEM = (
    "阅读下面这首宋词，完成下列各题。 鹊桥仙 陆游 华灯纵博，雕鞍驰射，谁记当年豪举①？"
    "镜湖元自属闲人，又何必君恩赐与③。"
)


def test_strips_quoted_stem_material_despite_footnotes_and_spacing():
    answer = "“镜湖元自属闲人，又何必君恩赐与！”这表达了作者的归隐之意。"
    out = strip_stem_spans(answer, [POEM_STEM])
    assert "镜湖元自属闲人" not in out, f"题干诗句应被剥离：{out}"
    assert "归隐之意" in out, f"作答内容必须保留：{out}"


def test_strips_whole_stem_prefix_with_formatting_noise():
    stem = "20.在下面一段文字横线处补恰当的语句，使整段文字语意完整连贯。研究发现，人们所受压力会增加血液中糖皮质激素的含量。"
    answer = "20．在下面一段文字横线处补恰当的语句，使整段文字语意完整连贯。研究发现，人们所受压力会增加血液中糖皮质激素的含量。 答：压力与糖皮质激素有关。"
    out = strip_stem_spans(answer, [stem])
    assert "答：压力与糖皮质激素有关" in out, f"作答内容必须保留：{out}"
    assert "研究发现" not in out, f"题干语句应被剥离：{out}"


def test_keeps_short_coincidental_overlap():
    stem = "随着电子商务的快速发展，我国快递业保持高速发展的态势，与此同时，由快递业带来的环境污染问题也日益显现。"
    answer = "环境污染问题不容忽视，应当推广绿色包装。"
    assert strip_stem_spans(answer, [stem]) == answer, "短重合与正常作答不应被改动"


def test_keeps_normal_answer_without_stem_overlap():
    answer = "（1）凯恩斯认为德国应该承担高额赔款，而凡尔赛和约则是要求德国为其所造成的所有损失买单。"
    assert strip_stem_spans(answer, [POEM_STEM]) == answer


def test_empty_inputs_return_unchanged():
    assert strip_stem_spans("", [POEM_STEM]) == ""
    assert strip_stem_spans("任何答案", []) == "任何答案"
    assert strip_stem_spans("任何答案", ["短"]) == "任何答案"


def test_length_is_preserved_by_space_substitution():
    stem = "镜湖元自属闲人，又何必君恩赐与"
    answer = "镜湖元自属闲人，又何必君恩赐与。这表明诗人无意于君恩。"
    out = strip_stem_spans(answer, [stem])
    assert len(out) == len(answer), "空格替代必须保持长度（字符索引稳定）"
    assert "这表明诗人无意于君恩" in out


def test_ascii_fold_parity():
    # ASCII 折叠：字母大小写不敏感，数字/标点忽略
    stem = "A.D. 1911 Revolution of China"
    answer = "AD1911 revolution OF china 起义"
    out = strip_stem_spans(answer, [stem])
    assert "起义" in out
    assert "revolution" not in out
