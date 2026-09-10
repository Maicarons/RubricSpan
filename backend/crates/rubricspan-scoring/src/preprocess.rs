//! 题干剥离（部署建议：答案文本进入评分前必须剥离题干，见论文讨论章）。
//!
//! 动机：学生答卷（尤其 OCR 与采集拼接来源）常原样携带题干材料——诗句、
//! 材料引文、题干语句。得分点表述往往就出自这些材料，逐点抽取的"忠于原文"
//! 会变成"忠于题干"，在专家判零分的答卷上产生高置信误报。系统级评测中
//! 零分答卷平均被给了 63.6% 卷面分，其主要根源即此。
//!
//! 做法：在归一化（忽略空白、标点、注释上标与数字）意义下，把答案文本中
//! 出自题干的长片段（≥ [`MIN_MATCH_CHARS`] 字）替换为空格。替换为空格而非
//! 删除，与管线内 `mask_credited` 的字符索引语义保持一致。短于阈值的偶然
//! 重合（常见短语、术语）不受影响，正常作答不会被误伤。

/// 归一化后视为"出自题干"的最小片段长度（字符数）。
/// 低于该值的重合视为偶然（常见短语/术语），不剥离。
const MIN_MATCH_CHARS: usize = 8;

/// 匹配时忽略的字符：空白、中英文标点、数字（多为序号）、注释上标（①…⑳）。
/// 数字全忽略可能让"2015 年"与"2016 年"在匹配中不可区分，
/// 但题干/答卷中的数字几乎只出现在序号与年份语境，权衡下仍忽略。
fn is_ignorable(c: char) -> bool {
    c.is_whitespace()
        || c.is_ascii_punctuation()
        || c.is_ascii_digit()
        || matches!(c,
            '，' | '。' | '；' | '：' | '、' | '！' | '？' | '（' | '）' | '【' | '】'
            | '《' | '》' | '「' | '」' | '『' | '』' | '“' | '”' | '‘' | '’' | '…'
            | '—' | '·' | '～' | '．' | '﹒' | '＊' | '＃' | '＋' | '－' | '／' | '＝'
            | '０'..='９' | '①'..='⑳' | '⑴'..='⑽' | '㈠'..='㈩')
}

/// 匹配折叠：拉丁字母转小写，其余不变。
fn fold(c: char) -> char {
    c.to_ascii_lowercase()
}

/// 归一化：删去 [`is_ignorable`] 字符并折叠大小写，返回用于匹配的字符串。
fn normalize(text: &str) -> String {
    text.chars().filter(|c| !is_ignorable(*c)).map(fold).collect()
}

