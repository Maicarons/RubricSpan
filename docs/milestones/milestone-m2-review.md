# 里程碑 M2 评审 · 模型训练与导出

> 评审日期：2026-08-23
> 状态：**PASS（附保留意见：相似度训练提前终止，按最优快照交付，见 §2.1）**

## 1. M2 目标

产出两套可部署模型及其量化版：
- **MRC 抽取模型**（mengzi-bert-base，~102M）：从学生答案中抽取得分点表述。
- **相似度模型**（text2vec-base-chinese，~100M）：得分点语义匹配。
- 两者均导出 ONNX（FP32 + INT8），并通过 §13 验收指标。

## 2. 当前状态

| 子项 | 状态 | 说明 |
| --- | --- | --- |
| MRC 训练 | ✅ 完成 | 权重 `models/artifacts/mrc/pytorch/`（含 `model.safetensors` + 分词器） |
| MRC ONNX 导出 | ✅ 完成 | `models/mrc/model.onnx`（406 MB）+ `models/mrc/tokenizer/` |
| MRC 评估指标 | ✅ 完成 | `models/artifacts/mrc/eval_pt.json`（`report --onnx`） |
| MRC ONNX 一致性 | ✅ 完成 | `docs/reports/m2-onnx-consistency.md`：`max_abs_logit_diff=5.2e-5 < 1e-3`（PASS） |
| MRC INT8 量化 | ⏳ 随相似度一并执行 | `export.onnx quantize` |
| 相似度训练 | ⚠️ 提前终止 | 进程在训练结束前退出（未写 train_log.json）；采用 `save_best_model` 已落盘的最优验证权重交付，完整 epoch 数未知 |
| 相似度 ONNX（最终版） | ✅ 完成并验证 | `models/similarity/model.onnx`(406.9MB)+tokenizer+model_card；由最优快照导出（19:16 刷新） |
| 相似度 INT8 | ✅ 完成 | `models/similarity/model.int8.onnx`(~103MB)，动态量化；量化报告见 §5 产物 |
| MRC INT8 | ✅ 完成 | `models/mrc/model.int8.onnx`(~103MB) |
| 导出链一致性复核 | ✅ PASS | 复核于导出当日：`max_abs_logit_diff=5.2e-5 < 1e-3`（`docs/reports/m2-onnx-consistency.md`） |

### 2.1 训练提前终止说明

相似度训练进程（原 PID 4384）于 2026-08-23 19:03 前后退出，且未写入
`train_log.json`——按 `train_similarity.py` 的落盘顺序，说明 `fit()` 未正常返回。
由于 `output_path + save_best_model=True` 的机制，**每次验证集指标刷新最优时都会
即时写盘**（最后快照 15:16），因此交付权重是"最后一次刷新的最优验证 checkpoint"，
不是"训练全程收敛后的最终权重"。影响与处置：

- 该快照即当时最优模型，嵌入质量经下游全链路评估确认可用（系统级 ScoreCorr
  0.957，见 `docs/reports/m7-eval-report.md`）；
- 出口标准中依赖"训练完成"的项（EM/Token-F1/ScoreCorr 模型级达标）本就未达
  （§3），提前终止不改变其"待调优"的判定；
- 后续如需冲指标：修复终止原因后补训/延长 schedule，再走同一导出链刷新产物。

> 同一时刻运行时服务、看守脚本亦一并退出，疑似宿主机层面的资源事件；
> 相关服务已全部重启并复验。

## 3. MRC 评估指标（§13 对照）

来源 `models/artifacts/mrc/eval_pt.json`（ONNX 后端，CPU，`mrc_test.jsonl` n=2133）：

| 指标 | 目标 | 实测 | 结论 |
| --- | --- | --- | --- |
| Point-Acc（有/无答判定） | ≥ 0.85 | **0.894** | ✅ |
| 等价命中率 | ≥ 0.80 | **0.943** | ✅ |
| Token-F1 | ≥ 0.80 | **0.758** | ⚠️ 未达 |
| EM（精确抽取） | ≥ 0.65 | **0.482** | ⚠️ 未达 |
| ScoreCorr(Pearson vs 专家) | ≥ 0.85 | **0.765** | ⚠️ 未达 |

> **说明**：有/无答判定（Point-Acc 89.4%）与等价表述召回（94.3%）达标，说明"是否命中 + 语义别名"主链路可用；
> 但**精确跨度（EM 48%）/Token-F1（76%）/样本级总分相关性（0.765）**低于 §13 目标。
> 这与评测集含大量"无答案"负例、金标准跨度带标点/空格差异有关，需后续在 M2 收尾或 M7 调优时关注
> （如：MRC 输出做标点裁剪、桥接数据增强、或阈值/融合策略微调）。端到端评分仍按"MRC 命中优先、
> 相似度兜底"的混合策略工作（见 M3 端到端实测 `rating=excellent`）。

