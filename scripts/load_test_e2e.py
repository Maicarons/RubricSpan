#!/usr/bin/env python
"""在线评分端到端压测：自启服务（或连已有实例）→ HTTP 种子数据 → 并发打 /api/score。

测的是完整在线链路（HTTP → 校验 → 存储读 → spawn_blocking 推理 → 批量落盘），
并按并发度扫描观察 ConcurrencyLimit(4) 的队列/饱和行为。

用法（仓库根目录；服务二进制需先构建）：
    cargo build --release -p rubricspan-server
    python scripts/load_test_e2e.py --precision fp16 --pool 2 --oversub 1 4 8 16

参数：
    --base-url  http://host:port   连已有服务（默认自启 127.0.0.1:18080）
    --precision fp16|fp32|int8    自启服务用的精度档（默认 fp16）
    --pool      N                  自启服务会话池（默认 2）
    --points    N                  每题得分点数（默认 4）
    --answers   N                  提交答卷数（默认 12）
    --oversub   1 4 8 16           并发客户端数（默认 1 4 8 16）
    --calls     N                  每个并发档的总评分请求数（默认 60）
"""
import argparse
import concurrent.futures as cf
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "backend" / "target" / "release" / ("rubricspan-server.exe" if os.name == "nt" else "rubricspan-server")

POINT_POOL = [
    "结合材料分析其历史背景", "指出其中的主张与论据", "概括该事件的影响",
    "说明作者持此观点的依据", "比较两者的异同", "评价其现实意义",
]
ANSWER_TEMPLATE = (
    "该问题需结合时代背景分析。从材料一可以看出，经济基础的变化推动了上层建筑调整，"
    "这既是长期积累的结果，也是多方力量共同作用的结果。作者之所以持此观点，"
    "是因为实践检验表明这一趋势不可逆转，其影响将随政策完善而进一步显现。"
)


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


def http_json(url: str, payload=None, method: str | None = None, timeout: float = 30.0):
    _assert_safe_runtime_url(url)
    data = json.dumps(payload).encode() if payload is not None else None
    if method is None:
        method = "POST" if payload is not None else "GET"
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} -> {e.code} {e.reason}: {e.read()[:200]}") from e


def start_server(args) -> tuple[subprocess.Popen, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="rs_e2e_"))
    env = os.environ.copy()
    env["RUBRICSPAN_MODEL_PRECISION"] = args.precision
    env["RUBRICSPAN_SESSION_POOL"] = str(args.pool)
    if args.concurrency:
        env["RUBRICSPAN_INFER_CONCURRENCY"] = str(args.concurrency)
    env_file = tmp / "env"
    env_file.write_text("", encoding="utf-8")
    cmd = [
        str(BIN), "--listen", "127.0.0.1:18080", "--models-dir", str(REPO / "models"),
        "--storage", "sqlite", "--store", str(tmp / "e2e.db"), "--env-file", str(env_file),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:18080"
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"服务启动即退出（{proc.returncode}），检查模型/二进制")
        try:
            if http_json(f"{base}/api/health", timeout=2).get("status") == "ok":
                return proc, tmp
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            time.sleep(0.5)
    raise RuntimeError("服务 120s 内未就绪")


def seed(base: str, args) -> list[str]:
    qid = "BENCH-E2E"
    http_json(f"{base}/api/questions", {
        "question_id": qid, "content": "性能压测题", "subject": "语文", "total_score": float(args.points * 2),
    })
    points = [
        {"point_id": i + 1, "point_text": POINT_POOL[i % len(POINT_POOL)], "weight": 2.0, "aliases": []}
        for i in range(args.points)
    ]
    http_json(f"{base}/api/standard-answer", {
        "question_id": qid, "total_score": float(args.points * 2), "points": points,
    }, method="PUT")
    peers = [ANSWER_TEMPLATE + f"（第{n}组表述，围绕同一核心观点展开）" for n in range(args.answers)]
    body = {"question_id": qid, "submissions": [{"answer_text": t, "source": "text"} for t in peers]}
    ids = http_json(f"{base}/api/answers", body)["answer_ids"]
    return ids


def load_run(base: str, ids: list[str], oversub: int, calls: int, ids_per_req: int) -> dict:
    latencies: list[float] = []
    errors = 0
    ids_done = 0
    wall_t0 = time.perf_counter()
    ids_by_worker = [ids[i % len(ids)] for i in range(calls * ids_per_req)]

    def one_call(chunk: list[str]) -> None:
        nonlocal errors
        t0 = time.perf_counter()
        try:
            http_json(f"{base}/api/score", {"question_id": "BENCH-E2E", "answer_ids": chunk}, timeout=60)
            latencies.append((time.perf_counter() - t0) * 1e3)
        except Exception:
            errors += 1

    chunks = [ids_by_worker[i * ids_per_req:(i + 1) * ids_per_req] for i in range(calls)]
    with cf.ThreadPoolExecutor(max_workers=oversub) as pool:
        list(pool.map(one_call, chunks))
    ids_done = calls * ids_per_req
    wall = time.perf_counter() - wall_t0
    latencies.sort()
    p = lambda q: latencies[min(len(latencies) - 1, int(q * len(latencies)))]
    return {
        "oversub": oversub, "calls": calls, "errors": errors,
        "wall": wall, "ids": ids_done, "tps": ids_done / wall,
        "p50": p(0.5), "p95": p(0.95), "p99": p(0.99), "max": latencies[-1],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--precision", default="fp16")
    ap.add_argument("--pool", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=None, help="RUBRICSPAN_INFER_CONCURRENCY（默认服务端 4）")
    ap.add_argument("--points", type=int, default=4)
    ap.add_argument("--answers", type=int, default=12)
    ap.add_argument("--oversub", type=int, nargs="+", default=[1, 4, 8, 16])
    ap.add_argument("--calls", type=int, default=60)
    args = ap.parse_args()

    if not BIN.exists():
        sys.exit(f"未找到 {BIN}\n请先执行：cargo build --release -p rubricspan-server")

    proc = tmp = None
    try:
        base = args.base_url
        if base is None:
            cc = f" concurrency={args.concurrency}" if args.concurrency else ""
            print(f"=== 自启服务：precision={args.precision} pool={args.pool}{cc}（对拍验收档为 fp32，fp16/静态int8 为 GPU 部署档）===")
            proc, tmp = start_server(args)
            base = f"http://127.0.0.1:18080"
            print(f"服务就绪：{base}")
        ids = seed(base, args)
        print(f"种子就绪：{len(ids)} 份答卷 × {args.points} 点")
        http_json(f"{base}/api/score", {"question_id": "BENCH-E2E", "answer_ids": ids[0:1]})  # 预热
        print(f"{'并发':<6}{'请求':<6}{'错误':<6}{'耗时s':<8}{'吞吐题/s':<10}{'p50 ms':<9}{'p95 ms':<9}{'p99 ms':<9}{'max ms':<9}")
        for oversub in args.oversub:
            r = load_run(base, ids, oversub, args.calls, ids_per_req=5)
            print(f"{r['oversub']:<6}{r['calls']:<6}{r['errors']:<6}{r['wall']:<8.1f}{r['tps']:<10.2f}"
                  f"{r['p50']:<9.1f}{r['p95']:<9.1f}{r['p99']:<9.1f}{r['max']:<9.1f}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if tmp is not None:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()