//! rubricspan-ocr —— 试卷作答文本识别（技术方案 §8）。
//!
//! 处理链路：
//! 图像预处理（灰度/归一/去噪）→ DB 文本检测 → 作答区过滤（坐标模板/题号软切分）
//! → CRNN 识别 → 按阅读顺序拼接 → 输出 [`rubricspan_core::ocr::OcrResult`]。
//!
//! 当前为占位骨架，M3 阶段实现（ONNX Runtime Rust 绑定或本地 RapidOCR 服务二选一）。

use rubricspan_core::ocr::OcrResult;

/// OCR 引擎错误。
#[derive(Debug, thiserror::Error)]
pub enum OcrError {
    #[error("OCR 模型缺失：{0}")]
    ModelMissing(String),
    #[error("图像无法解析：{0}")]
    InvalidImage(String),
    #[error("识别失败：{0}")]
    Recognition(String),
}

/// 作答区坐标模板（题号 → 作答区区域）。
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct AnswerRegionTemplate {
    pub template_id: String,
    /// 各题作答区区域：(题号, [x1, y1, x2, y2])。
    pub regions: Vec<(String, [f64; 4])>,
}

/// 低置信判定阈值：单行置信度低于该值标记为"识别存疑"。
pub const LOW_CONFIDENCE_THRESHOLD: f64 = 0.80;

/// 识别一张试卷图片，输出作答区文本。
///
/// ⚠️ 占位实现：M3 接入 RapidOCR 后替换。
pub fn recognize(
    question_id: &str,
    _image_bytes: &[u8],
    _template: Option<&AnswerRegionTemplate>,
) -> Result<OcrResult, OcrError> {
    // TODO(M3): 预处理 → 检测 → 作答区过滤 → 识别 → 拼接
    Ok(OcrResult {
        question_id: question_id.to_string(),
        answer_text: String::new(),
        confidence: 0.0,
        lines: Vec::new(),
        low_confidence: true,
    })
}
