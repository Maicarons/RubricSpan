# data/raw/extra_sources/ —— 外部补充数据集（获取记录与许可）

> 目标：为训练管线补充中文文科客观题/阅读/考点语料。
> 本目录内容**不入库**（除本说明）；每个来源的获取状态、许可、与训练管线的适配结论
> 见 [docs/reports/extra-datasets.md](../../docs/reports/extra-datasets.md)。

## 获取状态总览

> 模型发布许可为 **CC BY-NC-SA 4.0**（对齐最严格数据许可），全部许可清晰的训练数据合规可用；
> 商业使用需另行取得非商业来源数据集的商业授权（见 `docs/quality/licenses.md`）。

| 来源 | 状态 | 获取方式 | 许可 | 训练可用性 |
|---|---|---|---|---|
| M3KE | ✅ 已下载（143 文件，7.7MB） | GitHub tjunlp-lab/M3KE（经 raw.githubusercontent/API） | **Apache-2.0**（HF 元数据） | ✅ 可入训练（仅 dev 355 题带答案） |
| InternLM-History | ✅ 已下载（156MB） | Gitee 镜像 `sanbuphy/InternLM-History` | **MIT** | ✅ 可入训练 |
| GAOKAO-Bench | ✅ 已下载（14 文件，2.8MB） | GitHub OpenLMLab/GAOKAO-Bench（raw 批量拉取） | **Apache-2.0** | ✅ 可入训练（2010-2022 高考主/客观题含参考答案） |
| AGIEval | ✅ 已下载（4 文件，1.6MB） | GitHub ruixiangcui/AGIEval（raw 拉取高考子集） | **MIT** | ✅ 可入训练 |
| CMMLU | ✅ 已下载（40 CSV，859KB） | GitHub haonan-li/CMMLU（raw 拉取文科 20 科） | **CC BY-NC 4.0**（HF 元数据） | ✅ 可入训练（非商业，模型已对齐 NC-SA） |
| Reciter | ✅ 已下载（2 文件，308KB） | GitHub Binkic/Reciter（raw 拉取） | **MIT** | ✅ 可入训练（古诗文默写） |
| C-Eval | ✅ 已下载（3.1MB） | ModelScope `OmniData/C-Eval`（git clone） | **CC BY-NC-SA 4.0** | ✅ 可入训练（dev/val 带答案，模型已对齐 NC-SA；test 答案保密） |
| NCR | ⏳ 待数据+许可确认 | **Google Drive 文件夹**（见下） | **未标注** | 适配器就绪；许可确认前不入训练 |
| EXAMS | ⏳ 未取到中文数据 | HF `mhardalov/exams`（CC BY-SA 4.0）；multilingual 无中文行，zh 配置经 TFDS 分发 | **CC BY-SA 4.0** | 适配器就绪 |
| D175（数据堂） | ⛔ 不可自由获取 | OpenCSG `DatatangBeijing/D175_...` 仓仅元数据；数据 1.3 亿题，需购买/申请 | 商业授权 | ⛔ 不入训练（需购买） |
| CEAMC | ⛔ 未公开 | GitHub `cubenlp/CEAMC` 仅 README；论文无数据链接 | 未公开 | ⛔ 需联系作者 |

中考题注记：GitHub 无成规模开源中考题库（社区仓库为 JS/HTML 内嵌、体量小）；
初中段由 InternLM-History（2022 中考历史）、C-Eval（初中文科 12 科）与 NCR（中学语文阅读）覆盖。

## NCR 数据获取（待你操作）

NCR 数据在 Google Drive 公开文件夹（需登录后下载）：

- **链接**：https://drive.google.com/drive/folders/1Ci-KLHKk-yP-y5fWX4_cU8bA2fL_q76e?usp=sharing
- **放置位置**：把下载的 JSON 文件放入 `data/raw/extra_sources/ncr/` 目录（文件名任意，
  `import_ncr` 会按文件名中的 train/dev/test 自动判定 split；结构为 `[{ID, Content, Questions:[{Question, Choices, Answer, Q_id}], Type}]`）
- 放好后运行：`cd train && python -m rubricspan_train.data.import_extra`
- ⚠️ 该数据集许可未标注（README 仅论文引用），**确认许可（建议联系作者）后再入训练**；
  如需先试用可临时以 `--data-dir` 指到副本。数据经人工筛查自网络公开题，使用请保留论文引用。

## 命令（复现）

```bash
# M3KE（GitHub API 列树 + raw 批量拉取，见 import 脚本模块文档）
# InternLM-History
git clone --depth 1 https://gitee.com/an_hongjun/InternLM-History.git

# 归一化 → data/raw/extra/{source}/normalized.jsonl
cd train && python -m rubricspan_train.data.import_extra

# 生成训练数据 → data/processed/extra_{similarity_pairs,mrc_negatives}.jsonl
python -m rubricspan_train.data.extra_processed
```

## 隐私与分发约定

- 原始数据仅存本地 `data/`（不入库）；仅归一化 schema 与统计入报告；
- M3KE 无显式许可：按学术基准惯例仅用于本项目科研/训练，不外传；
- D175 为商业数据：任何形式不纳入发布物。
