//! rubricspan-inference —— 推理引擎（技术方案 §10.1 · 方案 A，M8 起全 Rust 原生）。
//!
//! 架构：Rust 后端拥有 HTTP API、评分编排、存储**与模型推理**——ONNX Runtime
//! Rust 绑定（`ort`）加载训练侧导出的 ONNX 模型，HuggingFace `tokenizers`
//! 官方 Rust 实现加载 tokenizer.json 完成分词与偏移映射。Python 仅保留在
//! 训练侧（train/），在线服务不再依赖任何 Python 进程。
//!
//! 本 crate 提供：
//! - [`OrtBackend`]：实现 `rubricspan_scoring::InferenceBackend`（MRC 抽取 / 相似度）；
//! - [`LlmClient`]：标准答案结构化解析的 OpenAI 兼容客户端（多端点 fallback）；
//! - [`DummyBackend`]：占位（无模型目录时兜底；不得用于生产评分）。
//!
//! 与训练↔推理一致性保障：分词器直接消费训练侧导出的同一份 tokenizer.json，
//! 数值对拍基准见 data/goldens/inference_golden.json（对拍工具 parity_check bin）。

mod llm;
mod ort_backend;

use anyhow::Result;
use rubricspan_scoring::backend::{InferenceBackend, MrcOutput, SimilarityOutput};

pub use llm::{EndpointSpec, LlmClient};
pub use ort_backend::{MrcDetail, OrtBackend, Precision};

/// 占位推理后端（无模型环境下的编译与联调用；始终返回"无答案 + 低相似度"）。
///
/// ⚠️ 不得用于生产评分。
#[derive(Debug, Default, Clone, Copy)]
pub struct DummyBackend;

impl InferenceBackend for DummyBackend {
    fn mrc_extract(&self, _candidate: &str, _student_answer: &str) -> Result<MrcOutput> {
        Ok(MrcOutput { has_answer_prob: 0.0, start: 0, end: 0 })
    }
    fn similarity(&self, _point_text: &str, _student_answer: &str) -> Result<SimilarityOutput> {
        Ok(SimilarityOutput { cosine: 0.0 })
    }
}
