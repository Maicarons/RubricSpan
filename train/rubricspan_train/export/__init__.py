"""export —— 模型导出（M2 收尾）。

职责（技术方案 §9.4 + contracts/model-artifacts.md）：
- ONNX 导出：MRC（mengzi-bert-base）与相似度（text2vec）模型；
- INT8 量化：体积压缩约 1/4，精度损失须 < 1%；
- PyTorch ↔ ONNX 输出一致性校验（同输入比对，容差内）；
- 产物落盘遵守 contracts/model-artifacts.md 目录/命名规范；
- 导出后计算并写入 sha256，ONNX Runtime 加载自检。

规划入口：python -m rubricspan_train.export.onnx
"""
