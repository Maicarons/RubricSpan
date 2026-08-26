//! 标准答案结构化解析 —— OpenAI 兼容端点的 Rust 直连客户端（M8 起）。
//!
//! 端点发现、fallback 顺序、重试/退避与 max_tokens 自适应等约定与训练侧
//! `train/rubricspan_train/labeling/client.py` 保持一致：
//! - `.env` 按 `LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL[,NAME]}` 配置多端点，
//!   n 升序即优先级；无编号端点时回落 `OPENAI_BASE_URL / OPENAI_API_KEY / LABELING_MODEL`；
//! - 每次调用从队首开始；单端点重试耗尽切下一个，全部失败才报错；
//! - 截断（finish_reason=length）或空 content 时按 2 倍递增 max_tokens 重试；
//! - 严格 JSON：剥 markdown 栅栏 + 平衡花括号扫描后解析。

use std::path::Path;
use std::time::Duration;

use anyhow::{anyhow, bail, Result};
use rand::Rng;
use serde_json::{json, Value};

/// 与 Python `_PARSE_PROMPT` 完全一致（保证解析行为不变）。
const PARSE_PROMPT: &str = r#"你是一位中学文科主观题阅卷专家。下面给出一道题的题干与自然语言标准答案原文，
请将其解析为结构化评分配置 JSON。

要求：
1. 将标准答案拆解为若干"得分点"，每个得分点用一句精炼的标准表述（point_text）；
2. 为每个得分点给出 1~3 个等价表述（aliases，如同义短语、别称），用于相似度匹配；
3. 为每个得分点分配满分值 weight，所有 weight 之和须等于 total_score；
4. 仅输出一个严格 JSON 对象，字段如下，不要任何解释与代码栅栏：
{{
  "question_id": "{qid}",
  "total_score": <数字>,
  "subject": "<学科，如 历史/地理/政治>",
  "points": [
    {{"point_id": 1, "point_text": "<标准表述>", "weight": <数字>, "aliases": ["<等价表述>"]}}
  ],
  "thresholds": {{"similarity_high": 0.85, "similarity_low": 0.60}}
}}

题干：
{question}

标准答案原文：
{answer}
"#;

#[derive(Debug, Clone)]
pub struct EndpointSpec {
    pub name: String,
    pub base_url: String,
    pub api_key: String,
    pub model: String,
}

/// LLM 解析客户端：多端点 fallback 队列（线程安全）。
pub struct LlmClient {
    endpoints: Vec<EndpointSpec>,
    http: reqwest::Client,
}

