# 模型产物目录规范（model-artifacts）

> 训练侧（Python）与推理侧（Rust 在线 / WASM 离线）通过**模型文件 + 配置文件**解耦。
> 本规范定义产物目录布局、文件命名与版本标识，是三方交接的唯一依据。

## 1. 目录布局

```
models/
├── README.md                 # 产物索引 + 获取方式 + 校验值
├── mrc/                      # MRC 抽取模型（mengzi-bert-base 微调）
│   ├── model.onnx            # FP32 全精度版
│   ├── model.int8.onnx       # INT8 量化版（可选，精度损失须 < 1%）
│   ├── tokenizer/            # 分词器（vocab.txt / tokenizer.json 等，与 HF 格式兼容）
│   └── model_card.json       # 模型卡（见 §3）
├── similarity/               # 语义相似度模型（text2vec-base-chinese 微调）
│   ├── model.onnx
│   ├── tokenizer/
│   └── model_card.json
├── ocr/                      # RapidOCR 检测 + 识别模型（官方 ONNX，不改动）
│   ├── det.onnx              # DB 文本检测模型
│   ├── rec.onnx              # CRNN/Transformer 识别模型
│   └── ocr_meta.json         # 引擎版本、来源、作答区模板索引
├── wasm/                     # WASM 离线备选专用（轻量模型）
│   ├── model.onnx            # 60M 蒸馏版或 INT8 量化版
│   ├── tokenizer/
│   └── model_card.json
└── scoring_defaults.json     # 全局评分默认配置（默认阈值等，题级配置可覆盖）
```

## 2. 命名与版本规则

1. 模型文件统一命名 `model.onnx` / `model.int8.onnx`，不带版本号；版本信息由 `model_card.json` 承载；
2. `model_card.json` 必含字段：

```json
{
  "name": "mrc-mengzi-bert",
  "version": "2026.08.0",
  "base_model": "Langboat/mengzi-bert-base",
  "task": "mrc_extraction",
  "max_seq_length": 384,
  "onnx_opset": 17,
  "training_data": { "dataset": "synthetic+pk liberal-arts", "samples": 3200, "seed": 42 },
  "metrics": { "em": 0.67, "token_f1": 0.82, "point_acc": 0.87, "score_corr": 0.88, "alias_hit_rate": 0.83 },
  "exported_at": "2026-09-30T10:00:00+08:00",
  "sha256": "model.onnx 的校验值（写入时计算）"
}
```

3. 训练侧导出后必须：① 计算并写入 `sha256`；② 通过 ONNX Runtime 加载自检；③ 在 `models/README.md` 登记版本与获取方式；
4. 推理侧加载前校验 `sha256`，不一致则拒绝启动并报错。

## 3. 配套配置文件

评分所需的题级配置不在本目录，存于后端数据目录 `data/scoring_configs/{question_id}.json`（Schema 见 `contracts/scoring-config.schema.json`）。本目录仅存放与模型强绑定的默认配置 `scoring_defaults.json`：

```json
{
  "similarity_high": 0.85,
  "similarity_low": 0.60,
  "mrc_has_answer_threshold": 0.5,
  "mrc_min_span_length": 1,
  "mrc_max_span_length": 64,
  "partial_credit_default": 0.5
}
```

## 4. 交接检查清单（训练 → 推理）

- [ ] 各模型 `model_card.json` 指标达到技术方案 §13 目标值；
- [ ] `sha256` 已写入且校验通过；
- [ ] 分词器与模型版本一致（同一次训练导出）；
- [ ] ONNX opset 版本与后端 ONNX Runtime 版本兼容（当前基线 opset 17）；
- [ ] PyTorch ↔ ONNX 输出一致性校验记录归档到 `docs/`。
