# models/ —— 模型产物目录（索引）

> 本目录只存放**索引与说明**；模型文件**不入版本库**，统一发布到 Hugging Face 与
> ModelScope 厂库（Git LFS），由 [`scripts/prepare_model_repos.py`](../scripts/prepare_model_repos.py)
> 整理生成厂库；后续下载脚本将按本索引拉取到本目录布局。
> 目录规范遵守 [`../contracts/model-artifacts.md`](../contracts/model-artifacts.md)。

## 厂库链接（HF / ModelScope 同名镜像；把 `USER` 换成你的用户名）

| 模型 | Hugging Face | ModelScope | 用途 |
|---|---|---|---|
| MRC 抽取（mengzi-bert 微调） | https://huggingface.co/{{USER}}/rubricspan-mrc-onnx | https://www.modelscope.cn/models/{{USER}}/rubricspan-mrc-onnx | 得分点片段抽取 |
| 语义相似度（text2vec 微调） | https://huggingface.co/{{USER}}/rubricspan-similarity-onnx | https://www.modelscope.cn/models/{{USER}}/rubricspan-similarity-onnx | 第 2 阶段相似度兜底 |

## 文件与校验（SHA-256 与厂库 model_card.json 一致）

| 文件 | 大小 | SHA-256 |
|---|---|---|
| mrc/model.onnx | 407MB | `aa07921b1881e5e5aa7ae25dccf200171a3bebd2152122db760704039600da26` |
| mrc/model.int8.onnx | 103MB | `d0a1000e12a1308b927967024964a59d5e211731df8b2c4ba1dcb9429a3bf302` |
| mrc/model.fp16.onnx | 204MB | `69db09efe1eb0325cc64fc222e6d371783fa3933702b73da529a7bf39f9b3a60` |
| similarity/model.onnx | 407MB | `97930a7b6ed122229a144dbdcc14c2601233818bc71f01121e8d6785d2ce2070` |
| similarity/model.int8.onnx | 103MB | `d9c4be1d2da12487fa9455023e1023af936c515893a900d1f2c2caa5270a9d98` |
| similarity/model.fp16.onnx | 204MB | `7f5ad23d8ade38305fef281acf8ed78321d6ea2316203b195701d27d1752ba6f` |

`tokenizer/`（tokenizer.json / config / vocab）随厂库分发，与模型同次导出。

## 精度档约定

- `model.onnx` — FP32，**对拍验收档**（与金标偏差 ≤1e-3）；
- `model.int8.onnx` — 动态 INT8，**CPU 部署档**；
- `model.fp16.onnx` — GPU Ada+ 最快档（~6ms/512-token 前向），非对拍档。

运行时按 `RUBRICSPAN_MODEL_PRECISION` 选择；缺失自动回落 FP32。

## OCR 模型

PP-OCRv6 det/rec 由 `rapidocr-core` 在缺失时**自动从 ModelScope 下载**，不在此厂库中维护。
本地 `models/ocr/` 仅为镜像缓存。

## 取证与复现

训练中间产物与基座权重（`artifacts/`、`backbone/`）已由 `.gitignore` 隔离，
如需继续训练/复现请直接使用厂库中的 ONNX 与 `train/` 脚本。
