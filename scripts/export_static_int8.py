#!/usr/bin/env python
"""【实验性，勿用于生产】把 fp32 ONNX 模型做静态 int8 量化（QDQ + per-channel 权重）。

结论（2026-08-27，ort 2.0-rc.13 / onnxruntime 1.29 CUDA EP 实测）：
静态 QDQ 产物在 CUDA 上**数值错误**（MRC 对拍仅 1/143 过 1e-3，prob/span 大范围
漂移），在 CPU 上极慢（~10s/流水线）。因此后端解析链**不会**选择本脚本产出
（`model.int8.static.onnx`），原动态量化 `model.int8.onnx` 保持为 int8 唯一档
（CPU 部署用）。保留本脚本仅作记录与 ORT 升级后的复测入口。

校准集取自已入库的对拍金标（真实试卷文本，分布与生产一致）。

用法（仓库根目录）：
    python scripts/export_static_int8.py [models_dir=../models]
依赖：onnxruntime>=1.20（quantization 内置）、tokenizers。
"""
import json
import sys
from pathlib import Path

import numpy as np
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from tokenizers import Tokenizer


def _encode_pair(tok: Tokenizer, max_len: int, query: str, context: str) -> dict:
    enc = tok.encode(query, context, add_special_tokens=True)
    ids = list(enc.ids)[:max_len]
    mask = list(enc.attention_mask)[:max_len]
    types = list(enc.type_ids)[:max_len]
    pad = tok.token_to_id("[PAD]") or 0
    ids += [pad] * (max_len - len(ids))
    mask += [0] * (max_len - len(mask))
    types += [0] * (max_len - len(types))
    return {"input_ids": np.asarray([ids], np.int64),
            "attention_mask": np.asarray([mask], np.int64),
            "token_type_ids": np.asarray([types], np.int64)}


def _encode_single(tok: Tokenizer, max_len: int, text: str) -> dict:
    enc = tok.encode(text, add_special_tokens=True)
    ids = list(enc.ids)[:max_len]
    mask = list(enc.attention_mask)[:max_len]
    types = list(enc.type_ids)[:max_len]
    pad = tok.token_to_id("[PAD]") or 0
    ids += [pad] * (max_len - len(ids))
    mask += [0] * (max_len - len(mask))
    types += [0] * (max_len - len(types))
    return {"input_ids": np.asarray([ids], np.int64),
            "attention_mask": np.asarray([mask], np.int64),
            "token_type_ids": np.asarray([types], np.int64)}


class _Reader(CalibrationDataReader):
    """按需喂入校准样本；用真实试卷文本分布（金标）而非随机数。"""

    def __init__(self, samples: list[dict]):
        self._samples = samples
        self._i = 0

    def get_next(self):
        if self._i >= len(self._samples):
            return None
        s = self._samples[self._i]
        self._i += 1
        return s

    def rewind(self):
        self._i = 0


def _load_golden() -> dict:
    p = Path(__file__).resolve().parent.parent / "data" / "goldens" / "inference_golden.json"
    return json.loads(p.read_text(encoding="utf-8"))


def quantize(model_dir: Path, sub: str, max_len: int, pair: bool) -> None:
    src = model_dir / sub / "model.onnx"
    out = model_dir / sub / "model.int8.static.onnx"
    tok = Tokenizer.from_file(str(model_dir / sub / "tokenizer" / "tokenizer.json"))
    tok.enable_truncation(max_length=max_len, stride=0)

    golden = _load_golden()
    samples = []
    if pair:
        for c in golden["mrc"][:64]:
            samples.append(_encode_pair(tok, max_len, c["query"], c["context"]))
    else:
        texts = []
        for c in golden["similarity"][:64]:
            texts += [c["a"], c["b"]]
        for t in texts[:96]:
            samples.append(_encode_single(tok, max_len, t))

    print(f"[1/3] {sub}: 校准样本 {len(samples)} 条 -> {out.name}")
    quantize_static(
        str(src), str(out), _Reader(samples),
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        activation_type=QuantType.QInt8,
        weight_type=QuantType.QInt8,
        reduce_range=False,
    )
    # 自检：不允许残留动态量化算子（否则 CUDA 仍会落 CPU）
    import onnx
    m = onnx.load(str(out))
    dynamic = [n.op_type for n in m.graph.node if n.op_type == "DynamicQuantizeLinear"]
    print(f"[2/3] 动态量化算子残留: {len(dynamic)}（须为 0）")
    print(f"[3/3] saved {out.name} ({out.stat().st_size / 1e6:.0f}MB)")
    if dynamic:
        raise SystemExit(f"{sub}: 静态量化失败，仍含 DynamicQuantizeLinear")


def main() -> int:
    models = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../models")
    try:
        quantize(models, "mrc", 512, pair=True)
        quantize(models, "similarity", 128, pair=False)
    except Exception as e:  # noqa: BLE001
        print(f"量化失败: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())