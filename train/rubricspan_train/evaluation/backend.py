# -*- coding: utf-8 -*-
"""推理后端抽象：PyTorch 权重与 ONNX（fp32/int8）统一接口。

返回 ``(start_logits, end_logits)`` 的 numpy 数组（batch × seq），
供评估 / 一致性校验 / 量化对比共用。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np


Backend = Callable[[np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]


def load_backend(model_dir: str, onnx_path: str = "") -> tuple[Backend, AnyTokenizer]:
    """返回 (backend_fn, tokenizer)。onnx_path 非空时走 ONNX Runtime。"""
    if onnx_path:
        return _onnx_backend(onnx_path), _load_tokenizer(model_dir)
    return _pt_backend(model_dir), _load_tokenizer(model_dir)


def _load_tokenizer(model_dir: str) -> AnyTokenizer:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_dir, use_fast=True)


AnyTokenizer = object


def _pt_backend(model_dir: str) -> Backend:
    import torch
    from transformers import AutoModelForQuestionAnswering

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForQuestionAnswering.from_pretrained(model_dir).to(device).eval()

    @torch.no_grad()
    def fn(input_ids: np.ndarray, attention: np.ndarray, token_type: np.ndarray):
        with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
            out = model(
                input_ids=torch.from_numpy(input_ids).to(device),
                attention_mask=torch.from_numpy(attention).to(device),
                token_type_ids=torch.from_numpy(token_type).to(device),
            )
        return (out.start_logits.float().cpu().numpy(), out.end_logits.float().cpu().numpy())

    return fn


def _onnx_backend(onnx_path: str) -> Backend:
    import onnxruntime as ort

    sess = ort.InferenceSession(
        onnx_path,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    input_names = {i.name for i in sess.get_inputs()}

    def fn(input_ids: np.ndarray, attention: np.ndarray, token_type: np.ndarray):
        feeds = {
            "input_ids": input_ids.astype(np.int64),
            "attention_mask": attention.astype(np.int64),
        }
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = token_type.astype(np.int64)
        s, e = sess.run(None, feeds)
        return s, e

    return fn
