//! 评分结果类型 —— 对应 openapi.yaml 的 PointDetail / ScoreResult。

use serde::{Deserialize, Serialize};

/// 得分点命中状态。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HitStatus {
    /// 精确命中（MRC 抽取成功）。
    HitExact,
    /// 语义命中（相似度 ≥ 高阈值）。
    HitSemantic,
    /// 部分命中（相似度介于高低阈值之间）。
    Partial,
    /// 未命中。
    Miss,
}

/// 本点得分来源路径。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreSource {
    /// 来自 MRC 多候选抽取。
    Mrc,
    /// 来自语义相似度兜底。
    Similarity,
    /// 来自选择型得分点选项规则判定（M8 新增，纯文本规则）。
    Option,
}

/// 单个得分点的评分明细。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PointDetail {
    pub point_id: i64,
    pub hit_status: HitStatus,
    /// 命中的候选表述（标准表述或某个 alias）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub matched_alias: Option<String>,
    /// 学生答案中命中的原文片段（逐字复制）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub extracted_span: Option<String>,
    /// MRC 抽取置信度（hit_exact 时给出）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub confidence: Option<f64>,
    /// 余弦相似度（相似度兜底时给出）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub similarity: Option<f64>,
    /// 本点实际得分。
    pub point_score: f64,
    /// 本点得分来源路径。
    pub source: ScoreSource,
}

/// 评级。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Rating {
    Excellent,
    Good,
    Pass,
    Fail,
}

/// 一份答卷的完整评分结果。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ScoreOutcome {
    pub question_id: String,
    pub total_score: f64,
    pub max_score: f64,
    pub rating: Rating,
    pub point_details: Vec<PointDetail>,
    /// 若答卷来源为图片，附带 OCR 整体置信度。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ocr_confidence: Option<f64>,
}
