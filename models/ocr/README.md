# models/ocr/ —— OCR 模型产物（不入库）

RapidOCR（PP-OCRv6 small，det + rec）ONNX 模型与识别字典。

- 来源：ModelScope `RapidAI/RapidOCR`（`onnx/PP-OCRv6/{det,rec}` 与 `paddle/.../ppocrv6_dict.txt`）
- 获取方式：`rubricspan-server` 首次启动（`--ocr-models-dir` 默认 `models/ocr`）自动下载并做
  SHA-256 校验；也可手工放置同名文件（文件名见 `rapidocr-core` 模型注册表）
- 模型集：默认 `ppocrv6-small`，可用 `RUBRICSPAN_OCR_MODEL_SET` 切换
  （如 `ppocrv5-ch-mobile`，注册表见 `rapidocr-core::model::model_set_by_name`）
- 许可：PP-OCR 系列遵循 PaddleOCR Apache-2.0 模型许可，详见 `docs/quality/licenses.md`

本目录除 `README.md` 外的文件均在 `.gitignore` 中（`models/ocr/**`）。