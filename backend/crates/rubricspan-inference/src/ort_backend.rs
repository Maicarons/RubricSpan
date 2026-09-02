//! ONNX Runtime 原生推理后端（技术方案 §10.1 · 方案 A 落地）。
//!
//! 职责与旧 Python 运行时（backend/runtime/model_runtime.py，已于 M8 移除）逐步对齐：
//! - MRC：BERT WordPiece 分词（`tokenizers` 官方 Rust 库，直接加载 tokenizer.json）
//!   → ONNX 推理 → log_softmax / null-prob sigmoid / 最优 span 搜索 → 字符级闭区间偏移；
//! - 相似度：单句编码 → attention-mask 平均池化 → 余弦；
//! - 执行提供者：CUDA → DirectML → CPU 逐级探测（CUDA/DML 注册失败即回落下一级，
//!   `RUBRICSPAN_FORCE_CPU=1` 可强制 CPU）；INT8 模型经 `RUBRICSPAN_MODEL_PRECISION=int8` 选择。
//!
//! **偏移契约**（与 rubricspan-scoring 及训练侧一致）：start/end 为学生答案内的
//! 字符级闭区间；`tokenizers` 的 offsets 为字符级半开区间，此处做同样换算。

use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::time::Instant;

use anyhow::{anyhow, Context, Result};
use rubricspan_scoring::backend::{InferenceBackend, MrcOutput, SimilarityOutput};
use tokenizers::tokenizer::{TruncationDirection, TruncationParams, TruncationStrategy};
use tokenizers::Tokenizer;

/// `RUBRICSPAN_PROFILE=1` 时输出推理各阶段耗时（perf 剖析用，默认关闭、零开销）。
fn profiling() -> bool {
    std::env::var_os("RUBRICSPAN_PROFILE").map(|v| v == "1").unwrap_or(false)
}

/// 阶段计时包装：`RUBRICSPAN_PROFILE=1` 时以 tracing info 输出 `phase/ms`。
fn timed<T>(label: &'static str, f: impl FnOnce() -> T) -> T {
    let t0 = Instant::now();
    let out = f();
    if profiling() {
        tracing::info!(phase = label, ms = t0.elapsed().as_secs_f64() * 1e3, "perf");
    }
    out
}

/// 与训练侧 featurize 一致的序列长度上限。
const MAX_SEQ_LEN: usize = 512;
/// 最优 span 搜索的最大 token 跨度（对应 Python `min(i + MAX_SPAN_TOKENS, hi+1)` 开区间右端）。
const MAX_SPAN_TOKENS: usize = 64;
/// 相似度模型编码长度上限。
const SIM_MAX_LEN: usize = 128;
/// 相似度模型输出维度（text2vec-base-chinese）。
const SIM_DIM: usize = 768;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Precision {
    Fp32,
    /// GPU 部署档（较新架构 Tensor Core、显存减半）；非对拍契约目标，缺失回退 fp32。
    /// 产物由 scripts/export_fp16.py 生成（模型不入库）。
    Fp16,
    Int8,
}

impl FromStr for Precision {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Self> {
        match s.trim().to_ascii_lowercase().as_str() {
            "fp16" => Ok(Precision::Fp16),
            "int8" => Ok(Precision::Int8),
            _ => Ok(Precision::Fp32),
        }
    }
}

/// 一个模型的 ONNX 会话池 + 分词器。ort rc.13 的 `run()` 需 `&mut`，共享会话
/// 以 Mutex 包裹；池化（`RUBRICSPAN_SESSION_POOL`，默认 2）让并发请求经
/// round-robin 落在不同会话上并行推理，消除"全进程单锁把 GPU 串行化"的吞吐瓶颈
/// （GPU 侧多会话可重叠 H2D 拷贝、CUDA 内核调度与 CPU 侧准备/解码的交替空档）。
struct Model {
    sessions: Vec<std::sync::Mutex<ort::session::Session>>,
    next: std::sync::atomic::AtomicUsize,
    tokenizer: Tokenizer,
    /// 输入是否包含 token_type_ids（BERT 类模型为 true）。
    has_token_type_ids: bool,
}

