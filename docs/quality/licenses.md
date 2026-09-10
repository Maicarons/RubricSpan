# 第三方数据集与模型许可登记（LICENSES）

> RubricSpan 仅将**代码、契约、文档**入库；原始数据集与模型产物不入库（见根目录 `.gitignore`）。
> 本文件登记 `data/raw/` 下**所有**第三方数据集的出处与许可，确保合规使用。
> 审计原则：**模型发布许可对齐训练数据中最严格的许可**——本项目模型以 CC BY-NC-SA 4.0 发布
> （见 [模型许可](#模型与运行库许可)），使全部许可清晰的训练数据（含 CC BY-NC / CC BY-SA / NC-SA）合规可用；
> 商业使用需另行取得非商业来源数据集的商业授权。

## 数据集许可一览（含外部补充数据集，2026-09-10 审计）

| 数据集 | 来源 | 许可 | 本地路径 | 训练可用 | 备注 |
|---|---|---|---|---|---|
| SAS-Bench | Hugging Face `aleversn/SAS-Bench` | **Apache-2.0**（HF 元数据） | `data/raw/sas-bench/` | ✅ | 4109 份专家标注学生答案，9 学科 |
| SAS-Datasets（ADS/LE/ASAG/SR + 中文 STS-B） | GitHub `aleversn/SAS-Datasets` | **Apache-2.0** | `data/raw/sas-datasets/` | ✅ | M-Sim 论文配套，中文短答案评分四件套 |
| DRCD | GitHub `DRCKnowledgeTeam/DRCD` | **CC BY-SA 3.0** | `data/raw/drcd/` | ✅（SA 兼容 NC-SA 模型） | 台达研究院繁体中文 MRC，训练前需 OpenCC 繁→简；发布衍生需署名+同协议共享 |
| CMRC 2018 | GitHub `ymcui/cmrc2018` | **Apache-2.0** | `data/raw/cmrc2018/` | ✅ | 中文 Span 抽取 MRC 基准 |
| CESA / ASAP-ZH | GitHub `catalpa-cl/ChineseShortAnswerDatasets` | 见仓库（学术用途） | `data/raw/ChineseShortAnswerDatasets/` | ✅（标注为研究用途） | 中文短答案/作文评分适配数据 |
| 中学文科简答题数据集（北大） | 国家基础学科公共科学数据中心 | 申请受阻，未下载 | （保留目录） | ⏳ | 获批后需补登许可与下载日期 |
| M3KE | HF/GitHub `TJUNLP/M3KE` | **Apache-2.0**（HF 元数据；仓库无 LICENSE 文件） | `data/raw/extra_sources/m3ke/` | ✅ | 20477 道多学段标准化题（仅 dev 355 题带答案） |
| InternLM-History | Gitee `sanbuphy/InternLM-History` | **MIT** | `data/raw/extra_sources/internlm-history/` | ✅ | 2022 中考历史专题分类对话 |
| GAOKAO-Bench | GitHub `OpenLMLab/GAOKAO-Bench` | **Apache-2.0** | `data/raw/extra_sources/gaokao-bench/` | ✅ | 2010-2022 高考主/客观题含参考答案 |
| AGIEval | GitHub `ruixiangcui/AGIEval` | **MIT** | `data/raw/extra_sources/agieval/` | ✅ | 高考各科 jsonl |
| CMMLU | HF `lmlmcat/cmmlu` | **CC BY-NC 4.0**（HF 元数据；仓库无 LICENSE） | `data/raw/extra_sources/cmmlu/` | ✅（NC：非商业，模型已对齐 NC-SA） | 67 学科知识测试（文科 20 科入训） |
| C-Eval | ModelScope `OmniData/C-Eval` | **CC BY-NC-SA 4.0** | `data/raw/extra_sources/ceval/` | ✅（NC-SA：模型已对齐 NC-SA） | 各学段知识测试；dev/val 带答案入训，test 答案保密 |
| Reciter | GitHub `Binkic/Reciter` | **MIT** | `data/raw/extra_sources/reciter/` | ✅ | 高考古诗文默写题库 |
| EXAMS | HF `mhardalov/exams` | **CC BY-SA 4.0**（HF 元数据） | `data/raw/extra_sources/exams/` | ⏳ 适配器就绪 | multilingual 无中文行、zh 配置经 TFDS 分发不可达；若入训需署名+同协议共享 |
| NCR | 鹏城实验室 OpenI | **未标注**（需与作者确认） | `data/raw/extra_sources/ncr/` | ⏳ 待数据+许可确认 | 数据在 Google Drive 需授权下载；许可确认前不入训练 |
| CEAMC | 华东师大 | **未公开**（论文无数据链接） | — | ⛔ | 需联系作者 |
| D175（数据堂） | OpenCSG `DatatangBeijing/D175_...` | **商业授权**（需购买） | — | ⛔ | 1.3 亿题，购买/申请后方可用 |

## 模型与运行库许可

| 组件 | 来源 | 许可 | 用途 |
|---|---|---|---|
| **RubricSpan 模型权重**（MRC/相似度 ONNX） | 本项目训练导出 | **CC BY-NC-SA 4.0** | 推理模型；训练数据含 CC BY-NC（CMMLU）/CC BY-NC-SA（C-Eval）/CC BY-SA（DRCD、EXAMS）来源，模型许可对齐最严格数据许可 |
| RapidOCR（PP-OCRv3 系列） | `rapidocr_onnxruntime` PyPI + PaddleOCR 权重 | Apache-2.0 | 答卷图像 OCR |
| PyTorch（CUDA 版） | PyTorch 官方 | BSD-3-Clause | GPU 训练框架 |
| sentence-transformers 3.3.1 | Hugging Face | Apache-2.0 | 相似度/嵌入模型微调 |
| 代码（后端/前端/训练/脚本） | 本项目 | **AGPL-3.0** | 见根 LICENSE |

## 合规使用约定

1. **数据不入库**：`data/raw/**` 整体忽略，仅 README 入库；下载产物存于本地。
2. **训练前转换**：DRCD 等繁体数据须 OpenCC 转简体后再入训练流水线。
3. **模型许可 = 数据许可交集**：模型以 CC BY-NC-SA 4.0 发布——可自由使用/分享（须署名、非商业、同协议共享）；
   **商业部署**需另行取得 CMMLU/C-Eval/DRCD/EXAMS 等非商业或共享许可数据集的商业授权，或改用不含
   这些来源的模型权重。
4. **署名与共享**：DRCD（CC BY-SA 3.0）、EXAMS（CC BY-SA 4.0）若发布衍生需保留署名并同协议共享。
5. **科研用途**：北大两类数据集仅限科研申请；NCR 许可未标注，确认前不入训练；CEAMC 需联系作者。
6. **商业数据**：D175 需购买/申请，任何形式不纳入发布物。
7. **许可变更记录**：2026-09-10 模型发布许可由 Apache-2.0 调整为 CC BY-NC-SA 4.0，以纳入
   CMMLU（CC BY-NC）与 C-Eval（CC BY-NC-SA）等非商业来源数据（此前因许可冲突被排除）。
