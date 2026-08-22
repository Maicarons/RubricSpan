//! rubricspan-inference —— 推理引擎（技术方案 §10.1）。
//!
//! 职责：
//! - 加载 `models/` 目录下的 ONNX 模型（MRC / 相似度），校验 `model_card.json` 中的 sha256；
//! - 实现 [`rubricspan_scoring::InferenceBackend`] trait，供评分引擎调用；
//! - GPU 路径（RTX 4060 CUDA）优先，CPU/INT8 路径兜底。
//!
//! 当前为占位骨架：`DummyBackend` 仅用于编译与测试，
//! M4 阶段接入 ONNX Runtime（或 Candle）后替换。

use rubricspan_scoring::backend::{InferenceBackend, MrcOutput, SimilarityOutput};

/// 模型产物根目录下的布局描述（对应 contracts/model-artifacts.md）。
#[derive(Debug, Clone)]
pub struct ModelPaths {
    pub mrc_dir: std::path::PathBuf,
    pub similarity_dir: std::path::PathBuf,
}

/// 推理引擎错误。
#[derive(Debug, thiserror::Error)]
pub enum InferenceError {
    #[error("模型文件缺失：{0}")]
    ModelMissing(String),
    #[error("sha256 校验失败：{0}")]
    ChecksumMismatch(String),
    #[error("推理失败：{0}")]
    Runtime(String),
}

/// 占位推理后端（M4 前的编译与联调用；始终返回"无答案 + 低相似度"）。
///
/// ⚠️ 不得用于生产评分。M4 接入真实模型后删除或移入测试模块。
#[derive(Debug, Default, Clone, Copy)]
pub struct DummyBackend;

impl InferenceBackend for DummyBackend {
    fn mrc_extract(&self, _candidate: &str, _student_answer: &str) -> anyhow::Result<MrcOutput> {
        Ok(MrcOutput {
            has_answer_prob: 0.0,
            start: 0,
            end: 0,
        })
    }

    fn similarity(
        &self,
        _point_text: &str,
        _student_answer: &str,
    ) -> anyhow::Result<SimilarityOutput> {
        Ok(SimilarityOutput { cosine: 0.0 })
    }
}

/// 构建真实推理后端（M4 实现）。
///
/// 实现步骤：
/// 1. 读取 `ModelPaths` 下 model.onnx + model_card.json，校验 sha256；
/// 2. 初始化 ONNX Runtime 会话（CUDA ExecutionProvider 优先）；
/// 3. 加载分词器，实现 [CLS] 得分点 [SEP] 学生答案 [SEP] 的输入构造；
/// 4. 输出 start/end logits → 字符级位置映射（与训练侧对齐策略一致）。
pub fn build_backend(_paths: &ModelPaths) -> Result<impl InferenceBackend, InferenceError> {
    // TODO(M4): 替换为真实实现
    Ok(DummyBackend)
}
