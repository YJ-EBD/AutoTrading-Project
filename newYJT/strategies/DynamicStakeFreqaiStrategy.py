from __future__ import annotations

import sys
from pathlib import Path


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "trade").is_dir() and (candidate / "vendor").is_dir():
            return candidate
    return current.parents[1]


ROOT = _find_project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade.dynamic_stake_freqai_strategy import DynamicStakeFreqaiStrategy as _DynamicStakeFreqaiStrategy


class DynamicStakeFreqaiStrategy(_DynamicStakeFreqaiStrategy):
    pass
