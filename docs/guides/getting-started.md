# 入门教程 · 快速开始

> 目标：15 分钟内把 RubricSpan（阅微）在本地完整跑通——配置环境 → 启动后端 → 启动前端 → 完成第一次评分。
> 如果你只想先了解架构，可先读 [技术方案（计划书）](/project/plan)；如果想深入某个组件，见右侧「组件指南」。

## 1. RubricSpan 是什么（一句话）

RubricSpan 是一个面向**中文主观题**（文科简答题 / 论述题 / 材料解析题）的**本地化智能阅卷系统**：
教师录入自然语言标准答案，系统自动解析为结构化评分配置；学生作答后，本地推理给出分数，
并**标注命中每个得分点的原文片段**（可解释评分）。评分链路全程本地推理，不依赖在线大模型。

核心能力：可解释评分、同义答案识别（等价表述 + 语义相似度兜底）、自然语言标准答案解析、
纸质试卷 OCR 接入、双后端（Rust + GPU 在线服务 / WASM 浏览器离线演示）。

## 2. 环境准备

| 工具 | 版本要求 | 用途 | 是否必需 |
|---|---|---|---|
| Git | 任意新版本 | 拉取代码 | ✅ |
| Rust（stable 工具链） | 含 `cargo` | 编译并运行后端 | ✅（运行后端） |
| Node.js | 20 或更高 | 运行前端 | ✅（运行前端） |
| Python | 3.10 或更高 | 训练流水线（打标 / 训练 / 导出） | ⚠️ 仅训练时需要，纯运行可跳过 |
| NVIDIA GPU（支持 CUDA） | 可选 | 推理 / OCR 的 GPU 加速 | ⚠️ 无 GPU 时自动回落 CPU，仅速度差异 |

> 后端推理与 OCR 默认优先 GPU，缺失时自动回落 CPU（`RUBRICSPAN_FORCE_CPU=1` 可显式强制 CPU）。
> 普通消费级 GPU 即可，无需特定显存门槛。

## 3. 获取代码

```bash
git clone https://github.com/Maicarons/RubricSpan.git
cd RubricSpan
```

（若你已在本仓库工作区，直接进入下一步即可。）

## 4. 一键跑起来（最快路径）

### 4.1 配置环境变量

仓库根目录提供了模板 `.env.example`，复制为 `.env` 后按需填写：

```bash
cp .env.example .env
```

需要填写的主要是**大模型接入**（标准答案解析、训练打标会用到，兼容 OpenAI Chat Completions 协议）：

```dotenv
# 方式 A：多端点 fallback 队列（推荐）
LLM_ENDPOINT_1_NAME=my-llm
LLM_ENDPOINT_1_BASE_URL=https://your-endpoint/v1
LLM_ENDPOINT_1_API_KEY=sk-xxxxxxxx
LLM_ENDPOINT_1_MODEL=your-model-name

# 方式 B：单端点（未配置任何编号端点时生效）
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_API_KEY=sk-xxxxxxxx
# LABELING_MODEL=gpt-4o-mini
# PARSE_MODEL=gpt-4o-mini
```

其余变量（监听地址、存储后端、模型目录、前端连接地址等）都有合理默认值，**本地体验一般无需改动**：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SERVER_LISTEN` | `127.0.0.1:8080` | 后端监听地址 |
| `RUBRICSPAN_STORAGE` | `sqlite` | 存储后端：`sqlite` / `mysql` / `memory` |
| `RUBRICSPAN_STORE` | `../data/store.db` | SQLite 库文件路径 |
| `MODELS_DIR` | `../models` | 模型产物目录 |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8080` | 前端连接的后端地址 |
| `RUBRICSPAN_FORCE_CPU` | 未设 | 设 `1` 强制 CPU 推理（无 GPU 运行时） |

> `.env` 已被 `.gitignore` 忽略，不会入库；密钥切勿提交。

### 4.2 启动后端（Rust 在线服务）

```bash
cd backend
cargo run -p rubricspan-server
```

