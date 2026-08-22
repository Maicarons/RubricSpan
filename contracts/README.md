# contracts/ —— 接口与数据契约

本目录存放项目全部**冻结契约**，是前端、后端（Rust / WASM）、训练侧三方协作的唯一接口依据。

## 契约清单

| 文件 | 内容 | 消费方 | 冻结时点 |
|---|---|---|---|
| `openapi.yaml` | 前后端全部 REST 接口（OpenAPI 3.0） | 前端 / Rust 后端 | M0 末 |
| `scoring-config.schema.json` | 评分配置 JSON Schema（得分点 / 权重 / aliases / 阈值） | 大模型解析 / 评分引擎 / 前端预览 | M0 末 |
| `labeling-schema.json` | 大模型打标输出 Schema（hit / hit_type / extracted_span 等） | 打标流水线 / 对齐后处理 | M1 启动前 |
| `ocr-output.schema.json` | OCR 输出契约（answer_text / confidence / lines） | OCR 模块 / 后端 / 前端预览 | M0 末 |
| `model-artifacts.md` | 模型产物目录规范（文件命名 / 目录布局 / 版本标识） | 训练导出 / Rust 后端 / WASM 构建 | M0 末 |

## 变更控制规则

1. 契约**冻结后**，任何字段级变更（增 / 删 / 改语义）必须：
   - 在 [`../docs/CHANGELOG-contracts.md`](../docs/CHANGELOG-contracts.md) 追加一条记录（原因、影响面、确认人）；
   - 经全部消费方确认后方可修改文件；
2. 接口实现以契约为准：后端须通过基于 `openapi.yaml` 的契约测试，不接受口头约定；
3. 契约文件的变更提交须在提交信息中引用变更记录编号（如 `contracts(openapi): CC-003 增加 ocr_confidence 字段`）。
