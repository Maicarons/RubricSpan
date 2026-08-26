#!/usr/bin/env python
"""解析 RUBRICSPAN_PROFILE=1 的 tracing 日志，聚合推理各阶段耗时。

配合 bench_infer / rubricspan-server 使用：
    RUST_LOG=info RUBRICSPAN_PROFILE=1 cargo run --release --bin bench_infer -- \
        --precision fp16 --iters 10 > prof.txt 2>&1
    python scripts/parse_profile.py prof.txt
输出各 phase 的 avg/min/max/n；默认模式打印 mean 排序，--mode min 打印 min 排序
（min 更接近真实计算成本，去掉首启/CUDA 预热等离群值）。
"""
import argparse
import collections
import re

ANSI = re.compile(r"\x1b\[[0-9;]*m")
PHASE = re.compile(r'phase="([a-zA-Z0-9._]+)" ms=([0-9.]+)')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="tracing 日志文件（ANSI 彩色可接受）")
    ap.add_argument("--mode", choices=["mean", "min", "max"], default="mean")
    args = ap.parse_args()

    ph: dict[str, list[float]] = collections.defaultdict(list)
    with open(args.log, "rb") as f:
        raw = f.read().decode("utf-8", errors="replace")
    for line in ANSI.sub("", raw).splitlines():
        m = PHASE.search(line)
        if m:
            ph[m.group(1)].append(float(m.group(2)))

    if not ph:
        print("未解析到 phase 记录（请确认日志来自 RUBRICSPAN_PROFILE=1 的运行）")
        return 1
    key = lambda kv: (sum(kv[1]) / len(kv[1]) if args.mode == "mean" else
                      (min(kv[1]) if args.mode == "min" else max(kv[1])))
    print(f"{'phase':<14} {args.mode + '  ':>12} {'min':>9} {'max':>9} {'n':>5}")
    for k, v in sorted(ph.items(), key=key):
        stat = sum(v) / len(v) if args.mode == "mean" else (min(v) if args.mode == "min" else max(v))
        print(f"{k:<14} {stat:12.3f}ms {min(v):9.3f} {max(v):9.3f} {len(v):5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())