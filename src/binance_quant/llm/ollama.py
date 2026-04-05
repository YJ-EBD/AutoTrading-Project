from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from ..config import LocalLLMConfig


LOGGER = logging.getLogger(__name__)
DEFAULT_SYSTEM_PROMPT = (
    "You are the final risk gate for a crypto paper trading system. "
    "Use only the supplied context. Return strict JSON with keys "
    "action, confidence, reason. Action must be one of allow, reject, defer."
)


@dataclass
class LLMDecision:
    action: str
    confidence: float
    reason: str
    raw_content: str


class OllamaDecisionClient:
    def __init__(self, config: LocalLLMConfig):
        self.config = config
        self.active_model = config.model
        self.available_models: list[str] = []

    def decide(self, context: dict[str, Any]) -> LLMDecision:
        prompt = self._build_prompt(context)
        system_prompt = self._build_system_prompt()
        last_exception: Exception | None = None
        for model_name in self._candidate_models():
            payload = {
                "model": model_name,
                "stream": False,
                "format": "json",
                "think": False,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_output_tokens,
                },
            }
            try:
                response = requests.post(
                    f"{self.config.base_url.rstrip('/')}/api/chat",
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                raw_content = str(data.get("message", {}).get("content", "")).strip()
                parsed = _safe_json(raw_content)
                action = str(parsed.get("action", "defer")).lower()
                if action not in {"allow", "reject", "defer"}:
                    action = "defer"
                confidence = float(parsed.get("confidence", 0.5))
                reason = str(parsed.get("reason", ""))
                self.active_model = model_name
                return LLMDecision(
                    action=action,
                    confidence=max(0.0, min(1.0, confidence)),
                    reason=reason,
                    raw_content=raw_content,
                )
            except Exception as exc:
                last_exception = exc
                LOGGER.warning("Local LLM model %s failed, trying fallback: %s", model_name, exc)
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("No local LLM models configured.")

    def ping(self) -> bool:
        try:
            response = requests.get(
                f"{self.config.base_url.rstrip('/')}/api/tags",
                timeout=min(self.config.timeout_seconds, 10),
            )
            response.raise_for_status()
            tags = response.json().get("models", [])
            self.available_models = [str(item.get("name", "")) for item in tags if item.get("name")]
            for model_name in self._configured_models():
                if model_name in self.available_models:
                    self.active_model = model_name
                    return True
            LOGGER.warning(
                "Local LLM server reachable but none of the configured models are installed. configured=%s available=%s",
                self._configured_models(),
                self.available_models,
            )
            return False
        except Exception as exc:
            LOGGER.warning("Local LLM ping failed: %s", exc)
            return False

    def _build_prompt(self, context: dict[str, Any]) -> str:
        context_json = json.dumps(context, ensure_ascii=True, indent=2, default=str)
        context_compact = json.dumps(context, ensure_ascii=True, separators=(",", ":"), default=str)
        if not self.config.prompt_template.strip():
            return context_json
        return (
            self.config.prompt_template.replace("{context_json}", context_json).replace(
                "{context_compact}",
                context_compact,
            )
        )

    def _build_system_prompt(self) -> str:
        custom = self.config.system_prompt.strip()
        return custom or DEFAULT_SYSTEM_PROMPT

    def status(self) -> dict[str, Any]:
        return {
            "active_model": self.active_model,
            "configured_models": self._configured_models(),
            "available_models": list(self.available_models),
        }

    def _configured_models(self) -> list[str]:
        return [self.config.model, *self.config.fallback_models]

    def _candidate_models(self) -> list[str]:
        ordered = [self.active_model, *self._configured_models()]
        deduped: list[str] = []
        for model_name in ordered:
            if model_name and model_name not in deduped:
                deduped.append(model_name)
        return deduped


def _safe_json(raw_content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = raw_content.find("{")
    end = raw_content.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw_content[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}
