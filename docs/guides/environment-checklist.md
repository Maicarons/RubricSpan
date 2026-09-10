# 环境要求检查单

> 运行 RubricSpan 阅微系统所需的软硬件环境一览，适用于首次部署、服务器迁移、CI/CD 配置等场景。
> 分「推荐环境」（日常开发/生产流畅运行）与「最低环境」（功能可用，性能受限）。

---

## 1. 硬件要求

### 1.1 CPU 与内存

| 项 | 最低要求 | 推荐要求 |
|---|---|---|
| **CPU 架构** | x86-64（amd64），支持 SSE4.2 | x86-64，8 核或以上 |
| **CPU 频率** | 2.0 GHz 双核 | 3.0 GHz 八核或更高 |
| **RAM（仅后端服务）** | 4 GB | 16 GB 或更多 |
| **RAM（全栈+训练）** | 8 GB | 32 GB 或更多 |

> 说明：后端推理时 MRC 模型约需 1.5 GB、相似度模型约需 1.5 GB、OCR 约需 500 MB，加上 SQLite 缓存与 HTTP 服务，**推荐 16 GB 以上**确保多任务不 swap。训练场景还需额外给 PyTorch 留出显存外的内存头寸。

### 1.2 GPU（可选，推理加速用）

| 项 | 最低要求 | 推荐要求 |
|---|---|---|
| **GPU 类型** | 任意支持 CUDA 的 NVIDIA GPU | NVIDIA GeForce RTX 3060 或更高 |
| **显存（VRAM）** | 4 GB | 8 GB 或更多 |
| **CUDA 计算能力** | 7.0（Volta 架构） | 8.6（Ampere 架构）或更高 |
| **驱动版本** | NVIDIA Driver ≥ 525 | NVIDIA Driver ≥ 610（CUDA 13.x） |

> 说明：
> - 无 GPU 时后端自动回落 CPU (`RUBRICSPAN_FORCE_CPU=1`)，仅推理速度差异（MRC 推理 CPU 约 2-5 s/题，GPU 约 50-150 ms/题）。
> - OCR 推理使用 **DirectML（DirectX 12 GPU）**，不依赖 CUDA 运行库，非 NVIDIA GPU 亦可加速（需 WDDM 驱动）。
> - 训练侧（PyTorch）必须使用 CUDA GPU，显存建议 **8 GB 以上**（batch size 8 + 序列长度 512）。

### 1.3 磁盘空间

| 项 | 大小 | 说明 |
|---|---|---|
| **仓库代码** | ~200 MB | 含 Rust 源码、前端源码、Python 训练脚本、文档 |
| **Rust 编译产物（debug）** | ~5 GB | `backend/target/debug/` |
| **Rust 编译产物（release）** | ~1.5 GB | `backend/target/release/`；最终二进制 ≈36 MB |
| **前端 node_modules** | ~510 MB | `frontend/node_modules/` |
| **模型产物（部署用 ONNX）** | ~1.4 GB | `models/mrc/`（681 MB）+ `models/similarity/`（681 MB）+ `models/ocr/`（30 MB） |
| **模型产物（训练用）** | ~3 GB | `models/artifacts/`（2 GB）+ `models/backbone/`（978 MB） |
| **数据目录** | ~100 MB+ | `data/`（SQLite 库、评分配置、合成数据、原始数据） |
| **Python 虚拟环境** | ~3 GB | `train/.venv/`（仅训练用） |
| **总估算（部署运行）** | **~3 GB** | 代码 + ONNX 模型 + 前端依赖 + 数据 |
| **总估算（全量开发）** | **~15 GB** | 含编译缓存、Python 虚拟环境、训练产物 |

### 1.4 网络

| 项 | 说明 |
|---|---|
| **模型下载** | OCR 模型首次启动自动从 ModelScope 下载（~30 MB）；训练模型需从 HuggingFace / ModelScope 下载预训练骨干 |
| **大模型 API** | 标准答案解析需连接 OpenAI 兼容大模型端点（内网/外网均可） |
| **前端访问** | 浏览器访问后端 API，局域网内无特殊要求 |
| **文档站** | 仅在发布时需 GitHub Pages 连接 |

