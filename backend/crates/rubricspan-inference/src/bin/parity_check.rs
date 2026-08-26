//! 推理迁移对拍工具：用 Python 运行时（CPU EP）采集的金标验证 Rust 实现一致性。
//!
//! 用法（backend/ 下）：
//! `cargo run -p rubricspan-inference --bin parity_check --release -- \
//!    --golden ../data/goldens/inference_golden.json --models-dir ../models`
//!
//! 验收：has_answer_prob / cosine |diff| ≤ 1e-3；start/end/span 须完全一致。

use std::path::PathBuf;

use anyhow::{bail, Result};
use rubricspan_inference::{OrtBackend, Precision};
use rubricspan_scoring::backend::InferenceBackend;
use serde_json::Value;

fn main() -> Result<()> {
    let mut golden = PathBuf::from("../data/goldens/inference_golden.json");
    let mut models_dir = PathBuf::from("../models");
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--golden" => golden = PathBuf::from(args.next().expect("缺参数")),
            "--models-dir" => models_dir = PathBuf::from(args.next().expect("缺参数")),
            other => bail!("未知参数 {other}"),
        }
    }

    let raw = std::fs::read_to_string(&golden)?;
    let data: Value = serde_json::from_str(&raw)?;
    let backend = OrtBackend::load(&models_dir, Precision::Fp32, true)?;

    let tol = data
        .pointer("/meta/tolerance_prob")
        .and_then(Value::as_f64)
        .unwrap_or(1e-3);

    let mut mrc_fail = 0usize;
    let mrc_total = data["mrc"].as_array().map(|a| a.len()).unwrap_or(0);
    for case in data["mrc"].as_array().cloned().unwrap_or_default() {
        let q = case["query"].as_str().unwrap_or_default();
        let c = case["context"].as_str().unwrap_or_default();
        let want = &case["out"];
        let got = backend.mrc_detail(q, c)?;
        let dp = (got.has_answer_prob - want["has_answer_prob"].as_f64().unwrap_or(0.0)).abs();
        let span_ok = got.start == want["start"].as_u64().unwrap_or(u64::MAX) as usize
            && got.end == want["end"].as_u64().unwrap_or(u64::MAX) as usize
            && got.span == want["span"].as_str().unwrap_or_default();
        if dp > tol || !span_ok {
            mrc_fail += 1;
            println!(
                "[MRC 不一致] q={q:?}\n  prob want={} got={} (Δ{dp:.2e})\n  span want=({}, {}) got=({}, {}, {:?})",
                want["has_answer_prob"],
                got.has_answer_prob,
                want["start"], want["span"], got.start, got.end, got.span,
            );
        }
    }

    let mut sim_fail = 0usize;
    let sim_total = data["similarity"].as_array().map(|a| a.len()).unwrap_or(0);
    for case in data["similarity"].as_array().cloned().unwrap_or_default() {
        let a = case["a"].as_str().unwrap_or_default();
        let b = case["b"].as_str().unwrap_or_default();
        let want = case["out"]["cosine"].as_f64().unwrap_or(0.0);
        let got = backend.similarity(a, b)?.cosine;
        if (got - want).abs() > tol {
            sim_fail += 1;
            println!("[SIM 不一致] a={a:?} want={want} got={got}");
        }
    }

    println!("==== 对拍结果 ====");
    println!("MRC: {}/{mrc_total} 通过；相似度: {}/{} 通过", mrc_total - mrc_fail, sim_total - sim_fail, sim_total);
    if mrc_fail + sim_fail > 0 {
        bail!("存在不一致项，迁移未达验收标准");
    }
    println!("全部通过 ✅");
    Ok(())
}
