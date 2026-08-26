//! rubricspan-wasm —— 浏览器离线评分入口（技术方案 §10.2 · 方案 B，M6）。
//!
//! 将 [`rubricspan_scoring`] 的混合评分核心（MRC 多候选抽取 → 置信度判定 →
//! 相似度兜底 → 加权汇总）编译为 WASM，供前端在**无网络环境**下本地评分，
//! 与在线端共用同一套评分配置 JSON 与结果结构，保证结果可比。
//!
//! ## 为什么是"预计算推理表"而不是回调桥
//!
//! 模型张量计算留在 JS 侧（onnxruntime-web + 分词器），但 WASM 导入函数只能
//! 同步返回，而浏览器推理是异步的；因此由 JS 先行完成全部推理，把结果按
//! 契约组织成 JSON 一次性传入，本模块内的 [`BrowserBridge`] 只做查表。
//! 评分编排逻辑仍完整运行在本 crate 中，与在线端逐分支一致。
//!
//! ## 推理表契约（`inference_json`）
//!
//! ```json
//! {
//!   "mrc":        { "<候选表述>": {"has_answer_prob": 0.97, "start": 3, "end": 6} },
//!   "similarity": { "<得分点文本>": {"cosine": 0.91} }
//! }
//! ```
//!
//! - `mrc` 以候选文本（标准表述或某个 alias）为键，须覆盖所有得分点的全部候选；
//! - `similarity` 以得分点文本为键；
//! - `start` / `end` 为学生答案内的**字符级（Unicode 标量）闭区间**偏移，
//!   与在线端契约一致；
//! - 任一形如 `{ "__error": "..." }` 的值表示 JS 侧该项推理失败，查到即报错。

use std::collections::HashMap;

use wasm_bindgen::prelude::*;

use rubricspan_scoring::backend::{MrcOutput, SimilarityOutput};
use rubricspan_scoring::InferenceBackend;

/// 解析单个 MRC 条目；`__error` 键表示 JS 侧推理失败。
fn parse_mrc(v: &serde_json::Value) -> anyhow::Result<MrcOutput> {
    if let Some(err) = v.get("__error").and_then(|e| e.as_str()) {
        anyhow::bail!("浏览器 MRC 推理失败：{err}");
    }
    let prob = v
        .get("has_answer_prob")
        .and_then(|x| x.as_f64())
        .ok_or_else(|| anyhow::anyhow!("MRC 条目缺少 has_answer_prob 字段"))?;
    let start = v
        .get("start")
        .and_then(|x| x.as_u64())
        .ok_or_else(|| anyhow::anyhow!("MRC 条目缺少 start 字段"))? as usize;
    let end = v
        .get("end")
        .and_then(|x| x.as_u64())
        .ok_or_else(|| anyhow::anyhow!("MRC 条目缺少 end 字段"))? as usize;
    Ok(MrcOutput { has_answer_prob: prob, start, end })
}

/// 解析单个相似度条目；`__error` 键表示 JS 侧推理失败。
fn parse_similarity(v: &serde_json::Value) -> anyhow::Result<SimilarityOutput> {
    if let Some(err) = v.get("__error").and_then(|e| e.as_str()) {
        anyhow::bail!("浏览器相似度推理失败：{err}");
    }
    let cosine = v
        .get("cosine")
        .and_then(|x| x.as_f64())
        .ok_or_else(|| anyhow::anyhow!("相似度条目缺少 cosine 字段"))?;
    Ok(SimilarityOutput { cosine })
}

/// 预计算推理表：JS 侧先行完成的全部分类推理结果。
#[derive(Debug)]
struct PrecomputedInference {
    mrc: HashMap<String, MrcOutput>,
    similarity: HashMap<String, SimilarityOutput>,
}

/// 解析整张推理表。
fn parse_inference(json: &str) -> anyhow::Result<PrecomputedInference> {
    let root: serde_json::Value = serde_json::from_str(json)
        .map_err(|e| anyhow::anyhow!("推理表不是合法 JSON：{e}"))?;
    let mut mrc = HashMap::new();
    if let Some(entries) = root.get("mrc").and_then(|x| x.as_object()) {
        for (key, val) in entries {
            mrc.insert(key.clone(), parse_mrc(val)?);
        }
    }
    let mut similarity = HashMap::new();
    if let Some(entries) = root.get("similarity").and_then(|x| x.as_object()) {
        for (key, val) in entries {
            similarity.insert(key.clone(), parse_similarity(val)?);
        }
    }
    Ok(PrecomputedInference { mrc, similarity })
}

