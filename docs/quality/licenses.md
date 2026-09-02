# 第三方数据集与模型许可登记（LICENSES）

> RubricSpan 仅将**代码、契约、文档**入库；原始数据集与模型产物不入库（见根目录 `.gitignore`）。
> 本文件登记 `data/raw/` 下所有第三方数据集的出处与许可，确保合规使用。

## 数据集许可一览

| 数据集 | 来源 | 许可 | 本地路径 | 备注 |
|---|---|---|---|---|
| SAS-Bench | Hugging Face `aleversn/SAS-Bench` | 见仓库 LICENSE（学术基准） | `data/raw/sas-bench/` | 4109 份专家标注学生答案，9 学科 |
| SAS-Datasets（ADS/LE/ASAG/SR + 中文 STS-B） | GitHub `aleversn/SAS-Datasets` | **Apache-2.0** | `data/raw/sas-datasets/` | M-Sim 论文配套，中文短答案评分四件套 |
| DRCD | GitHub `DRCKnowledgeTeam/DRCD` | **CC BY-SA 3.0** | `data/raw/drcd/` | 台达研究院繁体中文 MRC，训练前需 OpenCC 繁→简 |
| CMRC 2018 | GitHub `ymcui/cmrc2018` | **Apache-2.0** | `data/raw/cmrc2018/` | 中文 Span 抽取 MRC 基准 |
| CESA / ASAP-ZH | GitHub `catalpa-cl/ChineseShortAnswerDatasets` | 见仓库（学术用途） | `data/raw/ChineseShortAnswerDatasets/` | 中文短答案/作文评分适配数据 |
| 中学文科简答题数据集（北大） | 国家基础学科公共科学数据中心 | 申请受阻，未下载 | （保留目录） | R7 预案已由合成数据替代 |

## 模型与运行库许可

| 组件 | 来源 | 许可 | 用途 |
|---|---|---|---|
| RapidOCR（PP-OCRv3 系列） | `rapidocr_onnxruntime` PyPI + PaddleOCR 权重 | Apache-2.0 | 答卷图像 OCR（M0-6 已验证 GPU 推理） |
| PyTorch（CUDA 版） | PyTorch 官方 | BSD-3-Clause | GPU 训练框架 |
| sentence-transformers 3.3.1 | Hugging Face | Apache-2.0 | 相似度/嵌入模型微调 |

## 合规使用约定

1. **数据不入库**：`data/raw/**` 整体忽略，仅 `README.md` 入库；下载产物存于本地。
2. **训练前转换**：DRCD 等繁体数据须 OpenCC 转简体后再入训练流水线。
3. **署名与共享**：DRCD 采用 CC BY-SA 3.0，若对外发布衍生数据集/模型需保留署名并同协议共享。
4. **科研用途**：北大两类数据集仅限科研申请；若日后获批需在此补登许可并单独记录下载日期。