impl LlmClient {
    /// 从 .env 文件加载端点队列；无任何可用端点时仍返回实例，
    /// 调用时再报错（便于"未配置也能启动服务"）。
    pub fn from_env_file(path: &Path) -> Self {
        let env = read_env_file(path);
        let endpoints = parse_endpoints(&env);
        tracing::info!(count = endpoints.len(), file = %path.display(), "LLM 端点队列");
        for ep in &endpoints {
            tracing::info!(endpoint = %ep.name, model = %ep.model, "LLM 端点就绪");
        }
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(120))
            .build()
            .expect("reqwest client 构建失败");
        Self { endpoints, http }
    }

    /// 是否配置了至少一个端点。
    pub fn is_configured(&self) -> bool {
        !self.endpoints.is_empty()
    }

    /// 端点摘要（名称 + 模型名；**不含 base_url / api_key**），供管理后台只读展示。
    pub fn endpoints_summary(&self) -> Vec<(String, String)> {
        self.endpoints.iter().map(|e| (e.name.clone(), e.model.clone())).collect()
    }

    /// 单轮 JSON 对话：遍历端点 fallback，每端点最多 `MAX_ATTEMPTS` 次退避重试。
    pub async fn chat_json(&self, user_content: &str, temperature: f64) -> Result<(Value, String)> {
        if self.endpoints.is_empty() {
            bail!("未配置 LLM 端点：请在仓库根目录 .env 中配置 LLM_ENDPOINT_<n>_* 变量组");
        }
        const MAX_ATTEMPTS: usize = 4;
        const MAX_TOKENS_INITIAL: u64 = 3072;
        const MAX_TOKENS_MAX: u64 = 8192;

        let mut last_err = String::new();
        for ep in &self.endpoints {
            let mut limit = MAX_TOKENS_INITIAL;
            for attempt in 0..MAX_ATTEMPTS {
                match self
                    .chat_once(ep, user_content, temperature, limit)
                    .await
                {
                    Ok(text) => match extract_json(&text) {
                        Ok(v) => return Ok((v, format!("{}/{}", ep.name, ep.model))),
                        Err(e) => {
                            // 解析失败大概率是截断所致：同样放大预算后退避重试
                            last_err = format!("JSON 提取失败：{e}");
                            if limit < MAX_TOKENS_MAX {
                                limit = (limit * 2).min(MAX_TOKENS_MAX);
                            }
                            sleep_backoff(attempt).await;
                        }
                    },
                    Err(e) => {
                        last_err = e;
                        if limit < MAX_TOKENS_MAX {
                            limit = (limit * 2).min(MAX_TOKENS_MAX);
                        }
                        sleep_backoff(attempt).await;
                    }
                }
            }
            tracing::warn!(endpoint = %ep.name, "端点重试耗尽，切换下一端点");
        }
        bail!("全部 LLM 端点调用失败：{last_err}");
    }

    /// 解析标准答案为评分配置 JSON（补齐 question_id / thresholds 缺省）。
    pub async fn parse_standard_answer(
        &self,
        question_id: &str,
        raw_answer_text: &str,
        question: &str,
    ) -> Result<Value> {
        let prompt = PARSE_PROMPT
            .replace("{qid}", question_id)
            .replace("{question}", if question.is_empty() { "(未提供题干)" } else { question })
            .replace("{answer}", raw_answer_text);
        let (mut cfg, source) = self.chat_json(&prompt, 0.2).await?;
        if !cfg.is_object() {
            bail!("模型输出不是 JSON 对象");
        }
        if cfg.get("question_id").map(Value::is_null).unwrap_or(true) {
            cfg["question_id"] = json!(question_id);
        }
        if cfg.get("thresholds").map(Value::is_null).unwrap_or(true) {
            cfg["thresholds"] = json!({"similarity_high": 0.85, "similarity_low": 0.60});
        }
        tracing::info!(source = %source, qid = %question_id, "标准答案解析完成");
        Ok(cfg)
    }

    async fn chat_once(
        &self,
        ep: &EndpointSpec,
        content: &str,
        temperature: f64,
        max_tokens: u64,
    ) -> std::result::Result<String, String> {
        let url = format!("{}/chat/completions", ep.base_url.trim_end_matches('/'));
        let resp = match self
            .http
            .post(&url)
            .bearer_auth(&ep.api_key)
            .json(&json!({
                "model": ep.model,
                "messages": [{"role": "user", "content": content}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }))
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => return Err(format!("{} 请求失败：{e}", ep.name)),
        };

        let status = resp.status();
        let body: Value = resp.json().await.unwrap_or(Value::Null);
        if !status.is_success() {
            return Err(format!("{} HTTP {}：{}", ep.name, status, body));
        }
        let err = |msg: &str| -> String { format!("{} 响应异常：{msg}", ep.name) };
        let choice = body
            .get("choices")
            .and_then(|c| c.get(0))
            .ok_or_else(|| err("缺少 choices[0]"))?;
        let finish_reason = choice
            .get("finish_reason")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let content_text = choice
            .get("message")
            .and_then(|m| m.get("content"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();

        // 推理模型思考吃掉预算：截断/空 content 一律放大 max_tokens 由上层重试。
        if (finish_reason == "length" || content_text.is_empty()) && max_tokens < 8192 {
            return Err(format!(
                "{} finish={finish_reason} content_empty={} → 放大预算重试",
                ep.name,
                content_text.is_empty()
            ));
        }
        if content_text.is_empty() {
            return Err(format!("{} 返回空 content（finish={finish_reason}）", ep.name));
        }
        Ok(content_text)
    }
}

async fn sleep_backoff(attempt: usize) {
    let base = 2.0f64 * 2f64.powi(attempt as i32);
    let jitter = rand::thread_rng().gen_range(0.0..1.0);
    let secs = (base + jitter).min(60.0);
    tokio::time::sleep(Duration::from_secs_f64(secs)).await;
}

fn read_env_file(path: &Path) -> Vec<(String, String)> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => return Vec::new(),
    };
    text.lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                return None;
            }
            let (k, v) = line.split_once('=')?;
            Some((k.trim().to_string(), v.trim().to_string()))
        })
        .collect()
}

