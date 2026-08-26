# M2-7 INT8 量化对比

```json
{
  "quantized_at": "2026-08-23T11:42:23+00:00",
  "method": "quantize_dynamic QInt8 per-channel",
  "metric_drops_fp32_minus_int8": {
    "em": 0.0079,
    "token_f1": 0.0069,
    "point_accuracy": 0.0042
  },
  "pass": true,
  "mrc_fp32": {
    "em": 0.4815,
    "token_f1": 0.7578,
    "point_accuracy": 0.894,
    "equivalence_hit_rate": 0.9431
  },
  "mrc_int8": {
    "em": 0.4736,
    "token_f1": 0.7509,
    "point_accuracy": 0.8898,
    "equivalence_hit_rate": 0.9374
  }
}
```
