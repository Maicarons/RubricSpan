//! 本地推理基准：MRC 批量抽取 / 相似度兜底 / 端到端评分流水线的耗时统计。
//!
//! 用法（backend/ 下）：
//! ```text
//! cargo run -p rubricspan-inference --bin bench_infer --release -- \
//!     --precision int8 [--force-cpu] [--iters 10]
//! ```
//! 文本取自对拍金标（真实试卷数据），保证各次运行与优化前后可比。

use std::path::PathBuf;
use std::time::Instant;

use anyhow::{bail, Result};
use rubricspan_core::scoring::{ScoringConfig, ScoringPoint};
use rubricspan_inference::{OrtBackend, Precision};
use rubricspan_scoring::backend::InferenceBackend;
use rubricspan_scoring::{pipeline, ScoringSettings};
use serde_json::Value;

struct Timing {
    samples_ms: Vec<f64>,
}

impl Timing {
    fn new() -> Self {
        Self { samples_ms: Vec::new() }
    }

    fn measure<T>(&mut self, f: impl FnOnce() -> T) -> T {
        let t0 = Instant::now();
        let out = f();
        self.samples_ms.push(t0.elapsed().as_secs_f64() * 1e3);
        out
    }
}

fn summarize(label: &str, t: &Timing) {
    let xs = &t.samples_ms;
    let mean = xs.iter().sum::<f64>() / xs.len() as f64;
    let mut sorted = xs.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p50 = sorted[sorted.len() / 2];
    println!("{label:<34} n={:<3} mean={mean:9.2}ms  p50={p50:9.2}ms", xs.len());
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let mut models_dir = PathBuf::from("../models");
    let mut precision = Precision::Int8;
    let mut force_cpu = false;
    let mut iters = 10usize;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--models-dir" => models_dir = PathBuf::from(args.next().expect("缺参数")),
            "--precision" => precision = args.next().expect("缺参数").parse()?,
            "--force-cpu" => force_cpu = true,
            "--iters" => iters = args.next().expect("缺参数").parse()?,
            other => bail!("未知参数 {other}"),
        }
    }

    // ---- 样本文本：取自对拍金标（真实试卷长答案 + 得分点表述）----
    let raw = std::fs::read_to_string("../data/goldens/inference_golden.json")
        .map_err(|e| anyhow::anyhow!("读取金标失败（请在 backend/ 目录下运行）：{e}"))?;
    let data: Value = serde_json::from_str(&raw)?;
    let mrc_cases = data["mrc"].as_array().cloned().unwrap_or_default();
    if mrc_cases.len() < 12 {
        bail!("金标样本不足 12 条");
    }
    let answers: Vec<String> = mrc_cases
        .iter()
        .take(6)
        .map(|c| c["context"].as_str().unwrap_or_default().to_string())
        .collect();
    let point_texts: Vec<String> = mrc_cases
        .iter()
        .skip(6)
        .take(12)
        .map(|c| c["query"].as_str().unwrap_or_default().to_string())
        .filter(|s| !s.is_empty())
        .collect();
    // 每个答案配 4 个候选点做端到端流水线；批量 MRC 用 8 候选
    let candidates8: Vec<String> = point_texts.iter().take(8).cloned().collect();

    println!("==== 加载模型（precision={precision:?}, force_cpu={force_cpu}）====");
    let t0 = Instant::now();
    let backend = OrtBackend::load(&models_dir, precision, force_cpu)?;
    println!("加载耗时 {:.1}s", t0.elapsed().as_secs_f64());

    let answer0 = answers[0].clone();
    let ep_note = if force_cpu { "CPU" } else { "auto(探测)" };

    // ---- 预热（不计入统计）----
    let _ = backend.mrc_extract_batch(&candidates8[..1], &answer0)?;
    let _ = backend.similarity(&point_texts[0], &answer0)?;

    // ---- 1. MRC 批量抽取（k=1 / k=8 候选）----
    let mut t_mrc1 = Timing::new();
    for _ in 0..iters {
        t_mrc1.measure(|| backend.mrc_extract_batch(&candidates8[..1], &answer0).unwrap());
    }
    let mut t_mrc8 = Timing::new();
    for _ in 0..iters {
        t_mrc8.measure(|| backend.mrc_extract_batch(&candidates8, &answer0).unwrap());
    }

    // ---- 2. 相似度兜底：旧路径（每点两次 [1,L] 编码）----
    let sim_points = &candidates8;
    let mut t_sim_legacy = Timing::new();
    for _ in 0..iters {
        t_sim_legacy.measure(|| {
            for p in sim_points {
                let _ = backend.similarity(p, &answer0).unwrap();
            }
        });
    }

    // ---- 3. 端到端评分流水线（4 点全链路：选项规则跳过 → 两阶段 MRC + 兜底）----
    let config = make_config(point_texts.iter().take(4).cloned().collect());
    let mut t_pipeline = Timing::new();
    for _ in 0..iters {
        t_pipeline.measure(|| {
            pipeline::score_answer_configured(
                &config,
                &answer0,
                &backend,
                None,
                ScoringSettings::default(),
            )
            .unwrap()
        });
    }

    println!("==== 结果（EP={ep_note}, iter={iters}）====");
    summarize("mrc_batch(k=1)", &t_mrc1);
    summarize("mrc_batch(k=8)", &t_mrc8);
    summarize("similarity x8 (逐条)", &t_sim_legacy);
    summarize("pipeline (4 points)", &t_pipeline);
    Ok(())
}

fn make_config(texts: Vec<String>) -> ScoringConfig {
    let points: Vec<ScoringPoint> = texts
        .into_iter()
        .enumerate()
        .map(|(i, t)| ScoringPoint { point_id: i as i64 + 1, point_text: t, weight: 2.0, aliases: vec![] })
        .collect();
    ScoringConfig {
        question_id: "BENCH-001".into(),
        total_score: points.len() as f64 * 2.0,
        subject: None,
        points,
        thresholds: None,
        meta: None,
    }
}
