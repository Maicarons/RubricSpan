#!/usr/bin/env python3
"""M8 金标重采集（训练侧参考实现）：为新模型重算推理金标（旧 golden 作废）。

原采集脚本依赖已删除的 Python 运行时（:8771）；本脚本改用与 Rust 侧同一模型的
Python 参考实现（onnxruntime CPU EP + HuggingFace `tokenizers` 原生加载 tokenizer.json），
按 `rubricspan-inference/src/ort_backend.rs` 的逐步算法复刻（对齐注释见下），
产出与 `parity_check` 同构的 golden JSON。

用例复用旧 `data/goldens/inference_golden.json`（只重算 out），避免抽样偏差；
本脚本与 Rust 侧共享同一 tokenizer.json / model.onnx，offsets/截断语义同源。

用法：python scripts/m8_recapture_golden.py [--golden-in data/goldens/inference_golden.json] [--models-dir models]
产出：data/goldens/inference_golden.json（覆盖）
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


def log_softmax_stable(xs) -> np.ndarray:
    xs = np.asarray(xs, dtype=np.float64)
    m = xs.max()
    exps = np.exp(xs - m)
    z = exps.sum()
    return np.log(exps) - np.log(z)


def round6(x: float) -> float:
    return round(x * 1e6) / 1e6


def byte_to_char(s: str) -> list[int]:
    """UTF-8 字节偏移 → 字符序号映射表 m[byte_pos]；末位 m[len(bytes)] = 字符总数。"""
    bs = s.encode("utf-8")
    m = [0] * (len(bs) + 1)
    ci = 0
    pos = 0
    for ch in s:
        blen = len(ch.encode("utf-8"))
        for k in range(blen):
            m[pos + k] = ci
        pos += blen
        ci += 1
    m[len(bs)] = ci
    return m


class PyOrtBackend:
    """Python 参考实现：与 ort_backend.rs 逐步对齐。"""

    MAX_SEQ_LEN = 512
    MAX_SPAN_TOKENS = 64
    SIM_MAX_LEN = 128
    SIM_DIM = 768

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir

        self.mrc_tok = Tokenizer.from_file(str(models_dir / "mrc" / "tokenizer" / "tokenizer.json"))
        self.mrc_tok.enable_truncation(
            max_length=self.MAX_SEQ_LEN, stride=0, strategy="only_second",
            direction="right",
        )
        self.mrc_sess = ort.InferenceSession(
            str(models_dir / "mrc" / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self.mrc_pad = self.mrc_tok.token_to_id("[PAD]") or 0

        self.sim_tok = Tokenizer.from_file(str(models_dir / "similarity" / "tokenizer" / "tokenizer.json"))
        self.sim_tok.enable_truncation(
            max_length=self.SIM_MAX_LEN, stride=0, strategy="longest_first",
            direction="right",
        )
        self.sim_sess = ort.InferenceSession(
            str(models_dir / "similarity" / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self.sim_pad = self.sim_tok.token_to_id("[PAD]") or 0

    # ---- MRC（对应 ort_backend.rs mrc_detail / featurize_pair / decode_span）----
    def mrc_detail(self, query: str, context: str) -> dict:
        if not context:
            return {"has_answer_prob": 0.0, "start": 0, "end": 0, "span": ""}
        enc = self.mrc_tok.encode(query, context, add_special_tokens=True)
        ids = list(enc.ids) + [self.mrc_pad] * (self.MAX_SEQ_LEN - len(enc.ids))
        mask = list(enc.attention_mask) + [0] * (self.MAX_SEQ_LEN - len(enc.attention_mask))
        types = list(enc.type_ids) + [0] * (self.MAX_SEQ_LEN - len(enc.type_ids))
        ids = ids[: self.MAX_SEQ_LEN]
        mask = mask[: self.MAX_SEQ_LEN]
        types = types[: self.MAX_SEQ_LEN]
        seq_ids = enc.sequence_ids
        offsets = enc.offsets

        ctx_idx = [i for i, s in enumerate(seq_ids) if s == 1]
        if not ctx_idx:
            return {"has_answer_prob": 0.0, "start": 0, "end": 0, "span": ""}
        lo, hi = ctx_idx[0], ctx_idx[-1]

        feeds = {
            "input_ids": np.asarray([ids], dtype=np.int64),
            "attention_mask": np.asarray([mask], dtype=np.int64),
        }
        if any(o.name == "token_type_ids" for o in self.mrc_sess.get_inputs()):
            feeds["token_type_ids"] = np.asarray([types], dtype=np.int64)
        out = self.mrc_sess.run(None, feeds)
        names = [o.name for o in self.mrc_sess.get_outputs()]
        start_logits = out[names.index("start_logits")][0].astype(np.float64)
        end_logits = out[names.index("end_logits")][0].astype(np.float64)

        s_probs = log_softmax_stable(start_logits)
        e_probs = log_softmax_stable(end_logits)
        null_logprob = s_probs[0] + e_probs[0]

        best_score = -1e12
        best_i = best_j = lo
        for i in range(lo, hi + 1):
            j_last = min(i + self.MAX_SPAN_TOKENS - 1, hi)
            for j in range(i, j_last + 1):
                score = s_probs[i] + e_probs[j]
                if score > best_score:
                    best_score = score
                    best_i, best_j = i, j
        has_answer_prob = 1.0 / (1.0 + math.exp(null_logprob - best_score))

        # offsets 实测为**字符级**偏移（tokenizers 当前版本对 pair 返回字符位置），
        # 直接以此切片 context（字符串索引即字符下标）；不再做字节→字符换算。
        start_char = offsets[best_i][0] if best_i < len(offsets) else 0
        end_char_excl = offsets[best_j][1] if best_j < len(offsets) else start_char
        end_closed = max(end_char_excl - 1, start_char)
        span = context[start_char : end_closed + 1]
        return {
            "has_answer_prob": round6(has_answer_prob),
            "start": start_char,
            "end": end_closed,
            "span": span,
        }

    # ---- 相似度（对应 encode_mean + cosine）----
    def cosine(self, a: str, b: str) -> float:
        va = self._encode_mean(a)
        vb = self._encode_mean(b)
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(y * y for y in vb))
        return dot / (na * nb + 1e-9)

    def _encode_mean(self, text: str) -> list[float]:
        enc = self.sim_tok.encode(text, add_special_tokens=True)
        ids = (list(enc.ids) + [self.sim_pad] * self.SIM_MAX_LEN)[: self.SIM_MAX_LEN]
        mask = (list(enc.attention_mask) + [0] * self.SIM_MAX_LEN)[: self.SIM_MAX_LEN]
        types = (list(enc.type_ids) + [0] * self.SIM_MAX_LEN)[: self.SIM_MAX_LEN]
        feeds = {
            "input_ids": np.asarray([ids], dtype=np.int64),
            "attention_mask": np.asarray([mask], dtype=np.int64),
        }
        if any(o.name == "token_type_ids" for o in self.sim_sess.get_inputs()):
            feeds["token_type_ids"] = np.asarray([types], dtype=np.int64)
        data = self.sim_sess.run(None, feeds)[0][0].astype(np.float64)  # [128, 768]
        dim = self.SIM_DIM
        vec = np.zeros(dim, dtype=np.float64)
        denom = 0.0
        for t in range(min(data.shape[0], len(mask))):
            w = float(mask[t])
            if w <= 0:
                continue
            denom += w
            vec += data[t] * w
        if denom > 0:
            vec /= denom
        return vec.tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-in", default="data/goldens/inference_golden.json")
    ap.add_argument("--models-dir", default="models")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    golden_in = root / args.golden_in
    models_dir = root / args.models_dir
    old = json.loads(golden_in.read_text(encoding="utf-8"))
    backend = PyOrtBackend(models_dir)

    # MRC 用例：真实 full 卷等距抽样（避免空 query 等 argmax 边界合成用例）。
    # 旧 golden 的 mrc 用例一并保留（仅重算 out），保证与历史对拍连续性；
    # 过滤空 query（得分点文本在实际中恒非空）。
    used = {}
    for case in old["mrc"]:
        if case["query"]:
            used.setdefault((case["query"], case["context"]), None)
    mrc_rows = [json.loads(l) for l in (root / "data" / "processed" / "mrc_test.jsonl").open(encoding="utf-8")]
    full_pairs = list({(r["query"], r["context"]) for r in mrc_rows if r.get("origin") == "full" and r["query"]})
    step = max(1, len(full_pairs) // 50)
    for p in full_pairs[::step][:50]:
        used.setdefault(p, None)

    mrc_cases = []
    for q, c in used:
        mrc_cases.append({"query": q, "context": c, "out": backend.mrc_detail(q, c)})
    sim_cases = []
    for case in old["similarity"]:
        a, b = case["a"], case["b"]
        sim_cases.append({"a": a, "b": b, "out": {"cosine": round6(backend.cosine(a, b))}})

    payload = {
        "meta": {
            "source_runtime": "m8_recapture_golden.py（Python 参考实现，CPU EP，与 Rust 同模型/分词器）",
            "n_mrc": len(mrc_cases),
            "n_similarity": len(sim_cases),
            "tolerance_prob": 1e-3,
            "note": "Rust 对拍：has_answer_prob/cosine |diff|≤1e-3；start/end/span 须完全一致。"
            "模型经 M8 调优重训后重采集。",
        },
        "mrc": mrc_cases,
        "similarity": sim_cases,
    }
    golden_out = root / "data" / "goldens" / "inference_golden.json"
    golden_out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已重采集 {golden_out}: mrc={len(mrc_cases)} similarity={len(sim_cases)}")


if __name__ == "__main__":
    main()