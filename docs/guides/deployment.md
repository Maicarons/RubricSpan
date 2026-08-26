# 部署与运行手册（本地 GPU 环境）

> 适用版本：M7 交付基线。所有命令默认在仓库根目录执行；
> Windows + Git Bash 环境注意事项见 §6。

## 1. 交付物清单

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| 模型权重（PyTorch） | `models/artifacts/{mrc,similarity}/pytorch/` | 训练产物，含 train_log / eval_pt |
| ONNX 部署模型 | `models/mrc/model.onnx(+int8)`、`models/similarity/model.onnx(+int8)` | FP32 + INT8 双份；`model_card.json` 登记来源与指标 |
| 分词器 | `models/mrc/tokenizer/`、`models/similarity/tokenizer/` | vocab.txt 等 |
| Rust 服务（单二进制） | `backend/crates/rubricspan-server` | 业务 API + ort 原生推理 + 混合评分编排 :8080（M8 起无 Python 运行时） |
| 前端 | `frontend/` | Next.js 15；含 `/offline` WASM 离线演示 |
| WASM 离线资产 | `frontend/public/wasm/`（构建再生，不入库） | 见 `docs/guides/wasm-offline.md` |
| 文档站 | `docs/`（VitePress） | GitHub Pages 自动发布 |
| 契约 | `contracts/` | 接口 / Schema 冻结件 |

## 2. 在线服务（生产首选）

```bash
# 2.1 Rust 网关（内含 ort 推理；GPU EP 优先，设 RUBRICSPAN_FORCE_CPU=1 强制 CPU）
cargo build --release -p rubricspan-server       # 于 backend/ 下
cd backend && ./target/release/rubricspan-server \
    --listen 127.0.0.1:8080 --storage sqlite --store ../data/store.db   # 本地测试/单机（默认）

# 生产（MySQL，M8.1 起）：容器内先建好库与账号，--db-url 缺省回落 DATABASE_URL
cd backend && ./target/release/rubricspan-server \
    --listen 127.0.0.1:8080 --storage mysql --db-url 'mysql://rubricspan:密码@127.0.0.1:3306/rubricspan'

# 2.2 前端
cd frontend && npm install && npm run build && npm start   # :3000
```

健康检查：`curl :8080/api/health` —— `mode=online` 且 `models.mrc/similarity` 均为 true（任一为 false 说明模型加载失败已回落占位后端，查看启动日志）。

### 存储后端（M8.1）

| 后端 | 用途 | 说明 |
| --- | --- | --- |
| `sqlite`（默认） | 本地测试 / 单机部署 | `--store` 指定 db 文件，自动建表；无外部依赖 |
| `mysql` | 生产 | 连接串 `mysql://user:pass@host:port/db`；启动自动建表建索引（utf8mb4） |
| `memory` | 临时兼容 | M4 遗留内存 + JSON 落盘，重启失忆，不建议 |

MySQL 连接串与 `DATABASE_URL` 优先级：`--db-url` 优先于环境变量；管理后台 `/api/admin/config` 的 `store_path` 已自动脱敏（口令以 `***` 呈现）。

### 关键环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `RUBRICSPAN_FORCE_CPU` | 未设 | 设 1 时 ONNX 仅用 CPU EP（GPU 显存被训练占用时使用） |
| `RUBRICSPAN_MRC_THRESHOLD` | 0.5 | MRC has_answer 判定阈值；调优实验见 M7 评审 |
| `RUBRICSPAN_MODEL_PRECISION` | fp32 | `int8` 选择量化模型（缺失自动回落 FP32） |
| `DATABASE_URL` | 无 | `--storage mysql` 时作为 `--db-url` 的回落值 |
| `RUBRICSPAN_OCR_MODEL_SET` | `ppocrv6-small` | OCR 模型集（见 `rapidocr-core` 注册表，如 `ppocrv5-ch-mobile`） |
| `RUBRICSPAN_OCR_EP` | `directml`（GPU） | OCR 推理执行提供器：默认 DirectX 12 GPU（不依赖 CUDA 运行库）；设 `cpu` 强制 CPU |

