# .github —— GitHub 配置

| 路径 | 说明 |
|---|---|
| `workflows/ci.yml` | 持续集成：Rust 后端构建+测试+clippy、前端类型检查+构建、训练侧语法与契约校验 |
| `ISSUE_TEMPLATE/` | Issue 模板（bug / bad case 上报） |
| `PULL_REQUEST_TEMPLATE.md` | PR 模板 |

## 分支策略（执行计划 §6.2）

- `main`：始终可构建，里程碑评审通过后合并；
- `dev`：日常集成分支；
- 功能分支 `feat/<模块>-<简述>`，修复分支 `fix/<简述>`；
- 每个里程碑打 tag：`m0-env` … `m7-release`。
