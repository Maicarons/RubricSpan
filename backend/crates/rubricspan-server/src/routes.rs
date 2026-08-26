//! 路由实现 —— 与 `contracts/openapi.yaml` 的接口对应（含 M8 平台化新增管理后台端点）。
//!
//! 设计：Rust 负责 HTTP、校验、存储与评分编排；张量运算（MRC/相似度/OCR/解析）
//! 通过 `RuntimeClient` 委托给同机 Python 模型运行时。评分在主线程 `spawn_blocking`
//! 中同步执行（推理后端为阻塞式 HTTP 客户端，避免阻塞 tokio 工作线程）。

use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::{Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post, put},
    Json, Router,
};
use rubricspan_core::{ApiError, scoring::ScoringConfig};
use rubricspan_inference::LlmClient;
use rubricspan_scoring::{
    backend::InferenceBackend,
    result::{Rating, ScoreOutcome},
    score_answer_configured, ScoringSettings,
};
use rubricspan_storage::{ConfigStatus, Storage};
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::task::spawn_blocking;

/// 共享应用状态。
pub struct AppState {
    pub backend: Arc<dyn InferenceBackend>,
    pub storage: Arc<dyn Storage>,
    /// 标准答案解析的 LLM 客户端（M8 起由 Rust 直连 OpenAI 兼容端点）。
    pub llm: Arc<LlmClient>,
    /// ONNX 模型是否加载成功（false 时 /api/score 返回错误）。
    pub models_ready: bool,
    /// 数据落盘路径（管理后台只读展示）。
    pub store_path: String,
    /// OCR 引擎（M8.1 恢复；None 时 /api/ocr 返回 501）。
    pub ocr: Option<Arc<rubricspan_ocr::OcrEngine>>,
    /// 运行时评分参数（管理后台可调，持久化于 `<store_path>/scoring_settings.json`）。
    pub scoring_settings: Arc<tokio::sync::RwLock<ScoringSettings>>,
    /// 评分参数持久化文件（由 store 文件所在目录推导）。
    pub scoring_settings_path: std::path::PathBuf,
}

/// 构建完整路由表。
pub fn router(state: AppState) -> Router {
    let infer_concurrency = std::env::var("RUBRICSPAN_INFER_CONCURRENCY")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .unwrap_or(4)
        .clamp(1, 32);
    Router::new()
        .route("/api/questions", get(list_questions).post(create_question))
        .route("/api/standard-answer/parse", post(parse_standard_answer))
        .route("/api/standard-answer", put(save_standard_answer).get(get_standard_answer))
        .route("/api/answers", post(submit_answers).get(list_answers))
        // 推理型端点加并发限制：模型会话为受限并发资源（配合 RUBRICSPAN_SESSION_POOL），
        // 超发只会把请求堆在 spawn_blocking 线程池里空转（占满阻塞线程池还会饿死
        // 其他端点）。限制可调：RUBRICSPAN_INFER_CONCURRENCY（默认 4），保证队列有界、公平。
        .route("/api/ocr", post(run_ocr).layer(tower::limit::ConcurrencyLimitLayer::new(infer_concurrency)))
        .route("/api/score", post(score).layer(tower::limit::ConcurrencyLimitLayer::new(infer_concurrency)))
        .route("/api/results", get(query_results))
        .route("/api/health", get(health))
        .route("/api/admin/stats", get(admin_stats))
        .route("/api/admin/config", get(admin_config))
        .route("/api/admin/scoring-settings", get(get_scoring_settings).put(set_scoring_settings))
        .layer(
            // 前端（localhost:3000）与网关跨端口直连，本地服务放开 CORS
            tower_http::cors::CorsLayer::permissive(),
        )
        .with_state(Arc::new(state))
}

// ---------------------------------------------------------------------------
// 请求/响应体
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct QuestionCreate {
    #[serde(default)]
    question_id: Option<String>,
    content: String,
    subject: String,
    total_score: f64,
    #[serde(default)]
    standard_answer_text: Option<String>,
}

#[derive(Deserialize)]
struct AnswerSubmission {
    #[serde(default)]
    student_id: Option<String>,
    #[serde(default)]
    class_name: Option<String>,
    #[serde(default)]
    answer_text: Option<String>,
    #[serde(default)]
    image: Option<String>,
    #[serde(default)]
    source: Option<String>,
}

#[derive(Deserialize)]
struct AnswersBody {
    question_id: String,
    submissions: Vec<AnswerSubmission>,
}

#[derive(Deserialize)]
struct ScoreBody {
    question_id: String,
    answer_ids: Vec<String>,
}

#[derive(Serialize)]
struct ScoreResultResp {
    question_id: String,
    answer_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    student_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    class_name: Option<String>,
    total_score: f64,
    max_score: f64,
    rating: Rating,
    point_details: Vec<rubricspan_scoring::result::PointDetail>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ocr_confidence: Option<f64>,
    scored_at: String,
}

