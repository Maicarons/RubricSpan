# 里程碑 M4+M5 联合评审 · Rust 在线后端 与 前端（2026-08-23）

> 状态：**PASS**
> 说明：M4/M5 在执行中与 M3 集成验证并行推进，未单独出评审文档；
> 本页为补记，汇总两阶段的完成证据。集成侧证据另见
> [M3 评审](milestone-m3-review) §3 与 [M7 评审](milestone-m7-review)。

## M4 · Rust 在线后端

**交付范围**：Axum HTTP 服务（七组 REST）、SQLite 持久化、评分任务调度、
标准答案 LLM 解析落盘、混合评分引擎接入真实推理运行时。

| 出口项 | 证据 |
| --- | --- |
| workspace 编译 + 全部测试通过 | `cargo test --workspace` 绿（含评分流水线单测；CI 同款门） |
| clippy -D warnings 干净 | CI 门通过；历次修复记录见 M3 评审 |
| 服务可启动并完成端到端评分 | `/api/health` → `/api/score` 全链路实测（M3 评审 §3） |
| 启动崩溃修复 | reqwest::blocking 不能在 tokio runtime 内构造：`main.rs` 改同步上下文预建依赖后进入 runtime |
| 慢推理超时修复 | reqwest::blocking 默认整请求 30s 超时 → 显式 600s（CPU 模式懒加载场景） |

## M5 · 前端（Next.js 15）

**交付范围**：试题管理、答卷上传（文本/批量/图片 OCR 入口）、阅卷工作台
（逐点明细 + 命中片段高亮 + 总分评级）、结果与统计看板、在线模式 API 客户端。

| 出口项 | 证据 |
| --- | --- |
| typecheck 通过 | `tsc --noEmit` 绿（TypeScript strict） |
| 生产构建通过 | `next build` 全部路由静态生成成功 |
| 页面与契约对齐 | `lib/api.ts` 基于 `contracts/openapi.yaml` 封装 |
| 离线入口预留（M5-8） | 首页模块卡 + 后续 `/offline` 路由（M6 接通，见 [M6 评审](milestone-m6-review)） |

## 结论

M4/M5 **均 PASS**。两阶段的关键产出（在线服务、工作台界面）是 M7 全链路
评估与日常回归的载体；期间发现并沉淀的工程约束（blocking 客户端与 runtime 的
关系、显式超时、偏移量契约 CC-001）已写入[后端指南](../guides/guide-backend)。
