# 里程碑 M3 评审 · 模型运行时与推理集成

> 评审日期：2026-08-23
> 状态：**PASS（运行时集成完成；/similarity 接口随 M2 相似度模型导出后启用）**

## 1. M3 目标

将训练侧已验证的推理逻辑（MRC 多候选抽取、句向量相似度、OCR、标准答案解析）
封装为**同机 Python 模型运行时**（`backend/runtime/model_runtime.py`），通过 localhost
JSON 接口向 Rust 网关提供张量原语；Rust 侧（`rubricspan-server`）负责 HTTP、校验、
存储与评分编排，按技术方案 §10.1 完成"训练↔推理"一致性集成。

## 2. 交付内容

### 2.1 模型运行时（Python）

- 端点：`GET /health`、`POST /mrc`、`POST /similarity`、`POST /ocr`、`POST /parse`。
- 模型懒加载单例（`MODELS`），ONNX 推理通过
  `providers=["CUDAExecutionProvider","CPUExecutionProvider"]` 调用 —— **推理优先 GPU**。
- `/mrc`：复用训练侧 MRC 解码（字符级偏移 start/end 闭区间），`has_answer_prob` 阈值门控。
- `/ocr`：RapidOCR，返回 `OcrResult`（含 `confidence` / `low_confidence` 标记）。
- `/parse`：调用 LLM（OpenAI 兼容端点）将标准答案文本拆分为 `ScoringConfig`，
  已实测返回正确分解（如"发生在1898年 / 又称百日维新" + 等价表述别名）。
- `/similarity`：依赖 M2 相似度 ONNX，模型就绪后自动可用。

### 2.2 Rust 网关集成（`rubricspan-inference` / `rubricspan-server`）

- `RuntimeBackend` 实现 `InferenceBackend`（MRC / 相似度同步调用）；
  `RuntimeClient` 供 `/api/ocr`、`/api/standard-answer/parse` 异步调用。
- 8 组路由全部就绪：`/api/questions`、`/api/standard-answer`(PUT+GET)、
  `/api/standard-answer/parse`、`/api/answers`、`/api/ocr`、`/api/score`、
  `/api/results`、`/api/health`。
- 评分在 `spawn_blocking` 中同步执行，避免阻塞 tokio 工作线程。

## 3. 关键修复（本里程碑内）

| 问题 | 现象 | 修复 |
| --- | --- | --- |
| `/mrc` 抽取 `float - tuple` | `has_answer_prob = 1/(1+e^(null - span_score))` 中 `span_score` 被错赋为元组 | 改为 `best_score, best_i, best_j` 三元组解包，用 `best_score` 计算概率与字符偏移 |
| Rust 服务启动 panic | `Cannot drop a runtime in a context where blocking is not allowed` | `reqwest::blocking::Client` 不可在 `#[tokio::main]` 内构造；改为在**同步上下文**预建 `RuntimeBackend`，再 `rt.block_on(...)` 启动服务（`main.rs`） |

## 4. 验收证据（端到端实测）

启动运行时（PID）与 Rust 网关（`:8080`）后，经网关跑通完整链路：

1. `POST /api/questions` → 200，创建 `Q_E2E`（历史·戊戌变法）。
2. `PUT /api/standard-answer` → 200，保存含 2 个精确命中点的配置。
3. `POST /api/answers` → 200，提交含"发生在1898年，又称百日维新"的答卷。
4. `POST /api/score` → 200：
   - 点 1 `发生在1898年`：`hit_exact`，`source=mrc`，`confidence=0.999995`。
   - 点 2 `又称百日维新`：`hit_exact`，`source=mrc`，`confidence=0.999927`。
   - `total_score=2.0`，`rating=excellent`。
5. `GET /api/results` → 200，结果已持久化。

> 端到端验证刻意使用**精确表述得分点**：MRC 命中后即返回，相似度模型未参与，
> 因此即便 M2 相似度 ONNX 尚未导出，网关链路已可验证。

各运行时端点独立验证：`/mrc` 命中（prob 0.999995，span 正确）/ 无答案（prob 0.0，被阈值门控）；
`/ocr` 返回合法 `OcrResult`；`/parse` 返回正确 `ScoringConfig`；`/health` 报告 `mrc:true`。

## 5. 遗留 / 依赖

- **/similarity 接口**：待 M2 相似度 ONNX 导出后自动启用；届时补充语义命中端到端验证。
- **GPU 占用**：M2 相似度训练（PID 4384）占满 GPU（100% util），导出与量化需等其释放。
- `/parse` 使用代码内置默认 LLM 端点（无 `.env` 密钥时仍可调用），生产部署需配置 `OPENAI_*`。

## 6. 结论

M3 运行时集成完成，Rust 网关端到端评分链路打通，并修复两处真实缺陷（`/mrc` 解码 Bug、
服务启动 panic）。**M3 判定：PASS**。
