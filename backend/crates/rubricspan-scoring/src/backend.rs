//! 推理后端抽象：评分引擎通过本 trait 调用模型，不直接依赖具体推理实现。
//!
//! 在线模式由 `rubricspan-inference`（ONNX Runtime / Candle，GPU）实现；
//! 单元测试与 WASM 离线模式可注入各自的实现。
//!
//! **偏移量契约**：[`MrcOutput`] 的 `start` / `end` 一律为**字符级（char，非字节）**
//! 闭区间偏移，与训练侧对齐后处理（`contracts/labeling-schema.json`）保持一致；
//! 实现方须将模型输出的 token 位置映射为字符偏移后再返回。

/// MRC 单次抽取输出（一次 [得分点候选 × 学生答案] 的推理结果）。
#[derive(Debug, Clone, Copy)]
pub struct MrcOutput {
    /// "是否含答案"的概率（0–1）。
    pub has_answer_prob: f64,
    /// 抽取片段在学生答案中的字符级起始位置（闭区间，无答案时无意义）。
    pub start: usize,
    /// 抽取片段在学生答案中的字符级结束位置（闭区间）。
    pub end: usize,
}

/// 相似度推理输出。
#[derive(Debug, Clone, Copy)]
pub struct SimilarityOutput {
    /// "得分点文本 ↔ 学生答案整体"的余弦相似度（-1–1，通常 0–1）。
    pub cosine: f64,
}

/// 推理后端：由调用方注入实现。
pub trait InferenceBackend: Send + Sync {
    /// 对单个候选表述执行 MRC 抽取。
    ///
    /// - `candidate`：得分点的某个候选表述（标准表述或某个 alias）
    /// - `student_answer`：学生答案全文
    fn mrc_extract(&self, candidate: &str, student_answer: &str) -> anyhow::Result<MrcOutput>;

    /// 批量 MRC 抽取：同一学生答案上的多个候选。
    ///
    /// 默认实现逐条调用 [`mrc_extract`](Self::mrc_extract)，语义等价；
    /// 支持批量的实现可覆盖以复用同 context 的一次批量编码/推理（M8 性能优化）。
    fn mrc_extract_batch(
        &self,
        candidates: &[String],
        student_answer: &str,
    ) -> anyhow::Result<Vec<MrcOutput>> {
        candidates
            .iter()
            .map(|c| self.mrc_extract(c, student_answer))
            .collect()
    }

    /// 计算得分点文本与学生答案整体的余弦相似度。
    fn similarity(&self, point_text: &str, student_answer: &str)
        -> anyhow::Result<SimilarityOutput>;

    /// 批量相似度：同一学生答案对多个得分点文本。
    ///
    /// 默认实现逐条调用 [`similarity`](Self::similarity)，语义等价；
    /// 支持批量的实现可覆盖——学生答案只编码一次、得分点文本合批一次推理。
    /// 数值一致性依据：余弦基于 attention-mask 加权的均值池化，padding 不改变
    /// 真实位置的向量，批内按各自 mask 池化与逐条编码严格一致。
    fn similarity_batch(
        &self,
        point_texts: &[String],
        student_answer: &str,
    ) -> anyhow::Result<Vec<SimilarityOutput>> {
        point_texts
            .iter()
            .map(|p| self.similarity(p, student_answer))
            .collect()
    }
}
