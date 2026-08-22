//! rubricspan-scoring —— 混合评分引擎（技术方案 §4 / §5 / §12）。
//!
//! 评分链路（串联兜底）：
//! 1. 对每个得分点，遍历 [标准表述 + aliases]，逐一构造 MRC 输入做多候选抽取；
//! 2. 取最高置信候选，判定精确命中（hit_exact）；
//! 3. MRC 未命中或低置信时，计算"得分点 ↔ 学生答案整体"余弦相似度：
//!    - ≥ 高阈值 → 语义命中（hit_semantic，满分）
//!    - 介于高低阈值之间 → 部分命中（partial，按比例给分）
//!    - < 低阈值 → 未命中（miss，0 分）
//! 4. 加权汇总各得分点得分，映射评级。
//!
//! 本 crate 只编排评分逻辑；模型推理通过 [`InferenceBackend`] trait 注入，
//! 由 `rubricspan-inference` 提供具体实现，便于测试与离线替换。

use rubricspan_core::scoring::{ScoringConfig, Thresholds};

pub mod backend;
pub mod pipeline;
pub mod result;

pub use backend::{InferenceBackend, MrcOutput, SimilarityOutput};
pub use pipeline::score_answer;
pub use result::{HitStatus, PointDetail, ScoreOutcome, ScoreSource};

/// 全局默认阈值（题级配置可覆盖，见 contracts/model-artifacts.md）。
pub const DEFAULT_THRESHOLDS: Thresholds = Thresholds {
    similarity_high: 0.85,
    similarity_low: 0.60,
};

/// 默认部分命中给分比例（半分）。
pub const DEFAULT_PARTIAL_CREDIT: f64 = 0.5;

/// 解析题目生效阈值：题级配置优先，缺省回落到全局默认。
pub fn effective_thresholds(config: &ScoringConfig) -> Thresholds {
    config.thresholds.unwrap_or(DEFAULT_THRESHOLDS)
}

/// 评级：按得分率映射（优秀/良好/及格/不及格）。
pub fn rating(score: f64, max_score: f64) -> result::Rating {
    if max_score <= 0.0 {
        return result::Rating::Fail;
    }
    let ratio = score / max_score;
    if ratio >= 0.9 {
        result::Rating::Excellent
    } else if ratio >= 0.75 {
        result::Rating::Good
    } else if ratio >= 0.6 {
        result::Rating::Pass
    } else {
        result::Rating::Fail
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rating_boundaries() {
        assert_eq!(rating(9.0, 10.0), result::Rating::Excellent);
        assert_eq!(rating(7.5, 10.0), result::Rating::Good);
        assert_eq!(rating(6.0, 10.0), result::Rating::Pass);
        assert_eq!(rating(5.9, 10.0), result::Rating::Fail);
    }
}
