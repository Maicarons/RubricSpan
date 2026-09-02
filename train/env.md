# train/env.md —— 训练环境记录（M0-3 产出）

> 记录日期：2026-08-22。本文件由 M0 环境搭建任务产出，环境变更时更新。

## 硬件

| 项 | 值 |
|---|---|
| GPU | 支持 CUDA 的 NVIDIA GPU（消费级显存即可） |

## 软件栈

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 训练环境（具体要求见 requirements.txt） |
| PyTorch | CUDA 版（torch.cuda.is_available()=True） | 训练框架 |
| transformers | 4.57.3 | 与既有本地包兼容的版本（勿盲目升级到 5.x） |
| sentence-transformers | 3.3.1 | 固定此版本：≥5.0 要求 transformers>=5，会破坏 4.x 兼容 |
| onnxruntime-gpu | 固定（新版需更高 CUDA 运行库 DLL，**不要升级**） | CUDA EP 推理 |
| rapidocr-onnxruntime | 1.2.3 | OCR 引擎，`det_/cls_/rec_use_cuda=True` 启用 GPU |
| openai | 2.38.0 | OpenAI 兼容打标客户端 |

### 版本约束备忘（踩坑记录）

1. **sentence-transformers 5.x/6.x 强制 transformers>=5**，而环境内其他包依赖
   transformers 4.x → 必须固定 `sentence-transformers==3.3.1`。
2. **onnxruntime(-gpu) 新版编译于更高版本 CUDA 运行库**，加载 CUDA EP 报
   `cublasLt 缺失` → 固定 onnxruntime-gpu（不要升级到需更高 CUDA 的版本）。
3. **CUDA EP 的 DLL 解析**：ORT 找不到 cuDNN 时，把 PyTorch 自带的运行库目录
   （site-packages 下的 `torch/lib`，含 cuBLAS / cuDNN 运行库）
   加入 PATH。启动脚本需先设 PATH 再 import。
4. **RapidOCR 开 GPU 的正确姿势**（1.2.3）：必须传
   `RapidOCR(det_use_cuda=True, det_model_path=None, cls_use_cuda=True, cls_model_path=None, rec_use_cuda=True, rec_model_path=None)`；
   顶层 `use_cuda` 会落进 Global 段被忽略；传任意 `*_use_cuda` 时必须同时传对应
   `*_model_path=None`，否则 UpdateParameters 抛 KeyError。

## M0 冒烟样例（出口标准验证）

| 样例 | 命令 | 结果 |
|---|---|---|
| PyTorch CUDA 训练 | `python train/examples/smoke_cuda_train.py` | PASS：20 步 loss 7.82→6.05，23.9 it/s，峰值显存占用很低 |
| RapidOCR 推理 | `python train/examples/smoke_rapidocr.py`（PATH 加 torch/lib） | PASS：印刷体字符级准确率 100%；GPU 热身后单页 wall≈340–660ms（det≈40–60ms + rec≈200–470ms） |
| LLM 打标接口 | `python train/examples/smoke_llm_client.py` | PASS：配置的打标端点连通，严格 JSON 输出验证通过 |

## M1 环境补充（2026-08-22）

1. **Python 运行时**：流水线使用系统 Python（3.10+，与 requirements.txt 一致）；
   `train/.venv` 仅备用，未安装依赖。CI 的 compileall 用兼容语法子集。
2. **打标模型是推理型模型**：先输出 `reasoning_content`
   再输出 `content`，且 `thinking`/`reasoning_effort` 关闭参数经 litellm 报 400
   （不支持）。适配方案（`labeling/client.py`）：
   - `max_tokens` 初始 3072；`content=None 且 finish_reason=length` 时翻倍重试（上限 8192）；
   - 实测量级：单次打标约 3~5K tokens（reasoning 占 completion 大头）。
3. **依赖补充**：PyYAML 6.0.3（configs）；jsonschema/tqdm/numpy 系统环境已有。
4. **多端点 fallback 队列**（2026-08-22）：`labeling/client.py` 支持端点队列。
   `.env` 按 `LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL[,NAME]}` 配置多个接入
   （`n` 升序 = 优先级）。每次调用都从队首端点开始；某端点整轮重试耗尽后自动
   切到下一个，全部失败才计为该次调用失败（样本进重试队列）。无冷却、不记忆
   失败——队首端点恢复后，下一次调用立即回到它。
   未配置编号端点时回落旧单端点变量组（OPENAI_*），存量配置无需改动。

## 打标成本估算（M1 参考）

按 smoke 样例实测（约 300 tokens/条），单条样本打标约 300 tokens。
3000 条目标 × 300 tok ≈ 90 万 tokens；若开启 3 票自一致性则 ≈ 270 万 tokens。
以实际所用平台计费规则换算即可得到 M1 预算上限。
