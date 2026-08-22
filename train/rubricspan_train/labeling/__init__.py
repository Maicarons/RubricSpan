"""labeling —— 大模型打标流水线（M1）。

职责（技术方案 §7.3）：
- Prompt 构造：阅卷教师角色，要求严格 JSON 输出（契约：contracts/labeling-schema.json）；
- 合成答卷生成：四档水平（优秀/良好/及格/不及格），含同义表述设计；
- 批量调用：OpenAI 兼容 SDK，限速重试，结果落盘；
- 自一致性校验：高价值样本多温度多次调用，多数投票；
- 质量控制：过滤低置信/超长 span 异常标注。

规划入口：python -m rubricspan_train.labeling.run
"""
