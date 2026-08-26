//! rubricspan-storage —— 持久化层（技术方案 §10.2 · M8.1 双后端化）。
//!
//! 三种实现，统一经过 `Storage` trait（全程 `async_trait`，可运行在 tokio 运行时内）：
//! - [`SqliteStorage`]：SQLite 本地测试/单机部署（sqlx）；
//! - [`MySqlStorage`]：MySQL 生产环境（sqlx，含连接池与自动建表）；
//! - [`MemoryStorage`]：进程内内存 + JSON 文件落盘（M4 遗留，保留为临时兼容/演示）。
//!
//! SQLite 与 MySQL 共用同一套 schema 与行映射（[`sql`] 模块中的泛型 `SqlStore<DB>`），
//! 查询走 sqlx 运行时 API（`query_as` + `FromRow` derive），构建不依赖数据库实例。
//!
//! 存储实体：试题（`Question`）、评分配置（`ScoringConfig`）、答卷（`Answer`）、
//! 评分结果（`ScoreRecord`）、OCR 结果（`OcrResult`）。

mod sql;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;

use anyhow::Result;
use async_trait::async_trait;
use rubricspan_core::ocr::OcrResult;
use rubricspan_core::scoring::ScoringConfig;
use serde::{Deserialize, Serialize};

pub use sql::{MySqlStorage, SqliteStorage};

/// 试题（对应 openapi.yaml 的 Question）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Question {
    pub question_id: String,
    pub content: String,
    pub subject: String,
    pub total_score: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub standard_answer_text: Option<String>,
    #[serde(default)]
    pub config_status: ConfigStatus,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConfigStatus {
    #[default]
    None,
    PendingReview,
    Confirmed,
}

impl ConfigStatus {
    /// 数据库存储形态（TEXT 列），与 serde snake_case 保持一致。
    pub fn as_str(self) -> &'static str {
        match self {
            ConfigStatus::None => "none",
            ConfigStatus::PendingReview => "pending_review",
            ConfigStatus::Confirmed => "confirmed",
        }
    }

    pub fn parse(s: &str) -> ConfigStatus {
        match s {
            "pending_review" => ConfigStatus::PendingReview,
            "confirmed" => ConfigStatus::Confirmed,
            _ => ConfigStatus::None,
        }
    }
}

/// 答卷（对应 openapi.yaml 的 AnswerSubmission 落库形态）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Answer {
    pub answer_id: String,
    pub question_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub student_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub class_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub answer_text: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ocr_text: Option<String>,
}

/// 评分结果（对应 openapi.yaml 的 ScoreResult）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreRecord {
    pub question_id: String,
    pub answer_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub student_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub class_name: Option<String>,
    pub total_score: f64,
    pub max_score: f64,
    pub rating: String,
    pub point_details: serde_json::Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ocr_confidence: Option<f64>,
}

