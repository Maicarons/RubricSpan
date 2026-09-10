//! SQL 后端 —— SQLite / MySQL 共用同一套 schema 与实现（宏生成两个具体后端）。
//!
//! 设计要点：
//! - schema 双库兼容（VARCHAR 主键 / REAL 浮点 / TEXT 内容），同一份 DDL 两库通用；
//! - 写入统一走「事务内 DELETE + INSERT」实现覆盖语义（避开 MySQL `ON DUPLICATE KEY`
//!   与 SQLite `ON CONFLICT` 的方言差异），且与 Memory 后端的「同 id 覆盖」行为一致；
//! - 占位符统一用 `?`（两库均支持）；查询走 sqlx 运行时 API，构建不依赖数据库实例。

use anyhow::{Context, Result};
use async_trait::async_trait;
use rubricspan_core::scoring::ScoringConfig;
use sqlx::FromRow;
use std::str::FromStr;

use crate::{compute_stats, AdminStats, Answer, ConfigStatus, Question, ScoreRecord, Storage};

/// 共享 DDL（幂等）。MySQL 的 TEXT 列不能有 DEFAULT，故状态列统一用 VARCHAR(32)。
const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS projects (
  project_id VARCHAR(191) PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  subject TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS questions (
  question_id VARCHAR(191) PRIMARY KEY,
  project_id VARCHAR(191),
  content TEXT NOT NULL,
  subject TEXT NOT NULL,
  total_score REAL NOT NULL,
  standard_answer_text TEXT,
  config_status VARCHAR(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS configs (
  question_id VARCHAR(191) PRIMARY KEY,
  config TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answers (
  answer_id VARCHAR(191) PRIMARY KEY,
  question_id VARCHAR(191) NOT NULL,
  student_id TEXT,
  class_name TEXT,
  answer_text TEXT,
  source TEXT,
  ocr_text TEXT
);
CREATE TABLE IF NOT EXISTS results (
  answer_id VARCHAR(191) PRIMARY KEY,
  question_id VARCHAR(191) NOT NULL,
  student_id TEXT,
  class_name TEXT,
  total_score REAL NOT NULL,
  max_score REAL NOT NULL,
  rating VARCHAR(32) NOT NULL,
  point_details TEXT NOT NULL,
  ocr_confidence REAL
);
CREATE TABLE IF NOT EXISTS ocr (
  question_id VARCHAR(191) PRIMARY KEY,
  result TEXT NOT NULL
);
"#;

/// 业务索引（幂等）：SQLite 用 IF NOT EXISTS；MySQL 无此语法，靠忽略"重复名"错误。
const INDEXES: [&str; 2] = [
    "CREATE INDEX idx_answers_question ON answers(question_id)",
    "CREATE INDEX idx_results_question ON results(question_id)",
];

const Q_COLUMNS: &str =
    "question_id, project_id, content, subject, total_score, standard_answer_text, config_status";
const A_COLUMNS: &str =
    "answer_id, question_id, student_id, class_name, answer_text, source, ocr_text";
const R_COLUMNS: &str =
    "answer_id, question_id, student_id, class_name, total_score, max_score, rating, point_details, ocr_confidence";
const P_COLUMNS: &str =
    "project_id, name, description, subject, created_at, status";

// ---------------------------------------------------------------------------
// 行映射（FromRow derive 对任意 sqlx::Row 生效，两库共用）
// ---------------------------------------------------------------------------

#[derive(FromRow)]
struct QuestionRow {
    question_id: String,
    project_id: Option<String>,
    content: String,
    subject: String,
    total_score: f64,
    standard_answer_text: Option<String>,
    config_status: String,
}

#[derive(FromRow)]
struct AnswerRow {
    answer_id: String,
    question_id: String,
    student_id: Option<String>,
    class_name: Option<String>,
    answer_text: Option<String>,
    source: Option<String>,
    ocr_text: Option<String>,
}

#[derive(FromRow)]
struct ScoreRow {
    answer_id: String,
    question_id: String,
    student_id: Option<String>,
    class_name: Option<String>,
    total_score: f64,
    max_score: f64,
    rating: String,
    point_details: String,
    ocr_confidence: Option<f64>,
}

#[derive(FromRow)]
struct ProjectRow {
    project_id: String,
    name: String,
    description: Option<String>,
    subject: Option<String>,
    created_at: String,
    status: String,
}

impl From<QuestionRow> for Question {
    fn from(r: QuestionRow) -> Self {
        Question {
            question_id: r.question_id,
            project_id: r.project_id,
            content: r.content,
            subject: r.subject,
            total_score: r.total_score,
            standard_answer_text: r.standard_answer_text,
            config_status: ConfigStatus::parse(&r.config_status),
        }
    }
}

impl From<AnswerRow> for Answer {
    fn from(r: AnswerRow) -> Self {
        Answer {
            answer_id: r.answer_id,
            question_id: r.question_id,
            student_id: r.student_id,
            class_name: r.class_name,
            answer_text: r.answer_text,
            source: r.source,
            ocr_text: r.ocr_text,
        }
    }
}

impl From<ScoreRow> for ScoreRecord {
    fn from(r: ScoreRow) -> Self {
        ScoreRecord {
            answer_id: r.answer_id,
            question_id: r.question_id,
            student_id: r.student_id,
            class_name: r.class_name,
            total_score: r.total_score,
            max_score: r.max_score,
            rating: r.rating,
            point_details: serde_json::from_str(&r.point_details).unwrap_or_else(|_| serde_json::json!([])),
            ocr_confidence: r.ocr_confidence,
        }
    }
}

impl From<ProjectRow> for crate::Project {
    fn from(r: ProjectRow) -> Self {
        crate::Project {
            project_id: r.project_id,
            name: r.name,
            description: r.description,
            subject: r.subject,
            created_at: r.created_at,
            status: r.status,
        }
    }
}

// ---------------------------------------------------------------------------
// 存储类型（具体化两个后端；初始化/清空逻辑双份但极短）
// ---------------------------------------------------------------------------

pub type SqliteStorage = SqlStore<sqlx::sqlite::Sqlite>;
pub type MySqlStorage = SqlStore<sqlx::mysql::MySql>;

pub struct SqlStore<DB: sqlx::Database> {
    pool: sqlx::Pool<DB>,
}

/// 双后端共用的建表/索引与清空逻辑（sqlx 泛型查询约束所限，按具体 DB 各实现一份）。
async fn init_schema(pool: &sqlx::sqlite::SqlitePool) -> Result<()> {
    for stmt in SCHEMA.split(';').map(str::trim).filter(|s| !s.is_empty()) {
        sqlx::query(stmt).execute(pool).await.context("SQLite 建表失败")?;
    }
    for idx in INDEXES {
        if let Err(e) = sqlx::query(idx).execute(pool).await {
            let msg = e.to_string();
            if !msg.contains("already exists") && !msg.contains("Duplicate key name") {
                return Err(anyhow::Error::from(e));
            }
        }
    }
    Ok(())
}

async fn init_schema_mysql(pool: &sqlx::mysql::MySqlPool) -> Result<()> {
    for stmt in SCHEMA.split(';').map(str::trim).filter(|s| !s.is_empty()) {
        sqlx::query(stmt).execute(pool).await.context("MySQL 建表失败")?;
    }
    for idx in INDEXES {
        if let Err(e) = sqlx::query(idx).execute(pool).await {
            let msg = e.to_string();
            if !msg.contains("Duplicate key name") && !msg.contains("already exists") {
                return Err(anyhow::Error::from(e));
            }
        }
    }
    Ok(())
}

impl SqlStore<sqlx::sqlite::Sqlite> {
    /// 打开 SQLite 数据库（不存在则创建）。`:memory:` 强制单连接，保证单库语义。
    pub async fn open_sqlite(path: &str) -> Result<Self> {
        let max = if path == ":memory:" { 1 } else { 8 };
        let opts = sqlx::sqlite::SqliteConnectOptions::from_str(path)?
            .create_if_missing(true);
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .max_connections(max)
            .connect_with(opts)
            .await
            .context("连接 SQLite 失败")?;
        init_schema(&pool).await?;
        Ok(Self { pool })
    }

    /// 清空全部业务表（测试用）。
    #[cfg(test)]
    pub(crate) async fn clear(&self) -> Result<()> {
        for t in ["questions", "configs", "answers", "results", "ocr", "projects"] {
            sqlx::query(&format!("DELETE FROM {t}"))
                .execute(&self.pool)
                .await
                .with_context(|| format!("清空 {t} 失败"))?;
        }
        Ok(())
    }
}

impl SqlStore<sqlx::mysql::MySql> {
    /// 连接 MySQL（url 形如 `mysql://user:pass@host:port/db`），启动时自动建表。
    pub async fn open_mysql(url: &str) -> Result<Self> {
        let pool = sqlx::mysql::MySqlPoolOptions::new()
            .max_connections(8)
            .connect(url)
            .await
            .context("连接 MySQL 失败")?;
        init_schema_mysql(&pool).await?;
        Ok(Self { pool })
    }

    /// 清空全部业务表（测试用）。
    #[cfg(test)]
    pub(crate) async fn clear(&self) -> Result<()> {
        for t in ["questions", "configs", "answers", "results", "ocr", "projects"] {
            sqlx::query(&format!("DELETE FROM {t}"))
                .execute(&self.pool)
                .await
                .with_context(|| format!("清空 {t} 失败"))?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Storage 实现（具体 DB 下模板一致；宏避免两后端实现漂移）
// ---------------------------------------------------------------------------

macro_rules! impl_storage_sql {
    ($db:ty) => {
        #[async_trait]
        impl Storage for SqlStore<$db> {
            async fn save_question(&self, q: Question) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM questions WHERE question_id = ?")
                    .bind(&q.question_id)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query(&format!(
                    "INSERT INTO questions ({Q_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)"
                ))
                .bind(&q.question_id)
                .bind(&q.project_id)
                .bind(&q.content)
                .bind(&q.subject)
                .bind(q.total_score)
                .bind(q.standard_answer_text)
                .bind(q.config_status.as_str())
                .execute(&mut *tx)
                .await?;
                tx.commit().await?;
                Ok(())
            }

            async fn list_questions(&self, subject: Option<&str>) -> Vec<Question> {
                let sql = format!("SELECT {Q_COLUMNS} FROM questions");
                let rows: Vec<QuestionRow> = if let Some(sub) = subject {
                    sqlx::query_as::<_, QuestionRow>(&format!("{sql} WHERE subject = ?"))
                        .bind(sub)
                        .fetch_all(&self.pool)
                        .await
                } else {
                    sqlx::query_as::<_, QuestionRow>(&sql).fetch_all(&self.pool).await
                }
                .unwrap_or_default();
                rows.into_iter().map(Question::from).collect()
            }

            async fn get_question(&self, id: &str) -> Option<Question> {
                sqlx::query_as::<_, QuestionRow>(&format!("SELECT {Q_COLUMNS} FROM questions WHERE question_id = ?"))
                    .bind(id)
                    .fetch_optional(&self.pool)
                    .await
                    .ok()
                    .flatten()
                    .map(Question::from)
            }

            async fn save_config(&self, cfg: &ScoringConfig, status: ConfigStatus) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM configs WHERE question_id = ?")
                    .bind(&cfg.question_id)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query("INSERT INTO configs (question_id, config) VALUES (?, ?)")
                    .bind(&cfg.question_id)
                    .bind(serde_json::to_string(cfg)?)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query("UPDATE questions SET config_status = ? WHERE question_id = ?")
                    .bind(status.as_str())
                    .bind(&cfg.question_id)
                    .execute(&mut *tx)
                    .await?;
                tx.commit().await?;
                Ok(())
            }

            async fn get_config(&self, id: &str) -> Option<ScoringConfig> {
                sqlx::query_scalar::<_, String>("SELECT config FROM configs WHERE question_id = ?")
                    .bind(id)
                    .fetch_optional(&self.pool)
                    .await
                    .ok()
                    .flatten()
                    .and_then(|s| serde_json::from_str(&s).ok())
            }

            async fn save_answer(&self, a: Answer) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM answers WHERE answer_id = ?")
                    .bind(&a.answer_id)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query(&format!(
                    "INSERT INTO answers ({A_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)"
                ))
                .bind(&a.answer_id)
                .bind(&a.question_id)
                .bind(a.student_id)
                .bind(a.class_name)
                .bind(a.answer_text)
                .bind(a.source)
                .bind(a.ocr_text)
                .execute(&mut *tx)
                .await?;
                tx.commit().await?;
                Ok(())
            }

            async fn get_answer(&self, id: &str) -> Option<Answer> {
                sqlx::query_as::<_, AnswerRow>(&format!("SELECT {A_COLUMNS} FROM answers WHERE answer_id = ?"))
                    .bind(id)
                    .fetch_optional(&self.pool)
                    .await
                    .ok()
                    .flatten()
                    .map(Answer::from)
            }

            async fn list_answers(&self, question_id: Option<&str>) -> Vec<Answer> {
                let sql = format!("SELECT {A_COLUMNS} FROM answers");
                let rows: Vec<AnswerRow> = if let Some(qid) = question_id {
                    sqlx::query_as::<_, AnswerRow>(&format!("{sql} WHERE question_id = ?"))
                        .bind(qid)
                        .fetch_all(&self.pool)
                        .await
                } else {
                    sqlx::query_as::<_, AnswerRow>(&sql).fetch_all(&self.pool).await
                }
                .unwrap_or_default();
                rows.into_iter().map(Answer::from).collect()
            }

            async fn save_result(&self, r: ScoreRecord) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM results WHERE answer_id = ?")
                    .bind(&r.answer_id)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query(&format!(
                    "INSERT INTO results ({R_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ))
                .bind(&r.answer_id)
                .bind(&r.question_id)
                .bind(r.student_id)
                .bind(r.class_name)
                .bind(r.total_score)
                .bind(r.max_score)
                .bind(&r.rating)
                .bind(serde_json::to_string(&r.point_details)?)
                .bind(r.ocr_confidence)
                .execute(&mut *tx)
                .await?;
                tx.commit().await?;
                Ok(())
            }

            async fn save_results(&self, records: Vec<ScoreRecord>) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                for r in &records {
                    sqlx::query("DELETE FROM results WHERE answer_id = ?")
                        .bind(&r.answer_id)
                        .execute(&mut *tx)
                        .await?;
                    sqlx::query(&format!(
                        "INSERT INTO results ({R_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ))
                    .bind(&r.answer_id)
                    .bind(&r.question_id)
                    .bind(r.student_id.clone())
                    .bind(r.class_name.clone())
                    .bind(r.total_score)
                    .bind(r.max_score)
                    .bind(&r.rating)
                    .bind(serde_json::to_string(&r.point_details)?)
                    .bind(r.ocr_confidence)
                    .execute(&mut *tx)
                    .await?;
                }
                tx.commit().await?;
                Ok(())
            }

            async fn list_results(&self, question_id: Option<&str>, class_name: Option<&str>) -> Vec<ScoreRecord> {
                let mut sql = format!("SELECT {R_COLUMNS} FROM results");
                let mut conds: Vec<&str> = Vec::new();
                if question_id.is_some() {
                    conds.push("question_id = ?");
                }
                if class_name.is_some() {
                    conds.push("class_name = ?");
                }
                if !conds.is_empty() {
                    sql.push_str(" WHERE ");
                    sql.push_str(&conds.join(" AND "));
                }
                let mut q = sqlx::query_as::<_, ScoreRow>(&sql);
                if let Some(v) = question_id {
                    q = q.bind(v);
                }
                if let Some(v) = class_name {
                    q = q.bind(v);
                }
                q.fetch_all(&self.pool)
                    .await
                    .unwrap_or_default()
                    .into_iter()
                    .map(ScoreRecord::from)
                    .collect()
            }

            async fn save_ocr(&self, qid: &str, r: rubricspan_core::ocr::OcrResult) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM ocr WHERE question_id = ?")
                    .bind(qid)
                    .execute(&mut *tx)
                    .await?;
                sqlx::query("INSERT INTO ocr (question_id, result) VALUES (?, ?)")
                    .bind(qid)
                    .bind(serde_json::to_string(&r)?)
                    .execute(&mut *tx)
                    .await?;
                tx.commit().await?;
                Ok(())
            }

            async fn get_ocr(&self, qid: &str) -> Option<rubricspan_core::ocr::OcrResult> {
                sqlx::query_scalar::<_, String>("SELECT result FROM ocr WHERE question_id = ?")
                    .bind(qid)
                    .fetch_optional(&self.pool)
                    .await
                    .ok()
                    .flatten()
                    .and_then(|s| serde_json::from_str(&s).ok())
            }

            async fn stats(&self) -> AdminStats {
                let questions = self.list_questions(None).await;
                let answers = self.list_answers(None).await;
                let results = self.list_results(None, None).await;
                compute_stats(&questions, answers.len(), &results)
            }

            async fn delete_question(&self, id: &str) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM results WHERE question_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM answers WHERE question_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM configs WHERE question_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM questions WHERE question_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM ocr WHERE question_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                tx.commit().await?;
                Ok(())
            }

            async fn delete_answer(&self, id: &str) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM results WHERE answer_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM answers WHERE answer_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                tx.commit().await?;
                Ok(())
            }

            async fn save_project(&self, p: crate::Project) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM projects WHERE project_id = ?")
                    .bind(&p.project_id).execute(&mut *tx).await?;
                sqlx::query(&format!(
                    "INSERT INTO projects ({P_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)"
                ))
                .bind(&p.project_id)
                .bind(&p.name)
                .bind(&p.description)
                .bind(&p.subject)
                .bind(&p.created_at)
                .bind(&p.status)
                .execute(&mut *tx).await?;
                tx.commit().await?;
                Ok(())
            }

            async fn list_projects(&self) -> Vec<crate::Project> {
                sqlx::query_as::<_, ProjectRow>(&format!("SELECT {P_COLUMNS} FROM projects ORDER BY created_at DESC"))
                    .fetch_all(&self.pool).await.unwrap_or_default()
                    .into_iter().map(crate::Project::from).collect()
            }

            async fn get_project(&self, id: &str) -> Option<crate::Project> {
                sqlx::query_as::<_, ProjectRow>(&format!("SELECT {P_COLUMNS} FROM projects WHERE project_id = ?"))
                    .bind(id).fetch_optional(&self.pool).await.ok()
                    .flatten()
                    .map(crate::Project::from)
            }

            async fn delete_project(&self, id: &str) -> Result<()> {
                let mut tx = self.pool.begin().await?;
                sqlx::query("DELETE FROM results WHERE question_id IN (SELECT question_id FROM questions WHERE project_id = ?)")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM answers WHERE question_id IN (SELECT question_id FROM questions WHERE project_id = ?)")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM configs WHERE question_id IN (SELECT question_id FROM questions WHERE project_id = ?)")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM ocr WHERE question_id IN (SELECT question_id FROM questions WHERE project_id = ?)")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM questions WHERE project_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                sqlx::query("DELETE FROM projects WHERE project_id = ?")
                    .bind(id).execute(&mut *tx).await?;
                tx.commit().await?;
                Ok(())
            }
        }
    };
}

impl_storage_sql!(sqlx::sqlite::Sqlite);
impl_storage_sql!(sqlx::mysql::MySql);