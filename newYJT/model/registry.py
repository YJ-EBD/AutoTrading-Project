from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FREQAI_MODEL_NAME = "AggressiveMLDLHybridClassifier"
FREQAI_STRATEGY_NAME = "AggressiveDynamicFreqaiStrategy"
LOCAL_STRATEGY_PATH = ROOT / "trade" / "aggressive_dynamic_freqai_strategy.py"
DEFAULT_TIMEFRAMES = ("3m", "15m", "1h")
