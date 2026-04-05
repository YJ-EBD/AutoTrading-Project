from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STRATEGY_DIR = ROOT / "runtime" / "freqtrade" / "user_data" / "strategies"
VENDOR_STRATEGY_DIR = ROOT / "vendor" / "freqtrade" / "freqtrade" / "templates"

for candidate in (RUNTIME_STRATEGY_DIR, VENDOR_STRATEGY_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from FreqaiExampleHybridStrategy import FreqaiExampleHybridStrategy


class DynamicStakeFreqaiStrategy(FreqaiExampleHybridStrategy):
    """
    Freqtrade vendor strategy wrapper.

    Keeps all original entry / exit logic from FreqaiExampleHybridStrategy,
    but sizes new entries as 10% of the currently available stake balance.
    If the computed stake is below the pair's minimum stake requirement,
    the trade is skipped and the bot waits for balance to free up.
    """

    stake_ratio = 0.10

    @property
    def dynamic_stake_ratio(self) -> float:
        raw = os.getenv("NEWYJT_STAKE_RATIO_PCT", "10").strip()
        try:
            parsed = float(raw)
        except ValueError:
            parsed = 10.0
        parsed = max(0.1, min(parsed, 100.0))
        return parsed / 100.0

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        available_balance = max(float(max_stake or 0.0), 0.0)
        dynamic_stake = available_balance * self.dynamic_stake_ratio

        if dynamic_stake <= 0:
            return 0.0

        if min_stake is not None and dynamic_stake < float(min_stake):
            return 0.0

        return min(dynamic_stake, available_balance)
