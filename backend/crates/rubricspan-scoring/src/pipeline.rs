//! 评分流水线（技术方案 §12）：多候选抽取 → 置信度判定 → 相似度兜底 → 加权汇总。

use crate::backend::InferenceBackend;
use crate::option_rules;
use crate::result::{HitStatus, PointDetail, ScoreOutcome, ScoreSource};
use crate::{rating, ScoringSettings};
use rubricspan_core::scoring::{ScoringConfig, ScoringPoint, Thresholds};

/// 抽取片段最大合理长度（字符数），超长视为异常抽取。
const MAX_SPAN_CHARS: usize = 64;

/// 展示用跨度裁剪：去除首尾的空白与中英文标点，仅用于 `extracted_span` 展示，
/// 不影响命中判定（命中由 `has_answer_prob` 与阈值决定）。
/// 若裁剪后为空（如原片段本身就是标点），则保留原值以免丢失信息。
fn trim_display_span(span: &str) -> String {
    let trimmed = span.trim_matches(|c: char| {
        c.is_whitespace()
            || matches!(
                c,
                ',' | '.' | ';'
                    | ':'
                    | '!'
                    | '?'
                    | '('
                    | ')'
                    | '['
                    | ']'
                    | '{'
                    | '}'
                    | '"'
                    | '\''
                    | '，'
                    | '。'
                    | '；'
                    | '：'
                    | '！'
                    | '？'
                    | '（'
                    | '）'
                    | '「'
                    | '」'
                    | '『'
                    | '』'
                    | '“'
                    | '”'
                    | '‘'
                    | '’'
                    | '、'
                    | '·'
            )
    });
    if trimmed.is_empty() {
        span.to_string()
    } else {
        trimmed.to_string()
    }
}

/// 将学生答案中已由 MRC 给分的字符闭区间替换为空格（防止后续得分点重复给分）。
/// 用空格而非删除：保持相邻词的分词边界，避免掩码后文本粘连产生新词。
fn mask_credited(answer: &str, credited: &[(usize, usize)]) -> String {
    if credited.is_empty() || answer.is_empty() {
        return answer.to_string();
    }
    let n = answer.chars().count();
    let mut chars: Vec<char> = answer.chars().collect();
    for &(start, end) in credited {
        let lo = start.min(n.saturating_sub(1));
        let hi = end.min(n.saturating_sub(1));
        for c in &mut chars[lo..=hi.max(lo)] {
            *c = ' ';
        }
    }
    chars.into_iter().collect()
}

/// 对一份学生答案执行完整评分（使用默认评分参数）。
///
/// 返回逐点明细与总分；`ocr_confidence` 在答卷来源为图片时传入。
/// 等价于 [`score_answer_configured`] 以 [`ScoringSettings::default`] 调用。
pub fn score_answer(
    config: &ScoringConfig,
    student_answer: &str,
    backend: &dyn InferenceBackend,
    ocr_confidence: Option<f64>,
) -> anyhow::Result<ScoreOutcome> {
    score_answer_configured(config, student_answer, backend, ocr_confidence, ScoringSettings::default())
}

/// 与 [`score_answer`] 语义一致，但相似度阈值与部分命中给分比例来自运行时
/// [`ScoringSettings`]（管理后台可调）；题级配置的 `thresholds` 优先覆盖前两者。
///
/// 防重复给分：评分分两阶段——先逐点跑选项规则与 MRC 抽取，命中片段（字符闭区间）
/// 即时从学生答案中**掩码**；全部 MRC 结束后，再对未命中的点统一做相似度兜底，
/// 且兜底输入是掩掉**所有**已认领片段后的文本——同一段话不会先给 A 点加分、
/// 再抬升 B 点的相似度。掩码按精确片段而非整句，同一句里分属不同得分点的
/// 独立内容不受影响。
pub fn score_answer_configured(
    config: &ScoringConfig,
    student_answer: &str,
    backend: &dyn InferenceBackend,
    ocr_confidence: Option<f64>,
    settings: ScoringSettings,
) -> anyhow::Result<ScoreOutcome> {
    let thresholds = config.thresholds.unwrap_or(Thresholds {
        similarity_high: settings.similarity_high,
        similarity_low: settings.similarity_low,
    });
    let mut total = 0.0;
    let mut details: Vec<Option<PointDetail>> = vec![None; config.points.len()];

    // ---- 第 1 阶段：逐点选项规则 + MRC 抽取，命中片段即时掩码 ----
    // 已由 MRC 给分的字符闭区间（在掩码文本中的位置）
    let mut mrc_credited: Vec<(usize, usize)> = Vec::new();
    for (idx, point) in config.points.iter().enumerate() {
        let masked = mask_credited(student_answer, &mrc_credited);
        if let Some(detail) = score_point_mrc(point, &masked, settings.mrc_confidence_threshold, backend)? {
            if detail.hit_status == HitStatus::HitExact && detail.source == ScoreSource::Mrc {
                if let Some(span) = detail.extracted_span.as_deref() {
                    if !span.is_empty() {
                        if let Some(byte) = masked.find(span) {
                            let start = masked[..byte].chars().count();
                            let end = start + span.chars().count().saturating_sub(1);
                            mrc_credited.push((start, end));
                        }
                    }
                }
            }
            total += detail.point_score;
            details[idx] = Some(detail);
        }
    }

    // ---- 第 2 阶段：相似度兜底统一放在全部 MRC 之后——输入为掩掉所有已认领
    // 片段后的文本，任何点认领的内容都不会再抬升其他点的相似度。----
    let final_masked = mask_credited(student_answer, &mrc_credited);
    for (idx, point) in config.points.iter().enumerate() {
        if details[idx].is_some() {
            continue;
        }
        let detail =
            score_point_similarity(point, &final_masked, &thresholds, settings.partial_credit, backend)?;
        total += detail.point_score;
        details[idx] = Some(detail);
    }
    let details = details.into_iter().map(Option::unwrap).collect::<Vec<_>>();

    let max_score = config.total_score;
    Ok(ScoreOutcome {
        question_id: config.question_id.clone(),
        total_score: total,
        max_score,
        rating: rating(total, max_score),
        point_details: details,
        ocr_confidence,
    })
}