impl Model {
    /// `pair_truncation=true`：MRC 句对编码（only_second@512，与训练侧 featurize 一致）；
    /// `false`：相似度单句编码（longest_first@128，与旧运行时 `_encode_mean` 一致）。
    fn load(
        onnx_path: &Path,
        tokenizer_dir: &Path,
        force_cpu: bool,
        max_len: usize,
        pair_truncation: bool,
        pool_size: usize,
    ) -> Result<Self> {
        let mut tokenizer = Tokenizer::from_file(tokenizer_dir.join("tokenizer.json"))
            .map_err(|e| anyhow!("分词器加载失败 {}: {e}", tokenizer_dir.display()))?;
        tokenizer
            .with_truncation(Some(TruncationParams {
                max_length: max_len,
                stride: 0,
                strategy: if pair_truncation {
                    TruncationStrategy::OnlySecond
                } else {
                    TruncationStrategy::LongestFirst
                },
                direction: TruncationDirection::Right,
            }))
            .map_err(|e| anyhow!("分词器截断配置失败：{e}"))?;

        let mut sessions = Vec::with_capacity(pool_size);
        for i in 0..pool_size {
            let session = build_session(onnx_path, force_cpu)
                .with_context(|| format!("ONNX 会话创建失败 {}", onnx_path.display()))?;
            tracing::info!(session = %onnx_path.display(), pool = i, "ONNX 会话创建完成");
            sessions.push(std::sync::Mutex::new(session));
        }
        let has_token_type_ids = sessions[0]
            .lock()
            .expect("ONNX 会话锁中毒")
            .inputs()
            .iter()
            .any(|o| o.name() == "token_type_ids");
        Ok(Self {
            sessions,
            next: std::sync::atomic::AtomicUsize::new(0),
            tokenizer,
            has_token_type_ids,
        })
    }

    /// 取一个空闲倾向的会话：round-robin 选池内索引，锁住该会话执行推理。
    fn acquire(&self) -> std::sync::MutexGuard<'_, ort::session::Session> {
        use std::sync::atomic::Ordering;
        let i = self.next.fetch_add(1, Ordering::Relaxed) % self.sessions.len();
        self.sessions[i].lock().expect("ONNX 会话锁中毒")
    }

    fn pad_id(&self) -> i64 {
        self.tokenizer.token_to_id("[PAD]").map(|x| x as i64).unwrap_or(0)
    }
}

