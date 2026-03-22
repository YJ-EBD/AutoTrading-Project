from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from ..config import LocalLLMConfig


LOGGER = logging.getLogger(__name__)


@dataclass
class LLMDecision:
    action: str
    confidence: float
    reason: str
    raw_content: str


class OllamaDecisionClient:
    def __init__(self, config: LocalLLMConfig):
        self.config = config

    def decide(self, context: dict[str, Any]) -> LLMDecision:
        prompt = self._build_prompt(context)
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the final risk gate for a crypto paper trading system. "
                        "Return strict JSON with keys action, confidence, reason. "
                        "Action must be one of allow, reject, defer."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_output_tokens,
            },
        }
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
        return LLMDecision(
            action=action,
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason,
            raw_content=raw_content,
        )

    def ping(self) -> bool:
        try:
            response = requests.get(
                f"{self.config.base_url.rstrip('/')}/api/tags",
                timeout=min(self.config.timeout_seconds, 10),
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            LOGGER.warning("Local LLM ping failed: %s", exc)
            return False

    def _build_prompt(self, context: dict[str, Any]) -> str:
        return json.dumps(context, ensure_ascii=True, indent=2, default=str)


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
