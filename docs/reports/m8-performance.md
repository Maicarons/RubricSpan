# M8 模型运行性能调优报告（推理延迟）

> 日期：2026-08-24 · 触发：e2e 全链路评估 36 卷耗时 593s（~16.5s/卷）远超 §13 延迟目标 <500ms/题
> 结论：**总加速 33×（593s → 18s，单卷 ~0.5s）**，主因是修复了"CUDA EP 静默回退 CPU"。

## 1. 定位（P1/P2）

| 现象 | 根因 |
| --- | --- |
| 单次推理 ~0.46s（估算自 e2e 593s / 1280 次推理调用） | 网关全程运行在 **CPU EP**——ORT 注册 CUDA EP 失败后**静默回退 CPU 并返回成功**，代码无从察觉 |
| CUDA 注册失败原因 | `onnxruntime_providers_cuda.dll` 依赖更高版本 CUDA 运行库 DLL 缺失；本机 CUDA 运行库版本偏低 |
| 多次推理串行 | 每得分点对（标准表述 + 每个 alias）逐条 `session.run`，context 反复重新分词 |

关键代码误区：`with_execution_providers([CUDA, CPU])` 在 CUDA 加载失败时**不会返回 Err**——
ORT 跳过失败 EP 继续注册 CPU，session 创建"成功"。因此不能依赖返回值判断 GPU 是否生效
（曾试图用 `is_available()` 预判，该 API 在 ort 2.0-rc.13 不存在；正解是把候选 EP 全部列出）。

## 2. 优化（P3）

### 2.1 修复 EP 选择：CUDA → DirectML → CPU 级联（主收益，~30×）

- `ort` 依赖增加 `directml` feature（Windows D3D12 GPU 后端，无需更高版本 CUDA 运行库）。
- `build_session` 一次列出 `[CUDA, DirectML, CPU]`，ORT 自动跳过加载失败的 EP；
  本机 CUDA 缺库 → `DmlExecutionProvider` 生效（日志已确认 `Successfully registered DmlExecutionProvider`）。
- 部署侧收益：异构机器（无对应 CUDA 运行库）也能自动用 GPU；`RUBRICSPAN_FORCE_CPU=1` 仍可强制 CPU。

### 2.2 候选批处理推理（边际收益，~1.1×）

- `InferenceBackend` 新增 `mrc_extract_batch`（默认实现=逐条等价，实现方可覆盖）；
- `OrtBackend` 覆盖为同 context 多候选一次性 batch（复用解码逻辑 `decode_mrc_span`）；
- `pipeline.rs` 对每得分点候选收集后批量调用。
- 收益占比小（本抽样卷均 18 候选/卷），但真实大题（10 点 × 4 alias ≈ 44 候选）会放大；
  且与单条路径**数值逐位一致**（e2e ScoreCorr 0.9411777974297287 完全相同，parity 143+180 全过）。

## 3. 结果（P4）

| 度量 | 优化前（CPU EP） | 优化后（DirectML + batch） | 加速 |
| --- | --- | --- | --- |
| e2e 36 卷总耗时 | 593s | **18s** | **33×** |
| 单卷平均 | ~16.5s | ~0.5s | 33× |
| 单次推理（含分词/开销） | ~460ms | ~30ms | 15× |
| 对拍一致性 | — | MRC 143/143、similarity 180/180 ✅ | — |
| e2e 指标（ScoreCorr/等价率） | 0.9592 / 0.9739（旧基线） | **0.9412 / 0.9911**（新金标口径） | 指标等价，金标换新 |

> 新金标（仲裁修订后）指标：point_accuracy 0.716（受答案卷含题干原文的评估设计污染，
> 见 bad-cases BC-005，不影响模型判定）、equivalence_credit_rate 0.991、score_corr 0.941。
> 单题延迟 ~0.5s 已贴近 §13 目标 <500ms；真实大题 batch 化后仍有进一步收紧空间。

## 4. 复现

```bash
# EP：无需配置自动级联；验证方式
grep -E "Successfully registered" models/artifacts/gateway_m8.log   # 期望含 DmlExecutionProvider
# 对拍（单条路径一致性）
cd backend && cargo run -p rubricspan-inference --bin parity_check --release -- \
    --golden ../data/goldens/inference_golden.json --models-dir ../models
# e2e
python scripts/m7_e2e_eval.py --sample 36
```

## 5. 后续可选

- ~~更高版本 CUDA 运行库装上后自动优先 CUDA EP（代码无需改动）~~ —— **已修订**：见 §6，CUDA EP 与 DML EP 不能共存于同一会话，已改为逐级探测。
- tokenizer context 预编码复用（同一 context 的多候选不再重复分词——批处理已消除大部分）。
- 高并发时 `Mutex<Session>` 串行化 → 多 session 池化（当前单请求场景无虞）。

## 6. 修订（2026-08-24）：更高版本 CUDA 运行库落地后 DML 与 CUDA 的共存问题

装上更高版本 CUDA 运行库后，§2.1 的 `[CUDA, DirectML, CPU]` 一次列出方案**失效**：
ORT 1.28 拒绝 DML EP 与 CUDA EP 同会话（报错 `DML EP can only be used with CPU EPs.`，
且这是**硬错误、不是跳过**），导致 MRC 会话创建失败、网关回落占位后端。

修订（`rubricspan-inference/src/ort_backend.rs::build_session`）：改为按可用性逐级尝试
`[CUDA, CPU] → [DirectML, CPU] → [CPU]`，对 CUDA/DirectML 使用 `error_on_failure()`
（ort rc.13 的 `ExecutionProviderDispatch`），把"运行库缺失/注册失败"变为可捕获错误后再回落，
避免静默回退把"GPU 未生效"伪装成成功。本机验证：两个模型会话均 `ep="CUDA"` 创建完成，
`/api/score` 全链路 MRC 命中正常（hit_exact、confidence 1.0），进程出现在 `nvidia-smi` compute 列表。