/// 创建 ONNX 会话：CUDA → DirectML（Windows D3D12）→ 纯 CPU 逐级探测。
///
/// 旧设计把 `[CUDA, DirectML, CPU]` 一次性列出，依赖"ORT 对加载失败的 EP 自动跳过"；
/// 但 ORT 1.28 不允许 **DML 与 CUDA 共存于同一会话**（会直接报错
/// "DML EP can only be used with CPU EPs."，而非跳过），因此在 CUDA 运行库真正可用后
/// 会话创建反而会失败。这里改为按可用性逐级尝试：给 CUDA/DirectML 加 `error_on_failure`
/// 让"运行库缺失/注册失败"变成可捕获错误，任一 EP 注册失败即换下一级，避免静默回退
/// 把"GPU 未生效"伪装成成功；启动日志打印实际生效的 EP 便于部署侧确认。
fn build_session(onnx_path: &Path, force_cpu: bool) -> Result<ort::session::Session> {
    use ort::ep::{ArenaExtendStrategy, CPU, CUDA, DirectML};

    let threads = std::thread::available_parallelism()
        .map(|n| n.get().clamp(2, 8))
        .unwrap_or(4);
    let s = |e: String| anyhow!("{e}");
    let opts = ort::session::builder::GraphOptimizationLevel::Level3;

    // 尝试用给定 EP 列表创建会话；注册失败（error_on_failure）或初始化失败均返回 Err。
    let attempt = |eps: Vec<ort::ep::ExecutionProviderDispatch>| -> Result<ort::session::Session> {
        let session = ort::session::Session::builder()
            .map_err(|e| s(e.to_string()))?
            .with_optimization_level(opts)
            .map_err(|e| s(e.to_string()))?
            .with_intra_threads(threads)
            .map_err(|e| s(e.to_string()))?
            .with_execution_providers(eps)
            .map_err(|e| s(e.to_string()))?
            .commit_from_file(onnx_path)
            .map_err(|e| s(e.to_string()))?;
        Ok(session)
    };

    if !force_cpu {
        // CUDA arena 默认按 2 次幂扩展（单次跳 1GB）；cuDNN 与 ORT 的某些组合下，
        // 大块扩展后的 cuDNN 初始化会硬中止（exit 0xffffffff，无 panic），改为按需小步扩展规避。
        match attempt(
            vec![CUDA::default()
                .with_arena_extend_strategy(ArenaExtendStrategy::SameAsRequested)
                .build()
                .error_on_failure(), CPU::default().build()],
        ) {
            Ok(session) => return Ok(session),
            Err(e) => tracing::warn!(session = %onnx_path.display(), error = %e, "CUDA EP 不可用，回落 DirectML"),
        }
        match attempt( vec![DirectML::default().build().error_on_failure(), CPU::default().build()]) {
            Ok(session) => return Ok(session),
            Err(e) => tracing::warn!(session = %onnx_path.display(), error = %e, "DirectML EP 不可用，回落 CPU"),
        }
    }
    attempt(vec![CPU::default().build()])
}

/// 选定精度对应的 ONNX 文件（int8 缺失时回落 fp32 并告警）。
fn resolve_onnx(dir: &Path, precision: Precision) -> PathBuf {
    let fp32 = dir.join("model.onnx");
    match precision {
        Precision::Fp32 => fp32,
        Precision::Fp16 => {
            let fp16 = dir.join("model.fp16.onnx");
            if fp16.exists() {
                fp16
            } else {
                tracing::warn!("FP16 模型缺失，回落 FP32：{}", fp16.display());
                fp32
            }
        }
        // 仅动态量化（model.int8.onnx，CPU 部署档）。静态 QDQ（model.int8.static.onnx）
        // 已在 ort 2.0-rc.13 CUDA EP 验证为数值错误（MRC 1/143 过 1e-3），
        // 且 CPU 上极慢（~10s/流水线），故不进入解析链；详见 scripts/export_static_int8.py。
        Precision::Int8 => {
            let int8 = dir.join("model.int8.onnx");
            if int8.exists() {
                int8
            } else {
                tracing::warn!("INT8 模型缺失，回落 FP32：{}", int8.display());
                fp32
            }
        }
    }
}

/// 编码 (query, context) 对并补齐到固定长度。
struct Featurized {
    ids: Vec<i64>,
    mask: Vec<i64>,
    types: Vec<i64>,
    offsets: Vec<(usize, usize)>,
    seq_ids: Vec<Option<usize>>,
}

fn pad_to_len(mut v: Vec<i64>, pad_id: i64, len: usize) -> Vec<i64> {
    if v.len() > len {
        v.truncate(len);
    } else {
        v.resize(len, pad_id);
    }
    v
}

fn featurize_pair(model: &Model, query: &str, context: &str) -> Result<Featurized> {
    let enc = model
        .tokenizer
        .encode((query.to_string(), context.to_string()), true)
        .map_err(|e| anyhow!("分词失败：{e}"))?;

    Ok(Featurized {
        ids: pad_to_len(enc.get_ids().iter().map(|&x| x as i64).collect(), model.pad_id(), MAX_SEQ_LEN),
        mask: pad_to_len(enc.get_attention_mask().iter().map(|&x| x as i64).collect(), 0, MAX_SEQ_LEN),
        types: pad_to_len(enc.get_type_ids().iter().map(|&x| x as i64).collect(), 0, MAX_SEQ_LEN),
        offsets: enc.get_offsets().to_vec(),
        seq_ids: enc.get_sequence_ids(),
    })
}