/// 浏览器推理后端：从预计算表中按在线端相同的入参键查结果。
struct BrowserBridge {
    pre: PrecomputedInference,
}

impl InferenceBackend for BrowserBridge {
    fn mrc_extract(&self, candidate: &str, _student_answer: &str) -> anyhow::Result<MrcOutput> {
        self.pre
            .mrc
            .get(candidate)
            .copied()
            .ok_or_else(|| anyhow::anyhow!("推理表缺少候选「{candidate}」的 MRC 结果"))
    }

    fn similarity(
        &self,
        point_text: &str,
        _student_answer: &str,
    ) -> anyhow::Result<SimilarityOutput> {
        self.pre
            .similarity
            .get(point_text)
            .copied()
            .ok_or_else(|| anyhow::anyhow!("推理表缺少得分点「{point_text}」的相似度结果"))
    }
}

/// 对一份学生答案执行完整离线评分。
///
/// - `config_json`：评分配置（contracts/scoring-config Schema，与在线端完全一致）
/// - `student_answer`：学生答案文本（或图片 OCR 后的文本）
/// - `inference_json`：JS 侧预计算的模型推理结果表（见模块文档契约）
///
/// 返回 `ScoreOutcome` 的 JSON 序列化（结构与在线端 `/api/score` 响应一致）。
#[wasm_bindgen(js_name = scoreAnswer)]
pub fn score_answer(
    config_json: &str,
    student_answer: &str,
    inference_json: &str,
) -> Result<String, JsValue> {
    let config: rubricspan_core::scoring::ScoringConfig = serde_json::from_str(config_json)
        .map_err(|e| JsValue::from_str(&format!("评分配置解析失败：{e}")))?;
    let pre = parse_inference(inference_json).map_err(|e| JsValue::from_str(&e.to_string()))?;
    let outcome = rubricspan_scoring::score_answer(&config, student_answer, &BrowserBridge { pre }, None)
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    serde_json::to_string(&outcome).map_err(|e| JsValue::from_str(&e.to_string()))
}

/// 构建信息：前端可用于自检 WASM 模块加载成功。
#[wasm_bindgen(js_name = version)]
pub fn version() -> String {
    format!("rubricspan-wasm {}", env!("CARGO_PKG_VERSION"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_mrc_ok() {
        let v: serde_json::Value =
            serde_json::from_str(r#"{"has_answer_prob":0.97,"start":2,"end":5}"#).unwrap();
        let out = parse_mrc(&v).unwrap();
        assert_eq!(out.has_answer_prob, 0.97);
        assert_eq!(out.start, 2);
        assert_eq!(out.end, 5);
    }

    #[test]
    fn parse_mrc_bridge_error() {
        let v: serde_json::Value = serde_json::from_str(r#"{"__error":"session 失败"}"#).unwrap();
        let err = parse_mrc(&v).unwrap_err();
        assert!(err.to_string().contains("浏览器 MRC 推理失败"));
    }

    #[test]
    fn parse_mrc_missing_field() {
        let v: serde_json::Value = serde_json::from_str(r#"{"start":1,"end":2}"#).unwrap();
        assert!(parse_mrc(&v).is_err());
    }

    #[test]
    fn parse_similarity_ok() {
        let v: serde_json::Value = serde_json::from_str(r#"{"cosine":0.9123}"#).unwrap();
        let out = parse_similarity(&v).unwrap();
        assert!((out.cosine - 0.9123).abs() < 1e-9);
    }

    #[test]
    fn parse_inference_full_table() {
        let table = parse_inference(
            r#"{
              "mrc": {"百日维新": {"has_answer_prob": 0.99, "start": 0, "end": 3}},
              "similarity": {"戊戌变法": {"cosine": 0.42}}
            }"#,
        )
        .unwrap();
        assert_eq!(table.mrc.len(), 1);
        assert_eq!(table.similarity.len(), 1);
    }

    #[test]
    fn parse_inference_propagates_entry_error() {
        let err = parse_inference(r#"{"mrc": {"百日维新": {"__error": "OOM"}}}"#).unwrap_err();
        assert!(err.to_string().contains("浏览器 MRC 推理失败"));
    }

    #[test]
    fn bridge_lookup_miss_is_error() {
        let pre = parse_inference(r#"{"mrc": {}, "similarity": {}}"#).unwrap();
        let bridge = BrowserBridge { pre };
        assert!(bridge.mrc_extract("不存在", "答案").is_err());
        assert!(bridge.similarity("不存在", "答案").is_err());
    }
}
