//! 选择型得分点规则化判定（M8 调优）。
//!
//! 背景：评测集中"选B得3分""断句正确项为B"类得分点在 MRC 训练数据里占比虽小，
//! 但标注 span 常为单字母，模型学到"抽字母"捷径，产生 >0.98 高置信误判
//! （SAS-CHN-137 卷 pred 12/12 vs 金标 3/12 即此类）。对该类点改走纯规则判定：
//!
//! - [`is_option_point`]：从得分点文本/别名识别"选择型"并提取期望选项字母集合；
//! - [`answer_selects`]：识别学生答案中"选项式出现"的期望字母（`选B`、`B项`、
//!   `答案B`、`1）B`、`10.B11.A12.A` 清单、独立 `A,D,B` 等），并区分讲解式讨论
//!   （"A不对，应选B"只记 B 为命中）。
//!
//! 未命中时由调用方**回退**到 MRC 多候选 + 相似度兜底（保住变体表述召回）。
//! 本模块不感知模型，纯文本规则；与在线/WASM 两端共享同一评分 crate 自动生效。

use crate::result::{HitStatus, PointDetail, ScoreSource};
use rubricspan_core::scoring::ScoringPoint;

/// 选项字母范围（覆盖单选/多选常见 A–E）。
const OPTION_CHARS: [char; 5] = ['A', 'B', 'C', 'D', 'E'];

/// 判断得分点是否为"选择型"，并返回期望选项字母（去重、保序）。
///
/// 判定启发：point_text / 任一 alias 同时含 [A-E] 字母与选项动词词元
/// （选 / 答案 / 正确项 / 正确选项 / 项）。两者齐备才视为选择型，
/// 避免将普通文本得分点误判。
pub fn is_option_point(point: &ScoringPoint) -> Option<Vec<char>> {
    let mut letters: Vec<char> = Vec::new();
    let texts = std::iter::once(point.point_text.as_str())
        .chain(point.aliases.iter().map(String::as_str));
    for text in texts {
        let has_hint = ["选", "答案", "正确项", "正确选项", "项"]
            .iter()
            .any(|k| text.contains(k));
        if !has_hint {
            continue;
        }
        for c in text.chars() {
            if OPTION_CHARS.contains(&c) && !letters.contains(&c) {
                letters.push(c);
            }
        }
    }
    if letters.is_empty() {
        None
    } else {
        Some(letters)
    }
}

/// 学生答案中某个字母是否为"选项式出现"。
fn option_like_occurrence(chars: &[char], i: usize) -> bool {
    let prev = i.checked_sub(1).and_then(|j| chars.get(j)).copied();
    let next = chars.get(i + 1).copied();

    // 前置选择动词：选/填/答/写（应选B / 选B / 答案为B）
    let verb_before = prev.is_some_and(|c| matches!(c, '选' | '填' | '答' | '写' | '应'));
    // 后置选项名词：X项 / X得?分
    let noun_after = next.is_some_and(|c| matches!(c, '项' | '得'));
    // 独立答案条目：左右为分隔符/行首尾（"1）B"、"A,D,B"），或右接下一题号（"10.B11"）
    let left_delim = prev.is_none_or(is_answer_delim);
    let right_delim = next.is_none_or(is_answer_delim);
    let right_digit = next.is_some_and(|c| c.is_ascii_digit());

    verb_before || noun_after || (left_delim && (right_delim || right_digit))
}

/// 答案文本中的分隔符（空白 / 中英文标点 / 括号）。
fn is_answer_delim(c: char) -> bool {
    c.is_whitespace()
        || matches!(
            c,
            ',' | '.' | ';' | ':' | '!' | '?' | '(' | ')' | '[' | ']' | '{' | '}' | '"' | '\''
                | '，' | '。' | '；' | '：' | '！' | '？' | '、' | '（' | '）' | '【' | '】'
                | '『' | '』' | '「' | '」' | '\u{2014}' | '·' | '\n' | '\r' | '\t'
        )
}

