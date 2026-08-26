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
| `rubricspan-scoring` | 混合评分引擎：多候选抽取 → 相似度兜底 → 加权汇总 | ✅（wasm32 可编译） |
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
