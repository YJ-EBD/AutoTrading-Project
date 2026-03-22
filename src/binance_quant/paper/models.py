from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaperDecision:
    decided_at: str
    symbol: str
    strategy_id: str
    family: str
    side: str
    signal_time: str
    observed_price: float
    atr_value: float
    signal_strength: float
    ml_probability: float
    ml_threshold: float
    ml_accepted: bool
    llm_enabled: bool
    llm_action: str | None
    llm_confidence: float | None
    llm_reason: str | None
    final_action: str
    portfolio_reason: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperPosition:
    decision_id: int
    symbol: str
    strategy_id: str
    family: str
    side: str
    opened_at: str
    entry_observed_price: float
    latest_observed_price: float
    stop_price: float
    target_price: float
    liquidation_price: float
    atr_value: float
    model_probability: float
    llm_action: str | None
    llm_confidence: float | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetuneEvent:
    started_at: str
    status: str
    hypothesis: str
    source_artifact: str | None = None
    completed_at: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
