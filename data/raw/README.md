# data/raw/ —— 原始数据集

> 本目录存放未处理的原始数据集。目录内容**不入版本库**（见根目录 .gitignore），只保留本说明文件。

## 数据集清单与状态

| 数据集 | 来源 | 状态 | 用途 |
|---|---|---|---|
| 中学文科简答题评测数据集 | 北京大学（国家基础学科公共科学数据中心） | ❌ 申请受阻（2026-08-22 确认），保留目录待后续重试 | 真实考生答卷，核心训练/评测 |
| 中学文科简答题题库 | 北京大学 | ❌ 同上 | 标准答案与得分点参照 |
| SAS-Bench | Hugging Face `aleversn/SAS-Bench` | ✅ 已下载（14.4 MB） | 高考 9 学科、4109 份专家标注学生答案，逐步评分基准 |
| SAS-Datasets（ADS/LE/ASAG/SR + 中文 STS-B） | GitHub `aleversn/SAS-Datasets`（Apache-2.0） | ✅ 已克隆 | 中文短答案评分四件套（3127 条带分学生答案），M1 打标种子题源 + 相似度模型微调数据 |
| DRCD | GitHub `DRCKnowledgeTeam/DRCD` | ✅ 已克隆 | 繁体维基 MRC（33953 QA），繁→简转换后作 MRC 预训练桥接补充 |
| CMRC 2018 | GitHub `ymcui/cmrc2018` | ✅ 已克隆 | 中文 Span 抽取预训练桥接 |
| CESA / ASAP-ZH | GitHub `catalpa-cl/ChineseShortAnswerDatasets` | ✅ 已克隆 | 中文短答案评分适配数据 |

## 北大数据集：申请受阻与替代方案

两个数据集托管在**国家基础学科公共科学数据中心**，需注册账号后按科研用途申请下载：

1. 评测数据集：`https://cstr.cn/16666.11.nbsdc.MLy0Ts7T`
2. 题库：`https://cstr.cn/16666.11.nbsdc.sDwSyGzu`

> **状态更新（2026-08-22）**：申请确认受阻。按执行计划 §8 风险项 R7 执行预案：
> 主线改用 **SAS-Bench（题目+参考答案+逐步评分）** 作为真实题源，
> 学生答卷以大模型合成（四档水平 + 同义表述设计）补足；
> **SAS-Datasets 四个子集**提供真实"学生答案+人工分数"监督信号用于相似度模型微调与评测校准；
> MRC 桥接训练用 CMRC 2018 + DRCD（繁→简）。北大数据集若日后获批可增量并入。

## 已下载数据集说明

### SAS-Bench（`sas-bench/`）

- 15 个文件：12 个学科数据（JSONL）+ `ID_DICT.json` / `dataset_info.json` / `error_type.jsonl`；
- 与本项目（文科主观题）最相关：`1_History_ShortAns.jsonl`（历史，640 条）、
  `8_Political_ShortAns.jsonl`（政治，240 条）、`3_Geography_ShortAns.jsonl`（地理，140 条）；
- 字段：`question`（题干）/ `reference`（参考答案）/ `analysis`（解析）/
  `total`（总分）/ `steps`（学生逐步作答与评分）——逐步评分结构天然适配本项目的得分点评分建模。

### CMRC 2018（`cmrc2018/`）

- 数据位于 `cmrc2018/data/`（train/dev/test），SQuAD 格式位于 `cmrc2018/squad-style-data/`；
- 用于 MRC 模型的中文 Span 抽取预训练桥接（执行计划 M2-1）。

### CESA / ASAP-ZH（`ChineseShortAnswerDatasets/`）

- `CESA.txt`：1800 条学生短答案（5 个理科问题）；
- `ASAP_ZH.txt` / `ASAP_ZH_MT_train.txt` / `ASAP_ZH_MT_test.txt`：中文作文评分数据；
- 注意：CESA 为理科题目，主要作**格式与评分方法**适配参考；核心训练以 SAS-Bench 题源 + 合成数据为主。

### SAS-Datasets（`sas-datasets/`，aleversn，Apache-2.0）

中文短答案评分数据集合集（M-Sim 论文配套，Lai et al. 2024）：

| 子集 | 规模 | 领域 | 分数形式 | 文件 |
|---|---|---|---|---|
| ADS | 1582 答案 / 15 题 | 计算机科学（算法与数据结构） | 0–10 整数 | `ADS/all.jsonl`（含 question + 3 条 reference answers） |
| LE | 585 答案 / 100 题 | 物流工程 | 0–1 归一化 | `LE/train.csv` + `LE/qa.csv` |
| ASAG | 629 答案 / 7 题 | 计算机科学 | 0–5 整数（双标注员均值） | `ASAG/train_zh.csv` |
| SR | 331 句对 | 健康信息学 | 0–1 归一化 | `SR/sentences-goldstandard.csv` |
| STS-B 中文版 | 8628 句对 | 通用文本相似度 | 0–5 | `stsbenchmark/*.csv` |

本项目用途：
1. **M1 打标种子题源**：question + reference 结构可直接喂给打标流水线生成合成答卷；
2. **相似度模型微调**：`(学生答案, 参考答案, 分数)` 句对直接构造 CosineSimilarityLoss 训练对；
3. **评测校准集**：真实人工分数可校验大模型打标质量（对照抽检）。
注意：ADS/LE/SR 的参考答案是"多参考"或整段式，得分点拆分需在 M1 由大模型解析。

### DRCD（`drcd/`）

- 台达研究院繁体中文 MRC 数据集：train 26936 QA / dev 3524 QA / test 3493 QA（维基百科，SQuAD 格式，含 `answer_start`）；
- 用途：M2-1 MRC 预训练桥接的补充语料（与 CMRC 2018 并用）；
- 注意：繁体中文，训练前需 OpenCC 繁→简转换；许可 CC BY-SA 3.0（需在 LICENSES 登记）。

## 目录约定

```
data/raw/
├── README.md                  # 本文件（唯一入库文件）
├── sas-bench/                 # ✅
├── sas-datasets/              # ✅ ADS/LE/ASAG/SR + 中文 STS-B
├── drcd/                      # ✅ 繁体 MRC（训练前繁→简）
├── cmrc2018/                  # ✅
├── ChineseShortAnswerDatasets/  # ✅
└── pk-eval/  pk-bank/         # ❌ 北大数据集（申请受阻，保留目录）
```
