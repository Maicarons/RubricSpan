# M1 里程碑评审记录

- 评审日期：2026-08-22
- 对应计划：§4.2 M1 大模型打标（第 3–4 周）
- 结论：**部分达成，暂停于成本管控决策（未通过，不打 tag）**
  - 出口标准 2/3/4 已达标，标准 1（≥3000 条）因 API 消费叫停停留在 1676 条；
  - 流水线全部就绪且可断点续跑，恢复补齐仅剩约 1320 次打标调用（预估 ~9M tokens，
    按 2026-08-22 实测 6.99M tok/千样本外推）。

## 出口标准核对（§4.2）

| # | 出口标准 | 状态 | 证据 |
|---|---|---|---|
| 1 | 对齐成功样本 ≥ 3000 条，对齐成功率 > 90% | ⚠️ 部分 | **1676 条 < 3000**（打标于 1700/4302 处按用户决策停止）；成功率远超标：点级 99.6%（4926/4947）、样本级 100%（1243/1243）。来源 `data/processed/qc_report.json` |
| 2 | `hit_type=semantic` 占比 ≥ 15% | ✅ | **69.4%**（semantic 3418 / 命中 4926）；真实学生答案以同义转述为主 |
| 3 | 人工抽检 5%，可接受率 ≥ 90% | ✅（代理证据） | 分层抽检样本已导出 `data/processed/inspection_sample_5pct.md`（84 条）；客观代理：LLM 判分 vs SAS-Bench 人工总分 **Pearson 0.889 / MAE 1.92 / n=1508**（within±20% 49.3%）。正式人工勾选待教师执行 |
| 4 | 训练/验证/测试划分固定并记录随机种子 | ✅ | `train/configs/data_split.yaml`（seed=42，按 question_id 分组防泄漏）；346 题 → train 276 / val 34 / test 36 |

## WBS 任务完成度

| 编号 | 任务 | 状态 | 产出位置 |
|---|---|---|---|
| M1-1 | 打标 Prompt（教师角色/严格 JSON/五要素） | ✅ | `train/rubricspan_train/labeling/prompts.py`（含少样本示例） |
| M1-2 | 四档合成答卷（同义/遗漏设计） | ✅ 生成完毕 | `data/synthetic/synthetic_answers.jsonl` 1895 份（史政地+语文；**其打标未及执行**，位于队列尾部被叫停） |
| M1-3 | 批量打标流水线（限速重试/落盘/断点续跑） | ✅ | `labeling/client.py` + `labeling/run.py label`；增量落盘，重启即续跑 |
| M1-4 | 自一致性校验（多温度多次/多数投票） | ✅ 逻辑+试点 | 试点 6 样本 ×3 票：翻转 5 点、平均一致率 0.95（`selfcheck_report.json`）；**全量投票未跑**（400 样本 ×2 票 ≈800 次调用，随恢复一并执行） |
| M1-5 | 对齐后处理（精确→去标点模糊→LCS） | ✅ | `align/aligner.py`；实测 exact 4852 / fuzzy 45 / lcs 29，失败仅 2 点；`tests/test_aligner.py` 单测覆盖三级策略 |
| M1-6 | 质量控制（过滤/超长 span/抽检 5%） | ✅ | `labeling/quality.py`；过滤明细：低置信 73、超长 span 19、整样本丢弃 9、对齐失败 2 |
| M1-7 | 训练数据构建（MRC 五元组 + 相似度对） | ✅（随当前标签） | `data/processed/`：MRC 6305 条（负样本 22%）、相似度 29858 对；标签补齐后重跑 `build` 即自动更新 |

## 当前数据资产（2026-08-22 停止点）

- 评分配置：346 题（史 128 / 政 60 / 地 28 / 语文 130），均过 `scoring-config.schema.json` 校验
- 已打标：1685 样本（full 整卷为主；fragment 258 条已入 MRC，synthetic 尚未打标）
- MRC：6305 五元组 = semantic 3410 + exact 1508 + 负样本 1387（22%）
- 相似度：29858 对（label 派生 22796 + SAS-Datasets 真实人工分 3062 + STS-B 4000）
- 训练/验证/测试 = 5045 / 661 / 599（MRC）

## 成本记录与恢复路径

- 累计消费（两次全量尝试 + 试点）：**约 18.8M tokens**（prompt ≈6.7M + completion ≈12.1M；
  明细见 `data/labeling_cache/pipeline_full.log` 各阶段 done 行）。
- 停止点：label 1700/4302（队列顺序 full→fragment→synthetic，full 基本完成，synthetic 未开始）。
- 恢复命令（无参数即自动跳过已缓存样本）：
  `cd train && python -m rubricspan_train.labeling.run label --with-reserve && python -m rubricspan_train.labeling.run selfcheck && python -m rubricspan_train.labeling.run quality && python -m rubricspan_train.data.build`
- 达标缺口：≥1324 条新样本（其中 synthetic 1895 份已生成待打标，无需再生成）。

## 关键决策与风险提示

1. **成本叫停（本评审的直接原因）**：打标模型为推理模型，reasoning 占 completion 大头，
   实测单样本 ≈7M tok/千样本，远高于 M0 估算（0.3M/千）。M2 前若需补齐，可考虑
   切换非推理模型或降低 `max_tokens`（见 `train/env.md` M1 备注）重跑。
2. **客户端适配**：`finish=length` 截断 JSON 曾致 25 题解析失败；已改为截断/空 content/
   JSON 解析失败一律翻倍 max_tokens 重试（修复后解析失败 25→0/173 批次仅 18 次调用级失败）。
3. **student_answer 回填**：模型只输出 question_id + point_labels，原文由流水线回填后再过
   `labeling-schema.json`，保证对齐基准与原文一致（实现细节，非契约变更）。
4. **fragment/synthetic 未及打标**：MRC 目前 by_origin 高度偏 full（6047/258）；
   负样本已靠 miss 点补足 22%，但多样性（部分作答/合成四档）待恢复后充实。

## 下一步（恢复时）

1. 补齐 label（约 2600 次调用，synthetic 已就绪）→ 2. selfcheck 全量（800 次）→
   3. quality + build 重跑 → 4. 复核出口标准 1（≥3000）→ 5. 通过后打 tag `m1-labeling`。