/// 在学生答案中查找期望选项字母的"选项式出现"。
///
/// 返回 (命中的字母, 起止字符下标闭区间)；按期望字母顺序返回首个命中。
pub fn answer_selects(answer: &str, expected: &[char]) -> Option<(char, usize, usize)> {
    let chars: Vec<char> = answer.chars().collect();
    for &letter in expected {
        for (i, &c) in chars.iter().enumerate() {
            if c == letter && option_like_occurrence(&chars, i) {
                return Some((letter, i, i + 1));
            }
        }
    }
    None
}

/// 对选择型得分点执行规则化评分：命中直接给满分；未命中返回 `None` 由调用方回退。
pub fn score_option_point(
    point: &ScoringPoint,
    student_answer: &str,
    expected: &[char],
) -> Option<PointDetail> {
    let (_letter, start, end) = answer_selects(student_answer, expected)?;
    let span: String = student_answer.chars().skip(start).take(end - start).collect();
    Some(PointDetail {
        point_id: point.point_id,
        hit_status: HitStatus::HitExact,
        matched_alias: Some(point.point_text.clone()),
        extracted_span: Some(span),
        confidence: Some(1.0),
        similarity: None,
        point_score: point.weight,
        source: ScoreSource::Option,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pt(text: &str, aliases: &[&str]) -> ScoringPoint {
        ScoringPoint {
            point_id: 1,
            point_text: text.to_string(),
            weight: 2.0,
            aliases: aliases.iter().map(|s| s.to_string()).collect(),
        }
    }

    #[test]
    fn detects_option_points() {
        assert_eq!(is_option_point(&pt("选B得3分", &[])).unwrap(), vec!['B']);
        assert_eq!(
            is_option_point(&pt("选择B、E", &["B项正确", "E项正确"])).unwrap(),
            vec!['B', 'E']
        );
        assert_eq!(
            is_option_point(&pt("断句正确项为B", &[])).unwrap(),
            vec!['B']
        );
        // 普通文本点不误判
        assert!(is_option_point(&pt("表达诗人不甘沉沦的乐观之情", &[])).is_none());
        assert!(is_option_point(&pt("学习西方的制度和文化", &["自上而下的改革"])).is_none());
    }

    #[test]
    fn selects_from_answer_variants() {
        let expected = vec!['B'];
        // 独立条目：1）B、（1）B、行首 B
        assert_eq!(answer_selects("1）B", &expected), Some(('B', 2, 3)));
        assert_eq!(answer_selects("（1）B", &expected), Some(('B', 3, 4)));
        assert_eq!(answer_selects("B", &expected), Some(('B', 0, 1)));
        // 选择动词
        assert_eq!(answer_selects("我选B.", &expected), Some(('B', 2, 3)));
        // 题号清单 10.B11.A12.A
        assert_eq!(answer_selects("10.B11.A12.A", &expected), Some(('B', 3, 4)));
        // 讲解式讨论不命中 A，只命中应选 B
        let ab = vec!['A', 'B'];
        assert_eq!(answer_selects("A不对，应选B", &ab), Some(('B', 6, 7)));
        // 多选题清单
        assert_eq!(answer_selects("A,B,D", &['A', 'B', 'D']), Some(('A', 0, 1)));
    }

    #[test]
    fn option_miss_falls_back() {
        // 未出现任何选项式字母 → 未命中（由调用方 MRC/相似度兜底）
        assert_eq!(answer_selects("大力发展素质教育", &['B']), None);
        assert_eq!(answer_selects("我支持戊戌变法", &['A', 'B', 'C', 'D']), None);
    }

    #[test]
    fn score_option_hit_detail() {
        let p = pt("选D得2分", &[]);
        let d = score_option_point(&p, "答案选D，其余都有道理", &['D']).unwrap();
        assert_eq!(d.hit_status, HitStatus::HitExact);
        assert_eq!(d.source, ScoreSource::Option);
        assert_eq!(d.extracted_span.as_deref(), Some("D"));
        assert_eq!(d.point_score, 2.0);
        assert_eq!(d.confidence, Some(1.0));
    }
}