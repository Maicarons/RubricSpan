//! rubricspan-server —— Axum HTTP 服务主入口（技术方案 §10.1）。
//!
//! 职责：
//! - 七组 REST 接口（见 contracts/openapi.yaml）；
//! - 评分任务调度（图片先 OCR 再评分，异步任务池）；
//! - 标准答案结构化解析（调用 OpenAI 兼容接口 + Schema 校验 + 缓存落盘）；
//! - SQLite 持久化。
//!
//! 当前为脚手架骨架：路由已按契约挂载，处理函数返回 501（未实现），
//! M4 阶段逐个实现。

mod routes;

use clap::Parser;

/// 阅卷系统在线后端（Rust + Axum）。
#[derive(Debug, Parser)]
#[command(name = "rubricspan-server", version, about = "主观题阅卷教师模型 · 在线推理服务")]
struct Args {
    /// 监听地址（host:port）
    #[arg(long, default_value = "127.0.0.1:8080")]
    listen: String,

    /// 模型产物目录（见 contracts/model-artifacts.md）
    #[arg(long, default_value = "../models")]
    models_dir: String,

    /// SQLite 数据库文件
    #[arg(long, default_value = "rubricspan.db")]
    db: String,

    /// 评分配置目录
    #[arg(long, default_value = "../data/scoring_configs")]
    scoring_configs: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let args = Args::parse();
    tracing::info!(listen = %args.listen, "启动 rubricspan-server（脚手架骨架）");

    let app = routes::router();
    let listener = tokio::net::TcpListener::bind(&args.listen).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
