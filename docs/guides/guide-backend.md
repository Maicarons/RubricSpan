# 后端指南 · Rust Cargo Workspace

> 技术方案 §10 · 方案 A：Rust HTTP 服务（在线 · 生产首选）。
> 组件根目录：[`backend/`](https://github.com/Maicarons/RubricSpan/tree/main/backend)

## 构建与运行

```bash
cd backend
cargo build --workspace            # 编译全部 crate
cargo test --workspace             # 单元测试（含评分流水线、SQLite 后端集成测试）
cargo clippy --workspace -- -D warnings   # CI 同款 lint 门
cargo run -p rubricspan-server -- --listen 127.0.0.1:8080              # SQLite 本地（默认 ../data/store.db）
cargo run -p rubricspan-server -- --listen 127.0.0.1:8080 --storage mysql --db-url 'mysql://user:pass@127.0.0.1:3306/rubricspan'
```

依赖基线：Rust stable（根目录 `rust-toolchain.toml`）；tokio 1.x + axum 0.8 +
reqwest 0.12（rustls）+ sqlx 0.8（sqlite/mysql）。完整部署步骤见 [部署与运行手册](/guides/deployment)。

## crate 结构与状态

| crate | 职责 | 状态 |
|---|---|---|
| `rubricspan-server` | Axum 服务：试题/答卷/OCR/评分/结果 REST + 管理后台 + 标准答案解析 | ✅ 实现（M4，e2e 验证） |
| `rubricspan-core` | 领域模型：评分配置 / 结果 / 契约类型 | ✅ |
| `rubricspan-scoring` | 混合评分引擎：题干剥离 → 选项规则 → 多候选抽取 → 相似度兜底 → 加权汇总 | ✅（wasm32 可编译） |
| `rubricspan-inference` | 推理后端：ort 会话 + tokenizers 原生推理（CUDA EP 优先回落 CPU）；另含标准答案解析 LLM 客户端 | ✅（M8） |
| `rubricspan-wasm` | 浏览器离线评分入口（M6，预计算推理表契约） | ✅（7 个单测） |
| `rubricspan-ocr` | 试卷图片识别（M8.1 恢复：RapidOCR Rust 核心，det+rec，ort 2） | ✅（M8.1，CPU EP） |
| `rubricspan-storage` | 持久化：SQLite（本地测试）/ MySQL（生产）/ Memory（临时兼容） | ✅（M8.1，sqlx） |

## 关键设计

- **评分引擎与推理实现解耦**：`rubricspan-scoring` 通过 `InferenceBackend` trait
  注入实现——在线（ort 原生会话）、离线（WASM 预计算表）、测试（Fake）各自注入，
  评分逻辑单一实现、多端一致；
- **偏移量契约**：MRC 输出为学生答案内的字符级（Unicode 标量）**闭区间**，
  与训练侧对齐后处理一致（变更须走 [契约流程](/quality/changelog-contracts)，参见 CC-001）；
- **存储双后端（M8.1）**：`Storage` trait 全异步（`async_trait`），SQLite（本地测试/单机）
  与 MySQL（生产，连接池 + 启动自动建表）共用同一份 schema 与行映射（`storage/sql.rs` 宏生成
  两个具体后端），写入走「事务内 DELETE + INSERT」达成与 Memory 一致的覆盖语义；
  `--storage sqlite|mysql|memory` 切换，`--db-url`/`DATABASE_URL` 提供 MySQL 连接串（管理后台
  展示已脱敏）；MySQL 集成测试以 `RUBRICSPAN_TEST_MYSQL_URL` 门控（`--ignored`）；
- **启动顺序**：`main.rs` 在同步上下文加载 ONNX 会话（失败回落占位后端并告警）、
  与 LLM 客户端后再进入 tokio runtime 并打开存储（SQL 后端自动建库建表）；
  推理会话以 `Mutex<Session>` 共享（ort rc.13 的 `run` 需要 `&mut self`）；
  评分把**存储读取前置到异步段、纯 CPU 推理放 `spawn_blocking`**、再异步落盘，
  避免阻塞 tokio 工作线程；
- **OCR（M8.1 恢复）**：`/api/ocr` 走 Rust 进程内 `rapidocr-core`（ort 2 加载 PP-OCRv6，
  det + rec，推理 EP 默认 **DirectML（GPU）**、`RUBRICSPAN_OCR_EP=cpu` 回落 CPU，会话以 `Mutex` 串行化后在 `spawn_blocking` 中推理）；模型资产
  `models/ocr/` 首次启动自动从 ModelScope 下载并 SHA-256 校验（`RUBRICSPAN_OCR_MODEL_SET`
  切换模型集）；引擎加载失败仅告警，`admin/config.ocr.enabled=false` 且 `/api/ocr` 回落 501；
- **模型产物**：目录与校验规则见 `../contracts/model-artifacts.md`。

## 评分管线与运行时参数（2026-09 交付态）

### 题干剥离（输入净化，`preprocess.rs`）

OCR 与采集来源的答卷常原样携带题干，而题干材料（诗句、文段、设问句）往往正是
得分点表述的出处——逐点抽取会"忠于题干"，在专家判零分的答卷上产生高置信误报
（历史登记见 [BC-005](/quality/bad-cases)）。因此评分入口强制执行题干剥离：

- 匹配在**归一化意义**下进行：忽略空白、中英文标点、序号数字与①类注释上标，
  拉丁字母折叠小写；与题干重合 **≥8 字**的片段替换为空格（不足 8 字视为术语/
  短语的偶然重合，不剥离）；
- 与片段掩码一致使用**空格替代**而非删除，保持字符索引与分词边界稳定；
- 原始答卷文本仍完整落库，评分结果可回溯复核；
- 覆盖 OCR 来源（识别文本在进入评分前经过同一净化）；WASM 离线端同步接入
  （`rubricspan-wasm` 导出 `stripStemSpans`，JS 侧剥离后驱动推理与评分，索引对齐）。

同批 36 卷对照验证：仅剥离组 TP/FN/等价给分率与基线**逐位一致**（召回零损失），
误报 47→38；对不含题干的正常输入，匹配为空、原文原样返回，仅增加毫秒级开销。

### 出厂评分参数（从严档）

| 参数 | 出厂默认 | 说明 |
|---|---|---|
| `similarity_high`（τ_hi） | 0.95 | 兜底余弦 ≥ τ_hi → 语义命中（满分） |
| `similarity_low`（τ_lo） | 0.90 | τ_lo ≤ cos < τ_hi → 部分命中（γ 比例） |
| `partial_credit`（γ） | 0.25 | 部分命中给分比例 |
| `mrc_confidence_threshold`（θ） | 0.8 | MRC 抽取置信度 ≥ θ 判精确命中，否则回落兜底 |

题级配置 `scoring_configs/{qid}.json` 的 `thresholds` 仍优先覆盖 τ_hi/τ_lo。
运行时经管理后台 `GET/PUT /api/admin/scoring-settings` 调整，持久化于
`<store_path>/scoring_settings.json`。默认档为 2026-09 对照实验的结果：
交付配置 Point-Acc 0.8402 / MAE 1.569 / 误报 22（改进前 0.7160 / 2.667 / 47），
逐级归因见 [部署改进对照报告](/reports/deploy-improvement)。变更已登记
[CC-006](/quality/changelog-contracts)。