// ---------------------------------------------------------------------------
// 健康检查
// ---------------------------------------------------------------------------

async fn health(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    // 兼容字段：mode/status 语义不变；models 明示推理模型就绪情况。
    Json(json!({
        "status": "ok",
        "mode": "online",
        "models": { "mrc": state.models_ready, "similarity": state.models_ready },
    }))
}

// ---------------------------------------------------------------------------
// 管理后台（M8 平台化新增：聚合统计与只读运行信息，不含密钥）
// ---------------------------------------------------------------------------

/// 聚合统计：试题/答卷/评分概览、评级与得分占比分布、得分点命中率。
async fn admin_stats(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(state.storage.stats().await)
}

/// 只读运行信息：版本、落盘路径、模型就绪、LLM 端点摘要（名称/模型，密钥不暴露）、OCR 状态。
async fn admin_config(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let endpoints: Vec<serde_json::Value> = state
        .llm
        .endpoints_summary()
        .into_iter()
        .map(|(name, model)| json!({ "name": name, "model": model }))
        .collect();
    Json(json!({
        "server_version": env!("CARGO_PKG_VERSION"),
        "store_path": state.store_path,
        "models": { "mrc": state.models_ready, "similarity": state.models_ready },
        "llm": { "configured": !endpoints.is_empty(), "endpoints": endpoints },
        "ocr": {
            "enabled": state.ocr.is_some(),
            "note": if state.ocr.is_some() {
                "RapidOCR（Rust 侧推理 · M8.1 恢复）"
            } else {
                "OCR 引擎未加载（模型目录缺失或下载失败），请检查 --ocr-models-dir 与启动日志"
            }
        },
    }))
}

// ---------------------------------------------------------------------------
// 评分参数（管理后台）
// ---------------------------------------------------------------------------

/// 读取运行时评分参数（管理后台展示用）。
async fn get_scoring_settings(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let s = *state.scoring_settings.read().await;
    Json(json!({
        "similarity_high": s.similarity_high,
        "similarity_low": s.similarity_low,
        "partial_credit": s.partial_credit,
        "mrc_confidence_threshold": s.mrc_confidence_threshold,
        "note": "全局评分参数：题级配置 thresholds 仍优先覆盖高低阈值；partial_credit 作用于所有部分命中；mrc_confidence_threshold 为 MRC 抽取置信度判定阈值",
    }))
}

/// 更新运行时评分参数：校验范围 → 持久化到 `<store_path>/scoring_settings.json` → 立即生效。
async fn set_scoring_settings(
    State(state): State<Arc<AppState>>,
    Json(body): Json<ScoringSettings>,
) -> impl IntoResponse {
    if let Err(e) = body.validate() {
        return err(StatusCode::BAD_REQUEST, &e.to_string());
    }
    let path = state.scoring_settings_path.clone();
    if let Err(e) = body.save_to(&path) {
        tracing::error!(error = %e, path = %path.display(), "评分参数持久化失败");
        return err(StatusCode::INTERNAL_SERVER_ERROR, &format!("评分参数保存失败：{e}"));
    }
    *state.scoring_settings.write().await = body;
    tracing::info!(
        similarity_high = body.similarity_high,
        similarity_low = body.similarity_low,
        partial_credit = body.partial_credit,
        mrc_confidence_threshold = body.mrc_confidence_threshold,
        "评分参数已更新"
    );
    Json(json!({
        "similarity_high": body.similarity_high,
        "similarity_low": body.similarity_low,
        "partial_credit": body.partial_credit,
        "mrc_confidence_threshold": body.mrc_confidence_threshold,
    }))
    .into_response()
}

// ---------------------------------------------------------------------------
// 试题
// ---------------------------------------------------------------------------

async fn list_questions(
    State(state): State<Arc<AppState>>,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> impl IntoResponse {
    let subject = q.get("subject").cloned();
    let items = state.storage.list_questions(subject.as_deref()).await;
    Json(json!({ "items": items, "total": items.len() }))
}

async fn create_question(
    State(state): State<Arc<AppState>>,
    Json(body): Json<QuestionCreate>,
) -> impl IntoResponse {
    let existing = state.storage.list_questions(None).await.len();
    let qid = body
        .question_id
        .unwrap_or_else(|| format!("Q{:03}", existing + 1));
    let q = rubricspan_storage::Question {
        question_id: qid.clone(),
        content: body.content,
        subject: body.subject,
        total_score: body.total_score,
        standard_answer_text: body.standard_answer_text,
        config_status: ConfigStatus::None,
    };
    if let Err(e) = state.storage.save_question(q).await {
        return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string());
    }
    match state.storage.get_question(&qid).await {
        Some(q) => Json(q).into_response(),
        None => err(StatusCode::INTERNAL_SERVER_ERROR, "保存后无法读取"),
    }
}

