# -*- coding: utf-8 -*-
"""M2-5/6/7：ONNX 导出、一致性校验、INT8 量化。

用法（train/ 目录）::

    python -m rubricspan_train.export.onnx            # 导出 mrc + similarity → models/{mrc,similarity}/
    python -m rubricspan_train.export.onnx verify      # M2-6 PyTorch ↔ ONNX 一致性
    python -m rubricspan_train.export.onnx quantize    # M2-7 INT8 + 精度损失验证

产物布局严格遵守 ``contracts/model-artifacts.md``：
``models/mrc/model.onnx(+model.int8.onnx)/tokenizer/model_card.json``、
``models/similarity/...``、``models/scoring_defaults.json``。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..common_paths import DATA_DIR, MODELS_DIR, REPO_ROOT

MRC_PT = MODELS_DIR / "artifacts" / "mrc" / "pytorch"
SIM_PT = MODELS_DIR / "artifacts" / "similarity" / "pytorch"
MRC_OUT = MODELS_DIR / "mrc"
SIM_OUT = MODELS_DIR / "similarity"
OPSET = 17


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _export_bert(model, out_path: Path, example: dict, mode: str) -> None:
    import torch

    class _Wrapper(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask, token_type_ids):
            out = self.m(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
            )
            if mode == "qa":
                return out.start_logits, out.end_logits
            return out.last_hidden_state

    wrapped = _Wrapper(model).eval()
    output_names = (
        ["start_logits", "end_logits"] if mode == "qa" else ["last_hidden_state"]
    )
    with torch.no_grad():
        torch.onnx.export(
            wrapped,
            (example["input_ids"], example["attention_mask"], example["token_type_ids"]),
            str(out_path),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=output_names,
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "token_type_ids": {0: "batch", 1: "seq"},
            },
            opset_version=OPSET,
            dynamo=False,
            do_constant_folding=False,  # PyTorch 2.10+ 常量折叠可导致 LayerNormalization 类型混合
        )
    print(f"exported -> {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


def _example_batch(tokenizer) -> dict:
    import torch

    enc = tokenizer(
        ["得分点表述"], ["学生答案文本"],
        max_length=64, padding="max_length", return_tensors="pt",
    )
    return {k: v for k, v in enc.items() if k in ("input_ids", "attention_mask", "token_type_ids")}


def export_mrc() -> None:
    import torch
    from transformers import AutoModelForQuestionAnswering, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MRC_PT, use_fast=True)
    model = AutoModelForQuestionAnswering.from_pretrained(MRC_PT)
    MRC_OUT.mkdir(parents=True, exist_ok=True)
    _export_bert(model, MRC_OUT / "model.onnx", _example_batch(tok), mode="qa")
    tok.save_pretrained(MRC_OUT / "tokenizer")

    eval_pt = json.loads((MODELS_DIR / "artifacts" / "mrc" / "eval_pt.json").read_text(encoding="utf-8"))
    train_log = json.loads((MODELS_DIR / "artifacts" / "mrc" / "train_log.json").read_text(encoding="utf-8"))
    card = {
        "name": "mrc-mengzi-bert",
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "base_model": "Langboat/mengzi-bert-base",
        "task": "mrc_extraction",
        "max_seq_length": 512,
        "onnx_opset": OPSET,
        "training_data": {
            "dataset": "sasbench+synthetic MRC five-tuples (M1-7)",
            "samples": train_log.get("main", {}).get("train_features"),
            "bridge": "CMRC2018 1 epoch",
            "seed": 42,
        },
        "metrics": {
            "em": eval_pt.get("em"),
            "token_f1": eval_pt.get("token_f1"),
            "point_acc": eval_pt.get("point_accuracy"),
            "score_corr": (eval_pt.get("score_correlation") or {}).get("pearson_vs_expert"),
            "alias_hit_rate": eval_pt.get("equivalence_hit_rate"),
        },
        "has_answer_threshold": eval_pt.get("has_answer_threshold"),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": sha256_of(MRC_OUT / "model.onnx"),
    }
    (MRC_OUT / "model_card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def export_similarity() -> None:
    """导出 text2vec 的 BERT 主干（输出 last_hidden_state，池化由推理侧完成）。"""
    from sentence_transformers import SentenceTransformer

    # 显式 device="cpu"：导出与设备无关，且避免与同机训练争用 GPU。
    st = SentenceTransformer(str(SIM_PT), device="cpu")
    bert = st[0].auto_model
    tok = st.tokenizer
    SIM_OUT.mkdir(parents=True, exist_ok=True)
    _export_bert(bert, SIM_OUT / "model.onnx", _example_batch(tok), mode="encoder")
    # 分词器直接从微调产物拷贝（ST 格式 = HF 格式）
    tok_dir = SIM_OUT / "tokenizer"
    tok_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vocab.txt", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
        src = SIM_PT / name
        if src.exists():
            shutil.copy(src, tok_dir / name)

    # train_log.json 由训练脚本在 fit 结束后写入；对中途快照导出容忍缺失。
    log_path = SIM_PT / "train_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    card = {
        "name": "similarity-text2vec-base-chinese",
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "base_model": "shibing624/text2vec-base-chinese",
        "task": "sentence_similarity",
        "pooling": "mean (推理侧按 attention_mask 池化)",
        "max_seq_length": 128,
        "onnx_opset": OPSET,
        "training_data": {
            "dataset": "M1-7 similarity pairs + SAS-Datasets + STS-B zh",
            "pairs": log.get("train_pairs"),
            "loss": "CosineSimilarityLoss",
            "seed": 42,
        },
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": sha256_of(SIM_OUT / "model.onnx"),
    }
    (SIM_OUT / "model_card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_scoring_defaults() -> None:
    """全局评分默认配置（契约 §3：题级配置可覆盖）。"""
    eval_pt = {}
    p = MODELS_DIR / "artifacts" / "mrc" / "eval_pt.json"
    if p.exists():
        eval_pt = json.loads(p.read_text(encoding="utf-8"))
    defaults = {
        "similarity_high": 0.85,
        "similarity_low": 0.60,
        "mrc_has_answer_threshold": eval_pt.get("has_answer_threshold", 0.0),
        "mrc_min_span_length": 1,
        "mrc_max_span_length": 64,
        "partial_credit_default": 0.5,
    }
    (MODELS_DIR / "scoring_defaults.json").write_text(
        json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("scoring_defaults.json written")


def cmd_export() -> None:
    export_mrc()
    export_similarity()
    write_scoring_defaults()


# ---------------------------------------------------------------------------
# M2-6 一致性校验
# ---------------------------------------------------------------------------


def cmd_verify() -> None:
    import torch
    from transformers import AutoModelForQuestionAnswering, AutoTokenizer
    import onnxruntime as ort

    tok = AutoTokenizer.from_pretrained(MRC_PT, use_fast=True)
    model = AutoModelForQuestionAnswering.from_pretrained(MRC_PT).eval()
    sess = ort.InferenceSession(str(MRC_OUT / "model.onnx"), providers=["CPUExecutionProvider"])

    import json as _json

    test = [
        _json.loads(line)
        for line in (DATA_DIR / "processed" / "mrc_test.jsonl").read_text(encoding="utf-8").splitlines()
    ][:100]
    max_diff = 0.0
    for i in range(0, len(test), 16):
        chunk = test[i : i + 16]
        enc = tok(
            [r["query"] for r in chunk], [r["context"] for r in chunk],
            max_length=512, truncation="only_second", padding="max_length",
            return_tensors="np",
        )
        feeds = {k: enc[k].astype(np.int64) for k in ("input_ids", "attention_mask", "token_type_ids")}
        with torch.no_grad():
            pt_out = model(
                input_ids=torch.from_numpy(feeds["input_ids"]),
                attention_mask=torch.from_numpy(feeds["attention_mask"]),
                token_type_ids=torch.from_numpy(feeds["token_type_ids"]),
            )
        pt_s = pt_out.start_logits.numpy()
        pt_e = pt_out.end_logits.numpy()
        onx_s, onx_e = sess.run(None, feeds)
        max_diff = max(max_diff, float(np.abs(pt_s - onx_s).max()), float(np.abs(pt_e - onx_e).max()))
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_examples": len(test),
        "max_abs_logit_diff": max_diff,
        "tolerance": 1e-3,
        "pass": max_diff < 1e-3,
        "note": "FP32 导出，CPU EP；diff < 1e-3 判过（bf16 训练权重已 round 回 FP32）",
    }
    out = REPO_ROOT / "docs" / "m2-onnx-consistency.md"
    out.write_text(
        "# M2-6 PyTorch ↔ ONNX 一致性校验\n\n```json\n"
        + json.dumps(record, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(record, ensure_ascii=False))
    if not record["pass"]:
        sys.exit(1)


# ---------------------------------------------------------------------------
# M2-7 INT8 量化
# ---------------------------------------------------------------------------


def cmd_quantize() -> None:
    from onnxruntime.quantization import QuantFormat, QuantType, quantize_dynamic

    for out_dir, prefix in ((MRC_OUT, "mrc"), (SIM_OUT, "similarity")):
        src = out_dir / "model.onnx"
        dst = out_dir / "model.int8.onnx"
        try:
            quantize_dynamic(
                str(src), str(dst),
                weight_type=QuantType.QInt8,
                per_channel=True,
                extra_options={"EnableSubgraph": False},
            )
        except AssertionError as e:
            if "scale issue" in str(e):
                print(f"per_channel=True 失败，降级 per_channel=False: {e}")
                quantize_dynamic(
                    str(src), str(dst),
                    weight_type=QuantType.QInt8,
                    per_channel=False,
                    extra_options={"EnableSubgraph": False},
                )
            else:
                raise
        print(f"int8 -> {dst} ({dst.stat().st_size / 1e6:.1f} MB, "
              f"fp32 {src.stat().st_size / 1e6:.1f} MB)")

    # MRC INT8 精度损失验证（同一测试集复评，<1% 达标）
    r = subprocess.run(
        [sys.executable, "-m", "rubricspan_train.evaluation.report",
         "--onnx", str(MRC_OUT / "model.int8.onnx"), "--tag", "int8"],
        cwd=str(REPO_ROOT / "train"), capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(1)
    fp32 = json.loads((MODELS_DIR / "artifacts" / "mrc" / "eval_pt.json").read_text(encoding="utf-8"))
    int8 = json.loads((MODELS_DIR / "artifacts" / "mrc" / "eval_int8.json").read_text(encoding="utf-8"))
    drops = {
        k: round(fp32[k] - int8[k], 4)
        for k in ("em", "token_f1", "point_accuracy")
    }
    record = {
        "quantized_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "quantize_dynamic QInt8 per-channel",
        "metric_drops_fp32_minus_int8": drops,
        "pass": all(d < 0.01 for d in drops.values()),
        "mrc_fp32": {k: fp32[k] for k in ("em", "token_f1", "point_accuracy", "equivalence_hit_rate")},
        "mrc_int8": {k: int8[k] for k in ("em", "token_f1", "point_accuracy", "equivalence_hit_rate")},
    }
    out = REPO_ROOT / "docs" / "m2-int8-quantization.md"
    out.write_text(
        "# M2-7 INT8 量化对比\n\n```json\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(record, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="export", choices=["export", "verify", "quantize"])
    args = p.parse_args(argv)
    {"export": cmd_export, "verify": cmd_verify, "quantize": cmd_quantize}[args.cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
