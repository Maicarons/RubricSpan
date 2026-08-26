# M2-6 PyTorch ↔ ONNX 一致性校验

```json
{
  "checked_at": "2026-08-23T11:17:55+00:00",
  "n_examples": 100,
  "max_abs_logit_diff": 5.221366882324219e-05,
  "tolerance": 0.001,
  "pass": true,
  "note": "FP32 导出，CPU EP；diff < 1e-3 判过（bf16 训练权重已 round 回 FP32）"
}
```
