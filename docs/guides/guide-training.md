# 训练指南 · Python 流水线

> 技术方案 §7、§9。组件根目录：[`train/`](https://github.com/Maicarons/RubricSpan/tree/main/train)
> **职责边界：只做离线训练与模型导出；不提供在线服务。**

## 环境

- Python **3.10+**（PyTorch 尚不支持最新版本；系统 Python 版本过新时，建 venv
  须指定具体版本或 conda 指定版本）；
- GPU：支持 CUDA 的 NVIDIA GPU（消费级显存即可）；PyTorch CUDA 版按
  [官方指引](https://pytorch.org/get-started/locally/) 安装；
- 依赖：`pip install -e ".[dev,ocr]"`（或 `pip install -r requirements.txt`）；
- 硬件/软件栈实测记录与踩坑笔记：`train/env.md`（M0 产出，环境变更时更新）。

## 目录结构

```
train/
├── rubricspan_train/
│   ├── labeling/           # M1 ✅ 大模型打标（Prompt / 批量调用 / 自一致性 / 合成答卷）
│   ├── align/              # M1 ✅ extracted_span → 字符级起止对齐后处理
│   ├── data/               # M1 ✅ 训练数据构建（MRC 五元组 / 相似度句子对）
│   ├── training/           # M2 MRC 微调 / 相似度微调
│   ├── evaluation/         # M2 EM / F1 / Acc / Correlation / 等价命中率
│   └── export/             # M2 ONNX 导出 / INT8 量化 / 一致性校验 / sha256
├── configs/                # YAML 配置（打标 Prompt 版本、超参、划分种子）
└── tests/                  # 单元测试（对齐算法必测）
```

## 命令速查

```bash
# M1 打标与数据
python -m rubricspan_train.labeling.run {parse-points|synth|label|selfcheck|quality|stats}
python -m rubricspan_train.data.build

# M2 训练 / 评估 / 导出
python -m rubricspan_train.training.train_mrc          # --stage bridge|main|both [--strip-stems] [--extra-negatives PATH]
python -m rubricspan_train.training.train_similarity   # [--extra-pairs PATH]
python -m rubricspan_train.evaluation.report [--onnx]
python -m rubricspan_train.export.onnx export|verify|quantize
```

### 外部补充数据集（2026-09，opt-in）

M3KE / InternLM-History 已落地归一化与训练产物（体量、学科、去重、适配结论见
[外部数据集研究报告](/reports/extra-datasets)）：

```bash
# 归一化原始数据 → data/raw/extra/（需先按 extra_sources/README 获取原始数据）
python -m rubricspan_train.data.import_extra
# 生成训练产物 → data/processed/extra_{similarity_pairs,mrc_negatives}.jsonl
python -m rubricspan_train.data.extra_processed
# 训练时显式启用（默认关闭，不扰动主 build 的固定种子/划分）
python -m rubricspan_train.training.train_similarity --extra-pairs ../data/processed/extra_similarity_pairs.jsonl
python -m rubricspan_train.training.train_mrc --stage main --strip-stems --extra-negatives ../data/processed/extra_mrc_negatives.jsonl
```

### MRC 再训练 · 题干剥离口径（CC-006 训练侧）

推理侧评分入口在评分前剥离答卷中与题干重合的长片段（CC-006），因此**再训练时
应加 `--strip-stems`**，让训练 context 与推理输入同源净化，避免模型学到
"从题干材料里抽答案"：

- 实现 `train/rubricspan_train/training/stem_strip.py`——Rust
  `strip_stem_spans` 的 Python 端口（归一化 ≥8 字片段空格替代，字符索引稳定，
  `answer_start/end` 无需重新定位）；与 Rust 版同源对拍测试
  `train/tests/test_stem_strip.py`（7 例，改任一侧须同步另一侧）；
- 守卫：金标 answer 区间被整段清空的数据矛盾行保持原样（实测 train 6 行——
  均为"答案引用材料原文词句"类，可另行仲裁剔除）；
- 实测 mrc_train 24% 行、mrc_val 28% 行的 context 含题干污染，剥离前后指标
  变化以再训练对拍为准。

LLM 接入为**多端点 fallback 队列**：`.env` 配置
`LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL}`（升序即优先级），单端点故障自动切换、
恢复即回切；未配置时兼容旧 `OPENAI_*` 单端点变量。

## 关键约定

1. 打标输出必须通过 `contracts/labeling-schema.json` 校验，不合格样本进质检队列；
2. **对齐成功率 > 90%** 为 M1 出口标准；对齐失败样本按 §7.3 处理；
3. 数据划分使用固定随机种子并记录于 `configs/`；
4. 导出产物目录/命名严格遵守 `contracts/model-artifacts.md`，导出后写入 sha256。

## 数据目录（仓库根 `data/`，不入库）

`data/raw/`（北大评测集 / SAS-Bench / CMRC 2018）→ `data/synthetic/`（四档合成答卷）
→ `data/processed/`（MRC 五元组 / 相似度句子对）。
