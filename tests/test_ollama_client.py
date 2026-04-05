from __future__ import annotations

from typing import Any

import requests

from binance_quant.config import LocalLLMConfig
from binance_quant.llm.ollama import OllamaDecisionClient


class _Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_ping_selects_first_available_configured_model(monkeypatch) -> None:
    config = LocalLLMConfig(
        model="qwen3:8b",
        fallback_models=["gemma3:4b", "qwen3:14b"],
    )
    client = OllamaDecisionClient(config)

    def fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _Response(
            {
                "models": [
                    {"name": "gemma3:4b"},
                    {"name": "qwen3:14b"},
                ]
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    assert client.ping() is True
    assert client.active_model == "gemma3:4b"


def test_decide_falls_back_when_primary_model_request_fails(monkeypatch) -> None:
    config = LocalLLMConfig(
        model="qwen3:8b",
        fallback_models=["gemma3:4b"],
    )
    client = OllamaDecisionClient(config)
    client.available_models = ["qwen3:8b", "gemma3:4b"]

    calls: list[str] = []

    def fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        payload = kwargs["json"]
        calls.append(payload["model"])
        if payload["model"] == "qwen3:8b":
            raise requests.Timeout("primary timeout")
        return _Response(
            {
                "message": {
                    "content": '{"action":"allow","confidence":0.81,"reason":"fallback succeeded"}'
                }
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    decision = client.decide({"symbol": "BTCUSDT"})

    assert calls == ["qwen3:8b", "gemma3:4b"]
    assert client.active_model == "gemma3:4b"
    assert decision.action == "allow"
    assert decision.confidence == 0.81


def test_decide_uses_custom_prompt_template_and_system_prompt(monkeypatch) -> None:
    config = LocalLLMConfig(
        model="qwen3:8b",
        system_prompt="custom system prompt",
        prompt_template="CONTEXT START\n{context_json}\nCONTEXT END",
    )
    client = OllamaDecisionClient(config)
    captured: dict[str, Any] = {}

    def fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["payload"] = kwargs["json"]
        return _Response(
            {
                "message": {
                    "content": '{"action":"defer","confidence":0.51,"reason":"template applied"}'
                }
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    decision = client.decide({"symbol": "ETHUSDT", "probability": 0.62})

    assert decision.reason == "template applied"
    assert captured["payload"]["messages"][0]["content"] == "custom system prompt"
    assert "CONTEXT START" in captured["payload"]["messages"][1]["content"]
    assert '"symbol": "ETHUSDT"' in captured["payload"]["messages"][1]["content"]
