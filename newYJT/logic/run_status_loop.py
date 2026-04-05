from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "logic" / "generate_freqtrade_status.py"


def main() -> None:
    while True:
        try:
            completed = subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=False)
            if completed.returncode != 0:
                print(f"[status-loop] generator exited with {completed.returncode}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[status-loop] {exc}", file=sys.stderr, flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