/// 数值稳定的 log_softmax（与 Python `_log_softmax` 语义一致）。
fn log_softmax_stable(xs: &[f32]) -> Vec<f64> {
    let xs: Vec<f64> = xs.iter().map(|&x| x as f64).collect();
    let m = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let exps: Vec<f64> = xs.iter().map(|&x| (x - m).exp()).collect();
    let z: f64 = exps.iter().sum();
    exps.iter().map(|&e| e.ln() - z.ln()).collect()
}

fn round6(x: f64) -> f64 {
    (x * 1e6).round() / 1e6
}

/// 字节偏移 → 字符索引映射表：`m[byte_pos]` = 该字节所属字符的字符序号；
/// 末位 `m[len]` = 总字符数（供半开区间右端换算）。
fn byte_to_char(s: &str) -> Vec<usize> {
    let mut m = vec![0usize; s.len() + 1];
    let mut ci = 0usize;
    for (bi, ch) in s.char_indices() {
        for slot in &mut m[bi..bi + ch.len_utf8()] {
            *slot = ci;
        }
        ci += 1;
    }
    m[s.len()] = ci;
    m
}

/// 从 start/end logits 解码最优 span（与训练侧 Python 参考逐行一致）。
///
/// 返回 (has_answer_prob, start_char, end_char_closed)。offsets 为 **字节**偏移，
/// 经 [`byte_to_char`] 换算为字符级（契约要求）。
#[allow(clippy::needless_range_loop)]
fn decode_mrc_span(
    seq_ids: &[Option<usize>],
    offsets: &[(usize, usize)],
    s_probs: &[f64],
    e_probs: &[f64],
    context: &str,
) -> (f64, usize, usize) {
    let ctx: Vec<usize> = seq_ids
        .iter()
        .enumerate()
        .filter(|(_, s)| **s == Some(1))
        .map(|(i, _)| i)
        .collect();
    if ctx.is_empty() {
        return (0.0, 0, 0);
    }
    let (lo, hi) = (ctx[0], ctx[ctx.len() - 1]);
    let null_logprob = s_probs[0] + e_probs[0];

    let mut best_score = -1e12f64;
    let (mut best_i, mut best_j) = (lo, lo);
    for i in lo..=hi {
        let j_last = (i + MAX_SPAN_TOKENS - 1).min(hi);
        for j in i..=j_last {
            let score = s_probs[i] + e_probs[j];
            if score > best_score {
                best_score = score;
                best_i = i;
                best_j = j;
            }
        }
    }
    let has_answer_prob = 1.0 / (1.0 + (null_logprob - best_score).exp());

    let chars: Vec<char> = context.chars().collect();
    let n = chars.len();
    // tokenizers 原生 offsets 是**字节**偏移；契约要求字符级偏移，此处经字节→字符映射换算。
    let bcm = byte_to_char(context);
    let start_byte = offsets.get(best_i).map(|o| o.0).unwrap_or(0);
    let end_byte_excl = offsets.get(best_j).map(|o| o.1).unwrap_or(start_byte);
    let start_char = bcm
        .get(start_byte.min(context.len()))
        .copied()
        .unwrap_or(0)
        .min(n);
    let end_char_excl = bcm
        .get(end_byte_excl.min(context.len()))
        .copied()
        .unwrap_or(start_char)
        .min(n);
    // 契约：闭区间 end（offsets 为半开区间，故 -1 换算），与 Python 端一致。
    let end_closed = end_char_excl.saturating_sub(1).max(start_char);
    (round6(has_answer_prob), start_char, end_closed)
}

