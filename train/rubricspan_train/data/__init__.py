"""data —— 训练数据构建（M1 收尾）。

职责（技术方案 §7.4）：
- MRC 数据：对齐成功样本 → (得分点, 学生答案, start, end, has_answer) 五元组；
  随机约 20% 置为"无答案"负样本；semantic 样本的 span 对齐到学生答案中的同义表述；
- 相似度数据：(得分点, 学生答案, hit_type, partial_credit) → 句子对 + 连续标签
  （exact→1.0，semantic→partial_credit，miss→0.0）；
- 训练/验证/测试划分：固定随机种子并记录。
"""
