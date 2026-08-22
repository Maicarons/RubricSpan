# data/scoring_configs/ —— 评分配置（M1 打标产物）

> 大模型把 SAS-Bench 参考答案解析为结构化评分配置；每题一份 JSON，
> 严格符合 `contracts/scoring-config.schema.json`。

- 生成入口：`python -m rubricspan_train.labeling.run parse-points`（train/ 目录）
- 命名：`SAS-{HIST|POL|GEO|CHN}-{序号}.json`，与打标样本的 `question_id` 一一对应
- `meta.confirmed_by_teacher=false`：训练侧种子配置，未经教师确认；
  正式评分用配置由 M4 `/api/standard-answer/parse` 流程另行生成

## 字段速览

| 字段 | 说明 |
|---|---|
| `points[].point_text` | 得分点标准表述（MRC query / 相似度 anchor） |
| `points[].weight` | 分值，Σweight = total_score（解析后自动归一） |
| `points[].aliases` | 2–4 个等价表述（多候选抽取 + semantic 判定参照） |

目录内容不入库（见根 .gitignore），仅本说明入库。