// ---------------------------------------------------------------------------
// 管理后台聚合统计（/api/admin/stats）
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default, Serialize)]
pub struct AdminStats {
    pub questions: QuestionStats,
    pub answers: AnswerStats,
    pub scores: ScoreStats,
    /// 按 (question_id, point_id) 聚合的得分点命中统计。
    pub point_hits: Vec<PointHit>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct QuestionStats {
    pub total: usize,
    /// 评分配置状态分布（none / pending_review / confirmed）。
    pub by_config_status: HashMap<String, usize>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct AnswerStats {
    pub total: usize,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ScoreStats {
    pub total: usize,
    /// 所有评分记录的平均得分（保留两位小数）。
    pub average: f64,
    /// 所有评分记录满分（max_score）的平均值。
    pub max_score_average: f64,
    /// 评级分布（excellent / good / pass / fail）。
    pub by_rating: HashMap<String, usize>,
    /// 得分占比（total/max）分桶分布，10/20 分桶。
    pub distribution: Vec<ScoreBucketed>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ScoreBucketed {
    pub label: String,
    pub count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct PointHit {
    pub question_id: String,
    pub point_id: i64,
    /// 命中次数（hit_status != "miss"）。
    pub hit: usize,
    /// 评分总次数。
    pub total: usize,
}

/// 持久化接口（SQLite / MySQL / Memory 共用；生产建议 SQLite 或 MySQL）。
#[async_trait]
pub trait Storage: Send + Sync {
    async fn save_question(&self, q: Question) -> Result<()>;
    async fn list_questions(&self, subject: Option<&str>) -> Vec<Question>;
    async fn get_question(&self, id: &str) -> Option<Question>;
    async fn save_config(&self, cfg: &ScoringConfig, status: ConfigStatus) -> Result<()>;
    async fn get_config(&self, id: &str) -> Option<ScoringConfig>;
    async fn save_answer(&self, a: Answer) -> Result<()>;
    async fn get_answer(&self, id: &str) -> Option<Answer>;
    async fn list_answers(&self, question_id: Option<&str>) -> Vec<Answer>;
    async fn save_result(&self, r: ScoreRecord) -> Result<()>;
    async fn list_results(&self, question_id: Option<&str>, class_name: Option<&str>) -> Vec<ScoreRecord>;
    async fn save_ocr(&self, qid: &str, r: OcrResult) -> Result<()>;
    async fn get_ocr(&self, qid: &str) -> Option<OcrResult>;
    /// 管理后台聚合统计（/api/admin/stats 使用）。
    async fn stats(&self) -> AdminStats;
}

/// 纯内存 + JSON 文件落盘实现（M4 遗留；M8.1 起仅作临时兼容/演示，主路径用 SQL 后端）。
pub struct MemoryStorage {
    inner: Mutex<State>,
    path: Option<PathBuf>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct State {
    questions: HashMap<String, Question>,
    configs: HashMap<String, ScoringConfig>,
    answers: HashMap<String, Answer>,
    results: HashMap<String, ScoreRecord>,
    ocr: HashMap<String, OcrResult>,
}

impl MemoryStorage {
    /// `path` 非空时加载已有文件并在变更时写回。
    pub fn new(path: Option<PathBuf>) -> Self {
        let inner = path
            .as_ref()
            .and_then(|p| std::fs::read(p).ok())
            .and_then(|b| serde_json::from_slice::<State>(&b).ok())
            .unwrap_or_default();
        Self { inner: Mutex::new(inner), path }
    }

    fn flush(&self) {
        if let Some(p) = &self.path {
            if let Ok(s) = serde_json::to_string_pretty(&*self.inner.lock().unwrap()) {
                let _ = std::fs::write(p, s);
            }
        }
    }
}

#[async_trait]
impl Storage for MemoryStorage {
    async fn save_question(&self, q: Question) -> Result<()> {
        self.inner.lock().unwrap().questions.insert(q.question_id.clone(), q);
        self.flush();
        Ok(())
    }
    async fn list_questions(&self, subject: Option<&str>) -> Vec<Question> {
        let s = self.inner.lock().unwrap();
        s.questions
            .values()
            .filter(|q| subject.map(|sub| q.subject == sub).unwrap_or(true))
            .cloned()
            .collect()
    }
    async fn get_question(&self, id: &str) -> Option<Question> {
        self.inner.lock().unwrap().questions.get(id).cloned()
    }
    async fn save_config(&self, cfg: &ScoringConfig, status: ConfigStatus) -> Result<()> {
        let mut s = self.inner.lock().unwrap();
        s.configs.insert(cfg.question_id.clone(), cfg.clone());
        if let Some(q) = s.questions.get_mut(&cfg.question_id) {
            q.config_status = status;
        }
        drop(s);
        self.flush();
        Ok(())
    }
    async fn get_config(&self, id: &str) -> Option<ScoringConfig> {
        self.inner.lock().unwrap().configs.get(id).cloned()
    }
    async fn save_answer(&self, a: Answer) -> Result<()> {
        self.inner.lock().unwrap().answers.insert(a.answer_id.clone(), a);
        self.flush();
        Ok(())
    }
    async fn get_answer(&self, id: &str) -> Option<Answer> {
        self.inner.lock().unwrap().answers.get(id).cloned()
    }
    async fn list_answers(&self, question_id: Option<&str>) -> Vec<Answer> {
        let s = self.inner.lock().unwrap();
        s.answers
            .values()
            .filter(|a| question_id.map(|q| a.question_id == q).unwrap_or(true))
            .cloned()
            .collect()
    }
    async fn save_result(&self, r: ScoreRecord) -> Result<()> {
        self.inner.lock().unwrap().results.insert(r.answer_id.clone(), r);
        self.flush();
        Ok(())
    }
    async fn list_results(&self, question_id: Option<&str>, class_name: Option<&str>) -> Vec<ScoreRecord> {
        let s = self.inner.lock().unwrap();
        s.results
            .values()
            .filter(|r| question_id.map(|q| r.question_id == q).unwrap_or(true))
            .filter(|r| class_name.map(|c| r.class_name.as_deref() == Some(c)).unwrap_or(true))
            .cloned()
            .collect()
    }
    async fn save_ocr(&self, qid: &str, r: OcrResult) -> Result<()> {
        self.inner.lock().unwrap().ocr.insert(qid.to_string(), r);
        self.flush();
        Ok(())
    }
    async fn get_ocr(&self, qid: &str) -> Option<OcrResult> {
        self.inner.lock().unwrap().ocr.get(qid).cloned()
    }

    async fn stats(&self) -> AdminStats {
        let s = self.inner.lock().unwrap();
        let questions: Vec<Question> = s.questions.values().cloned().collect();
        let results: Vec<ScoreRecord> = s.results.values().cloned().collect();
        compute_stats(&questions, s.answers.len(), &results)
    }
}

/// 聚合统计公共计算（三个存储实现共用，保证分桶/命中口径一致）。
pub(crate) fn compute_stats(questions: &[Question], answer_count: usize, results: &[ScoreRecord]) -> AdminStats {
    let mut st = AdminStats::default();

    st.questions.total = questions.len();
    for q in questions {
        *st.questions.by_config_status.entry(q.config_status.as_str().to_string()).or_insert(0) += 1;
    }
    st.answers.total = answer_count;

    st.scores.total = results.len();
    let mut sum = 0.0f64;
    let mut max_sum = 0.0f64;
    let mut buckets = [0usize; 5];
    // (question_id, point_id) -> (hit, total)
    let mut point_hits: HashMap<(String, i64), (usize, usize)> = HashMap::new();
    for r in results {
        sum += r.total_score;
        max_sum += r.max_score;
        *st.scores.by_rating.entry(r.rating.clone()).or_insert(0) += 1;
        let ratio = if r.max_score > 0.0 { r.total_score / r.max_score } else { 0.0 };
        buckets[((ratio * 100.0) as usize).min(99) / 20] += 1;
        if let Some(arr) = r.point_details.as_array() {
            for p in arr {
                let pid = p.get("point_id").and_then(|v| v.as_i64()).unwrap_or(0);
                let hit = p.get("hit_status").and_then(|v| v.as_str()) != Some("miss");
                let e = point_hits.entry((r.question_id.clone(), pid)).or_insert((0, 0));
                e.1 += 1;
                if hit {
                    e.0 += 1;
                }
            }
        }
    }
    st.scores.average = if st.scores.total > 0 { sum / st.scores.total as f64 } else { 0.0 };
    st.scores.max_score_average = if st.scores.total > 0 { max_sum / st.scores.total as f64 } else { 0.0 };
    const LABELS: [&str; 5] = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"];
    st.scores.distribution = LABELS
        .iter()
        .zip(buckets)
        .map(|(label, count)| ScoreBucketed { label: label.to_string(), count })
        .collect();

    let mut hits: Vec<PointHit> = point_hits
        .into_iter()
        .map(|((question_id, point_id), (hit, total))| PointHit { question_id, point_id, hit, total })
        .collect();
    hits.sort_by(|a, b| a.question_id.cmp(&b.question_id).then(a.point_id.cmp(&b.point_id)));
    st.point_hits = hits;
    st
}

#[cfg(test)]
mod tests {
    use super::*;
    use rubricspan_core::scoring::ScoringConfig;
    use serde_json::json;

    fn point(pid: i64, status: &str) -> serde_json::Value {
        json!({ "point_id": pid, "hit_status": status, "point_score": 1.0 })
    }

    fn result(answer_id: &str, total: f64, details: serde_json::Value) -> ScoreRecord {
        ScoreRecord {
            question_id: "Q1".into(),
            answer_id: answer_id.into(),
            student_id: None,
            class_name: None,
            total_score: total,
            max_score: 5.0,
            rating: if total >= 4.0 { "excellent".into() } else { "pass".into() },
            point_details: details,
            ocr_confidence: None,
        }
    }

    /// memory 后端：读写 + 聚合口径单测。
    #[tokio::test]
    async fn memory_roundtrip_and_stats() {
        let s = MemoryStorage::new(None);
        s.save_question(Question {
            question_id: "Q1".into(),
            content: "题".into(),
            subject: "历史".into(),
            total_score: 5.0,
            standard_answer_text: None,
            config_status: ConfigStatus::Confirmed,
        })
        .await
        .unwrap();
        s.save_question(Question {
            question_id: "Q2".into(),
            content: "题".into(),
            subject: "历史".into(),
            total_score: 5.0,
            standard_answer_text: None,
            config_status: ConfigStatus::None,
        })
        .await
        .unwrap();
        s.save_config(&ScoringConfig { question_id: "Q1".into(), total_score: 5.0, points: vec![], thresholds: None, subject: None, meta: None }, ConfigStatus::Confirmed)
            .await
            .unwrap();
        s.save_answer(Answer { answer_id: "A1".into(), question_id: "Q1".into(), student_id: None, class_name: None, answer_text: Some("x".into()), source: None, ocr_text: None })
            .await
            .unwrap();
        s.save_answer(Answer { answer_id: "A2".into(), question_id: "Q1".into(), student_id: None, class_name: None, answer_text: Some("y".into()), source: None, ocr_text: None })
            .await
            .unwrap();
        s.save_result(result("A1", 5.0, json!([point(1, "hit_exact"), point(2, "miss")]))).await.unwrap();
        s.save_result(result("A2", 2.0, json!([point(1, "miss")]))).await.unwrap();

        let st = s.stats().await;
        assert_eq!(st.questions.total, 2);
        assert_eq!(st.questions.by_config_status["confirmed"], 1);
        assert_eq!(st.questions.by_config_status["none"], 1);
        assert_eq!(st.answers.total, 2);
        assert_eq!(st.scores.total, 2);
        assert_eq!(st.scores.average, 3.5);
        assert_eq!(st.scores.by_rating["excellent"], 1);
        assert_eq!(st.scores.distribution.len(), 5);
        // 100% 桶（index 4）与 40% 桶（index 2）各 1
        assert_eq!(st.scores.distribution[4].count, 1);
        assert_eq!(st.scores.distribution[2].count, 1);
        // 得分点 1：2 评 1 次命中；得分点 2：1 评 0 次命中
        let p1 = st.point_hits.iter().find(|p| p.point_id == 1).unwrap();
        assert_eq!((p1.hit, p1.total), (1, 2));
        let p2 = st.point_hits.iter().find(|p| p.point_id == 2).unwrap();
        assert_eq!((p2.hit, p2.total), (0, 1));
    }

    /// SQLite 内存后端（单连接）全链路：建表 → 读写 → 聚合。
    #[tokio::test]
    async fn sqlite_roundtrip_and_stats() {
        let s = SqliteStorage::open_sqlite(":memory:").await.expect("打开 SQLite 内存库失败");
        s.clear().await.expect("清空失败");
        roundtrip_assertions(&s).await;
    }

    /// MySQL 集成测试：需要运行中的 MySQL 实例。
    /// 运行方式：`RUBRICSPAN_TEST_MYSQL_URL=mysql://root:xxx@127.0.0.1:3306/rubricspan_test cargo test -p rubricspan-storage -- --ignored mysql`
    #[tokio::test]
    #[ignore = "需要 RUBRICSPAN_TEST_MYSQL_URL 指向运行中的 MySQL"]
    async fn mysql_roundtrip_and_stats() {
        let url = std::env::var("RUBRICSPAN_TEST_MYSQL_URL").expect("设置 RUBRICSPAN_TEST_MYSQL_URL 后运行");
        let s = MySqlStorage::open_mysql(&url).await.expect("连接 MySQL 失败");
        s.clear().await.expect("清空失败");
        roundtrip_assertions(&s).await;
    }

    /// 跨后端一致的读写/筛选/覆盖语义断言（memory / sqlite / mysql 共用）。
    async fn roundtrip_assertions(s: &dyn Storage) {
        // 试题：写入两次验证覆盖语义
        for (i, content) in ["题一", "题一·改"].iter().enumerate() {
            assert!(i <= 1); // 覆盖语义循环仅两轮
            s.save_question(Question {
                question_id: "Q1".into(),
                content: (*content).into(),
                subject: "历史".into(),
                total_score: 5.0,
                standard_answer_text: Some("标准答案".into()),
                config_status: ConfigStatus::None,
            })
            .await
            .unwrap();
        }
        s.save_question(Question {
            question_id: "Q2".into(),
            content: "题二".into(),
            subject: "地理".into(),
            total_score: 10.0,
            standard_answer_text: None,
            config_status: ConfigStatus::None,
        })
        .await
        .unwrap();

        // 配置保存会联动更新 config_status
        s.save_config(
            &ScoringConfig { question_id: "Q1".into(), total_score: 5.0, points: vec![], thresholds: None, subject: None, meta: None },
            ConfigStatus::Confirmed,
        )
        .await
        .unwrap();
        let q1 = s.get_question("Q1").await.expect("读取 Q1 失败");
        assert_eq!(q1.config_status, ConfigStatus::Confirmed);
        assert_eq!(q1.standard_answer_text.as_deref(), Some("标准答案"));
        let cfg = s.get_config("Q1").await.expect("读取配置失败");
        assert_eq!(cfg.total_score, 5.0);
        assert!(s.get_config("Q9").await.is_none());

        // 试题筛选
        assert_eq!(s.list_questions(Some("历史")).await.len(), 1);
        assert_eq!(s.list_questions(None).await.len(), 2);

        // 答卷
        let ans = |id: &str, cls: Option<&str>| Answer {
            answer_id: id.into(),
            question_id: "Q1".into(),
            student_id: None,
            class_name: cls.map(str::to_string),
            answer_text: Some("作答".into()),
            source: Some("text".into()),
            ocr_text: None,
        };
        s.save_answer(ans("A1", None)).await.unwrap();
        s.save_answer(ans("A2", Some("一班"))).await.unwrap();
        assert_eq!(s.list_answers(None).await.len(), 2);
        assert_eq!(s.list_answers(Some("Q1")).await.len(), 2);
        assert_eq!(s.list_answers(Some("Q9")).await.len(), 0);
        assert_eq!(s.get_answer("A2").await.unwrap().class_name.as_deref(), Some("一班"));

        // 评分结果 + 覆盖 + 筛选（A2 结果带班级，用于验证班级筛选）
        s.save_result(result("A1", 5.0, json!([point(1, "hit_exact"), point(2, "miss")]))).await.unwrap();
        let mut r2 = result("A2", 2.0, json!([point(1, "miss")]));
        r2.class_name = Some("一班".into());
        s.save_result(r2).await.unwrap();
        s.save_result(result("A1", 4.0, json!([point(1, "hit_semantic")]))).await.unwrap(); // 同 id 覆盖
        assert_eq!(s.list_results(None, None).await.len(), 2);
        assert_eq!(s.list_results(Some("Q1"), None).await.len(), 2);
        assert_eq!(s.list_results(None, Some("一班")).await.len(), 1);
        assert_eq!(s.list_results(Some("Q9"), None).await.len(), 0);

        // 聚合口径
        let st = s.stats().await;
        assert_eq!(st.questions.total, 2);
        assert_eq!(st.questions.by_config_status["confirmed"], 1);
        assert_eq!(st.answers.total, 2);
        assert_eq!(st.scores.total, 2);
        assert_eq!(st.scores.average, 3.0); // (4 + 2) / 2
        // A1（4/5=80%）位于 80-100% 桶（idx 4）；A2（2/5=40%）位于 40-60% 桶（idx 2）
        assert_eq!(st.scores.distribution[4].count, 1);
        assert_eq!(st.scores.distribution[2].count, 1);
        assert_eq!(st.point_hits.iter().filter(|p| p.point_id == 1).map(|p| (p.hit, p.total)).collect::<Vec<_>>(), vec![(1, 2)]);
    }
}