/// MRC 单次抽取的完整明细（trait 输出只含评分所需字段）。
#[derive(Debug, Clone)]
pub struct MrcDetail {
    pub has_answer_prob: f64,
    pub start: usize,
    pub end: usize,
    pub span: String,
}

/// ONNX Runtime 原生推理后端（MRC 抽取 + 相似度兜底）。
pub struct OrtBackend {
    mrc: Model,
    sim: Model,
}

impl OrtBackend {
    /// 从模型产物目录加载会话池（每个模型 `RUBRICSPAN_SESSION_POOL` 个会话，
    /// 默认 2，范围 1..=4；1 即旧版全串行行为）。目录布局见 contracts/model-artifacts.md：
    /// `{dir}/mrc/{model.onnx,tokenizer/}`、`{dir}/similarity/{model.onnx,tokenizer/}`。
    ///
    /// 会话池会把显存占用乘以池大小（int8 ~100MB/会话可接受；FP32 大模型在
    /// 显存吃紧场景请设 1 或 2）。
    pub fn load(models_dir: &Path, precision: Precision, force_cpu: bool) -> Result<Self> {
        let pool_size = std::env::var("RUBRICSPAN_SESSION_POOL")
            .ok()
            .and_then(|v| v.trim().parse::<usize>().ok())
            .unwrap_or(2)
            .clamp(1, 4);
        let mrc_onnx = resolve_onnx(&models_dir.join("mrc"), precision);
        let sim_onnx = resolve_onnx(&models_dir.join("similarity"), precision);
        let mrc = Model::load(&mrc_onnx, &models_dir.join("mrc/tokenizer"), force_cpu, MAX_SEQ_LEN, true, pool_size)?;
        let sim = Model::load(&sim_onnx, &models_dir.join("similarity/tokenizer"), force_cpu, SIM_MAX_LEN, false, pool_size)?;
        tracing::info!(
            mrc = %mrc_onnx.display(),
            sim = %sim_onnx.display(),
            pool_size,
            force_cpu,
            "OrtBackend 加载完成"
        );
        Ok(Self { mrc, sim })
    }

    /// MRC 抽取：返回字符级片段与有答概率（与旧 Python 实现逐步对齐）。
    pub fn mrc_detail(&self, query: &str, context: &str) -> Result<MrcDetail> {
        if context.is_empty() {
            return Ok(MrcDetail { has_answer_prob: 0.0, start: 0, end: 0, span: String::new() });
        }
        let f = featurize_pair(&self.mrc, query, context)?;
        let (start_logits, end_logits) = self.run_mrc_session(&f)?;
        let s_probs = log_softmax_stable(&start_logits);
        let e_probs = log_softmax_stable(&end_logits);
        let (prob, start_char, end_closed) =
            decode_mrc_span(&f.seq_ids, &f.offsets, &s_probs, &e_probs, context);
        let chars: Vec<char> = context.chars().collect();
        let upper = (end_closed + 1).min(chars.len());
        let span: String = chars[start_char..upper].iter().collect();
        Ok(MrcDetail {
            has_answer_prob: prob,
            start: start_char,
            end: end_closed,
            span,
        })
    }

