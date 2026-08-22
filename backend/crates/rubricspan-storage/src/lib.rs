//! rubricspan-storage —— SQLite 持久化（技术方案 §10.1）。
//!
//! 表规划（M4 实现建表迁移）：
//! - `questions`：试题（question_id / content / subject / total_score / 标准答案原文 / 配置状态）
//! - `answers`：答卷（answer_id / question_id / student_id / class / answer_text / source / ocr 关联）
//! - `ocr_tasks`：OCR 任务（任务状态 / 置信度 / 低置信标记）
//! - `score_results`：评分结果（逐点明细 JSON / 总分 / 评级 / scored_at）
//! - `scoring_configs`：评分配置落盘索引（question_id → JSON 文件路径）
//!
//! 当前为占位骨架，M4 接入 sqlx。

/// 数据库错误。
#[derive(Debug, thiserror::Error)]
pub enum StorageError {
    #[error("数据库连接失败：{0}")]
    Connection(String),
    #[error("记录不存在：{0}")]
    NotFound(String),
    #[error("查询/写入失败：{0}")]
    Query(String),
}

/// 数据库句柄（M4 实现：持有 sqlx::SqlitePool）。
#[derive(Debug)]
pub struct Database {
    pub path: std::path::PathBuf,
}

impl Database {
    /// 打开或创建数据库文件（M4 实现：建表迁移）。
    pub fn open(path: impl Into<std::path::PathBuf>) -> Result<Self, StorageError> {
        // TODO(M4): sqlx 连接池 + 迁移
        Ok(Self { path: path.into() })
    }
}
