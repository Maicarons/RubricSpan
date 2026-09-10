# kaggle/ —— Kaggle 云端训练

> 把 `train/` 的离线训练流水线搬到 Kaggle Notebook（免费 GPU）运行；
> 数据走 Kaggle 私有数据集，产物回流 Hugging Face 厂库或本地。
> 代码侧已落地三处适配：路径环境变量覆盖、AMP 按卡降级、环境变量加载。

## Kaggle 环境要点（数字以控制台显示为准）

| 项 | 值 |
|---|---|
| GPU | T4 ×2（推荐）或 P100，约 30 GPU 时/周共享 |
| 会话 | 单次最长 12h；长任务用 **Save & Run All**（后台执行） |
| 内存/磁盘 | 约 4 vCPU / 29GB RAM / ~73GB 磁盘 |
| 持久化 | 仅 `/kaggle/working` 保存输出（每版本 ~20GB 上限） |
| 联网 | 需手机验证后打开 Internet |

> **⚠️ 重要：P100 不可用**。Kaggle 默认镜像的 PyTorch(cu128) 缺少 Pascal(SM 6.0) 内核，
> 训练会报 `cudaErrorNoKernelImageForDevice`。**必须在 kernel-metadata.json 中设置**
> `"machine_shape": "NvidiaTeslaT4"` 明确指定 T4。

## 使用流程

### 1. 上传数据（本地，一次性 + 数据更新时重跑）

```bash
pip install kagglehub
# 认证：export KAGGLE_API_TOKEN=... 或 ~/.kaggle/kaggle.json
python train/kaggle/upload_dataset.py --handle <KAGGLE用户名>/rubricspan-data
python train/kaggle/upload_repo.py --handle <KAGGLE用户名>/rubricspan-repo
```

`upload_dataset.py` 上传 `data/` 的 `raw` / `processed` / `synthetic` / `goldens` / `labeling_cache`
（约 175MB，私有数据集）；`upload_repo.py` 上传 `train/` 源码和 `contracts/`（~400KB）。

> **为什么不 git clone？** 本地仓库没有配置 GitHub remote（或仓库未公开），
> 直接从 GitHub 拉取会 404。上传源码数据集是更可靠的方式。

### 2. 云端 Notebook

两种方式：

**A. 网页交互（推荐含 Secrets 的场景）**：Kaggle → Code → New Notebook → Import Notebook，
选 [`rubricspan_train.ipynb`](./rubricspan_train.ipynb)；Settings → Accelerator =
**GPU T4 x2**，Internet = **ON**；Add Input → 挂上 rubricspan-data 和 rubricspan-repo；
Secrets（Add-ons → Secrets）按需添加：`LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL}`
（打标）、`HF_TOKEN`（回传 HF）；逐格执行，Save Version（Run All）。

**B. API 推送（等价后台 Save & Run All）**：

```bash
# train/kaggle/kernel-metadata.json 里把 id 换成 <你的用户名>/rubricspan-train
kaggle kernels push -p train/kaggle
kaggle kernels status <用户名>/rubricspan-train
kaggle kernels output <用户名>/rubricspan-train -p <下载目录>  # 完成后的产物
```

> 注意：API 推送的运行**读不到网页 UI 里配置的 Secrets**（HF 发布和 LLM 打标需网页方式）。

### 3. 产物回流

`/kaggle/working/models/` 下的 ONNX 三精度档 + tokenizer + model_card.json → 下载回本地，
或 notebook 最后一格用 `upload_folder` 推回 HF 厂库。

## 代码适配记录

三个模块级改动，不设环境变量时本地行为完全不变：

1. **`common_paths.py`** — `DATA_DIR`/`MODELS_DIR` 支持 `RUBRICSPAN_DATA_DIR`/`RUBRICSPAN_MODELS_DIR` 覆盖。
2. **`train_mrc.py`** — AMP 按 GPU 计算能力选择：Ampere+(sm≥8.0) 用 bf16；T4(sm_75) 和 P100 退 FP32 全精度
   （T4 的混合精度在 PyTorch 2.10+cu128 上不稳定，产生 NaN loss）。
3. **`labeling/client.py`** — `load_env` 合并 `os.environ`（环境变量优先、空值不遮蔽、`.env` 缺失不报错），
   Kaggle Secrets 直接可用。

## 踩坑记录

| 问题 | 表现 | 原因 | 解决 |
|---|---|---|---|
| 数据集挂载名不固定 | `StopIteration` | kagglehub 上传的数据集挂在 `/kaggle/input/datasets/` 而非 slug 名 | 按 `mrc_train.jsonl` 标记文件递归定位 |
| P100 CUDA 不兼容 | `cudaErrorNoKernelImageForDevice` | 默认镜像 PyTorch cu128 缺 Pascal 内核 | kernel-metadata 设 `machine_shape: "NvidiaTeslaT4"` |
| T4 bf16 NaN | MRC loss=NaN | T4 bf16 在 PyTorch 2.10 上不稳定 | 按 CC 判卡，T4 退 FP32 全精度 |
| GradScaler 崩溃 | `Attempting to unscale FP16 gradients` | PyTorch 2.10 GradScaler 在 T4 上的 bug | 移除 GradScaler，直接 `loss.backward()` |
| HF 本地路径拒绝 | `Repo id must be in the form` | `huggingface_hub` 新版校验 | 降级 `huggingface_hub<0.23`（已集成到 notebook 环境） |
| ONNX 类型混合 | `LayerNormalization` 类型不匹配 | PyTorch 2.10 常量折叠导致 | `do_constant_folding=False` |
| INT8 量化 | `scale issue` | 特定层权重范围异常 | 自动降级 `per_channel=False` |

## HF 模型上传

```bash
pip install huggingface_hub hf_transfer
# 认证：export HF_TOKEN=... 或 hf auth login

# 脚本（消费 prepare_model_repos.py 产物）
python train/kaggle/publish_to_hf.py --user <HF用户名>

# 或 CLI 直接传
hf upload <HF用户名>/RubricSpan-mrc-1.0-flash <本地厂库目录>/ --repo-type model
```

每次 upload 即一个 commit，可在 Hub 上回滚。
## 治理后重训（题干剥离口径，2026-09 补充）

部署改进闭环（CC-006）把"题干剥离"下沉到评分入口后，再训练应让训练 context
与推理输入同源：`train_mrc.py --strip-stems`（实现 `stem_strip.py`，Rust 版 Python
端口，`answer_start/end` 因空格替代无需重新定位）。

零分带残余（18%）治理清单见 `paper/artifacts/zero_band_audit.md`
（`scripts/audit_zero_band.py` 生成）：金标错位类（SAS-CHN-004/017、SAS-HIST-121）
由人工仲裁修订金标后重训；合成泄漏类（全量扫描 3 行）由数据侧改写后重训。

**建议重训命令（main 阶段）**：

```bash
python -m rubricspan_train.training.train_mrc --stage main --strip-stems
# 对拍：旧权重 vs 剥离口径新权重，用 scripts/m7_e2e_eval.py 同批 36 卷复测
python scripts/m7_e2e_eval.py --gateway http://127.0.0.1:8080
```