    /// 批量 MRC 抽取：同一学生答案上多个候选一次 batch 推理（M8 性能优化）。
    /// 与逐条 [`mrc_detail`](Self::mrc_detail) 数值一致（同 EP 同模型）。
    pub fn mrc_extract_batch_impl(&self, candidates: &[String], context: &str) -> Result<Vec<MrcOutput>> {
        use ort::value::Tensor;

        if context.is_empty() {
            return Ok(vec![MrcOutput { has_answer_prob: 0.0, start: 0, end: 0 }; candidates.len()]);
        }
        let n = candidates.len();
        let feats: Vec<Featurized> = timed("mrc.tokenize", || {
            candidates
                .iter()
                .map(|c| featurize_pair(&self.mrc, c, context))
                .collect::<Result<_>>()
        })?;

        let inputs: Vec<(&str, Tensor<i64>)> = timed("mrc.tensor", || {
            let mut ids: Vec<i64> = Vec::with_capacity(n * MAX_SEQ_LEN);
            let mut mask: Vec<i64> = Vec::with_capacity(n * MAX_SEQ_LEN);
            let mut types: Vec<i64> = Vec::with_capacity(n * MAX_SEQ_LEN);
            for f in &feats {
                ids.extend_from_slice(&f.ids);
                mask.extend_from_slice(&f.mask);
                types.extend_from_slice(&f.types);
            }
            let mut inputs: Vec<(&str, Tensor<i64>)> = vec![
                ("input_ids", Tensor::from_array(([n, MAX_SEQ_LEN], ids))?),
                ("attention_mask", Tensor::from_array(([n, MAX_SEQ_LEN], mask))?),
            ];
            if self.mrc.has_token_type_ids {
                inputs.push(("token_type_ids", Tensor::from_array(([n, MAX_SEQ_LEN], types))?));
            }
            Ok::<_, anyhow::Error>(inputs)
        })?;
        let mut session = self.mrc.acquire();
        let outputs = timed("mrc.run", || session.run(inputs))?;
        let take = |name: &str| -> Result<Vec<f32>> {
            let (_, data) = outputs
                .get(name)
                .ok_or_else(|| anyhow!("MRC 模型缺少输出 {name}"))?
                .try_extract_tensor::<f32>()?;
            Ok(data.to_vec())
        };
        let start_logits = take("start_logits")?;
        let end_logits = take("end_logits")?;

        let out = timed("mrc.decode", || {
            let mut out = Vec::with_capacity(n);
            for (i, f) in feats.iter().enumerate() {
            let s0 = i * MAX_SEQ_LEN;
            let s_probs = log_softmax_stable(&start_logits[s0..s0 + MAX_SEQ_LEN]);
            let e_probs = log_softmax_stable(&end_logits[s0..s0 + MAX_SEQ_LEN]);
            let (prob, start_char, end_closed) =
                decode_mrc_span(&f.seq_ids, &f.offsets, &s_probs, &e_probs, context);
                out.push(MrcOutput { has_answer_prob: prob, start: start_char, end: end_closed });
            }
            out
        });
        Ok(out)
    }

    /// 运行 MRC 会话，返回 (start_logits, end_logits)，各长 MAX_SEQ_LEN。
    fn run_mrc_session(&self, f: &Featurized) -> Result<(Vec<f32>, Vec<f32>)> {
        use ort::value::Tensor;

        let mut inputs: Vec<(&str, Tensor<i64>)> = vec![
            ("input_ids", Tensor::from_array(([1usize, MAX_SEQ_LEN], f.ids.clone()))?),
            ("attention_mask", Tensor::from_array(([1usize, MAX_SEQ_LEN], f.mask.clone()))?),
        ];
        if self.mrc.has_token_type_ids {
            inputs.push(("token_type_ids", Tensor::from_array(([1usize, MAX_SEQ_LEN], f.types.clone()))?));
        }
        let mut session = self.mrc.acquire();
        let outputs = session.run(inputs)?;
        let take = |name: &str| -> Result<Vec<f32>> {
            let (_, data) = outputs
                .get(name)
                .ok_or_else(|| anyhow!("MRC 模型缺少输出 {name}"))?
                .try_extract_tensor::<f32>()?;
            Ok(data.to_vec())
        };
        Ok((take("start_logits")?, take("end_logits")?))
    }

