# models/ —— 模型产物目录

> 本目录存放训练导出的模型文件，内容**不入版本库**（仅本说明入库）。
> 目录布局、命名与校验规则遵守 [`../contracts/model-artifacts.md`](../contracts/model-artifacts.md)。

## 规划布局（M2 训练导出后填充）

```
models/
├── mrc/                # MRC 抽取模型（mengzi-bert-base 微调 → ONNX）
│   ├── model.onnx
│   ├── tokenizer/
│   └── model_card.json
├── similarity/         # 语义相似度模型（text2vec-base-chinese 微调 → ONNX）
├── ocr/                # RapidOCR 检测/识别模型（官方 ONNX）
├── wasm/               # WASM 离线备选专用轻量模型（M6）
└── scoring_defaults.json   # 全局评分默认配置
```

## 交接检查

训练侧导出后须完成（见 model-artifacts.md §4）：

1. 计算并写入各模型的 `sha256` 到 `model_card.json`；
2. ONNX Runtime 加载自检通过；
3. 在本文件登记版本与获取方式；
4. 推理侧（Rust 后端）加载前校验 `sha256`。

## 预训练基座（训练时自动下载，不落本目录）

- `Langboat/mengzi-bert-base`（Hugging Face）—— MRC 抽取基座
- `shibing624/text2vec-base-chinese`（Hugging Face）—— 相似度兜底基座
