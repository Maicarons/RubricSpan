//! 打标产物交换类型 —— 对应 `contracts/labeling-schema.json`。
//!
//! 训练侧（Python）产出的标注结果如需经后端交换/查看，使用本类型。

use serde::{Deserialize, Serialize};

/// 一条样本的完整打标结果。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct LabelingOutput {
    pub question_id: String,
    pub student_answer: String,
    pub point_labels: Vec<PointLabel>,
}

/// 命中类型（技术方案 §4.2 / §7.3）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HitType {
    /// 原文精确命中。
    Exact,
    /// 语义等价命中（同义表述，如"百日维新"→"戊戌变法"）。
    Semantic,
    /// 未命中。
    Miss,
}

/// 单个得分点的标注。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PointLabel {
    pub point_id: i64,
    pub hit: bool,
    pub hit_type: HitType,
    /// 命中片段：从学生答案逐字复制；未命中时为空字符串。
    #[serde(default)]
    pub extracted_span: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub confidence: Option<f64>,
    /// semantic 命中时的给分比例（如 0.5）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub partial_credit: Option<f64>,
}
