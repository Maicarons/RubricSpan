# -*- coding: utf-8 -*-
"""M0-7: OpenAI-compatible labeling client connectivity check.

Loads ../.env, lists models, makes one minimal chat completion call with the
configured labeling model, and prints token usage for cost estimation.

Usage:
    python train/examples/smoke_llm_client.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    env = load_env(root / ".env")
    base_url = env.get("OPENAI_BASE_URL")
    api_key = env.get("OPENAI_API_KEY")
    model = env.get("LABELING_MODEL", "")
    timeout = float(env.get("LLM_TIMEOUT_SECS", "120"))
    if not base_url or not api_key or not model:
        print("FAIL: OPENAI_BASE_URL / OPENAI_API_KEY / LABELING_MODEL not set in .env")
        return 1

    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    # 1) list models (connectivity + auth)
    models = [m.id for m in client.models.list().data]
    print(f"endpoint OK, {len(models)} models; labeling model '{model}' available: {model in models}")

    # 2) one strict-JSON chat completion, mimicking a tiny labeling call
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是阅卷教师。只输出严格 JSON，不要多余文本。"},
            {
                "role": "user",
                "content": (
                    '得分点: {"point_text": "戊戌变法", "aliases": ["百日维新", "维新运动"]}\n'
                    '学生答案: "百日维新促进了思想启蒙"\n'
                    '输出 JSON: {"hit": true/false, "hit_type": "exact|semantic|miss", '
                    '"extracted_span": "...", "confidence": 0.0-1.0}'
                ),
            },
        ],
        temperature=0.1,
        max_tokens=120,
    )
    dt = time.time() - t0
    content = resp.choices[0].message.content.strip()
    usage = resp.usage
    print(f"chat OK in {dt:.1f}s | prompt={usage.prompt_tokens} tok, completion={usage.completion_tokens} tok")
    print(f"response: {content[:200]}")

    import json as _json

    try:
        parsed = _json.loads(content)
        assert parsed.get("hit_type") in ("exact", "semantic", "miss")
        print("PASS: strict JSON labeling output verified")
    except Exception as e:
        print(f"WARN: JSON parse issue ({e}); provider may need response_format/json mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
