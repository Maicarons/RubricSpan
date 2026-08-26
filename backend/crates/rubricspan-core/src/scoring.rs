//! 评分配置领域类型 —— 对应 `contracts/scoring-config.schema.json`。

use serde::{Deserialize, Serialize};

/// 题目级评分配置（落盘于 data/scoring_configs/{question_id}.json）。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ScoringConfig {
    pub question_id: String,
    pub total_score: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub subject: Option<String>,
    pub points: Vec<ScoringPoint>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub thresholds: Option<Thresholds>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub meta: Option<ConfigMeta>,
}

/// 单个得分点。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ScoringPoint {
    pub point_id: i64,
    /// 得分点标准表述（用于 MRC 抽取与相似度计算）。
    pub point_text: String,
    /// 本得分点满分值。
    pub weight: f64,
    /// 等价表述列表（供 MRC 多候选抽取 + 相似度语义匹配）。
    #[serde(default)]
    pub aliases: Vec<String>,
}

/// 本题相似度阈值（缺省用全局默认 0.90 / 0.75；全局默认可在管理后台调整）。
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct Thresholds {
    #[serde(default = "Thresholds::default_high")]
    pub similarity_high: f64,
    #[serde(default = "Thresholds::default_low")]
    pub similarity_low: f64,
}

impl Thresholds {
    fn default_high() -> f64 {
        0.90
    }
    fn default_low() -> f64 {
        0.75
    }
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            similarity_high: Self::default_high(),
            similarity_low: Self::default_low(),
        }
    }
}

/// 解析元信息。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ConfigMeta {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parsed_by: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parsed_at: Option<String>,
    /// 教师确认标记；未确认的配置不得用于正式评分。
    #[serde(default)]
    pub confirmed_by_teacher: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 契约示例（技术方案 §6.4）必须能正确反序列化。
    #[test]
    fn deserialize_contract_example() {
        let json = r#"{
            "question_id": "Q001",
            "total_score": 5,
            "subject": "历史",
            "points": [
                {"point_id": 1, "point_text": "发生在1898年", "weight": 1, "aliases": ["1898年", "一八九八年"]},
                {"point_id": 2, "point_text": "又称百日维新", "weight": 1, "aliases": ["百日维新", "戊戌维新"]}
            ],
            "thresholds": {"similarity_high": 0.90, "similarity_low": 0.75}
        }"#;
        let cfg: ScoringConfig = serde_json::from_str(json).expect("契约示例应可解析");
        assert_eq!(cfg.points.len(), 2);
        assert_eq!(cfg.points[0].aliases.len(), 2);
    }
}
