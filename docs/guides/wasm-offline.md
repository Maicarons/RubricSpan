# 离线演示使用说明（M6 · 技术方案 §10.2 方案 B）

## 快速开始

```bash
bash scripts/m6_wasm_build.sh   # 产出前端静态资产（首次已执行）
cd frontend && npm run build && npm start
# 浏览器访问 http://localhost:3000/offline
```

页面操作：**初始化本地引擎**（加载 WASM 评分核心 + 分词器 + ONNX 模型）→
选择示例答案或输入任意答案 → **离线评分**。

## 架构与数据流

```
浏览器（全部本地，无服务端参与评分）
├─ onnxruntime-web (wasm EP)      MRC / 相似度 张量推理
├─ src/lib/bert-tokenizer.ts      BERT 中文 WordPiece 分词（码点级偏移）
└─ rubricspan-wasm (.wasm)        Rust 混合评分核心（与在线端同一套代码）
     scoreAnswer(configJson, answer, inferenceJson)
       ├ inferenceJson = JS 预计算的推理结果表 {mrc:{...}, similarity:{...}}
       └ 返回 ScoreOutcome JSON（结构与在线端 /api/score 一致）
```

> 为什么是"预计算推理表"：WASM 导入函数只能同步返回，而浏览器推理是异步的；
> 故 JS 先行完成全部推理再交由 Rust 编排。评分判定逻辑零移植，保证两套后端
> 结果可比（§10.3）。

## 资产清单（frontend/public/wasm/）

| 路径 | 内容 | 来源 |
| --- | --- | --- |
| `pkg/` | wasm-bindgen 产物（rubricspan_wasm.js/.wasm/.d.ts） | `scripts/m6_wasm_build.sh` |
| `ort/` | onnxruntime-web 的 .wasm/.mjs 运行时 | node_modules 本地复制（不走 CDN） |
| `models/vocab.txt` | BERT 中文词表（21128 词） | models/mrc/tokenizer |
| `models/mrc/model(.int8).onnx` | MRC 模型（优先 INT8，回落 FP32） | M2 导出 |
| `models/sim/model(.int8).onnx` | 相似度模型（同上） | M2 导出 |

## 能力边界

- **单题/小批量演示场景**：WASM CPU 推理慢于 GPU 服务（首题含会话初始化约
  10s，预热后单题约 1–2s），不替代生产后端；
- 标准答案解析降级为**手动编辑评分配置 JSON**（或离线本地大模型，如有，§10.3）;
- 不含 OCR：图片答卷请走在线模式；离线入口接受文本答案；
- 模型文件较大（FP32 双模型 ~800MB），INT8 量化版就位后体积约减至 1/4。

## 实测记录（2026-08-23）

- 示例答案 1「这场变法发生在1898年，历史上把它称作百日维新。」→ **2/2 excellent**，
  两点精确命中，命中片段与在线 Rust 网关输出完全一致；
- 示例答案 3「猪肉炖粉条是一道东北名菜。」→ **0/2 fail**，两点相似度兜底未命中
  （cos 0.240 / 0.022），与在线行为一致。
