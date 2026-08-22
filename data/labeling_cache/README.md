# data/labeling_cache/ —— 打标中间产物

> M1 打标流水线的断点续跑缓存；`labels_final.jsonl` 是唯一向下游
> （`data/build.py`）输出的文件。

| 文件 | 产生阶段 | 说明 |
|---|---|---|
| `labels_raw.jsonl` | label | 首轮打标。信封格式：`sample_id` / `origin` / `expert_*`（SAS-Bench 人工分，质检对照用）+ `labels`（严格符合 `contracts/labeling-schema.json` 的对象，`student_answer` 由流水线回填原文） |
| `labels_voted.jsonl` | selfcheck | 高价值样本多温度多数投票后 + 其余样本透传 |
| `labels_final.jsonl` | quality | 三级策略对齐 + 质检过滤后的最终样本 |
| `selfcheck_report.json` | selfcheck | 一致性报告（票数 / 翻转点数 / 平均一致率） |
| `pipeline_full.log` | — | 全量运行日志 |

目录内容不入库，仅本说明入库。
