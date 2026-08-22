# 训练与打标配置目录

存放 YAML 配置文件：打标 Prompt 版本、训练超参、数据划分种子等。

## 规划清单（M1–M2 填充）

| 文件 | 用途 |
|---|---|
| `labeling.yaml` | 打标模型、温度、并发限速、自一致性投票次数 |
| `train_mrc.yaml` | MRC 微调超参（lr / batch / epoch / max_len / 早停） |
| `train_similarity.yaml` | 相似度模型微调超参 |
| `data_split.yaml` | 训练/验证/测试划分比例与随机种子 |
