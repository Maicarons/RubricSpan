# RubricSpan-1.0-pro 训练方案（待审阅）

> 2026-09-10 · 目标：利用**全部既有数据 + 八个外部补充来源**训练新一代模型
> `RubricSpan-{mrc,similarity}-1.0-pro`（拟发布 HF + ModelScope，许可 CC BY-NC-SA 4.0）。
> 本文为**训练前方案**：数据构成、训练配方、验收门、导出与发布、风险与回退。
> 预处理产物见 §9；**训练执行须经审阅通过后启动**（本机 GPU 或 Kaggle 云端）。

## 1. 版本策略

| 版本 | 定位 | 数据 | 状态 |
|---|---|---|---|
| **1.0-flash**（现模型） | 轻量基线，已重命名待上传 | 旧数据（SAS-Bench 打标 + 合成 + CMRC bridge） | ✅ 训练完成，`RubricSpan-{mrc,similarity}-1.0-flash` |
| **1.0-pro**（新模型） | 全数据增强版 | 旧数据 + 8 外部来源 | ⏳ 本方案待审阅 → 预处理完成 → 训练 |

模型命名：`RubricSpan-mrc-1.0-pro`（MRC 抽取）/ `RubricSpan-similarity-1.0-pro`（相似度兜底）。
发布物：ONNX 三精度档（fp32 验收档 / fp16 GPU 档 / int8 CPU 档）+ tokenizer + model_card.json，Git LFS。

## 2. 数据构成（全部入训）

### 2.1 主 build（旧数据，data/processed/）

| 文件 | 条数 | 说明 |
|---|---|---|
| `mrc_train.jsonl` | 18,148（is_impossible 3,959，22%） | MRC 五元组（SAS-Bench 真实+合成答卷打标） |
| `mrc_val.jsonl` / `mrc_test.jsonl` | 2,313 / 2,137 | 验证/测试（**不参与训练**，固定不变） |
| `similarity_train.jsonl` | 55,199 | 相似度句子对（label 派生 + SAS-Datasets + STS-B） |
| `similarity_val.jsonl` / `similarity_test.jsonl` | 6,214 / 5,838 | 验证/测试 |

### 2.2 外部补充（新数据，2026-09 接入，data/raw/extra/ 归一化 68,349 条）

| 来源 | 许可 | 归一化 | 入训产物 |
|---|---|---|---|
| InternLM-History | MIT | 20,813 | 相似度对（题干↔考点 ± 跨考点负例）+ MRC 负例 6,807 |
| M3KE | Apache-2.0 | 20,477 | 相似度对（题干↔选项，dev 355 带答案） |
| NCR | 未标注（研究用途） | 20,477 | 相似度对 + **MRC 负例 20,477**（阅读材料） |
| CMMLU | CC BY-NC 4.0 | 3,540 | 相似度对（文科 20 科） |
| GAOKAO-Bench | Apache-2.0 | 1,123 | 相似度对（高考客观题↔选项 + **主观题↔参考答案**） |
| AGIEval | MIT | 986 | 相似度对 + MRC 负例 522（高考阅读材料） |
| Reciter | MIT | 609 | 相似度对（古诗文默写空位↔答案） |
| C-Eval | CC BY-NC-SA 4.0 | 324 | 相似度对（文科 12 科 dev/val） |

### 2.3 训练集汇总（train split）

| 任务 | 组成 | 条数 | 正负比 |
|---|---|---|---|
| MRC | `mrc_train` + `--extra-negatives`（train 21,200） | **39,348** | is_impossible ≈ **64%**（旧 22% → 大幅上升，见 §8 风险） |
| 相似度 | `similarity_train` + `--extra-pairs`（train 132,150） | **187,349** | 正 79,185 / 负 108,164（≈1:1.37，hard 负例偏多） |

验证集不变（mrc_val / similarity_val）——外部数据**不污染 val/test**，指标可横向对比 1.0-flash。

## 3. MRC 训练配方（RubricSpan-mrc-1.0-pro）

1. **bridge 阶段**：CMRC2018 微调基座（mengzi-bert-base）1 epoch，lr 3e-5，max_len 512，AMP bf16（sm≥8.0）/fp32 回落；
2. **main 阶段**：
   - 数据：`mrc_train.jsonl`（drop_option_points=True，选择型正例剔除，M8 约定）+ `--strip-stems`（训练 context 与推理侧 CC-006 口径一致）+ `--extra-negatives`（全部 21,200 条外部负例）；
   - 超参：3 epochs，lr 2.5e-5，batch 16，grad_accum 自适应显存，seed 42（与 1.0-flash 同源可复现）；
3. **has_answer 阈值再校准**：负例占比 22%→64% 会显著抬高 has_answer 分布，训练后必须在
   `mrc_val` 上重扫 θ（现有阈值扫描机制），再进入验收门；**θ 出厂默认可能由 0.8 上移**。