// ---------------------------------------------------------------------------
// 配置与答卷读取（前端工作台 / 结果页使用）
// ---------------------------------------------------------------------------

async fn get_standard_answer(
    State(state): State<Arc<AppState>>,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> impl IntoResponse {
    let qid = match q.get("question_id") {
        Some(v) => v.clone(),
        None => return err(StatusCode::BAD_REQUEST, "缺少 question_id 参数"),
    };
    match state.storage.get_config(&qid).await {
        Some(cfg) => Json(cfg).into_response(),
        None => err(StatusCode::NOT_FOUND, "该试题尚无已保存的评分配置"),
    }
}

async fn list_answers(
    State(state): State<Arc<AppState>>,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> impl IntoResponse {
    let qid = q.get("question_id").cloned();
    let items = state.storage.list_answers(qid.as_deref()).await;
    Json(json!({ "items": items, "total": items.len() })).into_response()
}

// ---------------------------------------------------------------------------
// 标准答案解析与保存
// ---------------------------------------------------------------------------

async fn parse_standard_answer(
    State(state): State<Arc<AppState>>,
    Json(body): Json<serde_json::Value>,
) -> impl IntoResponse {
    let qid = body["question_id"].as_str().unwrap_or("").to_string();
    let raw = body["raw_answer_text"].as_str().unwrap_or("").to_string();
    let question = body
        .get("question")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    match state.llm.parse_standard_answer(&qid, &raw, &question).await {
        Ok(cfg) => Json(json!({
            "status": "parsed",
            "scoring_config": cfg,
            "warnings": [],
        }))
        .into_response(),
        Err(e) => err(StatusCode::UNPROCESSABLE_ENTITY, &e.to_string()),
    }
}

async fn save_standard_answer(
    State(state): State<Arc<AppState>>,
    Json(cfg): Json<ScoringConfig>,
) -> impl IntoResponse {
    if let Err(e) = state.storage.save_config(&cfg, ConfigStatus::Confirmed).await {
        return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string());
    }
    Json(json!({ "question_id": cfg.question_id, "saved_at": now_rfc3339() })).into_response()
}

// ---------------------------------------------------------------------------
// 答卷提交
// ---------------------------------------------------------------------------

async fn submit_answers(
    State(state): State<Arc<AppState>>,
    Json(body): Json<AnswersBody>,
) -> impl IntoResponse {
    if body.submissions.iter().any(|s| s.image.is_some()) {
        return err(
            StatusCode::NOT_IMPLEMENTED,
            "OCR 推理已随 Python 模型运行时移除（M8）：试卷图片识别待 Rust 原生移植，当前请使用文本录入",
        );
    }
    let mut answer_ids = Vec::new();
    for (i, sub) in body.submissions.into_iter().enumerate() {
        let aid = format!("{}-A{:03}", body.question_id, i + 1);
        let (source, ocr_text) = (sub.source.clone(), None);
        let ans = rubricspan_storage::Answer {
            answer_id: aid.clone(),
            question_id: body.question_id.clone(),
            student_id: sub.student_id.clone(),
            class_name: sub.class_name.clone(),
            answer_text: sub.answer_text.clone(),
            source,
            ocr_text,
        };
        if let Err(e) = state.storage.save_answer(ans).await {
            return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string());
        }
        answer_ids.push(aid);
    }
    Json(json!({ "accepted": answer_ids.len() as i64, "answer_ids": answer_ids })).into_response()
}

// ---------------------------------------------------------------------------
// OCR
// ---------------------------------------------------------------------------

async fn run_ocr(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    // M8.1 恢复：Rust 侧 RapidOCR 推理（无 Python）。请求体为图片二进制，
    // 试题标识走 X-Question-Id 头（与前端 api.ts ocrImage 契约一致）。
    let Some(engine) = state.ocr.clone() else {
        return err(
            StatusCode::NOT_IMPLEMENTED,
            "OCR 引擎未加载（模型目录缺失或下载失败），请检查 --ocr-models-dir 与启动日志",
        );
    };
    let qid = match headers.get("x-question-id").and_then(|v| v.to_str().ok()) {
        Some(v) => v.to_string(),
        None => return err(StatusCode::BAD_REQUEST, "缺少 X-Question-Id 请求头"),
    };

    // ort 会话为阻塞式推理：spawn_blocking 执行，避免阻塞 tokio 工作线程。
    let engine_for_block = engine.clone();
    let body_for_block = body;
    let qid_for_block = qid.clone();
    let result = spawn_blocking(move || {
        rubricspan_ocr::recognize(&engine_for_block, &qid_for_block, &body_for_block, None)
    })
    .await;

    match result {
        Ok(Ok(ocr_result)) => {
            // 结果落盘供前端复核与评分阶段取 OCR 置信度；落盘失败不阻断响应。
            if let Err(e) = state.storage.save_ocr(&qid, ocr_result.clone()).await {
                tracing::warn!(question_id = %qid, "OCR 结果落盘失败：{e}");
            }
            Json(ocr_result).into_response()
        }
        Ok(Err(e)) => err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
        Err(e) => err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
    }
}