/// 端点解析：`LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL[,NAME]}` 按 n 升序；
/// 组内不全跳过；无编号端点回落旧单端点变量组。
fn parse_endpoints(env: &[(String, String)]) -> Vec<EndpointSpec> {
    let mut groups: Vec<(usize, [Option<String>; 4])> = Vec::new(); // BASE_URL, API_KEY, MODEL, NAME
    for (k, v) in env {
        if v.is_empty() || !k.starts_with("LLM_ENDPOINT_") {
            continue;
        }
        let rest = match k.strip_prefix("LLM_ENDPOINT_") {
            Some(r) => r,
            None => continue,
        };
        let (num_str, field) = match rest.split_once('_') {
            Some(x) => x,
            None => continue,
        };
        let idx = match field {
            "BASE_URL" => 0,
            "API_KEY" => 1,
            "MODEL" => 2,
            "NAME" => 3,
            _ => continue,
        };
        let n: usize = match num_str.parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        let slot = match groups.iter_mut().find(|(g, _)| *g == n) {
            Some((_, s)) => s,
            None => {
                groups.push((n, [None, None, None, None]));
                &mut groups.last_mut().unwrap().1
            }
        };
        slot[idx] = Some(v.clone());
    }
    groups.sort_by_key(|(n, _)| *n);

    let mut specs = Vec::new();
    for (n, g) in groups {
        let (Some(base_url), Some(api_key), Some(model)) = (&g[0], &g[1], &g[2]) else {
            tracing::warn!("LLM_ENDPOINT_{n} 不完整，已跳过");
            continue;
        };
        specs.push(EndpointSpec {
            name: g[3].clone().unwrap_or_else(|| format!("ep{n}")),
            base_url: base_url.clone(),
            api_key: api_key.clone(),
            model: model.clone(),
        });
    }
    if !specs.is_empty() {
        return specs;
    }
    // 回落旧单端点变量组
    let get = |key: &str| env.iter().find(|(k, _)| k == key).map(|(_, v)| v.clone());
    match (get("OPENAI_BASE_URL"), get("OPENAI_API_KEY"), get("LABELING_MODEL")) {
        (Some(base_url), Some(api_key), Some(model)) if !base_url.is_empty() && !api_key.is_empty() && !model.is_empty() => {
            vec![EndpointSpec { name: "ep1".into(), base_url, api_key, model }]
        }
        _ => Vec::new(),
    }
}

/// 从模型输出提取 JSON：剥栅栏 → 首个 '{' 到与之平衡的 '}'（容忍文本内偶发花括号）。
fn extract_json(text: &str) -> Result<Value> {
    let mut t = text.trim();
    for fence in ["```json", "```JSON", "```"] {
        if let Some(rest) = t.strip_prefix(fence) {
            t = rest.trim_start();
            break;
        }
    }
    if t.ends_with("```") {
        t = t.trim_end_matches('`').trim_end();
    }
    let start = t.find('{').ok_or_else(|| anyhow!("输出中没有 '{{'"))?;
    let bytes: Vec<char> = t.chars().collect();
    let mut depth = 0usize;
    let mut in_str = false;
    let mut esc = false;
    for i in start..bytes.len() {
        let ch = bytes[i];
        if in_str {
            if esc {
                esc = false;
            } else if ch == '\\' {
                esc = true;
            } else if ch == '"' {
                in_str = false;
            }
            continue;
        }
        match ch {
            '"' => in_str = true,
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    let slice: String = bytes[start..=i].iter().collect();
                    return serde_json::from_str(&slice).map_err(Into::into);
                }
            }
            _ => {}
        }
    }
    bail!("输出中 JSON 不平衡")
}
