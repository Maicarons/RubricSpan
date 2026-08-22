"""evaluation —— 评估指标（M2）。

职责（技术方案 §13）：一键复算以下指标并输出报告：
- Exact Match（EM）：预测 Span 与标注 Span 完全一致比例（目标 > 65%）；
- Token-level F1：Span 的 token 重叠 F1（目标 > 80%）；
- Point-wise Accuracy：各得分点命中准确率（目标 > 85%）；
- Score Correlation（Pearson）：与人工/大模型给分相关（目标 > 0.85，核心指标）；
- Human Agreement（Cohen's Kappa）（目标 > 0.7）；
- 等价命中率：aliases 命中识别能力（目标 > 80%）。

规划入口：python -m rubricspan_train.evaluation.report
"""
