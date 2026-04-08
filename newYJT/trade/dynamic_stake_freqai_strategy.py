from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STRATEGY_DIR = ROOT / "runtime" / "freqtrade" / "user_data" / "strategies"
VENDOR_STRATEGY_DIR = ROOT / "vendor" / "freqtrade" / "freqtrade" / "templates"
SETTINGS_ENV_PATH = ROOT / "settings.env"
SETTINGS_STATE_PATH = ROOT / "runtime" / "settings_state.json"

for candidate in (RUNTIME_STRATEGY_DIR, VENDOR_STRATEGY_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from FreqaiExampleHybridStrategy import FreqaiExampleHybridStrategy


def _parse_stake_ratio_pct(raw: str | None, default: float = 10.0) -> float:
    try:
        parsed = float((raw or "").strip())
    except (TypeError, ValueError):
        parsed = default
    return max(0.1, min(parsed, 100.0))


def _stake_ratio_from_settings_files() -> float:
    if SETTINGS_STATE_PATH.exists():
        try:
            state = json.loads(SETTINGS_STATE_PATH.read_text(encoding="utf-8"))
            return _parse_stake_ratio_pct(str(state.get("stake_ratio_pct", "")))
        except (OSError, ValueError, TypeError):
            pass

    if SETTINGS_ENV_PATH.exists():
        try:
            for line in SETTINGS_ENV_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                if key.strip() == "DYNAMIC_STAKE_RATIO_PCT":
                    return _parse_stake_ratio_pct(value)
        except OSError:
            pass

    return 10.0


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
        env_value = os.getenv("NEWYJT_STAKE_RATIO_PCT")
        if env_value is not None and env_value.strip():
            return _parse_stake_ratio_pct(env_value) / 100.0
        return _stake_ratio_from_settings_files() / 100.0

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
