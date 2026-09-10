//! rubricspan-scoring —— 混合评分引擎（技术方案 §4 / §5 / §12）。
//!
//! 评分链路（串联兜底）：
//! 1. 对每个得分点，遍历 [标准表述 + aliases] 合批做 MRC 抽取（同答案一次批量推理）；
//! 2. 取最高置信候选，判定精确命中（hit_exact）；
//! 3. MRC 未命中或低置信时，计算"得分点 ↔ 学生答案整体"余弦相似度：
//!    - ≥ 高阈值 → 语义命中（hit_semantic，满分）
//!    - 介于高低阈值之间 → 部分命中（partial，按比例给分）
//!    - < 低阈值 → 未命中（miss，0 分）
//!
//!    相似度阈值与部分命中比例是运行时参数（[`ScoringSettings`]，管理后台可调）。
//! 4. 加权汇总各得分点得分，映射评级。
//!
//! 本 crate 只编排评分逻辑；模型推理通过 [`InferenceBackend`] trait 注入，
//! 由 `rubricspan-inference` 提供具体实现，便于测试与离线替换。

use rubricspan_core::scoring::{ScoringConfig, Thresholds};
use serde::{Deserialize, Serialize};

pub mod backend;
pub mod option_rules;
pub mod pipeline;
pub mod preprocess;
pub mod result;

pub use backend::{InferenceBackend, MrcOutput, SimilarityOutput};
pub use pipeline::{score_answer, score_answer_configured};
pub use preprocess::strip_stem_spans;
pub use result::{HitStatus, PointDetail, ScoreOutcome, ScoreSource};

/// 全局默认阈值（题级配置可覆盖，见 contracts/model-artifacts.md）。
///
/// 默认从严（部署建议：偏松证据下先压误报，再观察召回损失）：
/// τ_hi = 0.95、τ_lo = 0.90；管理后台与题级配置可调，但出厂默认取保守档。
pub const DEFAULT_THRESHOLDS: Thresholds = Thresholds {
    similarity_high: 0.95,
    similarity_low: 0.90,
};

/// 默认部分命中给分比例（相似度虚高收紧后为四分之一分）。
pub const DEFAULT_PARTIAL_CREDIT: f64 = 0.25;

/// 默认 MRC `has_answer` 判定阈值：抽取置信度 ≥ 该值才判精确命中（hit_exact），
/// 低于则回落相似度兜底。默认从严取 0.8（与部署基线一致）。
pub const DEFAULT_MRC_CONFIDENCE_THRESHOLD: f64 = 0.8;

/// serde 缺省补齐：老版本 `scoring_settings.json` 无此字段时回落默认，其余字段不受影响。
const fn default_mrc_confidence_threshold() -> f64 {
    DEFAULT_MRC_CONFIDENCE_THRESHOLD
}

/// 运行时评分参数（管理后台可调，持久化于 `<store_path>/scoring_settings.json`）。
///
/// - `similarity_high / similarity_low`：语义命中 / 部分命中的相似度判定阈值；
///   题级配置的 `thresholds` 优先覆盖；
/// - `partial_credit`：部分命中给分比例（`weight × 比例`）；
/// - `mrc_confidence_threshold`：MRC 抽取置信度判定阈值（≥ 判精确命中）。
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ScoringSettings {
    pub similarity_high: f64,
    pub similarity_low: f64,
    pub partial_credit: f64,
    #[serde(default = "default_mrc_confidence_threshold")]
    pub mrc_confidence_threshold: f64,
}

impl Default for ScoringSettings {
    fn default() -> Self {
        Self {
            similarity_high: DEFAULT_THRESHOLDS.similarity_high,
            similarity_low: DEFAULT_THRESHOLDS.similarity_low,
            partial_credit: DEFAULT_PARTIAL_CREDIT,
            mrc_confidence_threshold: DEFAULT_MRC_CONFIDENCE_THRESHOLD,
        }
    }
}

impl ScoringSettings {
    /// 从 JSON 文件加载；文件缺失或解析失败时回落默认值并告警。
    pub fn load_from(path: &std::path::Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(s) => match serde_json::from_str::<ScoringSettings>(&s) {
                Ok(v) => v,
                Err(e) => {
                    tracing::warn!(path = %path.display(), error = %e, "评分参数文件解析失败，使用默认值");
                    Self::default()
                }
            },
            Err(_) => Self::default(),
        }
    }

    /// 保存到 JSON 文件。
    pub fn save_to(&self, path: &std::path::Path) -> anyhow::Result<()> {
        let s = serde_json::to_string_pretty(self)?;
        std::fs::write(path, s)?;
        Ok(())
    }

    /// 校验取值范围：`0 < similarity_low < similarity_high <= 1`，`0 <= partial_credit <= 1`，
    /// `0 <= mrc_confidence_threshold <= 1`。
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.similarity_high > self.similarity_low
                && self.similarity_low > 0.0
                && self.similarity_high <= 1.0
                && (0.0..=1.0).contains(&self.partial_credit)
                && (0.0..=1.0).contains(&self.mrc_confidence_threshold),
            "评分参数非法：需满足 0 < similarity_low < similarity_high ≤ 1，且 0 ≤ partial_credit ≤ 1、0 ≤ mrc_confidence_threshold ≤ 1"
        );
        Ok(())
    }
}

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
