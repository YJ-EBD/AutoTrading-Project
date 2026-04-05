from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "trade" / "live_preflight.py"


def main() -> None:
    while True:
        try:
            completed = subprocess.run([sys.executable, str(PREFLIGHT)], cwd=ROOT, check=False)
            if completed.returncode != 0:
                print(f"[live-preflight] exited with {completed.returncode}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[live-preflight] {exc}", file=sys.stderr, flush=True)
        time.sleep(300)


if __name__ == "__main__":
    main()
