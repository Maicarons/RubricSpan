//! rubricspan-core —— 领域模型与契约类型。
//!
//! 本模块的序列化结构必须与 `contracts/` 下的契约保持一致：
//! - [`scoring`] 对应 `contracts/scoring-config.schema.json`
//! - [`labeling`] 对应 `contracts/labeling-schema.json`（打标产物交换格式）
//! - [`ocr`] 对应 `contracts/ocr-output.schema.json`
//!
//! 契约变更须先走 `docs/CHANGELOG-contracts.md` 流程，再同步本模块。

pub mod labeling;
pub mod ocr;
pub mod scoring;

/// API 统一错误响应体（对应 openapi.yaml 的 Error schema）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ApiError {
    pub code: String,
    pub message: String,
}

impl ApiError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