/// 单个得分点第 1 阶段：选项型规则判定 → MRC 多候选抽取；未命中返回 `None`，
/// 留给第 2 阶段的相似度兜底。`mrc_threshold` 为 has_answer 置信度判定阈值
/// （管理后台 `mrc_confidence_threshold` 可调）。
fn score_point_mrc(
    point: &ScoringPoint,
    student_answer: &str,
    mrc_threshold: f64,
    backend: &dyn InferenceBackend,
) -> anyhow::Result<Option<PointDetail>> {
    // ---- 第 0 步：选择型得分点规则化判定（M8）----
    // "选B得3分"类点由选项字母规则直接判定，避免 MRC 的"抽字母"高置信误判；
    // 规则未命中时**跳过 MRC**（选项字母识别不是抽取任务，回退会让 MRC 随意
    // 抽片段产生高置信误判），只保留相似度兜底保守接住"变体表述"。
    let option_point = option_rules::is_option_point(point);
    if let Some(expected) = &option_point {
        if let Some(detail) = option_rules::score_option_point(point, student_answer, expected) {
            return Ok(Some(detail));
        }
        return Ok(None);
    }

    // ---- MRC 多候选抽取（标准表述 + aliases，任一命中即命中）----
    // 偏移量契约：MrcOutput 的 start/end 为字符级（char）闭区间偏移，
    // 与训练侧对齐后处理（contracts/labeling-schema.json 的 extracted_span）保持一致。
    let chars: Vec<char> = student_answer.chars().collect();
    let mut best: Option<(f64, usize, usize, String, String)> = None; // (prob, start, end, candidate, span)
    // M8 性能：候选批量推理（同一 context 一次 batch；实现方不支持时默认逐条等价）
    let cand_vec: Vec<String> = std::iter::once(point.point_text.clone())
        .chain(point.aliases.clone())
        .collect();
    let outs = backend.mrc_extract_batch(&cand_vec, student_answer)?;
    for (out, candidate) in outs.into_iter().zip(cand_vec.iter()) {
        let span_len = out.end.saturating_sub(out.start).saturating_add(1);
        let span_ok = out.start <= out.end && out.end < chars.len() && span_len <= MAX_SPAN_CHARS;
        if out.has_answer_prob >= mrc_threshold && span_ok {
            let is_better = best.as_ref().map(|(p, _, _, _, _)| out.has_answer_prob > *p).unwrap_or(true);
            if is_better {
                let raw_span: String = chars[out.start..=out.end].iter().collect();
                let span = trim_display_span(&raw_span);
                best = Some((out.has_answer_prob, out.start, out.end, candidate.clone(), span));
            }
        }
    }

    if let Some((prob, _start, _end, candidate, span)) = best {
        return Ok(Some(PointDetail {
            point_id: point.point_id,
            hit_status: HitStatus::HitExact,
            matched_alias: Some(candidate),
            extracted_span: Some(span),
            confidence: Some(prob),
            similarity: None,
            point_score: point.weight,
            source: ScoreSource::Mrc,
        }));
    }
    Ok(None)
}

