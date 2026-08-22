# -*- coding: utf-8 -*-
"""多端点 fallback 客户端单测（注入假 OpenAI 客户端，不联网）。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from rubricspan_train.labeling import client as client_mod
from rubricspan_train.labeling.client import (
    EndpointSpec,
    LLMClient,
    LabelCallError,
    parse_endpoints,
)

MSG = [{"role": "user", "content": "hi"}]


def _resp(content='{"hit": true}', finish="stop", pt=10, ct=5) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish,
            )
        ],
        usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct),
    )


class FakeOpenAI:
    """按 behavior(**kwargs) 出牌的假客户端；记录调用次数。"""

    def __init__(self, behavior) -> None:
        self.calls = 0
        self._behavior = behavior
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        return self._behavior(**kwargs)


def _make_client(monkeypatch, specs, behaviors, **kwargs):
    monkeypatch.setattr(client_mod._EndpointRuntime, "_sleep", lambda self, attempt: None)
    fakes = {spec.name: FakeOpenAI(behaviors[spec.name]) for spec in specs}
    client = LLMClient(
        specs,
        max_attempts=kwargs.pop("max_attempts", 2),
        backoff_base=kwargs.pop("backoff_base", 0.0),
        client_factory=lambda spec, timeout: fakes[spec.name],
        **kwargs,
    )
    return client, fakes


class TestParseEndpoints:
    def test_numbered_groups_sorted_and_incomplete_skipped(self):
        env = {
            "LLM_ENDPOINT_10_BASE_URL": "b10",
            "LLM_ENDPOINT_10_API_KEY": "k10",
            "LLM_ENDPOINT_10_MODEL": "m10",
            "LLM_ENDPOINT_10_NAME": "backup",
            "LLM_ENDPOINT_2_BASE_URL": "b2",
            "LLM_ENDPOINT_2_API_KEY": "k2",
            "LLM_ENDPOINT_2_MODEL": "m2",
            "LLM_ENDPOINT_3_BASE_URL": "b3",  # 缺 API_KEY/MODEL → 跳过
        }
        specs = parse_endpoints(env)
        assert [(s.name, s.model) for s in specs] == [("ep2", "m2"), ("backup", "m10")]

    def test_legacy_single_endpoint_fallback(self):
        env = {"OPENAI_BASE_URL": "b", "OPENAI_API_KEY": "k", "LABELING_MODEL": "m"}
        specs = parse_endpoints(env)
        assert len(specs) == 1
        assert specs[0].model == "m" and specs[0].base_url == "b"

    def test_numbered_takes_precedence_over_legacy(self):
        env = {
            "OPENAI_BASE_URL": "legacy",
            "OPENAI_API_KEY": "k",
            "LABELING_MODEL": "m",
            "LLM_ENDPOINT_1_BASE_URL": "b1",
            "LLM_ENDPOINT_1_API_KEY": "k1",
            "LLM_ENDPOINT_1_MODEL": "m1",
        }
        specs = parse_endpoints(env)
        assert [s.base_url for s in specs] == ["b1"]

    def test_empty_env_yields_no_endpoints(self):
        assert parse_endpoints({"LLM_TIMEOUT_SECS": "120"}) == []


class TestFallbackQueue:
    def test_primary_failure_falls_back_every_call(self, monkeypatch):
        """无冷却：每次调用都先打队首端点（整轮重试）再落到下一个。"""
        specs = [
            EndpointSpec("ep1", "u1", "k1", "m1"),
            EndpointSpec("ep2", "u2", "k2", "m2"),
        ]
        behaviors = {
            "ep1": lambda **kw: (_ for _ in ()).throw(RuntimeError("down")),
            "ep2": lambda **kw: _resp('{"hit": true}'),
        }
        client, fakes = _make_client(monkeypatch, specs, behaviors)
        out = client.chat_json(MSG)
        assert out["hit"] is True
        assert isinstance(out, dict)
        assert out.source_model == "m2" and out.source_endpoint == "ep2"
        assert fakes["ep1"].calls == client._endpoints[0].max_attempts

        out2 = client.chat_json(MSG)  # 不记忆失败：ep1 仍被优先尝试
        assert out2.source_endpoint == "ep2"
        assert fakes["ep1"].calls == 2 * client._endpoints[0].max_attempts

    def test_recovery_returns_traffic_to_primary_immediately(self, monkeypatch):
        specs = [
            EndpointSpec("ep1", "u1", "k1", "m1"),
            EndpointSpec("ep2", "u2", "k2", "m2"),
        ]
        state = {"ep1_ok": False}

        def ep1_behavior(**kw):
            if not state["ep1_ok"]:
                raise RuntimeError("down")
            return _resp('{"hit": true}')

        behaviors = {"ep1": ep1_behavior, "ep2": lambda **kw: _resp('{"hit": true}')}
        client, _ = _make_client(monkeypatch, specs, behaviors)
        assert client.chat_json(MSG).source_endpoint == "ep2"

        state["ep1_ok"] = True  # ep1 恢复 → 下一次调用立即回到队首，无需等待
        assert client.chat_json(MSG).source_endpoint == "ep1"
        assert client.chat_json(MSG).source_endpoint == "ep1"

    def test_all_endpoints_fail_raises(self, monkeypatch):
        specs = [
            EndpointSpec("ep1", "u1", "k1", "m1"),
            EndpointSpec("ep2", "u2", "k2", "m2"),
        ]
        behaviors = {
            "ep1": lambda **kw: (_ for _ in ()).throw(RuntimeError("down1")),
            "ep2": lambda **kw: (_ for _ in ()).throw(RuntimeError("down2")),
        }
        client, fakes = _make_client(monkeypatch, specs, behaviors)
        with pytest.raises(LabelCallError) as ei:
            client.chat_json(MSG)
        assert "2 endpoints" in str(ei.value)
        assert "down1" in str(ei.value) and "down2" in str(ei.value)
        assert all(f.calls for f in fakes.values())  # 两个端点都被试过

    def test_shared_meter_counts_cross_endpoint(self, monkeypatch):
        specs = [
            EndpointSpec("ep1", "u1", "k1", "m1"),
            EndpointSpec("ep2", "u2", "k2", "m2"),
        ]
        behaviors = {
            "ep1": lambda **kw: (_ for _ in ()).throw(RuntimeError("down")),
            "ep2": lambda **kw: _resp(pt=100, ct=50),
        }
        client, _ = _make_client(monkeypatch, specs, behaviors)
        client.chat_json(MSG)
        client.chat_json(MSG)
        assert client.meter.calls == 2
        assert client.meter.prompt_tokens == 200
        assert client.meter.completion_tokens == 100
        assert client.meter.failures == 0  # fallback 成功不算整调用失败

    def test_empty_endpoints_rejected(self):
        with pytest.raises(ValueError):
            LLMClient([])

    def test_describe_lists_priority_order(self, monkeypatch):
        specs = [
            EndpointSpec("ep1", "u1", "k1", "m1"),
            EndpointSpec("ep2", "u2", "k2", "m2"),
        ]
        behaviors = {"ep1": lambda **kw: _resp(), "ep2": lambda **kw: _resp()}
        client, _ = _make_client(monkeypatch, specs, behaviors)
        assert client.describe() == "ep1(m1) -> ep2(m2)"
