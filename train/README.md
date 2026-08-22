# train/ —— Python 训练流水线

技术方案第 7、9 章的训练侧实现。**职责边界：只做离线训练与模型导出；不提供在线服务。**

## 环境与版本注意

- 要求 Python **3.10–3.12**（PyTorch 稳定版暂不支持 3.13/3.14；本机当前为 3.14，搭环境时请用 `py -3.12 -m venv .venv` 或 conda 指定版本）；
- GPU：RTX 4060（8GB）+ CUDA 12 + cuDNN；PyTorch CUDA 版按 [官方指引](https://pytorch.org/get-started/locally/) 安装；
- 依赖安装：`pip install -e ".[dev,ocr]"`（或直接 `pip install -r requirements.txt`）。

## 目录结构

```
train/
├── pyproject.toml          # 工程与依赖定义
├── requirements.txt        # 锁定式依赖清单（环境基线）
├── rubricspan_train/        # 主包
│   ├── labeling/           # M1：大模型打标流水线（Prompt / 批量调用 / 自一致性 / 合成答卷）
│   ├── align/              # M1：extracted_span → 字符级起止对齐后处理
│   ├── data/               # M1：训练数据构建（MRC 五元组 / 相似度句子对）
│   ├── training/           # M2：MRC 微调 / 相似度微调（CMRC 桥接可选）
│   ├── evaluation/         # M2：EM / F1 / Acc / Correlation / 等价命中率
│   └── export/             # M2：ONNX 导出 / 量化 / 一致性校验 / sha256
├── configs/                # 训练与打标配置（YAML）
├── tests/                  # 单元测试（对齐算法为必测项）
└── README.md
```

## 各模块与里程碑对照

| 模块 | 里程碑 | 入口 | 契约依赖 |
|---|---|---|---|
| `labeling/` | M1 ✅ | `python -m rubricspan_train.labeling.run {parse-points\|synth\|label\|selfcheck\|quality\|stats}` | `contracts/labeling-schema.json`、`contracts/scoring-config.schema.json` |
| `align/` | M1 ✅ | 被 labeling/quality 调用；`tests/test_aligner.py` 覆盖三级策略 | 同上 |
| `data/` | M1 ✅ | `python -m rubricspan_train.data.build` | — |
| `training/` | M2 | `python -m rubricspan_train.training.train_mrc` / `.train_similarity`（规划） | — |
| `evaluation/` | M2 | `python -m rubricspan_train.evaluation.report`（规划） | 技术方案 §13 指标 |
| `export/` | M2 | `python -m rubricspan_train.export.onnx`（规划） | `contracts/model-artifacts.md` |

M1 运行备注：环境用系统 Python（`train/env.md`）；打标模型为推理模型，
completion 预算被 reasoning 占用，客户端已适配（`labeling/client.py`）。
LLM 接入为多端点 fallback 队列：`.env` 配置 `LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL}`
（升序即优先级），每次调用都从队首端点开始，单端点故障自动切下一个、恢复后立即
回切，无冷却状态；未配置时兼容旧 `OPENAI_*` 单端点变量。

## 关键约定

1. **打标输出必须通过** `contracts/labeling-schema.json` 校验，不合格样本进入质检队列而非静默丢弃；
2. **对齐成功率 > 90%** 是 M1 出口标准，对齐失败的样本按技术方案 §7.3 处理（负样本或丢弃）；
3. 训练/验证/测试划分使用**固定随机种子**并记录于 `configs/`；
4. 导出产物目录与命名严格遵守 `contracts/model-artifacts.md`，导出后必须计算并写入 `sha256`。

## 数据目录

训练数据统一存放于仓库根 `data/` 下（不入库）：

- `data/raw/` —— 北大评测集 / SAS-Bench / CMRC 2018 等原始数据集；
- `data/synthetic/` —— 大模型合成的四档答卷；
- `data/processed/` —— 对齐后的训练数据（MRC 五元组 / 相似度句子对）。
