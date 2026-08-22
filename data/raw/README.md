# data/raw/ —— 原始数据集

> 本目录存放未处理的原始数据集。目录内容**不入版本库**（见根目录 .gitignore），只保留本说明文件。

## 数据集清单与状态

| 数据集 | 来源 | 状态 | 用途 |
|---|---|---|---|
| 中学文科简答题评测数据集 | 北京大学（国家基础学科公共科学数据中心） | ⏳ 待人工申请 | 真实考生答卷，核心训练/评测 |
| 中学文科简答题题库 | 北京大学 | ⏳ 待人工申请 | 标准答案与得分点参照 |
| SAS-Bench | Hugging Face `aleversn/SAS-Bench` | ✅ 已下载（14.4 MB） | 高考 9 学科、4109 份专家标注学生答案，逐步评分基准 |
| CMRC 2018 | GitHub `ymcui/cmrc2018` | ✅ 已克隆 | 中文 Span 抽取预训练桥接 |
| CESA / ASAP-ZH | GitHub `catalpa-cl/ChineseShortAnswerDatasets` | ✅ 已克隆 | 中文短答案评分适配数据 |

## 待人工申请：北京大学两类数据集

两个数据集托管在**国家基础学科公共科学数据中心**，需注册账号后按科研用途申请下载：

1. 评测数据集：`https://cstr.cn/16666.11.nbsdc.MLy0Ts7T`
2. 题库：`https://cstr.cn/16666.11.nbsdc.sDwSyGzu`

**申请步骤（参考）**：

1. 打开上述链接，进入数据详情页；
2. 注册/登录数据中心账号（通常需实名与机构信息）；
3. 按页面指引提交**科研用途**数据使用申请；
4. 审批通过后下载，解压到本目录（建议分别放 `pk-eval/` 与 `pk-bank/` 子目录）；
5. 在本文件"状态"列更新为 ✅ 并记录下载日期。

> 备选方案（若申请受阻）：按执行计划 §8 风险项 R7，主线改用 SAS-Bench + CMRC + 合成数据。

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
- 注意：CESA 为理科题目，主要作**格式与评分方法**适配参考；核心训练仍以北大评测集 + 合成数据为主。

## 目录约定

```
data/raw/
├── README.md                  # 本文件（唯一入库文件）
├── sas-bench/                 # ✅
├── cmrc2018/                  # ✅
├── ChineseShortAnswerDatasets/  # ✅
├── pk-eval/                   # ⏳ 北大评测数据集（下载后放这里）
└── pk-bank/                   # ⏳ 北大题库（下载后放这里）
```
