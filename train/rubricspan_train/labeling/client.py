# -*- coding: utf-8 -*-
"""OpenAI 兼容打标客户端（M1-3 基础设施）。

封装 OpenAI 兼容端点（多端点 fallback 队列）的调用细节：

- 多端点 fallback 队列：``.env`` 按 ``LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL[,NAME]}``
  配置多个接入（``n`` 升序即调用优先级），未配置编号端点时回落到旧单端点变量组
  （OPENAI_BASE_URL / OPENAI_API_KEY / LABELING_MODEL）。每次调用都从队首端点
  开始；某端点整轮重试耗尽后自动切到下一个，全部端点失败才抛错（样本进重试
  队列）。无冷却、不记忆失败：队首端点恢复后，下一次调用立即回到它；
- 推理模型适配：推理型模型先输出 reasoning_content 再输出 content，
  completion 预算被思考占用。出现 ``content=None`` 且 ``finish_reason=length`` 时，
  按 2 倍递增 max_tokens 重试（上限 ``max_tokens_max``）；
- 限速与重试：并发线程池 + 指数退避（429 / 5xx / 超时 / JSON 解析失败）；
- 严格 JSON：剥离 markdown 代码栅栏后解析，失败按普通重试处理；
- token 计量：累计 prompt/completion 用量（跨端点共享），供成本核算。
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_ENDPOINT_RE = re.compile(r"^LLM_ENDPOINT_(\d+)_(BASE_URL|API_KEY|MODEL|NAME)$")


def load_env(env_path: Path) -> dict[str, str]:
    """极简 .env 读取（不引入 python-dotenv 依赖）。

    环境变量优先于 .env 文件（云端如 Kaggle Secrets 以环境变量注入，可无 .env 文件）。
    """
    env: dict[str, str] = {k: v for k, v in os.environ.items() if v}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env.setdefault(k.strip(), v.strip())
    return env


class LabelCallError(RuntimeError):
    """重试耗尽后的调用失败。"""


@dataclass
class UsageMeter:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.calls += 1

    def add_failure(self) -> None:
        with self._lock:
            self.failures += 1

    def summary(self) -> str:
        return (
            f"calls={self.calls} failures={self.failures} "
            f"prompt={self.prompt_tokens} tok completion={self.completion_tokens} tok "
            f"total={self.prompt_tokens + self.completion_tokens} tok"
        )


def extract_json(text: str) -> Any:
    """从模型输出提取 JSON：剥栅栏 → 首个 '{' 到与之平衡的 '}'。

    打标输出是单个 JSON 对象；平衡匹配可容忍答案文本内偶发的花括号。
    """
    text = _FENCE_RE.sub("", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("no '{' in model output")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON in model output")


# ---------------------------------------------------------------------------
# 端点队列
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EndpointSpec:
    """一个接入端点的静态配置。"""

    name: str
    base_url: str
    api_key: str
    model: str


def parse_endpoints(env: dict[str, str]) -> list[EndpointSpec]:
    """解析端点队列：``LLM_ENDPOINT_<n>_{BASE_URL,API_KEY,MODEL[,NAME]}`` 按 n 升序。

    组内变量不全的端点跳过并告警；无任何编号端点时回落到旧单端点变量组，
    保证存量 ``.env`` 不改也能跑。
    """
    groups: dict[int, dict[str, str]] = {}
    for key, value in env.items():
        m = _ENDPOINT_RE.match(key)
        if m and value:
            groups.setdefault(int(m.group(1)), {})[m.group(2)] = value
    specs: list[EndpointSpec] = []
    for n in sorted(groups):
        g = groups[n]
        missing = [f for f in ("BASE_URL", "API_KEY", "MODEL") if not g.get(f)]
        if missing:
            print(f"WARN: LLM_ENDPOINT_{n} incomplete (missing {'/'.join(missing)}), skipped")
            continue
        specs.append(
            EndpointSpec(
                name=g.get("NAME") or f"ep{n}",
                base_url=g["BASE_URL"],
                api_key=g["API_KEY"],
                model=g["MODEL"],
            )
        )
    if specs:
        return specs
    base_url = env.get("OPENAI_BASE_URL")
    api_key = env.get("OPENAI_API_KEY")
    model = env.get("LABELING_MODEL")
    if base_url and api_key and model:
        return [EndpointSpec(name="ep1", base_url=base_url, api_key=api_key, model=model)]
    return []


class LLMResponse(dict):
    """chat_json 的返回值：解析后的 JSON 对象（dict 兼容），附带产出端点信息。"""

    source_endpoint: str = ""
    source_model: str = ""


def _default_client_factory(spec: EndpointSpec, timeout: float) -> Any:
    from openai import OpenAI

    return OpenAI(base_url=spec.base_url, api_key=spec.api_key, timeout=timeout)


class _EndpointRuntime:
    """单端点运行时：独立的 OpenAI 客户端（无状态，线程安全）。"""

    def __init__(
        self,
        spec: EndpointSpec,
        *,
        timeout: float,
        max_attempts: int,
        backoff_base: float,
        max_tokens_initial: int,
        max_tokens_max: int,
        meter: UsageMeter,
        client_factory: Callable[[EndpointSpec, float], Any],
    ) -> None:
        self.spec = spec
        self.model = spec.model
        self._client = client_factory(spec, timeout)
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.max_tokens_initial = max_tokens_initial
        self.max_tokens_max = max_tokens_max
        self.meter = meter  # 跨端点共享的计量器

    def chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """单端点调用：退避重试 + reasoning 模型 max_tokens 自适应 + 严格 JSON 解析。"""
        limit = max_tokens or self.max_tokens_initial
        last_err: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=list(messages),
                    temperature=temperature,
                    max_tokens=limit,
                )
                choice = resp.choices[0]
                content = choice.message.content
                usage = resp.usage
                if usage is not None:
                    self.meter.add(usage.prompt_tokens, usage.completion_tokens)
                truncated = choice.finish_reason == "length"
                if (truncated or not content or not content.strip()) and limit < self.max_tokens_max:
                    # 推理模型思考吃掉预算：截断/空 content 一律放大重试
                    limit = min(limit * 2, self.max_tokens_max)
                    raise _Retry(
                        f"finish={choice.finish_reason}, content_empty={not content}, "
                        f"raise max_tokens -> {limit}"
                    )
                if not content or not content.strip():
                    raise _Retry(f"content empty (finish={choice.finish_reason})")
                out = LLMResponse(extract_json(content))
                out.source_endpoint = self.spec.name
                out.source_model = self.model
                return out
            except _Retry as r:
                last_err = r  # 已知可重试状态，直接退避
            except Exception as e:  # noqa: BLE001 - 429/5xx/超时/JSON 解析统一退避
                last_err = e
                if limit < self.max_tokens_max:
                    # JSON 解析失败大概率也是截断所致，同样放大预算
                    limit = min(limit * 2, self.max_tokens_max)
            self._sleep(attempt)
        raise LabelCallError(
            f"{self.spec.name}/{self.model} failed after {self.max_attempts} attempts: {last_err}"
        )

    def _sleep(self, attempt: int) -> None:
        delay = self.backoff_base * (2**attempt) + random.uniform(0, 1)
        time.sleep(min(delay, 60.0))


class LLMClient:
    """线程安全的多端点批量 chat 客户端（fallback 队列）。

    每次调用都从队首（最高优先级）端点开始；某端点整轮重试耗尽后自动切到
    下一个，全部端点失败才向调用方抛 ``LabelCallError``（样本进重试队列）。
    无冷却、不记忆失败：队首端点恢复后，下一次调用立即回到它。
    """

    def __init__(
        self,
        endpoints: Sequence[EndpointSpec],
        *,
        timeout: float = 120.0,
        concurrency: int = 8,
        max_attempts: int = 4,
        backoff_base: float = 2.0,
        max_tokens_initial: int = 3072,
        max_tokens_max: int = 8192,
        client_factory: Callable[[EndpointSpec, float], Any] | None = None,
    ) -> None:
        if not endpoints:
            raise ValueError("at least one endpoint is required")
        self.meter = UsageMeter()
        self.concurrency = concurrency
        self._endpoints = [
            _EndpointRuntime(
                spec,
                timeout=timeout,
                max_attempts=max_attempts,
                backoff_base=backoff_base,
                max_tokens_initial=max_tokens_initial,
                max_tokens_max=max_tokens_max,
                meter=self.meter,
                client_factory=client_factory or _default_client_factory,
            )
            for spec in endpoints
        ]

    @classmethod
    def from_env(
        cls, env_path: Path, cfg: dict[str, Any] | None = None
    ) -> "LLMClient":
        cfg = cfg or {}
        env = load_env(env_path)
        specs = parse_endpoints(env)
        if not specs:
            raise SystemExit(
                f"FAIL: no LLM_ENDPOINT_<n>_{{BASE_URL,API_KEY,MODEL}} groups (nor legacy "
                f"OPENAI_BASE_URL/OPENAI_API_KEY/LABELING_MODEL) set in {env_path}"
            )
        ccfg = cfg.get("client", {})
        return cls(
            specs,
            timeout=float(env.get("LLM_TIMEOUT_SECS", "120")),
            concurrency=int(ccfg.get("concurrency", 8)),
            max_attempts=int(ccfg.get("max_attempts", 4)),
            backoff_base=float(ccfg.get("backoff_base_secs", 2.0)),
            max_tokens_initial=int(ccfg.get("max_tokens_initial", 3072)),
            max_tokens_max=int(ccfg.get("max_tokens_max", 8192)),
        )

    @property
    def model(self) -> str:
        """元数据回退值：队首端点的模型名（精确值见 LLMResponse.source_model）。"""
        return self._endpoints[0].model

    def describe(self) -> str:
        """端点队列一览（优先级从左到右）。"""
        return " -> ".join(f"{ep.spec.name}({ep.model})" for ep in self._endpoints)

    # ------------------------------------------------------------------ single

    def chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """一次调用并解析为 JSON：每次都从队首端点开始，失败依次 fallback。"""
        errors: list[str] = []
        for i, ep in enumerate(self._endpoints):
            try:
                return ep.chat_json(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as e:  # noqa: BLE001 - 该端点整轮重试耗尽 → 切下一个端点
                errors.append(f"{ep.spec.name}({ep.model}): {e}")
                nxt = self._endpoints[i + 1].spec.name if i + 1 < len(self._endpoints) else "-"
                print(
                    f"  [client] endpoint '{ep.spec.name}' failed -> try '{nxt}'",
                    flush=True,
                )
        self.meter.add_failure()
        raise LabelCallError(
            f"all {len(self._endpoints)} endpoints failed: " + " | ".join(errors)
        )

    # ------------------------------------------------------------------- batch

    def map_json(
        self,
        items: Iterable[Any],
        fn: Callable[[Any], tuple[Sequence[dict[str, str]], dict[str, Any]]],
        *,
        progress_every: int = 50,
        progress_label: str = "",
        on_result: Callable[[Any, Any], None] | None = None,
    ) -> list[tuple[Any, Any]]:
        """并发处理 items：fn(item) 返回 (messages, kwargs)，结果为 (item, json)。

        单项失败不中断批次：失败项以 (item, LabelCallError) 返回，由调用方落盘为
        待重试队列（断点续跑）。``on_result(item, result)`` 在每个 future 完成时
        同步回调，供长批次增量落盘。
        """
        items = list(items)
        results: list[tuple[Any, Any]] = []
        done = 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futures = {}
            for it in items:
                messages, kwargs = fn(it)
                futures[ex.submit(self.chat_json, messages, **kwargs)] = it
            for fut in as_completed(futures):
                it = futures[fut]
                try:
                    res = fut.result()
                    results.append((it, res))
                except LabelCallError as e:
                    res = e
                    results.append((it, e))
                if on_result is not None:
                    try:
                        on_result(it, res)
                    except Exception:  # noqa: BLE001 - 落盘失败不拖垮批次
                        pass
                done += 1
                if progress_every and done % progress_every == 0:
                    rate = done / max(time.time() - t0, 1e-6)
                    print(f"  [{progress_label}] {done}/{len(items)} ({rate:.1f}/s) {self.meter.summary()}", flush=True)
        return results


class _Retry(Exception):
    """内部可控重试信号。"""
