# backend/ —— Rust 后端（Cargo workspace）

技术方案第 10 章 · 方案 A：Rust HTTP 服务（在线 · 生产首选）。

## 构建与运行

```bash
cargo build            # 编译全部 crate
cargo test             # 运行单元测试（含评分流水线测试）
cargo run -p rubricspan-server   # 启动服务（默认 127.0.0.1:8080）
```

> 依赖基线：Rust stable（见根目录 `rust-toolchain.toml`）。
> GPU 推理（CUDA）相关依赖在 M4 启用，见 `crates/rubricspan-inference/Cargo.toml` 内注释。

## crate 结构

| crate | 职责 | 状态 |
|---|---|---|
| `rubricspan-server` | Axum 服务：七组 REST 接口 + 任务调度 + 标准答案解析 | 骨架（路由已挂载，处理函数 501 占位） |
| `rubricspan-core` | 领域模型：评分配置 / 打标产物 / OCR 契约类型 | 骨架可用（含契约反序列化测试） |
| `rubricspan-scoring` | 混合评分引擎：多候选抽取 → 相似度兜底 → 加权汇总 | 核心逻辑已实现（注入式推理后端） |
| `rubricspan-inference` | 模型加载与推理（ONNX Runtime / Candle，GPU 优先） | 占位（DummyBackend，M4 替换） |
| `rubricspan-ocr` | RapidOCR 集成：检测 + 作答区过滤 + 识别 + 拼接 | 占位（M3 实现） |
| `rubricspan-storage` | SQLite 持久化 | 占位（M4 接入 sqlx） |

## 关键设计

- **评分引擎与推理实现解耦**：`rubricspan-scoring` 通过 `InferenceBackend` trait 注入模型实现，
  在线（GPU）、离线（WASM）、测试（Fake）各注入自己的实现，评分逻辑单一实现、多端一致；
- **契约类型集中在 `rubricspan-core`**：序列化结构与 `contracts/` 保持逐字段一致，变更走契约流程；
- **模型产物**：目录与校验规则见 `../contracts/model-artifacts.md`，推理前校验 `model_card.json` 中的 `sha256`。
