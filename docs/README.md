# docs/ —— 项目文档

| 文件 | 说明 |
|---|---|
| `CHANGELOG-contracts.md` | 契约变更记录（契约冻结后的任何字段变更在此登记） |
| `bad-cases.md` | bad case 登记（迭代闭环入口：收集 → 重打标 → 增量微调） |
| `deployment.md` | 部署手册（M7 编写） |
| `evaluation/` | 各阶段评估报告（M2 / M7） |

## 契约变更流程

1. 在本目录 `CHANGELOG-contracts.md` 追加记录（原因 / 影响面 / 确认人）；
2. 经全部消费方确认后修改 `../contracts/` 下的契约文件；
3. 提交信息引用变更编号，如 `contracts(openapi): CC-001 ...`。
