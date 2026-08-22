# data/ —— 数据目录

> 本目录存放全部数据文件，内容**不入版本库**（仅各子目录的 README / .gitkeep / 模板入库）。

| 子目录 | 内容 |
|---|---|
| `raw/` | 原始数据集（SAS-Bench、SAS-Datasets、CMRC 2018、DRCD、CESA 等，见 `raw/README.md`） |
| `synthetic/` | 大模型合成的四档水平学生答卷（M1-2 生成） |
| `labeling_cache/` | 大模型打标中间产物：raw / voted / final 三级（M1-3~M1-6） |
| `processed/` | 对齐后训练数据：MRC 五元组 + 相似度句子对 + 质检报告（M1 产出） |
| `scoring_configs/` | 评分配置 JSON：M1 打标种子配置 + 运行时教师确认配置（`{question_id}.json`） |

## 约定

1. 数据文件一律不提交到 git；数据集的**来源、版本、获取方式**记录在对应子目录的 README；
2. 涉及授权的数据集（如北大两类）仅限本项目科研/训练用途，不得外传；
3. `scoring_configs/` 是运行时目录，后端服务默认读写该目录（见 `../.env` 的 `SCORING_CONFIGS_DIR`）。
