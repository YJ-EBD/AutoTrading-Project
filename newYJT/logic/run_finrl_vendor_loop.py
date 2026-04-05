from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "finrl_venv" / "Scripts" / "python.exe"
WORKDIR = ROOT / "vendor" / "FinRL-Trading"
PREPARE_DATA = ROOT / "logic" / "prepare_finrl_data.py"


def run_command(args: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(args, cwd=cwd or ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def main() -> None:
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"

    run_command([str(PYTHON), str(PREPARE_DATA)])

    while True:
        try:
            run_command(
                [
                    str(PYTHON),
                    "src/strategies/run_adaptive_rotation_strategy.py",
                    "--config",
                    "src/strategies/AdaptiveRotationConf_v1.2.1.yaml",
                    "--backtest",
                    "--start",
                    "2023-01-01",
                    "--end",
                    "2024-12-31",
                ],
                cwd=WORKDIR,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[finrl-loop] {exc}", file=sys.stderr, flush=True)
        time.sleep(21600)


if __name__ == "__main__":
    main()