## 3. 试卷图片识别（RapidOCR · Rust 侧，M8.1 恢复）

`/api/ocr` 由 Rust 进程内 `rapidocr-core`（ort 2 加载 PP-OCRv6 ONNX，det + rec）完成，无 Python 运行时。
推理 EP **默认 GPU（DirectML，DirectX 12）**，`RUBRICSPAN_OCR_EP=cpu` 可回落 CPU（本机实测 900×1240
试卷图：DirectML ≈3.0s/张，CPU ≈4.4s/张）。模型资产默认放 `models/ocr/`（`--ocr-models-dir` 可改），
**首次启动自动从 ModelScope 下载**（`PP-OCRv6_det_small.onnx` / `PP-OCRv6_rec_small.onnx` / 字典，
SHA-256 校验）；资产不入库（`.gitignore`）。加载失败仅告警不阻断服务，此时 `/api/ocr` 返回 501 且
原因写入 `/api/admin/config` 的 `ocr.note`。

```bash
curl -X POST :8080/api/ocr --data-binary @作答区.png -H 'X-Question-Id: Q001'   # 返回 OcrResult JSON 并落盘
```

前端「答卷上传」页提供图片识别入口：识别文本填入作答框，可编辑后提交为文本答卷。

## 4. WASM 离线模式（备选）

```bash
bash scripts/m6_wasm_build.sh     # 生成前端静态资产（模型 + ORT + wasm 胶包）
cd frontend && npm run build && npm start    # 访问 /offline
```

能力边界与数据流见 `docs/guides/wasm-offline.md`。评分配置在离线场景为手动编辑 JSON（§10.3）。

## 5. 训练流水线（复现实验）

```bash
python -m rubricspan_train.labeling.run        # M1 大模型打标（OpenAI 兼容端点）
python -m rubricspan_train.data.build          # 构建五元组/相似度对
python -m rubricspan_train.training.train_mrc        # MRC 抽取模型
python -m rubricspan_train.training.train_similarity # 相似度模型
python -m rubricspan_train.evaluation.report --onnx  # §13 模型级指标
python -m rubricspan_train.export.onnx export   # ONNX 导出 + scoring_defaults.json
python -m rubricspan_train.export.onnx verify   # PyTorch↔ONNX 一致性（≤1e-3）
python -m rubricspan_train.export.onnx quantize # 动态 INT8 + 精度损失对比
```

## 6. 评估

- 模型级：`evaluation.report` 产出（EM / Token-F1 / Point-Acc / 等价命中率 / ScoreCorr）。
- **系统级全链路**（经真实网关）：`python scripts/m7_e2e_eval.py --sample N`
  → `models/artifacts/e2e_eval.json`，指标口径见 `docs/reports/m7-eval-report.md`。

## 7. 已知环境陷阱（Windows + Git Bash）

1. **cuDNN DLL 遮蔽**：系统 CUDA 运行库目录的 cuDNN 与 torch 自带版本冲突，
   运行 torch 相关命令需干净 PATH（前置 `torch/lib`、剔除系统 CUDA 目录）；
2. **空字符串环境变量被丢弃**：Git Bash 启动原生 exe 时 `VAR=` 等价未设置，
   CPU 指定一律用代码级参数或非空值；
3. **后台任务 PATH 不完整**：脚本内显式设置 PATH 与 Python 全路径；
4. **MSYS 路径改写**：`tasklist //FI`（双斜杠）而非 `/FI`。

## 8. 交付前检查单

- [ ] `/api/health` 通过且 models.mrc/similarity 为 true，GPU EP 生效（在线模式）；
- [ ] INT8 模型一致性损失 < 1%（`export.onnx quantize` 报告）；
- [ ] e2e 评估重跑且关键指标不低于已登记基线（见 M7 评审文档表）；
- [ ] `/offline` 页面离线评分冒烟通过；
- [ ] `/api/ocr` 对真实作答图片识别冒烟通过（识别文本含关键字、`admin/config.ocr.enabled=true`）；
- [ ] 契约变更（若有）已在 `docs/quality/changelog-contracts.md` 登记。
