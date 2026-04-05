from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, parse_float

GENERATOR = ROOT / "trade" / "generate_binance_trade_shadow_status.py"
SETTINGS_ENV_PATH = ROOT / "settings.env"


def _poll_seconds() -> float:
    settings = load_settings_env(SETTINGS_ENV_PATH)
    return max(10.0, parse_float(settings.get("TRADE_SHADOW_POLL_SECONDS"), 30.0))


def main() -> None:
    while True:
        try:
            completed = subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=False)
            if completed.returncode != 0:
                print(f"[trade-shadow] generator exited with {completed.returncode}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[trade-shadow] {exc}", file=sys.stderr, flush=True)
        time.sleep(_poll_seconds())


if __name__ == "__main__":
    main()
