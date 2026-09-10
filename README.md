# RubricSpan · 阅微 —— 主观题阅卷教师模型

> 面向中文主观题（文科简答题 / 论述题 / 材料解析题）的**本地化智能阅卷系统**：大模型离线生成训练标签，训练轻量编码器模型，在普通 PC / 本地 GPU 上完成"上传试卷 → 作答识别 → 自动评分 → 审阅反馈"闭环。

## 核心特性

- **可解释评分**：给出分数的同时，标注学生答案中命中每个得分点的原文片段
- **本地可运行**：评分链路全程本地推理，不依赖在线大模型
- **同义答案识别**：等价表述扩展（aliases）+ 语义相似度兜底，正确处理"戊戌变法 / 百日维新 / 维新运动"类答案
- **自然语言标准答案**：教师粘贴自然语言评分说明，自动解析为结构化评分配置
- **纸质试卷接入**：扫描件 / 照片 OCR 识别（RapidOCR PP-OCRv6 · Rust 侧推理，M8.1 恢复；模型首次启动自动下载）
- **双后端模式**：Rust + GPU 在线服务（生产首选）与 WASM 浏览器离线演示（备选）

## 技术栈

| 层级 | 选型 |
|---|---|
| 前端 | React 19 + Next.js 15（App Router）+ Radix UI + Tailwind CSS |
| 后端（在线） | Rust 全栈：Axum 网关 + ort（ONNX Runtime）原生推理，单二进制无 Python（GPU/CPU EP 可选） |
| 后端（离线） | 轻量模型 + WASM（浏览器内推理） |
| 模型 | `Langboat/mengzi-bert-base`（MRC 抽取）+ `shibing624/text2vec-base-chinese`（相似度兜底） |
| 文本识别 | RapidOCR（PP-OCRv6 · Rust 侧推理，M8.1 恢复；Python 仅用于训练） |
| 训练 | Python + PyTorch + Transformers / Sentence-Transformers（仅训练侧，推理已全部 Rust 化） |
| 存储 | SQLite（本地测试/单机）/ MySQL（生产）/ Memory（临时兼容） |

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

> 环境基线：Rust 工具链、Node.js、Python（仅训练需要）；可选 NVIDIA GPU 用于推理加速。

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

文档统一由 [VitePress](https://vitepress.dev) 站点管理，通过 GitHub Pages 自动部署（见 `.github/workflows/docs.yml`）。

| 文档 | 说明 |
|---|---|
| [技术方案（计划书）](docs/project/plan.md) | 技术方案（v4）：架构、算法、训练、双后端、OCR、指标与风险 |
| [执行计划](docs/project/execution-plan.md) | 执行计划：里程碑、WBS、验收标准、风险登记册 |
| [后端指南](docs/guides/guide-backend.md) / [前端指南](docs/guides/guide-frontend.md) / [训练指南](docs/guides/guide-training.md) | 三大组件的构建、结构与约定（组件目录内 README 为指针） |
| [部署与运行手册](docs/guides/deployment.md) | 在线/离线/训练三种模式的部署步骤与环境陷阱 |
| [全链路评估报告](docs/reports/m7-eval-report.md) | 系统级 §13 指标实测与调优实验结论 |
| [VitePress 文档站](https://maicarons.github.io/RubricSpan/) | 部署后的在线文档（构建产物，详见 `docs/`） |
| [contracts/](contracts/README.md) | 接口与数据契约（冻结后变更走 [变更记录](docs/quality/changelog-contracts.md)） |
| [docs/quality/bad-cases.md](docs/quality/bad-cases.md) | bad case 登记（迭代闭环入口） |

## 里程碑

数据与环境 → 大模型打标 → 模型训练与导出 → OCR 集成 → Rust 在线后端 → 前端开发 → WASM 离线备选 → 联调评估与交付（共 13 周，详见执行计划 §3）。

当前进度：**M0–M8 完成**。M8 将推理栈去 Python 化：ort + tokenizers 原生实现与旧运行时金标对拍（53 MRC + 180 相似度逐位一致），e2e 指标零回退后删除 `backend/runtime/`，交付物收敛为单个 Rust 二进制。交付 FP32+INT8 双模型（ONNX）、Rust 在线服务、WASM 浏览器离线演示与完整训练/评估工具链。[全链路评估报告](docs/reports/m7-eval-report.md)：系统级 ScoreCorr **0.959**（目标 ≥0.85 ✅）、等价给分率 **97.4%**（目标 ≥80% ✅）；Point-Acc 78.4%（受金标口径分歧影响，34 条仲裁清单见 [arbitration-sheet](docs/reports/arbitration-sheet.md)）与模型级 EM/F1 经评审裁剪至迭代闭环（[M7 评审](docs/milestone-m7-review.md)）。

浏览器离线单题评分演示：启动前端后访问 `/offline`（[使用说明](docs/guides/wasm-offline.md)）；部署细节见[部署与运行手册](docs/guides/deployment.md)。

## 许可证

[AGPL-3.0](LICENSE) —— 本项目**代码**以 GNU Affero General Public License v3.0 发布。
通过网络提供服务时，服务端修改后的源代码同样须向用户提供（见 LICENSE 第 13 条）。

**模型权重**（MRC/相似度 ONNX，发布至 HF/ModelScope 厂库）以 **CC BY-NC-SA 4.0** 发布：
训练数据含 CC BY-NC 4.0（CMMLU）与 CC BY-NC-SA 4.0（C-Eval）等非商业来源，模型发布许可
对齐最严格的数据许可，保证**全部训练数据合规可用**；商业使用需另行取得相关数据集商业授权。
完整数据集许可审计见 [docs/quality/licenses.md](docs/quality/licenses.md)。