/// 单个得分点第 2 阶段：相似度兜底（得分点整句 vs 掩码后答案全文的余弦，无片段证据）。
fn score_point_similarity(
    point: &ScoringPoint,
    student_answer: &str,
    thresholds: &rubricspan_core::scoring::Thresholds,
    partial_credit: f64,
    backend: &dyn InferenceBackend,
) -> anyhow::Result<PointDetail> {
    let sim = backend.similarity(&point.point_text, student_answer)?;
    let (status, score) = if sim.cosine >= thresholds.similarity_high {
        (HitStatus::HitSemantic, point.weight)
    } else if sim.cosine >= thresholds.similarity_low {
        (HitStatus::Partial, point.weight * partial_credit)
    } else {
        (HitStatus::Miss, 0.0)
    };

    Ok(PointDetail {
        point_id: point.point_id,
        hit_status: status,
        matched_alias: None,
        extracted_span: None,
        confidence: None,
        similarity: Some(sim.cosine),
        point_score: score,
        source: ScoreSource::Similarity,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::{MrcOutput, SimilarityOutput};
    use crate::result::Rating;
    use rubricspan_core::scoring::Thresholds;

    /// 测试用假后端：学生答案包含"百日维新"时命中候选，相似度固定 0.9。
    struct FakeBackend;

    impl InferenceBackend for FakeBackend {
        fn mrc_extract(&self, candidate: &str, student_answer: &str) -> anyhow::Result<MrcOutput> {
            if let Some(byte_pos) = student_answer.find(candidate) {
                // 字节偏移 → 字符偏移（与评分引擎的字符级偏移契约一致）
                let start = student_answer[..byte_pos].chars().count();
                let end = start + candidate.chars().count() - 1;
                Ok(MrcOutput { has_answer_prob: 0.97, start, end })
            } else {
                Ok(MrcOutput { has_answer_prob: 0.1, start: 0, end: 0 })
            }
        }

        fn similarity(&self, _point_text: &str, _student_answer: &str) -> anyhow::Result<SimilarityOutput> {
            Ok(SimilarityOutput { cosine: 0.9 })
        }
    }

    /// 记录相似度输入文本的后端：仅当候选包含 `mrc_target` 时 MRC 命中，
    /// 相似度固定 0.5（低于低阈值，用于断言"掩码后文本"而非判定结果）。
    struct RecordingBackend {
        sim_inputs: std::sync::Mutex<Vec<String>>,
        mrc_target: &'static str,
    }

    impl InferenceBackend for RecordingBackend {
        fn mrc_extract(&self, candidate: &str, student_answer: &str) -> anyhow::Result<MrcOutput> {
            if candidate.contains(self.mrc_target) {
                if let Some(byte_pos) = student_answer.find(self.mrc_target) {
                    let start = student_answer[..byte_pos].chars().count();
                    let end = start + self.mrc_target.chars().count() - 1;
                    return Ok(MrcOutput { has_answer_prob: 0.97, start, end });
                }
            }
            Ok(MrcOutput { has_answer_prob: 0.1, start: 0, end: 0 })
        }

        fn similarity(&self, _point_text: &str, student_answer: &str) -> anyhow::Result<SimilarityOutput> {
            self.sim_inputs.lock().unwrap().push(student_answer.to_string());
            Ok(SimilarityOutput { cosine: 0.5 })
        }
    }

    /// 已由 MRC 给分的片段，不得再参与后续得分点的相似度兜底（防重复给分）。
    #[test]
    fn masks_mrc_credited_span_before_later_points() {
        let backend = RecordingBackend {
            sim_inputs: std::sync::Mutex::new(Vec::new()),
            mrc_target: "AB",
        };
        let config = ScoringConfig {
            question_id: "Q002".into(),
            total_score: 2.0,
            subject: None,
            points: vec![
                ScoringPoint { point_id: 1, point_text: "AB目标".into(), weight: 1.0, aliases: vec![] },
                ScoringPoint { point_id: 2, point_text: "PQ目标".into(), weight: 1.0, aliases: vec![] },
            ],
            thresholds: None,
            meta: None,
        };
        let outcome = score_answer(&config, "ABXYZ", &backend, None).unwrap();
        let inputs = backend.sim_inputs.lock().unwrap();
        assert_eq!(outcome.point_details[0].hit_status, HitStatus::HitExact);
        assert_eq!(outcome.point_details[0].extracted_span.as_deref(), Some("AB"));
        // 后续点的相似度输入中，"AB" 已掩码为空格
        assert_eq!(inputs.len(), 1);
        assert_eq!(inputs[0], "  XYZ");
    }

    #[test]
    fn alias_hit_via_mrc() {
        let config = ScoringConfig {
            question_id: "Q001".into(),
            total_score: 2.0,
            subject: None,
            points: vec![ScoringPoint {
                point_id: 1,
                point_text: "戊戌变法".into(),
                weight: 2.0,
                aliases: vec!["百日维新".into()],
            }],
            thresholds: Some(Thresholds::default()),
            meta: None,
        };
        // 学生用了别名"百日维新"——应通过多候选抽取命中
        let outcome = score_answer(&config, "这场改革就是百日维新", &FakeBackend, None).unwrap();
        let d = &outcome.point_details[0];
        assert_eq!(d.hit_status, HitStatus::HitExact);
        assert_eq!(d.matched_alias.as_deref(), Some("百日维新"));
        assert_eq!(d.extracted_span.as_deref(), Some("百日维新"));
        assert_eq!(outcome.total_score, 2.0);
        assert_eq!(outcome.rating, Rating::Excellent);
    }

    #[test]
    fn trim_display_span_strips_punctuation() {
        assert_eq!(trim_display_span("发生在1898年，"), "发生在1898年");
        assert_eq!(trim_display_span("。又称百日维新。"), "又称百日维新");
        assert_eq!(trim_display_span("  （戊戌变法）  "), "戊戌变法");
        // 纯标点裁剪后为空，保留原值以免丢失信息
        assert_eq!(trim_display_span("，。"), "，。");
    }

    #[test]
    fn semantic_fallback_when_mrc_misses() {
        let config = ScoringConfig {
            question_id: "Q001".into(),
            total_score: 2.0,
            subject: None,
            points: vec![ScoringPoint {
                point_id: 1,
                point_text: "促进了思想启蒙".into(),
                weight: 2.0,
                aliases: vec![],
            }],
            thresholds: Some(Thresholds::default()),
            meta: None,
        };
        // MRC 必然未命中 → 相似度 0.9 ≥ 0.90 → 语义命中满分
        let outcome = score_answer(&config, "推动了当时的思想解放潮流", &FakeBackend, None).unwrap();
        let d = &outcome.point_details[0];
        assert_eq!(d.hit_status, HitStatus::HitSemantic);
        assert_eq!(d.source, ScoreSource::Similarity);
        assert_eq!(d.point_score, 2.0);
    }

    #[test]
    fn option_point_rule_hits_letter() {
        // 选择型得分点：学生答案清单含期望字母 → 规则命中（不经 MRC）
        let config = ScoringConfig {
            question_id: "SAS-CHN-137".into(),
            total_score: 6.0,
            subject: None,
            points: vec![
                ScoringPoint {
                    point_id: 1,
                    point_text: "选B得3分".into(),
                    weight: 3.0,
                    aliases: vec!["B项正确".into()],
                },
                ScoringPoint {
                    point_id: 2,
                    point_text: "选A得1分".into(),
                    weight: 1.0,
                    aliases: Vec::new(),
                },
                ScoringPoint {
                    point_id: 3,
                    point_text: "表达了乐观自勉之情".into(),
                    weight: 2.0,
                    aliases: Vec::new(),
                },
            ],
            thresholds: Some(Thresholds::default()),
            meta: None,
        };
        let outcome = score_answer(&config, "1）B\n（2）诗人虽有感叹，却依旧自勉乐观", &FakeBackend, None).unwrap();
        assert_eq!(outcome.point_details[0].hit_status, HitStatus::HitExact);
        assert_eq!(outcome.point_details[0].source, ScoreSource::Option);
        assert_eq!(outcome.point_details[0].extracted_span.as_deref(), Some("B"));
        assert_eq!(outcome.point_details[0].point_score, 3.0);
        // 未出现的期望字母 → 回退 MRC/相似度（FakeBackend 相似度 0.9 ≥ 0.90 → 语义满分）
        assert_eq!(outcome.point_details[1].source, ScoreSource::Similarity);
        assert_eq!(outcome.point_details[1].hit_status, HitStatus::HitSemantic);
        assert_eq!(outcome.total_score, 3.0 + 1.0 + 2.0);
    }

    #[test]
    fn option_point_discussion_only_falls_back() {
        // 讲解式讨论（A不对，应选B）只使 B 命中；未提及字母的点回退语义兜底
        let config = ScoringConfig {
            question_id: "Q001".into(),
            total_score: 3.0,
            subject: None,
            points: vec![
                ScoringPoint {
                    point_id: 1,
                    point_text: "选A得1分".into(),
                    weight: 1.0,
                    aliases: vec![],
                },
                ScoringPoint {
                    point_id: 2,
                    point_text: "选B得2分".into(),
                    weight: 2.0,
                    aliases: vec![],
                },
            ],
            thresholds: Some(Thresholds::default()),
            meta: None,
        };
        let outcome = score_answer(&config, "A不对，应选B", &FakeBackend, None).unwrap();
        assert_eq!(outcome.point_details[0].source, ScoreSource::Similarity); // A 未命中 → 兜底
        assert_eq!(outcome.point_details[1].source, ScoreSource::Option); // B 命中
        assert_eq!(outcome.point_details[1].extracted_span.as_deref(), Some("B"));
    }
}
