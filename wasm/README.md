# wasm/ —— 浏览器离线推理（备选模式，M6）

技术方案第 10 章 · 方案 B：模型（INT8 量化版 / FP32）经 onnxruntime-web 在浏览器内
加载，配合编译为 WASM 的 Rust 评分核心，实现**无网络环境的单题评分演示**。

## 实际结构（M6 已建成）

```
wasm/
├── README.md           # 本文件（结构总览）
wasm/（构建产物与运行时资产，实际位于前端静态目录）
frontend/public/wasm/
├── pkg/                # rubricspan-wasm 的 wasm-bindgen 产物（Rust 混合评分核心）
├── ort/                # onnxruntime-web 运行时（本地分发，不走 CDN）
└── models/             # mrc / sim ONNX + vocab.txt（优先 INT8，回落 FP32）

相关代码：
├── backend/crates/rubricspan-wasm/   # JS 入口 crate（scoreAnswer 预计算推理表契约）
├── frontend/src/lib/bert-tokenizer.ts# BERT 中文 WordPiece 分词（码点级偏移）
├── frontend/src/lib/local-inference.ts # ORT 推理层（复刻在线运行时算法）
├── frontend/src/app/offline/page.tsx   # 离线单题评分演示页
└── scripts/m6_wasm_build.sh            # 一键构建脚本

使用说明与能力边界：docs/guides/wasm-offline.md
```

## 约束与边界

- 与在线端**共用同一套评分配置（JSON）与一致的混合评分路线**（评分编排跑在
  同一份 Rust 代码里），保证结果可比；
- 仅用于单题 / 小批量演示场景，推理速度慢于 GPU 服务，不替代生产后端；
- 模型产物遵守 `../contracts/model-artifacts.md`。

## 离线场景降级

标准答案解析在离线场景下降级为"手动编辑评分配置 JSON"
（或调用本地大模型，如有），见技术方案 §10.3。