    /// 批量单文本编码（相似度模型）：多文本合一次 `[n, L]` 推理，L 为批内最长
    /// 实际 token 数（≤ SIM_MAX_LEN，截断已由分词器配置保证）。
    ///
    /// **数值一致性**：attention_mask 屏蔽 pad 键，真实位置的输出向量与 padding
    /// 长度无关；池化只按各自行 mask>0 的位置加权，因此与逐条定长 128 编码
    /// 严格一致（对拍金标覆盖此断言）。学生答案向量在批内只算一次。
    fn encode_mean_batch(&self, texts: &[&str]) -> Result<Vec<Vec<f64>>> {
        use ort::value::Tensor;

        let n = texts.len();
        if n == 0 {
            return Ok(Vec::new());
        }
        let encs: Vec<_> = timed("sim.tokenize", || {
            texts.iter()
                .map(|t| {
                    self.sim
                        .tokenizer
                        .encode(t.to_string(), true)
                        .map_err(|e| anyhow!("分词失败：{e}"))
                })
                .collect::<Result<_>>()
        })?;
        let len = |i: usize| encs[i].get_ids().len();
        let max_len = (0..n).map(len).max().unwrap_or(1).max(1);

        let (ids, mask, types) = timed("sim.tensor", || {
            let pad = self.sim.pad_id();
            let mut ids: Vec<i64> = Vec::with_capacity(n * max_len);
            let mut mask: Vec<i64> = Vec::with_capacity(n * max_len);
            let mut types: Vec<i64> = Vec::with_capacity(n * max_len);
            for enc in &encs {
                let l = enc.get_ids().len();
                ids.extend(enc.get_ids().iter().map(|&x| x as i64));
                ids.resize(ids.len() + (max_len - l), pad);
                mask.extend(enc.get_attention_mask().iter().map(|&x| x as i64));
                mask.resize(mask.len() + (max_len - l), 0);
                types.extend(enc.get_type_ids().iter().map(|&x| x as i64));
                types.resize(types.len() + (max_len - l), 0);
            }
            (ids, mask, types)
        });

        let inputs: Vec<(&str, Tensor<i64>)> = timed("sim.tensor2", || {
            let mut inputs: Vec<(&str, Tensor<i64>)> = vec![
                ("input_ids", Tensor::from_array(([n, max_len], ids))?),
                ("attention_mask", Tensor::from_array(([n, max_len], mask))?),
            ];
            if self.sim.has_token_type_ids {
                inputs.push(("token_type_ids", Tensor::from_array(([n, max_len], types))?));
            }
            Ok::<_, anyhow::Error>(inputs)
        })?;
        let mut session = self.sim.acquire();
        let out_name = session
            .outputs()
            .first()
            .map(|o| o.name().to_string())
            .ok_or_else(|| anyhow!("相似度模型无输出"))?;
        let outputs = timed("sim.run", || session.run(inputs))?;
        let (_, data) = outputs
            .get(&out_name)
            .ok_or_else(|| anyhow!("相似度模型缺少输出 {out_name}"))?
            .try_extract_tensor::<f32>()?;

        // [n, max_len, SIM_DIM] → 逐行按各自 mask 加权均值池化
        let out = timed("sim.pool", || {
            let mut out = Vec::with_capacity(n);
        for (i, enc) in encs.iter().enumerate() {
            let real = enc.get_ids().len().min(max_len);
            let denom = real as f64;
            let mut vec = vec![0.0f64; SIM_DIM];
            if denom > 0.0 {
                let row = &data[i * max_len * SIM_DIM..(i * max_len + real) * SIM_DIM];
                for chunk in row.chunks_exact(SIM_DIM) {
                    for (v, &x) in vec.iter_mut().zip(chunk) {
                        *v += x as f64;
                    }
                }
                for v in &mut vec {
                    *v /= denom;
                }
            }
                out.push(vec);
            }
            out
        });
        Ok(out)
    }

    fn cosine(a: &[f64], b: &[f64]) -> f64 {
        let dot: f64 = a.iter().zip(b).map(|(x, y)| x * y).sum();
        let na: f64 = a.iter().map(|x| x * x).sum::<f64>().sqrt();
        let nb: f64 = b.iter().map(|x| x * x).sum::<f64>().sqrt();
        dot / (na * nb + 1e-9)
    }