// ---------------------------------------------------------------------------
// 评分
// ---------------------------------------------------------------------------

async fn score(
    State(state): State<Arc<AppState>>,
    Json(body): Json<ScoreBody>,
) -> impl IntoResponse {
    let cfg = match state.storage.get_config(&body.question_id).await {
        Some(c) => c,
        None => {
            return err(
                StatusCode::BAD_REQUEST,
                "该试题尚无已保存的评分配置（请先解析并确认标准答案）",
            )
        }
    };

    // 收集答卷与 OCR 置信度（异步存储读；OCR 随 M8 暂停但契约字段保留）。
    // OCR 结果按题存储：同一题的所有答卷共享同一置信度，只需查询一次（消除 N+1）。
    let ocr_conf_for_question = state.storage.get_ocr(&body.question_id).await.map(|o| o.confidence);
    let mut items: Vec<(String, rubricspan_storage::Answer, Option<f64>)> = Vec::new();
    for aid in &body.answer_ids {
        if let Some(a) = state.storage.get_answer(aid).await {
            let ocr_conf = if a.source.as_deref() == Some("ocr") {
                ocr_conf_for_question
            } else {
                None
            };
            items.push((aid.clone(), a, ocr_conf));
        }
    }
    let qid = body.question_id.clone();
    let backend = state.backend.clone();
    let scoring_settings = *state.scoring_settings.read().await;
    let items_for_score = items.clone();

    // 纯 CPU 评分：无存储访问，放 spawn_blocking 避免阻塞 tokio 工作线程
    let scored = spawn_blocking(move || -> anyhow::Result<Vec<(String, ScoreOutcome, Option<f64>)>> {
        let mut out = Vec::new();
        for (aid, ans, ocr_conf) in &items_for_score {
            let text = ans.ocr_text.clone().or(ans.answer_text.clone()).unwrap_or_default();
            let outcome = score_answer_configured(&cfg, &text, backend.as_ref(), *ocr_conf, scoring_settings)?;
            out.push((aid.clone(), outcome, *ocr_conf));
        }
        Ok(out)
    })
    .await;

    let scored = match scored {
        Ok(inner) => match inner {
            Ok(v) => v,
            Err(e) => return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
        },
        Err(e) => return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
    };

    // 结果落盘（单事务批量写；学生信息从收集时的 items 关联）
    let mut resps = Vec::new();
    let mut records = Vec::with_capacity(scored.len());
    for (aid, outcome, ocr_conf) in scored {
        let (student_id, class_name) = items
            .iter()
            .find(|(a, _, _)| a == &aid)
            .map(|(_, a, _)| (a.student_id.clone(), a.class_name.clone()))
            .unwrap_or((None, None));
        let now = now_rfc3339();
        resps.push(ScoreResultResp {
            question_id: outcome.question_id.clone(),
            answer_id: aid.clone(),
            student_id: student_id.clone(),
            class_name: class_name.clone(),
            total_score: outcome.total_score,
            max_score: outcome.max_score,
            rating: outcome.rating,
            point_details: outcome.point_details.clone(),
            ocr_confidence: ocr_conf,
            scored_at: now,
        });
        records.push(rubricspan_storage::ScoreRecord {
            question_id: outcome.question_id,
            answer_id: aid,
            student_id,
            class_name,
            total_score: outcome.total_score,
            max_score: outcome.max_score,
            rating: format!("{:?}", outcome.rating).to_lowercase(),
            point_details: serde_json::to_value(&outcome.point_details).unwrap_or(json!([])),
            ocr_confidence: ocr_conf,
        });
    }
    if let Err(e) = state.storage.save_results(records).await {
        return err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string());
    }
    Json(json!({ "question_id": qid, "results": resps })).into_response()
}

// ---------------------------------------------------------------------------
// 结果查询
// ---------------------------------------------------------------------------

async fn query_results(
    State(state): State<Arc<AppState>>,
    Query(q): Query<std::collections::HashMap<String, String>>,
) -> impl IntoResponse {
    let qid = q.get("question_id").cloned();
    let cls = q.get("class_name").cloned();
    let items = state.storage.list_results(qid.as_deref(), cls.as_deref()).await;
    Json(json!({ "items": items, "total": items.len() })).into_response()
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

fn now_rfc3339() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn err(status: StatusCode, msg: &str) -> Response {
    (status, Json(ApiError::new("error", msg.to_string()))).into_response()
}