- 默认监听 `127.0.0.1:8080`，数据落盘到 `../data/store.db`（SQLite，自动建库建表）。
- 首次运行若**没有训练好的模型权重**，后端会回落「占位后端」并告警——服务照常可用，
  但评分为占位结果。要拿到真实评分，见 [§7 获取模型权重](#7-获取模型权重让评分真正生效)。
- 想用 MySQL：加 `--storage mysql --db-url 'mysql://user:pass@127.0.0.1:3306/rubricspan'`。

### 4.3 启动前端（Next.js）

新开一个终端：

```bash
cd frontend
npm install      # 首次需要，安装依赖
npm run dev      # 开发模式，默认 3000 端口
```

浏览器打开 **http://localhost:3000** 即可。前端默认连接 `http://127.0.0.1:8080`，
若后端地址不同，可用环境变量 `NEXT_PUBLIC_API_BASE` 或在管理后台「设置」页运行时覆盖。

### 4.4 健康检查

```bash
curl http://127.0.0.1:8080/api/health
# 期望返回 mode=online 且 models.mrc / models.similarity 均为 true
#（任一为 false 说明对应模型未加载，检查启动日志与模型目录）
```

## 5. 第一次评分（端到端走通）

1. **录入试题与标准答案** —— 打开「试题管理」(`/questions`)：
   新建一道题，粘贴**题干**与**自然语言标准答案**（例如「答对戊戌变法的时间、人物、意义各得 1 分」）。
   点击「解析」，系统调用大模型把自然语言答案转为结构化评分配置，教师确认后保存。
2. **录入学生作答** —— 打开「答卷」(`/answers`)：
   文本批量录入，或上传试卷图片（OCR 自动识别，见 [部署与运行手册](/guides/deployment)）。
3. **查看评分** —— 打开「阅卷工作台」(`/workbench`)：
   选择试题 + 答卷，点击评分。结果页逐点展示**每个得分点是否命中、命中原文片段高亮、总分与评级**。
4. **结果统计** —— 「结果」(`/results`) 可查询、查看分布看板并导出。

> 标准答案解析依赖 §4.1 配置的大模型端点；若未配置，该步骤会失败，其余功能不受影响。

## 6. 目录结构速览

```
RubricSpan/
├── backend/        # Rust 后端（Cargo workspace）：服务 / 评分 / 推理 / OCR / 存储
├── frontend/       # Next.js 15 前端（阅卷工作台等）
├── train/          # Python 训练侧：打标 / 对齐 / 训练 / 评估 / 导出 ONNX
├── wasm/           # WASM 离线推理构建（备选模式）
├── contracts/      # 冻结契约：OpenAPI、JSON Schema、模型产物规范
├── models/         # 模型产物目录（不入库，需自行训练或放入）
├── data/           # 数据目录（原始 / 合成 / 处理后，不入库）
└── docs/           # 本文档站（VitePress）
```

各组件的内部结构与约定见对应指南：
[后端](/guides/guide-backend) · [前端](/guides/guide-frontend) · [训练](/guides/guide-training) ·
[WASM 离线](/guides/wasm-offline)。

## 7. 获取模型权重（让评分真正生效）

本仓库**不附带训练好的模型权重**（已被 `.gitignore` 忽略）。让评分从「占位」变为「真实」有两种途径：

- **自行训练导出（推荐，可复现）**：按 [训练指南](/guides/guide-training) 跑通打标 → 训练 → 导出 ONNX，
  产物落到 `models/`（MRC 模型 + 相似度模型，FP32/INT8 双版本）。
- **OCR 模型自动下载**：`models/ocr/` 在 OCR 引擎首次启动时自动从 ModelScope 下载并做 SHA-256 校验，
  通常无需手动准备。
- 模型产物的目录结构与命名规则见 `contracts/model-artifacts.md`。

> 模型就绪后重启后端即可；`/api/health` 中 `models.mrc` / `models.similarity` 会变为 `true`。

## 8. 常见问题（FAQ）

| 现象 | 原因与处理 |
|---|---|
| 后端启动报 ONNX / Execution Provider 相关错误 | 多为缺少 CUDA 运行库；设 `RUBRICSPAN_FORCE_CPU=1` 强制 CPU，或补齐 GPU 运行库后重启。 |
| 端口被占用 | 改监听地址：`cargo run -p rubricspan-server -- --listen 127.0.0.1:9090`，或调 `SERVER_LISTEN`。 |
| 前端连不上后端（状态点红色） | 检查 `NEXT_PUBLIC_API_BASE` 是否指向正确后端；也可在 admin「设置」页直接改。 |
| 标准答案解析失败 | `.env` 未配置任何大模型端点（§4.1）。 |
| 评分为占位 / `models.*` 为 false | 尚未准备模型权重，见 [§7](#7-获取模型权重让评分真正生效)。 |
| 想用 MySQL 而非 SQLite | `cargo run -p rubricspan-server -- --storage mysql --db-url '<连接串>'`。 |
| WASM 离线演示 | 启动前端后访问 `/offline`，详见 [WASM 离线指南](/guides/wasm-offline)。 |

## 9. 接下来读什么

- 想部署到服务器 / 生产：见 [部署与运行手册](/guides/deployment)。
- 想参与训练或复现模型：见 [训练指南](/guides/guide-training)。
- 想了解某个组件的代码结构：见 [后端](/guides/guide-backend) / [前端](/guides/guide-frontend) 指南。
- 想看系统实测指标：见 [全链路评估报告](/reports/m7-eval-report)。
