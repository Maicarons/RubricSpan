# 契约变更记录（CHANGELOG-contracts）

> 契约文件（`../contracts/`）冻结后的任何字段级变更，须先在本文件登记，经全部消费方确认后方可修改。
> 编号规则：`CC-XXX`，按时间递增。

| 编号 | 日期 | 契约文件 | 变更内容 | 原因与影响面 | 确认人 |
|---|---|---|---|---|---|
| CC-001 | 2026-08-23 | 运行时 `/mrc` 接口语义（backend/runtime/model_runtime.py） | `end` 字段由切片式开区间改为**字符级闭区间**（`offset_mapping` end −1），与 Rust `MrcOutput` 及训练侧对齐后处理的既有文档契约对齐；修复前在线路径存在"跨度多含 1 字符 + 答案末尾命中被误判未抽取"两处偏差 | 消费方：rubricspan-inference（透传）、rubricspan-scoring（闭区间消费）、浏览器 local-inference（已按闭区间实现）；实测网关重评分结果正确 | 自动评审（M6 过程发现） |
| CC-002 | 2026-08-23 | 内部运行时 HTTP 接口（`/mrc` `/similarity` `/parse`，:8771）与网关 `/api/ocr` | **M8 推理栈去 Python 化**：删除 `backend/runtime/model_runtime.py`，推理改由 `rubricspan-inference` 内嵌 ort + tokenizers 原生实现（与旧运行时 CPU 金标对拍 53 MRC + 180 相似度逐位一致，e2e 指标零回退）；`/api/ocr` 路由保留但返回 501（OCR 随 Python 运行时移除而暂停，Rust 原生移植排期中） | 影响面：部署不再需要 :8771 进程；`MODEL_RUNTIME_URL` 环境变量废止（改为 `RUBRICSPAN_FORCE_CPU` / `RUBRICSPAN_MODEL_PRECISION`）；前端 OCR 上传入口需隐藏或提示文本录入 | 待评审确认 |
| CC-003 | 2026-08-24 | `contracts/openapi.yaml` → `PointDetail.source` 枚举 | `source` 枚举新增 `option`：选择型得分点（"选B得3分"等）由选项字母规则判定（`rubricspan-scoring::option_rules`），不再依赖 MRC/相似度 | 消费方：前端 `api.ts` ScoreSource（已同步加 `"option"`）、阅卷工作台展示（source=option 显示为选项规则）；在线与 WASM 共享同一评分 crate 自动生效 | 自动评审（M8 调优闭环） |
| CC-004 | 2026-08-24 | `contracts/openapi.yaml` | **新增管理后台端点**（纯增量，不改既有字段）：`GET /api/admin/stats`（聚合统计：试题/答卷/评分概览、得分占比分桶、得分点命中率）、`GET /api/admin/config`（只读运行信息：版本/落盘路径/模型就绪/LLM 端点名称与模型名/**不含密钥**/OCR 状态）；配套新增 `admin` tag、`AdminStats`/`AdminConfig` schema | 消费方：前端 admin 总览页与系统状态卡（替换 N+1 逐题拉取）；后端 `rubricspan-storage::stats()`、`rubricspan-inference::endpoints_summary()` 与两个新路由；无破坏性变更 | 待评审确认（M8 UI 平台化新增） |
| CC-005 | 2026-08-24 | `contracts/openapi.yaml` → `/api/ocr` 行为 | **OCR 恢复（行为变化，契约字段不变）**：`/api/ocr` 由 M8 的 501（Python 运行时移除后的占位）恢复为 200 真识别——Rust 侧 `rapidocr-core`（ort 2 加载 PP-OCRv6 ONNX，det + rec，CPU EP）；请求形态保持「图片二进制 + `X-Question-Id` 头」，响应沿用 `OcrResult`/`OcrLine` 契约；识别结果同步落盘（`storage.save_ocr`） | 消费方：前端答卷页恢复「图片识别」入口（识别文本填入作答框后可编辑提交）、阅卷工作台 OCR 来源答卷继续显示 `ocr_confidence`；部署变化：新增 `--ocr-models-dir`（默认 `<models_dir>/ocr`，首次启动自动从 ModelScope 下载并 SHA-256 校验）、`RUBRICSPAN_OCR_MODEL_SET`（默认 `ppocrv6-small`）；模型资产不入库（`models/ocr/**` 忽略）；OCR 引擎加载失败时仍返回 501（原因入 `admin/config.ocr.note`） | 待评审确认（M8.1 全 Rust 化闭环） |
