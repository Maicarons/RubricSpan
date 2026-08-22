//! 评分流水线（技术方案 §12）：多候选抽取 → 置信度判定 → 相似度兜底 → 加权汇总。

use crate::backend::InferenceBackend;
use crate::result::{HitStatus, PointDetail, ScoreOutcome, ScoreSource};
use crate::{effective_thresholds, rating, DEFAULT_PARTIAL_CREDIT};
use rubricspan_core::scoring::{ScoringConfig, ScoringPoint};

/// MRC has_answer 概率判定阈值（可后续移入配置文件）。
const HAS_ANSWER_THRESHOLD: f64 = 0.5;
/// 抽取片段最大合理长度（字符数），超长视为异常抽取。
const MAX_SPAN_CHARS: usize = 64;

/// 对一份学生答案执行完整评分。
///
/// 返回逐点明细与总分；`ocr_confidence` 在答卷来源为图片时传入。
pub fn score_answer(
    config: &ScoringConfig,
    student_answer: &str,
    backend: &dyn InferenceBackend,
    ocr_confidence: Option<f64>,
) -> anyhow::Result<ScoreOutcome> {
    let thresholds = effective_thresholds(config);
    let mut total = 0.0;
    let mut details = Vec::with_capacity(config.points.len());

    for point in &config.points {
        let detail = score_point(point, student_answer, &thresholds, backend)?;
        total += detail.point_score;
        details.push(detail);
    }

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

/// 单个得分点评分：MRC 多候选抽取 → 相似度兜底。
fn score_point(
    point: &ScoringPoint,
    student_answer: &str,
    thresholds: &rubricspan_core::scoring::Thresholds,
    backend: &dyn InferenceBackend,
) -> anyhow::Result<PointDetail> {
    // ---- 第 1 步：MRC 多候选抽取（标准表述 + aliases，任一命中即命中）----
    let candidates = std::iter::once(point.point_text.as_str()).chain(point.aliases.iter().map(String::as_str));

    // 偏移量契约：MrcOutput 的 start/end 为字符级（char）闭区间偏移，
    // 与训练侧对齐后处理（contracts/labeling-schema.json 的 extracted_span）保持一致。
    let chars: Vec<char> = student_answer.chars().collect();

    let mut best: Option<(f64, usize, usize, String, String)> = None; // (prob, start, end, candidate, span)
    for candidate in candidates {
        let out = backend.mrc_extract(candidate, student_answer)?;
        let span_len = out.end.saturating_sub(out.start).saturating_add(1);
        let span_ok = out.start <= out.end && out.end < chars.len() && span_len <= MAX_SPAN_CHARS;
        if out.has_answer_prob >= HAS_ANSWER_THRESHOLD && span_ok {
            let is_better = best.as_ref().map(|(p, _, _, _, _)| out.has_answer_prob > *p).unwrap_or(true);
            if is_better {
                let span: String = chars[out.start..=out.end].iter().collect();
                best = Some((out.has_answer_prob, out.start, out.end, candidate.to_string(), span));
            }
        }
    }

    if let Some((prob, _start, _end, candidate, span)) = best {
        return Ok(PointDetail {
            point_id: point.point_id,
            hit_status: HitStatus::HitExact,
            matched_alias: Some(candidate),
            extracted_span: Some(span),
            confidence: Some(prob),
            similarity: None,
            point_score: point.weight,
            source: ScoreSource::Mrc,
        });
    }

    // ---- 第 2 步：相似度兜底 ----
    let sim = backend.similarity(&point.point_text, student_answer)?;
    let (status, score) = if sim.cosine >= thresholds.similarity_high {
        (HitStatus::HitSemantic, point.weight)
    } else if sim.cosine >= thresholds.similarity_low {
        (HitStatus::Partial, point.weight * DEFAULT_PARTIAL_CREDIT)
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
        // MRC 必然未命中 → 相似度 0.9 ≥ 0.85 → 语义命中满分
        let outcome = score_answer(&config, "推动了当时的思想解放潮流", &FakeBackend, None).unwrap();
        let d = &outcome.point_details[0];
        assert_eq!(d.hit_status, HitStatus::HitSemantic);
        assert_eq!(d.source, ScoreSource::Similarity);
        assert_eq!(d.point_score, 2.0);
    }
}
