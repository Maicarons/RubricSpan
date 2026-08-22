"""training —— 模型训练（M2）。

职责（技术方案 §9）：
- MRC 微调：Langboat/mengzi-bert-base，起点/终点交叉熵 + has_answer 二分类损失；
  超参基线：lr 2e-5~3e-5，AdamW + 线性 warmup(0.1)，batch 16–32，epoch 3–5 早停，max_len 384；
- 相似度微调：shibing624/text2vec-base-chinese + CosineSimilarityLoss；
- CMRC 2018 预训练桥接（可选）；
- 显存不足时降 batch + 梯度累积。

规划入口：
  python -m rubricspan_train.training.train_mrc
  python -m rubricspan_train.training.train_similarity
"""