---

## 2. 软件要求

### 2.1 操作系统

| 系统 | 最低要求 | 推荐要求 | 备注 |
|---|---|---|---|
| **Windows** | Windows 10 22H2 | Windows 11 24H2 | WDDM 2.7+ 用于 DirectML OCR |
| **Linux** | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 | 二进制使用 `x86_64-unknown-linux-gnu` 目标 |
| **macOS** | macOS 14 Sonoma | macOS 15 Sequoia | 仅开发/前端；GPU 推理（Metal）暂未验证 |

### 2.2 运行时与工具链

| 工具 | 最低要求 | 推荐要求 | 用途 |
|---|---|---|---|
| **Git** | 任意新版本 | 最新稳定版 | 拉取代码、版本管理 |
| **Rust（stable）** | 1.80+ | 1.96+（当前 stable） | 编译并运行后端服务 |
| **Node.js** | 20 LTS | 22 LTS | 运行前端开发/构建 |
| **npm** | 10+ | 10+（随 Node.js 自带） | 前端依赖管理 |
| **Python** | 3.10 | 3.12 | 训练流水线（打标/训练/导出 ONNX） |
| **CUDA Toolkit** | 11.8 | 13.3+ | GPU 推理加速（可选） |
| **cuDNN** | 8.9 | 9.6+ | GPU 推理加速（可选） |

> 本机实测环境（2026-09）：Rust 1.96.0 / Node.js 25.5.0 / Python 3.14.3 / CUDA 13.3.1 / cuDNN 9.6 / NVIDIA Driver 610.88。

### 2.3 数据库

| 后端 | 最低要求 | 推荐要求 | 说明 |
|---|---|---|---|
| **SQLite**（默认） | 无需额外安装 | 无需额外安装 | 零外部依赖，自动建库建表；适合本地测试和单机部署 |
| **MySQL**（生产） | MySQL 8.0 | MySQL 8.4+ | 生产环境，需独立安装/容器化部署；连接串 `mysql://user:pass@host:port/db` |
| **Memory**（临时） | 无需额外安装 | 不推荐 | M4 临时兼容，重启失忆 |

### 2.4 浏览器（前端）

| 浏览器 | 最低要求 | 推荐要求 |
|---|---|---|
| **Chrome/Edge** | 120+ | 最新稳定版 |
| **Firefox** | 120+ | 最新稳定版 |
| **Safari** | 17+ | 18+ |

> WASM 离线模式（`/offline`）需要浏览器支持 WebAssembly SIMD。

---

## 3. 模型文件夹结构要求

```
models/
├── mrc/                    # MRC 抽取模型 + 分词器（~681 MB）
│   ├── model.onnx           # FP32 模型 / 或 model.int8.onnx
│   ├── model_card.json      # 模型来源与指标登记
│   └── tokenizer/
│       ├── vocab.txt
│       └── ...
├── similarity/              # 相似度模型 + 分词器（~681 MB）
│   ├── model.onnx
│   ├── model_card.json
│   └── tokenizer/
│       ├── vocab.txt
│       └── ...
└── ocr/                     # OCR 模型（首次启动自动下载，~30 MB）
    ├── det.onnx
    ├── rec.onnx
    └── dict.txt
```

