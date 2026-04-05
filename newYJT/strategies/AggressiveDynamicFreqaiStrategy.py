from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade.aggressive_dynamic_freqai_strategy import AggressiveDynamicFreqaiStrategy as _AggressiveDynamicFreqaiStrategy


class AggressiveDynamicFreqaiStrategy(_AggressiveDynamicFreqaiStrategy):
    pass