/// 从答案文本中剥离与任一题干文本重合的长片段（空格替代，长度不变）。
///
/// `stems` 为该题的题干文本（可含材料段；多题干来源时全部传入）。
/// 算法：对答案的归一化序列逐位置二分最长匹配——若归一化答案的
/// `norm[i..j]` 出现在某题干中，则更短的 `norm[i..j']`（j' < j）必然也出现，
/// 匹配长度对 j 单调，可安全二分。
pub fn strip_stem_spans(answer: &str, stems: &[&str]) -> String {
    if answer.is_empty() || stems.is_empty() {
        return answer.to_string();
    }
    // 归一化保留字符在原串中的字节偏移
    let kept: Vec<usize> = answer
        .char_indices()
        .filter(|(_, c)| !is_ignorable(*c))
        .map(|(i, _)| i)
        .collect();
    if kept.len() < MIN_MATCH_CHARS {
        return answer.to_string();
    }
    let norm: Vec<char> = kept.iter().map(|&i| fold(answer[i..].chars().next().unwrap())).collect();
    let stem_norms: Vec<String> = stems
        .iter()
        .map(|s| normalize(s))
        .filter(|s| s.chars().count() >= MIN_MATCH_CHARS)
        .collect();
    if stem_norms.is_empty() {
        return answer.to_string();
    }

    let contains_stem = |pat: &str| stem_norms.iter().any(|s| s.contains(pat));
    let mut marked = vec![false; answer.len()];
    let n = norm.len();
    let mut i = 0usize;
    while i < n {
        let mut best = 0usize;
        if n - i >= MIN_MATCH_CHARS {
            // 二分最长匹配长度：lo 恒可行（MIN_MATCH_CHARS-1 视为不匹配基准），
            // hi 上界为剩余长度。
            let mut lo = MIN_MATCH_CHARS - 1;
            let mut hi = n - i;
            while lo < hi {
                let mid = (lo + hi).div_ceil(2);
                let pat: String = norm[i..i + mid].iter().collect();
                if contains_stem(&pat) {
                    lo = mid;
                } else {
                    hi = mid - 1;
                }
            }
            if lo >= MIN_MATCH_CHARS {
                best = lo;
            }
        }
        if best > 0 {
            for k in &kept[i..i + best] {
                marked[*k] = true;
            }
            i += best;
        } else {
            i += 1;
        }
    }
    if marked.iter().all(|&m| !m) {
        return answer.to_string();
    }
    let mut out = String::with_capacity(answer.len());
    for (off, c) in answer.char_indices() {
        if marked[off] {
            out.push(' ');
        } else {
            out.push(c);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const POEM_STEM: &str = "阅读下面这首宋词，完成下列各题。 鹊桥仙 陆游 华灯纵博，雕鞍驰射，谁记当年豪举①？\
                             镜湖元自属闲人，又何必君恩赐与③。";

    #[test]
    fn strips_quoted_stem_material_despite_footnotes_and_spacing() {
        // 答卷引用题干中的词句：注释上标③与换行差异不应阻碍剥离。
        let answer = "“镜湖元自属闲人，又何必君恩赐与！”这表达了作者的归隐之意。";
        let out = strip_stem_spans(answer, &[POEM_STEM]);
        assert!(!out.contains("镜湖元自属闲人"), "题干诗句应被剥离：{out}");
        assert!(out.contains("归隐之意"), "作答内容必须保留：{out}");
    }

    #[test]
    fn strips_whole_stem_prefix_with_formatting_noise() {
        let stem = "20.在下面一段文字横线处补恰当的语句，使整段文字语意完整连贯。研究发现，人们所受压力会增加血液中糖皮质激素的含量。";
        // 答卷把题干整段抄在最前（含格式噪声：全角空格、序号改写）
        let answer = "20．在下面一段文字横线处补恰当的语句，使整段文字语意完整连贯。研究发现，人们所受压力会增加血液中糖皮质激素的含量。 答：压力与糖皮质激素有关。";
        let out = strip_stem_spans(answer, &[stem]);
        assert!(out.contains("答：压力与糖皮质激素有关"), "作答内容必须保留：{out}");
        assert!(!out.contains("研究发现"), "题干语句应被剥离：{out}");
    }

    #[test]
    fn keeps_short_coincidental_overlap() {
        // 与题干的最长归一化重合“环境污染问题”仅 6 字，低于阈值，不得剥离
        let stem = "随着电子商务的快速发展，我国快递业保持高速发展的态势，与此同时，由快递业带来的环境污染问题也日益显现。";
        let answer = "环境污染问题不容忽视，应当推广绿色包装。";
        let out = strip_stem_spans(answer, &[stem]);
        assert_eq!(out, answer, "短重合与正常作答不应被改动");
    }

    #[test]
    fn keeps_normal_answer_without_stem_overlap() {
        let answer = "（1）凯恩斯认为德国应该承担高额赔款，而凡尔赛和约则是要求德国为其所造成的所有损失买单。";
        let out = strip_stem_spans(answer, &[POEM_STEM]);
        assert_eq!(out, answer);
    }

    #[test]
    fn empty_inputs_return_unchanged() {
        assert_eq!(strip_stem_spans("", &[POEM_STEM]), "");
        assert_eq!(strip_stem_spans("任何答案", &[]), "任何答案");
        assert_eq!(strip_stem_spans("任何答案", &["短"]), "任何答案");
    }

    #[test]
    fn length_is_preserved_by_space_substitution() {
        let stem = "镜湖元自属闲人，又何必君恩赐与";
        let answer = "镜湖元自属闲人，又何必君恩赐与。这表明诗人无意于君恩。";
        let out = strip_stem_spans(answer, &[stem]);
        assert_eq!(out.chars().count(), answer.chars().count());
        assert!(out.contains("这表明诗人无意于君恩"));
    }
}
