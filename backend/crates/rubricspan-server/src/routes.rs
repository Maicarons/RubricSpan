//! 路由挂载 —— 与 `contracts/openapi.yaml` 的七组接口一一对应。
//!
//! 当前全部处理函数为占位实现（501 Not Implemented），M4 阶段逐个落地。
//! 契约变更须先走 `docs/CHANGELOG-contracts.md` 流程。

use axum::{
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post, put},
    Json, Router,
};
use rubricspan_core::ApiError;

/// 构建完整路由表。
pub fn router() -> Router {
    Router::new()
        // questions —— 试题管理
        .route("/api/questions", get(list_questions).post(create_question))
        // standard-answer —— 标准答案解析与保存
        .route("/api/standard-answer/parse", post(parse_standard_answer))
        .route("/api/standard-answer", put(save_standard_answer))
        // answers —— 答卷提交
        .route("/api/answers", post(submit_answers))
        // ocr —— 试卷图片识别
        .route("/api/ocr", post(run_ocr))
        // scoring —— 评分与结果
        .route("/api/score", post(score))
        .route("/api/results", get(query_results))
        // 健康检查（部署与联调用）
        .route("/api/health", get(health))
}

/// 占位响应：501 Not Implemented。
fn not_implemented(name: &'static str) -> impl IntoResponse {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(ApiError::new(
            "not_implemented",
            format!("接口 {name} 尚未实现（M4 阶段，见项目执行计划 §4.5）"),
        )),
    )
}

async fn health() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "ok", "mode": "online" }))
}

async fn list_questions() -> impl IntoResponse {
    not_implemented("GET /api/questions")
}

async fn create_question() -> impl IntoResponse {
    not_implemented("POST /api/questions")
}

async fn parse_standard_answer() -> impl IntoResponse {
    not_implemented("POST /api/standard-answer/parse")
}

async fn save_standard_answer() -> impl IntoResponse {
    not_implemented("PUT /api/standard-answer")
}

async fn submit_answers() -> impl IntoResponse {
    not_implemented("POST /api/answers")
}

async fn run_ocr() -> impl IntoResponse {
    not_implemented("POST /api/ocr")
}

async fn score() -> impl IntoResponse {
    not_implemented("POST /api/score")
}

async fn query_results() -> impl IntoResponse {
    not_implemented("GET /api/results")
}
