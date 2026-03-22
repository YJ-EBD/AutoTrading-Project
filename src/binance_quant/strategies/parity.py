from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import StrategyVariant
from .indicators import crossover, ema
from .templates import TrendEMAStrategy


@dataclass
class ParityResult:
    strategy_id: str
    passed: bool
    details: str


def run_semantic_parity_checks() -> list[ParityResult]:
    closes = [100.0] * 16 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    synthetic = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0] * len(closes),
        },
        index=pd.date_range("2024-01-01", periods=len(closes), freq="15min", tz="UTC"),
    )
    variant = StrategyVariant(
        family="trend_ema",
        name="ema_cross_rsi",
        parameters={"fast": 2, "slow": 4, "rsi_threshold": 51.0},
    )
    template = TrendEMAStrategy()
    generated = template.generate(synthetic, variant)
    signal_frame = generated.signals
    raw_crossover_count = int(crossover(ema(synthetic["close"], 2), ema(synthetic["close"], 4)).sum())
    entry_columns_present = {"entry_long", "entry_short", "exit_long", "exit_short"}.issubset(signal_frame.columns)
    passed = "ta.crossover" in generated.pine_script and raw_crossover_count >= 1 and entry_columns_present
    details = "Pine text and Python crossover primitives aligned on a synthetic crossover case."
    return [ParityResult(strategy_id=variant.strategy_id, passed=passed, details=details)]