    /// 临时调试：打印单文本编码的中间量（对拍用）。
    pub fn debug_encode(&self, text: &str) -> Result<()> {
        use ort::value::Tensor;

        let enc = self.sim.tokenizer.encode(text.to_string(), true).map_err(|e| anyhow!("分词失败：{e}"))?;
        let ids = pad_to_len(enc.get_ids().iter().map(|&x| x as i64).collect(), self.sim.pad_id(), SIM_MAX_LEN);
        let mask = pad_to_len(enc.get_attention_mask().iter().map(|&x| x as i64).collect(), 0, SIM_MAX_LEN);
        println!("ids_len={} mask_sum={} ids[:8]={:?} ids[-2:]={:?}", enc.get_ids().len(), mask.iter().sum::<i64>(), &ids[..8.min(ids.len())], &ids[ids.len()-2..]);
        println!("pad_id={} types[:6]={:?}", self.sim.pad_id(), &enc.get_type_ids()[..6.min(enc.get_type_ids().len())]);

        let mut inputs: Vec<(&str, Tensor<i64>)> = vec![
            ("input_ids", Tensor::from_array(([1usize, SIM_MAX_LEN], ids.clone()))?),
            ("attention_mask", Tensor::from_array(([1usize, SIM_MAX_LEN], mask.clone()))?),
        ];
        if self.sim.has_token_type_ids {
            let types = pad_to_len(enc.get_type_ids().iter().map(|&x| x as i64).collect(), 0, SIM_MAX_LEN);
            inputs.push(("token_type_ids", Tensor::from_array(([1usize, SIM_MAX_LEN], types))?));
        }
        let mut session = self.sim.acquire();
        let out_name = session.outputs().first().map(|o| o.name().to_string()).ok_or_else(|| anyhow!("无输出"))?;
        println!("out_name={out_name}");
        let outputs = session.run(inputs)?;
        let (_, data) = outputs.get(&out_name).ok_or_else(|| anyhow!("缺输出"))?.try_extract_tensor::<f32>()?;
        println!("data_len={} seq={}", data.len(), data.len() / SIM_DIM);
        println!("hidden[0][:5]={:?}", &data[..5]);
        println!("hidden[last_real][..5]={:?}", &data[(mask.iter().sum::<i64>() as usize - 1) * SIM_DIM..(mask.iter().sum::<i64>() as usize - 1) * SIM_DIM + 5]);
        Ok(())
    }
}

impl InferenceBackend for OrtBackend {
    fn mrc_extract(&self, candidate: &str, student_answer: &str) -> Result<MrcOutput> {
        let d = self.mrc_detail(candidate, student_answer)?;
        Ok(MrcOutput { has_answer_prob: d.has_answer_prob, start: d.start, end: d.end })
    }

    fn mrc_extract_batch(
        &self,
        candidates: &[String],
        student_answer: &str,
    ) -> Result<Vec<MrcOutput>> {
        self.mrc_extract_batch_impl(candidates, student_answer)
    }

    fn similarity(&self, point_text: &str, student_answer: &str) -> Result<SimilarityOutput> {
        let vecs = self.encode_mean_batch(&[point_text, student_answer])?;
        Ok(SimilarityOutput { cosine: round6(Self::cosine(&vecs[0], &vecs[1])) })
    }

    /// 学生答案编码一次 + 全部得分点合批一次推理（性能优化，数值同逐条）。
    fn similarity_batch(
        &self,
        point_texts: &[String],
        student_answer: &str,
    ) -> Result<Vec<SimilarityOutput>> {
        let mut texts: Vec<&str> = Vec::with_capacity(point_texts.len() + 1);
        texts.push(student_answer);
        texts.extend(point_texts.iter().map(|s| s.as_str()));
        let vecs = self.encode_mean_batch(&texts)?;
        let ans = &vecs[0];
        Ok(vecs[1..]
            .iter()
            .map(|v| SimilarityOutput { cosine: round6(Self::cosine(ans, v)) })
            .collect())
    }
}