## 4. 相似度训练配方（RubricSpan-similarity-1.0-pro）

1. 数据：`similarity_train.jsonl` + `--extra-pairs`（train 132,150：高考主观题↔参考答案、客观题↔选项 hard 负例、默写空位↔答案）；
2. 超参：2 epochs，batch 64，lr 2e-5，warmup 0.1，max_len 128，手写循环（M8 调优后的等效实现），seed 42；
3. 负例占比略高（合并 ≈1:1.37）：hard 负例是刻意构造的"表述沾边"拒判信号（BC-002 同族），维持全量入训，以 val Pearson 为准观察。

## 5. 验收门（不达标不进导出）

| 门 | 指标 | 基线（1.0-flash） | 目标（1.0-pro） |
|---|---|---|---|
| MRC val | span_exact / null_acc | 记录于 flash train_log | **不劣于 flash**，null_acc 显著↑（负例收益） |
| 相似度 val | cosine-Pearson | flash 记录 | **≥ flash**（应↑，得分点语义增强） |
| **e2e 36 卷**（同批同网关同设置） | Point-Acc / MAE / 零分带给分率 | 0.8402 / 1.569 / 18.0% | Point-Acc ≥ 0.85、MAE ≤ 1.5、零分带 < 10% |
| 对拍 | fp32 vs 金标 | ≤1e-3 偏差 | 同 |
| 阈值网格 | 交付配置后验 | 网格最优=交付配置 | 重扫（θ/τ 随分布漂移需重定） |

回退策略：任一主指标劣于 flash → 回退数据配比（负例抽样/去 M3KE 数学段）或超参，重训后复测；
两次不收敛则维持 flash 发布、pro 挂起。

## 6. 导出与发布（1.0-pro）

1. 导出：`export/onnx.py export|verify|quantize` → fp32（验收）/ fp16 / int8（CPU 动态档）三档 + tokenizer；
2. 厂库：`prepare_model_repos.py` 生成 `G:\GitHub\RubricSpan-{mrc,similarity}-1.0-pro`（LFS、sha256 表、model_card name/version=1.0-pro、license=CC BY-NC-SA 4.0）；
3. 上传：`publish_to_hf.py --user <HF用户名>` / ModelScope 推送（token 用户侧）；
4. 索引：models/README.md 增补 1.0-pro 链接（与 1.0-flash 并列）。

## 7. 执行环境

- 本机 GPU（CUDA 13.3 + cuDNN，flash 同环境）优先；显存不足则 Kaggle T4×2（`--strip-stems` 与 `--extra-*` 已在云端管线就绪）；
- 时长估算：相似度 187k 对 × 2 epochs ≈ 本机 8–12h（T4 约 2×）；MRC 39k 样本 × 3 epochs ≈ 本机 3–5h；
- 全部命令已具备（train_similarity/train_mrc 的 opt-in flag），无需新代码。

## 8. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| MRC 负例 64% 失衡 | has_answer 偏保守 → FN 升 | 训练后 θ 重扫（§3.3）+ 36 卷 e2e 门；若 e2e 召回受损，负例按来源抽样至 ~45% |
| 外部客观题分布漂移 | 相似度对中学题干↔选项语义与判分场景有差异 | 高考主观题↔参考答案对是"同构"核心；val Pearson + e2e 门把关，不达标回退 |
| M3KE 数学/理科段污染 | 与文科判分无关 | 仅 dev 355 题带答案（数量小）；如 val 异常可只保留文科 dev |
| NCR 许可未标注 | 发布合规 | 模型许可 CC BY-NC-SA 覆盖研究用途；对外引用前联系作者 |
| 训练成本 | token/GPU 时 | 复用既有管线零新增调用；用户对 LLM 打标敏感——本方案**不引入新打标**（纯监督数据） |

## 9. 预处理（本次已完成，产物见 data/processed/）

1. **全数据再生成**：`import_extra`（8 来源归一化 68,349 条）+ `extra_processed`（相似度对 168,121 / MRC 负例 27,806）已是最新全量（含 NCR）；
2. **清单**：`data/processed/pro_data_manifest.json`（各文件条数/train 计数/正负比，本方案 §2 数字的来源）；
3. **平衡性报告**：随清单输出（相似度合并 1:1.37、MRC 负例 64% 提示）；
4. **验证集隔离**：外部数据仅入 train，val/test 不变，可横向对比 flash。

## 10. 审批点

- [ ] 数据构成与训练配方（§2–4）
- [ ] 验收门与回退策略（§5）
- [ ] 执行环境（本机 vs Kaggle，§7）
- [ ] 许可与发布物（§6，模型 CC BY-NC-SA 4.0）
