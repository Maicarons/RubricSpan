//! OCR 输出契约类型 —— 对应 `contracts/ocr-output.schema.json`。

use serde::{Deserialize, Serialize};

/// RapidOCR 作答区识别结果。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct OcrResult {
    pub question_id: String,
    /// 按阅读顺序拼接的完整作答文本。
    pub answer_text: String,
    /// 整体识别置信度（0–1）。
    pub confidence: f64,
    #[serde(default)]
    pub lines: Vec<OcrLine>,
    /// 整体是否含识别存疑片段。
    #[serde(default)]
    pub low_confidence: bool,
}

/// 单行识别结果。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct OcrLine {
    pub text: String,
    /// 检测框坐标：四个顶点，每顶点 [x, y]。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub r#box: Option<Vec<[f64; 2]>>,
    /// 单行识别置信度（0–1）。
    pub score: f64,
    /// 该行是否识别存疑（供前端高亮提示人工核对）。
    #[serde(default)]
    pub low_confidence: bool,
}
