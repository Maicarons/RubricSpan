#!/usr/bin/env python3
"""M8 推理迁移金标采集：对旧 Python 运行时批量调用 /mrc 与 /similarity，落盘金标。

用途：MRC/相似度推理从 Python 运行时迁入 Rust（ort + tokenizers）后，
用本脚本产出的金标对 Rust 实现做一致性对拍（概率容差 ≤1e-3，span 偏移须逐字符一致）。

⚠️ 金标须以 **CPU EP** 采集（RUNTIME_FORCE_CPU=1 启动运行时），与 Rust 侧
CPU 推理同 EP 对拍；GPU 数值差异会放大边界翻转风险。

用法：python scripts/m8_capture_inference_golden.py [--sample N] [--runtime URL]
产出：data/goldens/inference_golden.json
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MRC_TEST = ROOT / "data" / "processed" / "mrc_test.jsonl"
CONFIGS = ROOT / "data" / "scoring_configs"
OUT = ROOT / "data" / "goldens" / "inference_golden.json"


def http_json(url: str, body: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--runtime", default="http://127.0.0.1:8771")
    args = ap.parse_args()

    # 1) MRC 用例：去重 (query, context)，等距抽样 + 边界用例
    pairs: "OrderedDict[tuple[str, str], None]" = OrderedDict()
    with open(MRC_TEST, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("origin") != "full":
                continue
            pairs.setdefault((row["query"], row["context"]), None)
    keys = list(pairs)
    step = max(1, len(keys) // args.sample)
    sampled = keys[::step][: args.sample]
    # 边界用例：空上下文 / 超长上下文（>512 token 风险）/ 空查询
    longest = max(keys, key=lambda k: len(k[1]))
    edge = [
        ("戊戌变法", ""),  # 空答案
        (longest[0], longest[1]),  # 最长答案
        ("", longest[1]),  # 空候选
    ]
    mrc_cases = []
    for q, c in sampled + edge:
        out = http_json(f"{args.runtime}/mrc", {"query": q, "context": c})
        mrc_cases.append({"query": q, "context": c, "out": out})

    # 2) 相似度用例：取若干配置的 point_text / aliases 对抽样上下文
    sim_cases = []
    ctxs = [c for _, c in sampled[:10]]
    cfg_files = sorted(CONFIGS.glob("*.json"))[:12]
    for cf in cfg_files:
        cfg = json.loads(cf.read_text(encoding="utf-8"))
        for p in cfg.get("points", []):
            texts = [p["point_text"]] + list(p.get("aliases", []))[:2]
            for t in texts:
                if not t.strip():
                    continue
                b = ctxs[hash(t) % len(ctxs)]
                out = http_json(f"{args.runtime}/similarity", {"a": t, "b": b})
                sim_cases.append({"a": t, "b": b, "out": out})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "source_runtime": f"{args.runtime}（CPU EP）",
            "n_mrc": len(mrc_cases),
            "n_similarity": len(sim_cases),
            "tolerance_prob": 1e-3,
            "note": "Rust 对拍：has_answer_prob/cosine |diff|≤1e-3；start/end/span 须完全一致",
        },
        "mrc": mrc_cases,
        "similarity": sim_cases,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {OUT}: mrc={len(mrc_cases)} similarity={len(sim_cases)}")


if __name__ == "__main__":
    main()
