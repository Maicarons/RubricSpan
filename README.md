# RubricSpan · 阅微 —— 主观题阅卷教师模型

> 面向中文主观题（文科简答题 / 论述题 / 材料解析题）的**本地化智能阅卷系统**：大模型离线生成训练标签，训练轻量编码器模型，在 RTX 4060（8GB）普通 PC 上完成"上传试卷 → 作答识别 → 自动评分 → 审阅反馈"闭环。

## 核心特性

- **可解释评分**：给出分数的同时，标注学生答案中命中每个得分点的原文片段
- **本地可运行**：评分链路全程本地推理，不依赖在线大模型
- **同义答案识别**：等价表述扩展（aliases）+ 语义相似度兜底，正确处理"戊戌变法 / 百日维新 / 维新运动"类答案
- **自然语言标准答案**：教师粘贴自然语言评分说明，自动解析为结构化评分配置
- **纸质试卷接入**：RapidOCR 本地识别试卷扫描件 / 照片为作答文本
- **双后端模式**：Rust + GPU 在线服务（生产首选）与 WASM 浏览器离线演示（备选）

## 技术栈

| 层级 | 选型 |
|---|---|
| 前端 | React 19 + Next.js 15（App Router）+ Radix UI + Tailwind CSS |
| 后端（在线） | Rust + Axum + ONNX Runtime / Candle（RTX 4060 GPU） |
| 后端（离线） | 轻量模型 + WASM（浏览器内推理） |
| 模型 | `Langboat/mengzi-bert-base`（MRC 抽取）+ `shibing624/text2vec-base-chinese`（相似度兜底） |
| 文本识别 | RapidOCR（ONNX Runtime，本地 GPU/CPU） |
| 训练 | Python + PyTorch + Transformers / Sentence-Transformers |
| 存储 | SQLite + 本地文件系统 |

## 仓库结构

```
RubricSpan/
├── contracts/          # 冻结契约：OpenAPI、JSON Schema、模型产物规范
├── train/              # Python 训练侧：打标 / 对齐 / 训练 / 评估 / 导出
├── backend/            # Rust 后端（Cargo workspace：服务 / 评分 / 推理 / OCR / 存储）
├── frontend/           # Next.js 15 前端（阅卷工作台等）
├── wasm/               # WASM 离线推理构建（备选模式）
├── data/               # 数据目录（原始 / 合成 / 处理后，不入库）
├── models/             # 模型产物目录（不入库，见 contracts/model-artifacts.md）
├── docs/               # 项目文档：契约变更记录、评估报告、bad case、部署手册
└── .github/            # CI 工作流与 Issue/PR 模板
```

## 快速开始

> 环境基线：RTX 4060 + CUDA 12、Python 3.10+、Rust stable、Node.js 20+

### 后端（Rust 在线服务）

```bash
cd backend
cargo run -p rubricspan-server
```

### 前端（Next.js）

```bash
cd frontend
npm install
npm run dev
```

### 训练流水线（Python）

```bash
cd train
python -m venv .venv
.venv\Scripts\activate        # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r requirements.txt
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [主观题阅卷教师模型项目计划](主观题阅卷教师模型项目计划.md) | 技术方案（v4）：架构、算法、训练、双后端、OCR、指标与风险 |
| [主观题阅卷教师模型-项目执行计划](主观题阅卷教师模型-项目执行计划.md) | 执行计划：里程碑、WBS、验收标准、风险登记册 |
| [contracts/](contracts/README.md) | 接口与数据契约（冻结后变更走 [变更记录](docs/CHANGELOG-contracts.md)） |
| [docs/bad-cases.md](docs/bad-cases.md) | bad case 登记（迭代闭环入口） |

## 里程碑

数据与环境 → 大模型打标 → 模型训练与导出 → OCR 集成 → Rust 在线后端 → 前端开发 → WASM 离线备选 → 联调评估与交付（共 13 周，详见执行计划 §3）

## 许可证

[AGPL-3.0](LICENSE) —— 本项目以 GNU Affero General Public License v3.0 发布。
通过网络提供服务时，服务端修改后的源代码同样须向用户提供（见 LICENSE 第 13 条）。
