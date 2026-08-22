# data/processed/ —— M1-7 训练数据（对齐 + 质检后）

> 构建入口：`python -m rubricspan_train.data.build`（train/ 目录）；
> 划分配置与随机种子：`train/configs/data_split.yaml`（**划分单位 = question_id**，
> 同一题的全部样本进入同一 split，防止泄漏）。

## 文件

| 文件 | 内容 | 记录结构 |
|---|---|---|
| `mrc_{train,val,test}.jsonl` | MRC 抽取五元组 | `context`(学生答案) `query`(得分点标准表述) `answer` `answer_start` `answer_end` + `is_impossible` 负样本（answer 空、start/end=-1，目标占比 ≥20%） |
| `similarity_{train,val,test}.jsonl` | 相似度句子对 | `sentence1` `sentence2` `score`∈[0,1] + `source`（label-exact / label-semantic / label-miss / label-alias / sas-ads / sas-le / sas-asag / sas-sr / stsb-zh） |
| `qc_report.json` | M1-6 质检报告（对齐成功率 / hit_type 分布 / 过滤明细 / 专家分数一致性） | — |
| `dataset_stats.json` | 划分、种子、分布统计 | — |
| `inspection_sample_5pct.md` | 5% 人工抽检样本导出（分层） | — |

## 数据来源构成

- **label-\\***：SAS-Bench 真实学生答案（整卷 + 步骤片段）与四档合成答卷，
  经大模型打标 → 自一致性投票 → 三级策略对齐 → 质检过滤；
- **sas-\\***：SAS-Datasets（ADS/LE/ASAG/SR）真实人工分对，仅并入 train；
- **stsb-zh**：中文 STS-B（抽样 4000 对，0–5 归一 0–1），仅并入 train。

目录内容不入库，仅本说明入库。
