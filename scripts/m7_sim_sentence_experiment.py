#!/usr/bin/env python3
"""BC-003 实验：相似度兜底的"全文均值池化 vs 句级最大值"分离度对比。

动机（docs/m7-eval-report.md §3.3）：全文均值池化使"同题长答案"对任意得分点
的余弦整体抬升，阈值语义随答案长度漂移。候选改进：对答案分句，取
max(句级 cos) 替代全文 cos——理论上"命中一点"的答案只有局部句子相关，
句级 max 应拉开 命中/未命中 两分布。

口径：与 m7_e2e_eval.py 相同的 36 卷等距抽样、逐点金标；模型用当前
models/similarity/model.onnx（快照版权重，结论可迁移）。CPU 推理，不扰训练。

产出：models/artifacts/sim_sentence_experiment.json + stdout 摘要
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from m7_e2e_eval import load_answers, stratified_sample  # noqa: E402

SENT_SPLIT = re.compile(r"[。！？；\n]+")
OUT = ROOT / "models" / "artifacts" / "sim_sentence_experiment.json"


def _assert_safe_runtime_url(url: str) -> None:
    """仅允许 http/https 且目标为环回/私网地址（内部评测脚本，防 SSRF）。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的协议: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1") and not (
        host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.")
    ):
        raise ValueError(f"不允许的目标主机: {host!r}")


def sim(a: str, b: str, base: str) -> float:
    """经在线运行时 /similarity 计算（模型已在服务进程内，避免重复占内存）。"""
    _assert_safe_runtime_url(base)
    req = urllib.request.Request(
        f"{base}/similarity", data=json.dumps({"a": a, "b": b}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return float(json.loads(resp.read().decode("utf-8"))["cosine"])


def auc(pos: list[float], neg: list[float]) -> float:
    """Mann–Whitney AUC：pos 得分高于 neg 的概率。"""
    if not pos or not neg:
        return float("nan")
    wins = sum(1 for p in pos for n in neg if p > n) + 0.5 * sum(
        1 for p in pos for n in neg if p == n)
    return wins / (len(pos) * len(neg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", default="http://127.0.0.1:8771")
    args = ap.parse_args()

    answers = stratified_sample(load_answers(), 36)
    print(f"评测 {len(answers)} 卷（经运行时 {args.runtime}）", flush=True)

    # 预收集全部待计算对：全文 1 次/点 + 句级 S_p 次/点
    pairs: list[dict] = []
    for ai, ans in enumerate(answers):
        sents = [s.strip() for s in SENT_SPLIT.split(ans["context"]) if s.strip()]
        for p in ans["points"]:
            pairs.append({"point": p["query"], "answer": ans["context"],
                          "sents": sents, "gold": not p["impossible"]})
    n_calls = sum(1 + len(p["sents"]) for p in pairs)
    print(f"{len(pairs)} 个得分点对，约 {n_calls} 次 /similarity 调用 …", flush=True)

    t0 = time.time()
    for i, p in enumerate(pairs):
        p["cos_full"] = sim(p["point"], p["answer"], args.runtime)
        p["cos_sent_max"] = max(
            (sim(p["point"], s, args.runtime) for s in p["sents"]), default=0.0)
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(pairs)} （累计 {time.time()-t0:.0f}s）", flush=True)

    gold = [p["gold"] for p in pairs]

    def summarize(scores: list[float]) -> dict:
        pos = [s for s, g in zip(scores, gold) if g]
        negv = [s for s, g in zip(scores, gold) if not g]
        return {"mean_pos": round(sum(pos) / max(len(pos), 1), 4),
                "mean_neg": round(sum(negv) / max(len(negv), 1), 4),
                "auc": round(auc(pos, negv), 4),
                "召回@0.60": round(sum(s >= 0.60 for s in pos) / max(len(pos), 1), 4),
                "误报率@0.60": round(sum(s >= 0.60 for s in negv) / max(len(negv), 1), 4)}

    report = {
        "n_pairs": len(pairs),
        "n_gold_present": int(gold.count(True)),
        "full_answer_pooling": summarize([p["cos_full"] for p in pairs]),
        "sentence_max": summarize([p["cos_sent_max"] for p in pairs]),
        "pairs_detail": [
            {"point": p["point"], "gold": p["gold"],
             "cos_full": round(p["cos_full"], 4),
             "cos_sent_max": round(p["cos_sent_max"], 4)}
            for p in pairs],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== 全文均值池化 ====")
    print(json.dumps(report["full_answer_pooling"], ensure_ascii=False, indent=2))
    print("==== 句级最大值 ====")
    print(json.dumps(report["sentence_max"], ensure_ascii=False, indent=2))
    print(f"\n明细 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
