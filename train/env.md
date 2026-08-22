# train/env.md —— 训练环境记录（M0-3 产出）

> 记录日期：2026-08-22。本文件由 M0 环境搭建任务产出，环境变更时更新。

## 硬件

| 项 | 值 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU（8188 MiB） |
| 驱动 | 610.88 |
| CUDA Compute Capability | (8, 9) Ada Lovelace |

## 软件栈

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.14.3 | 系统 Python（Windows，pythoncore-3.14-64） |
| PyTorch | 2.11.0+cu128 | CUDA 12.8 官方轮子，`torch.cuda.is_available()=True` |
| transformers | 4.57.3 | 与 qwen-tts 等本地包兼容的版本（勿盲目升级到 5.x） |
| sentence-transformers | 3.3.1 | 固定此版本：≥5.0 要求 transformers>=5，会破坏 4.x 兼容 |
| onnxruntime-gpu | 1.24.1 | CUDA EP 可用；1.28+ 需要 CUDA 13 DLL，**不要升级** |
| rapidocr-onnxruntime | 1.2.3 | OCR 引擎，`det_/cls_/rec_use_cuda=True` 启用 GPU |
| openai | 2.38.0 | OpenAI 兼容打标客户端 |

### 版本约束备忘（踩坑记录）

1. **sentence-transformers 5.x/6.x 强制 transformers>=5**，而本机其他包依赖
   transformers==4.57.3 → 必须固定 `sentence-transformers==3.3.1`。
2. **onnxruntime(-gpu) 1.25+ 编译于 CUDA 13**，加载 CUDA EP 报
   `cublasLt64_13.dll missing` → 固定 `onnxruntime-gpu==1.24.1`（CUDA 12 系）。
3. **CUDA EP 的 DLL 解析**：ORT 找不到 cuDNN 时，把 PyTorch 自带的运行库目录加入 PATH：
   `%LOCALAPPDATA%\Python\pythoncore-3.14-64\Lib\site-packages\torch\lib`
   （含 cublas64_12 / cublasLt64_12 / cudnn64_9 等）。启动脚本需先设 PATH 再 import。
4. **RapidOCR 开 GPU 的正确姿势**（1.2.3）：必须传
   `RapidOCR(det_use_cuda=True, det_model_path=None, cls_use_cuda=True, cls_model_path=None, rec_use_cuda=True, rec_model_path=None)`；
   顶层 `use_cuda` 会落进 Global 段被忽略；传任意 `*_use_cuda` 时必须同时传对应
   `*_model_path=None`，否则 UpdateParameters 抛 KeyError。

## M0 冒烟样例（出口标准验证）

| 样例 | 命令 | 结果 |
|---|---|---|
| PyTorch CUDA 训练 | `python train/examples/smoke_cuda_train.py` | PASS：20 步 loss 7.82→6.05，23.9 it/s，峰值显存 31.7 MiB |
| RapidOCR 推理 | `python train/examples/smoke_rapidocr.py`（PATH 加 torch/lib） | PASS：印刷体字符级准确率 100%；GPU 热身后单页 wall≈340–660ms（det≈40–60ms + rec≈200–470ms） |
| LLM 打标接口 | `python train/examples/smoke_llm_client.py` | PASS：fiblab 端点连通，deepseek-v4-flash-0731 严格 JSON 输出验证通过（188 prompt tok + 82 completion tok，2.2s） |

## 打标成本估算（M1 参考）

按 smoke 样例实测（188 prompt + 82 completion tokens/次），单条样本打标约 300 tokens。
3000 条目标 × 300 tok ≈ 90 万 tokens；若开启 3 票自一致性则 ≈ 270 万 tokens。
以 fiblab 平台计费规则换算即可得到 M1 预算上限。