> 模型权重不随仓库提供（`models/` 已 `.gitignore`），需自行训练导出或从 HuggingFace/ModelScope 的 [rubricspan 组织](https://huggingface.co/rubricspan) 下载。详见 [入门教程 · 获取模型权重](/guides/getting-started#7-获取模型权重让评分真正生效)。

---

## 4. 环境变量（.env）配置清单

```dotenv
# ──── 必需 ────
# 大模型端点（至少一组，标准答案解析用）
# 方式 A：多端点 fallback（推荐）
LLM_ENDPOINT_1_BASE_URL=https://your-endpoint/v1
LLM_ENDPOINT_1_API_KEY=sk-xxxxxxxx
LLM_ENDPOINT_1_MODEL=your-model-name

# 方式 B：单端点（未配任何编号端点时生效）
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_API_KEY=sk-xxxxxxxx
# LABELING_MODEL=gpt-4o-mini
# PARSE_MODEL=gpt-4o-mini

# ──── 可选（有合理默认值） ────
SERVER_LISTEN=127.0.0.1:8080          # 后端监听地址（默认 127.0.0.1:8080）
RUBRICSPAN_STORAGE=sqlite             # 存储后端：sqlite / mysql / memory
RUBRICSPAN_STORE=../data/store.db     # SQLite 库文件路径
RUBRICSPAN_MODEL_PRECISION=fp32       # fp32 / int8 / fp16
RUBRICSPAN_FORCE_CPU=0                # 设 1 强制 CPU 推理
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8080  # 前端连接后端地址
```

> 完整变量说明见 [部署与运行手册 · 关键环境变量](/guides/deployment#关键环境变量)。

---

## 5. 快速检查单（表格汇总）

> 以下为**推荐**要求，满足即可流畅运行全栈。

### 5.1 运行后端（在线服务）

| 检查项 | 要求 | 验证方式 |
|---|---|---|
| 操作系统 | Windows 10+ / Ubuntu 22.04+ | `uname -a` 或 `ver` |
| Rust 工具链 | 1.80+ 含 cargo | `rustc --version && cargo --version` |
| NVIDIA GPU（可选） | 显存 ≥ 8 GB，CUDA 11.8+ | `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader` |
| ONNX 模型目录 | `models/mrc/` + `models/similarity/` + `models/ocr/` | `ls models/{mrc,similarity,ocr}` |
| SQLite 写权限 | 数据目录可写 | `touch ../data/test_write && rm ../data/test_write` |
| 磁盘剩余空间 | ≥ 3 GB | `df -h .`（Linux）或 `wmic logicaldisk get size,freespace,caption`（Windows） |

### 5.2 运行前端

| 检查项 | 要求 | 验证方式 |
|---|---|---|
| Node.js | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| 浏览器 | Chrome/Edge/Firefox 120+ | 访问 `http://localhost:3000` |
| 后端可达 | `NEXT_PUBLIC_API_BASE` 对应后端运行中 | `curl http://127.0.0.1:8080/api/questions` |

### 5.3 运行训练流水线

| 检查项 | 要求 | 验证方式 |
|---|---|---|
| Python | 3.10+ | `python --version` |
| CUDA Toolkit | 11.8+ | `nvcc --version` |
| PyTorch GPU 可用 | 同 CUDA | `python -c "import torch; print(torch.cuda.is_available())"` |
| 磁盘剩余空间 | ≥ 10 GB | 见上 |
| HuggingFace Token（可选） | 写权限 | `huggingface-cli whoami` |

---

## 6. 已知环境陷阱

> 详见 [部署与运行手册 · 已知环境陷阱（Windows + Git Bash）](/guides/deployment#7-已知环境陷阱windows--git-bash)。

1. **cuDLL 遮蔽**：系统 CUDA 运行库目录的 cuDNN 与 torch 自带版本冲突，运行 torch 相关命令需干净 PATH（前置 `torch/lib`）。
2. **空字符串环境变量被丢弃**：Git Bash 启动原生 exe 时 `VAR=` 等价未设置，CPU 指定一律用代码级参数或非空值。
3. **后台任务 PATH 不完整**：脚本内显式设置 PATH 与 Python 全路径。
4. **MSYS 路径改写**：Windows Git Bash 中 `tasklist //FI`（双斜杠）而非 `/FI`。
5. **OCR 模型自动下载**：首次启动需网络连接 ModelScope，若网络受限可预下载放至 `models/ocr/`。