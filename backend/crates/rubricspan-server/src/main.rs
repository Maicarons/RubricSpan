//! rubricspan-server —— Axum HTTP 服务主入口（技术方案 §10.1 · 方案 A）。
//!
//! 架构（M8 起全 Rust）：HTTP、校验、存储、评分编排与**模型推理**均在 Rust 进程内
//! 完成（ort 加载 ONNX + tokenizers 官方 Rust 分词）；Python 仅保留在训练侧。
//! 模型目录缺失时自动回落占位后端（仅可用于编译/契约测试，不产出真实评分）。

mod routes;

use std::path::PathBuf;
use std::str::FromStr;
use std::sync::Arc;

use clap::Parser;
use rubricspan_inference::{LlmClient, OrtBackend, Precision};
use rubricspan_storage::{MySqlStorage, SqliteStorage};
use routes::AppState;

/// 存储后端：SQLite（本地测试/单机，默认）/ MySQL（生产）/ memory（M4 遗留临时兼容）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
enum StorageKind {
    Sqlite,
    Mysql,
    Memory,
}

/// 阅卷系统在线后端（Rust + Axum · 单进程）。
#[derive(Debug, Parser)]
#[command(name = "rubricspan-server", version, about = "主观题阅卷教师模型 · 在线推理服务")]
struct Args {
    /// 监听地址（host:port）
    #[arg(long, default_value = "127.0.0.1:8080")]
    listen: String,

    /// 模型产物根目录（含 mrc/ 与 similarity/）
    #[arg(long, default_value = "../models")]
    models_dir: PathBuf,

    /// 存储后端：sqlite（本地/默认）/ mysql（生产）/ memory（临时兼容）；
    /// 缺省读环境变量 RUBRICSPAN_STORAGE，再缺省 sqlite
    #[arg(long, value_enum)]
    storage: Option<StorageKind>,

    /// SQLite 数据库文件（--storage sqlite）或 Memory JSON 落盘路径（--storage memory）；
    /// 缺省读环境变量 RUBRICSPAN_STORE，再缺省 ../data/store.db
    #[arg(long)]
    store: Option<PathBuf>,

    /// MySQL 连接串（--storage mysql；如 `mysql://user:pass@127.0.0.1:3306/rubricspan`）；
    /// 优先级：--db-url > RUBRICSPAN_DB_URL > DATABASE_URL
    #[arg(long)]
    db_url: Option<String>,

    /// LLM 端点配置文件（标准答案解析用）
    #[arg(long, default_value = "../.env")]
    env_file: PathBuf,

    /// OCR 模型目录（det/rec 资产与字典；缺省用 `<models_dir>/ocr`，首次启动自动下载）
    #[arg(long)]
    ocr_models_dir: Option<PathBuf>,

    /// 管理后台静态文件目录（如 `../frontend-admin/out`）；缺省用 `../frontend-admin/out`，
    /// 目录不存在时静默跳过（仅 API 模式）。
    #[arg(long, default_value = "../frontend-admin/out")]
    admin_dir: PathBuf,
}

/// 脱敏 MySQL 连接串：`mysql://user:pass@host/db` → `mysql://user:***@host/db`（口令不出现在管理后台）。
fn redact_mysql_url(url: &str) -> String {
    let Some(scheme_end) = url.find("://") else {
        return url.to_string();
    };
    let Some(auth_end) = url.find('@') else {
        return url.to_string();
    };
    if auth_end <= scheme_end {
        return url.to_string();
    }
    let user = url[scheme_end + 3..auth_end]
        .split_once(':')
        .map(|(u, _)| u)
        .unwrap_or(&url[scheme_end + 3..auth_end]);
    format!("{}://{}:***@{}", &url[..scheme_end], user, &url[auth_end + 1..])
}

fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let args = Args::parse();
    let precision = std::env::var("RUBRICSPAN_MODEL_PRECISION")
        .ok()
        .and_then(|v| Precision::from_str(&v).ok())
        .unwrap_or(Precision::Fp32);
    let force_cpu = matches!(
        std::env::var("RUBRICSPAN_FORCE_CPU").as_deref(),
        Ok("1") | Ok("true") | Ok("yes")
    );

    // 存储配置解析：CLI 参数 > 进程环境变量 > --env-file 中的 RUBRICSPAN_* > 默认值
    let env_file_key = |key: &str| -> Option<String> {
        std::fs::read_to_string(&args.env_file)
            .ok()?
            .lines()
            .find_map(|line| {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    return None;
                }
                let (k, v) = line.split_once('=')?;
                (k.trim() == key).then(|| v.trim().to_string()).filter(|v| !v.is_empty())
            })
    };
    let storage_kind = args.storage.unwrap_or_else(|| {
        let from_env = std::env::var("RUBRICSPAN_STORAGE").ok().or_else(|| env_file_key("RUBRICSPAN_STORAGE"));
        match from_env.as_deref() {
            Some("mysql") => StorageKind::Mysql,
            Some("memory") => StorageKind::Memory,
            _ => StorageKind::Sqlite,
        }
    });
    let store = args.store.unwrap_or_else(|| {
        std::env::var("RUBRICSPAN_STORE")
            .ok()
            .or_else(|| env_file_key("RUBRICSPAN_STORE"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("../data/store.db"))
    });
    let db_url = args
        .db_url
        .clone()
        .or_else(|| std::env::var("RUBRICSPAN_DB_URL").ok())
        .or_else(|| env_file_key("RUBRICSPAN_DB_URL"));
    tracing::info!(storage = ?storage_kind, store = %store.display(), "存储配置（CLI > env > env-file > 默认）");

    // ort 会话为阻塞式加载：在同步上下文完成初始化，再手动拉起 tokio runtime。
    let (backend, models_ready) = match OrtBackend::load(&args.models_dir, precision, force_cpu) {
        Ok(b) => {
            let b = Arc::new(b);
            (b.clone() as Arc<dyn rubricspan_scoring::InferenceBackend>, true)
        }
        Err(e) => {
            tracing::warn!(
                "模型加载失败（{}）：回落占位后端，/api/score 将不可用",
                e
            );
            (Arc::new(rubricspan_inference::DummyBackend) as _, false)
        }
    };
    let llm = Arc::new(LlmClient::from_env_file(&args.env_file));

    // OCR 引擎（M8.1 恢复，纯 Rust）：模型缺失自动下载，加载失败仅告警不阻断服务。
    let ocr_model_set = std::env::var("RUBRICSPAN_OCR_MODEL_SET")
        .unwrap_or_else(|_| "ppocrv6-small".to_string());
    let ocr_dir = args
        .ocr_models_dir
        .clone()
        .unwrap_or_else(|| args.models_dir.join("ocr"));
    let ocr: Option<Arc<rubricspan_ocr::OcrEngine>> =
        match rubricspan_ocr::OcrEngine::open(&ocr_dir, &ocr_model_set) {
            Ok(e) => Some(Arc::new(e)),
            Err(e) => {
                tracing::warn!("OCR 引擎未就绪（{e}）：/api/ocr 返回 501");
                None
            }
        };

    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()?;
    rt.block_on(async move {
        if !models_ready {
            tracing::warn!("推理模型未就绪：/api/score 不可用，请检查 --models-dir");
        }
        if !llm.is_configured() {
            tracing::warn!("LLM 端点未配置：/api/standard-answer/parse 不可用");
        }

        // 存储后端按 --storage / RUBRICSPAN_STORAGE 选择；SQL 后端启动时自动建库建表。
        let store_display = store.display().to_string();
        let storage: Arc<dyn rubricspan_storage::Storage> = match storage_kind {
            StorageKind::Sqlite => {
                tracing::info!(store = %store_display, "存储后端：SQLite");
                Arc::new(SqliteStorage::open_sqlite(&store_display).await?) as Arc<dyn rubricspan_storage::Storage>
            }
            StorageKind::Mysql => {
                let url = db_url
                    .clone()
                    .or_else(|| std::env::var("DATABASE_URL").ok())
                    .ok_or_else(|| anyhow::anyhow!("RUBRICSPAN_STORAGE=mysql 需要 --db-url 或 RUBRICSPAN_DB_URL / DATABASE_URL"))?;
                tracing::info!(store = %redact_mysql_url(&url), "存储后端：MySQL");
                Arc::new(MySqlStorage::open_mysql(&url).await?) as Arc<dyn rubricspan_storage::Storage>
            }
            StorageKind::Memory => {
                tracing::warn!(store = %store_display, "存储后端：memory（临时兼容，重启即失忆）");
                Arc::new(rubricspan_storage::MemoryStorage::new(Some(store.clone()))) as Arc<dyn rubricspan_storage::Storage>
            }
        };
        let store_path = match storage_kind {
            StorageKind::Mysql => redact_mysql_url(db_url.as_deref().unwrap_or_default()),
            _ => store_display,
        };

        let scoring_settings_path = std::path::Path::new(&store_path)
            .parent()
            .unwrap_or_else(|| std::path::Path::new("."))
            .join("scoring_settings.json");
        let scoring_settings = Arc::new(tokio::sync::RwLock::new(
            rubricspan_scoring::ScoringSettings::load_from(&scoring_settings_path),
        ));
        let state = AppState {
            backend,
            storage,
            llm,
            models_ready,
            store_path,
            ocr,
            scoring_settings,
            scoring_settings_path,
        };
        let app = routes::router(state, Some(args.admin_dir));
        let listener = tokio::net::TcpListener::bind(&args.listen).await?;
        tracing::info!(listen = %args.listen, "rubricspan-server listening");
        axum::serve(listener, app).await?;
        Ok::<(), anyhow::Error>(())
    })?;
    Ok(())
}
