# M0 里程碑评审记录

- 评审日期：2026-08-22
- 对应计划：§4.1 M0 数据与环境（第 1–2 周）
- 结论：**通过，进入 M1**

## 出口标准核对（§4.1）

| # | 出口标准 | 状态 | 证据 |
|---|---|---|---|
| 1 | 五个数据源中至少 3 个实际可用 | ✅ | SAS-Bench（4109 样本）、CMRC 2018（train 10142 QA / dev 3219 QA）、CESA/ASAP-ZH 均已入库 `data/raw/`；北大两类待人工申请（R7 备选主线已就位） |
| 2 | GPU 上 PyTorch 训练样例跑通 | ✅ | `train/examples/smoke_cuda_train.py` PASS：loss 7.82→6.05，23.9 it/s |
| 2b | GPU 上 RapidOCR 推理样例跑通 | ✅ | `train/examples/smoke_rapidocr.py` PASS：CUDA EP 生效，印刷体字符准确率 100%，热身后单页 ≈340–660ms |
| 3 | `contracts/` 三份契约文档冻结 | ✅ | 实际五份齐备：openapi.yaml、scoring-config.schema.json、model-artifacts.md、labeling-schema.json、ocr-output.schema.json；变更控制见 contracts/README.md 与 docs/quality/changelog-contracts.md |
| 4 | 大模型打标接口单次调用成功且成本可估算 | ✅ | 配置的打标端点连通，严格 JSON 输出验证通过；成本估算见 train/env.md（≈300 tok/条，3000 条 ≈90 万 tokens） |

## WBS 任务完成度

| 编号 | 任务 | 状态 |
|---|---|---|
| M0-1 | 北大数据集申请 | ⏳ 需人工注册申请（唯一未闭环项，不阻塞 M1——M1 打标数据以 SAS-Bench 题目 + 合成答卷为主） |
| M0-2 | SAS-Bench / CMRC / CESA 下载 | ✅ |
| M0-3 | Python 训练环境 | ✅（版本约束记录于 train/env.md） |
| M0-4 | Rust 工具链 + Axum hello-world | ✅（release 构建通过，路由挂载返回 501 stub 属预期） |
| M0-5 | Next.js 15 骨架 | ✅（production build 通过，First Load JS 103kB） |
| M0-6 | RapidOCR GPU 推理验证 | ✅（含速度初测） |
| M0-7 | 打标供应商打通 | ✅（OpenAI 兼容多端点 fallback） |
| M0-8 | 契约草案冻结 | ✅ |
| M0-9 | 仓库结构 / 分支策略 / CI 冒烟 | ✅（git init、main 分支、tag m0-env、本地 CI 冒烟：build + clippy -D warnings 全绿） |

## 关键决策与风险提示

1. **onnxruntime-gpu 版本固定**：新版需更高版本 CUDA DLL，与当前 CUDA 运行库不符；
   CUDA EP 的 cuDNN 依赖复用 PyTorch 运行库目录（PATH 注入），已写入 env.md。
2. **sentence-transformers 固定 3.3.1**：5.x 强制 transformers>=5，破坏 transformers 4.x 兼容。
3. **RapidOCR GPU 开关**：必须 `det_/cls_/rec_use_cuda` + `*_model_path=None` 四件套，
   顶层 `use_cuda` 无效（详见 train/env.md 踩坑记录）。
4. **北大数据集（A2）**：若第 1 周内未获批，按 R7 主线走 SAS-Bench + CMRC + 合成数据，
   不阻塞 M1。

## Tag

`m0-env` @ main