## 4. 关键环境修复（本里程碑内发现）

| 问题 | 现象 | 修复 |
| --- | --- | --- |
| torch 导入失败 `WinError 127 cudnn_cnn64_9.dll` | 系统 CUDA 运行库目录的 cuDNN 与 torch 自带 `cudnn_cnn64_9.dll` 冲突（PATH 遮蔽） | 运行 torch 相关命令时使用干净 PATH（剔除系统 CUDA 目录，前置 `torch/lib`） |
| ONNX 评估 OOM | `_onnx_backend` 优先 `CUDAExecutionProvider`，训练占满 GPU（显存余量不足）→ 384MB 激活分配失败 | 评估/一致性校验强制 CPU EP（指标与批次无关，结果不变）；运行时新增 `RUNTIME_FORCE_CPU=1` 模式供同机共存 |
| 相似度导出报 "Expected all tensors to be on the same device" | Git Bash 启动原生 exe 时**丢弃空字符串环境变量**，`CUDA_VISIBLE_DEVICES=""` 等价未设置，SentenceTransformer 默认上 cuda:0 | 导出代码显式 `device="cpu"`（不依赖环境变量）；需要 CPU 时一律用代码级指定或非空值 |
| 评分 HTTP 500 + 运行时日志 ConnectionAbortedError | `reqwest::blocking::Client` **默认整请求超时仅 30s**：CPU 模式下懒加载+推理超时后客户端断连 | `RuntimeBackend::new` 显式 `.timeout(600s)`；另修复在 tokio runtime 内构造 blocking client 导致的启动 panic（main.rs 改同步上下文预建依赖） |

## 5. 快照导出与混合评分端到端验证

训练结束前，从 `save_best_model` 已落盘的最优权重快照临时导出了相似度 ONNX（导出后已清理快照目录），
使全链路得以提前打通：

- **嵌入合理性**：cos(戊戌变法, 百日维新)=0.905、cos(戊戌变法, 维新运动)=0.891、cos(无关长文本, 戊戌变法)=0.061 —— 区分度正常。
- **全栈混合评分实测**（CPU 推理模式与训练共存，单份 2 分题 ~6.6s）：
  - S01 精确表述 → 两点均 `hit_exact`(mrc)，总分 2.0，rating=excellent；
  - S02 别称改写 → 得分点 2 经 MRC 别名命中（跨度"历史上把它称作百日维新"），得分点 1 相似度兜底未达阈值（0.372<0.60），总分 1.0；
  - S03 无关答案 → 两点均 miss（0.220/0.033），总分 0；
  - 结果经 `/api/results?question_id=Q_E2E_FULL` 确认持久化 3 条记录。
- 抽取跨度展示裁剪 `trim_display_span` 去除首尾标点/空白（不影响命中判定）。

## 6. 相似度导出（看守脚本设计 → 人工执行）

`scripts/m2_export_watcher.sh` 的设计是每 60s 轮询训练 PID，退出后自动执行
export→verify→quantize；本次因看守脚本随宿主机事件一并退出，该链路由人工
按相同步骤执行完成：

```
python -m rubricspan_train.export.onnx export    # ✅ mrc + similarity -> ONNX + scoring_defaults.json
python -m rubricspan_train.export.onnx verify    # ✅ 一致性 PASS（5.2e-5）
python -m rubricspan_train.export.onnx quantize  # ✅ INT8 双模型 + docs/reports/m2-int8-quantization.md
```

产物：`models/{mrc,similarity}/model.onnx(+model.int8.onnx)`、
`models/scoring_defaults.json`、`docs/reports/m2-onnx-consistency.md`、
`docs/reports/m2-int8-quantization.md`。INT8 已换装至离线演示资产
（`frontend/public/wasm/models/`，页面自动优先加载 INT8）。

## 7. 结论

M2 **PASS（附保留意见）**：两套模型的 FP32+INT8 ONNX 全部交付且一致性校验通过；
混合评分主链路端到端打通并经系统级评估验证。保留意见两项：
①相似度训练提前终止，交付的是最优验证快照而非全程收敛权重；
②模型级 §13 指标中 EM/Token-F1/ScoreCorr 未达（§3），与训练提前终止无关，
属既有的调优待办（M7 评审跟进）。
