from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "llm_venv" / "Scripts" / "python.exe"
WORKDIR = ROOT / "vendor" / "binance-anthropic-trading-bot"
RUNTIME_CONFIG = ROOT / "runtime" / "llm" / "config.json"
TARGET_CONFIG = WORKDIR / "config.json"


def run_command(args: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(args, cwd=cwd or ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def main() -> None:
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("ALL_PROXY", None)

    while True:
        try:
            shutil.copyfile(RUNTIME_CONFIG, TARGET_CONFIG)
            run_command([str(PYTHON), "main.py"], cwd=WORKDIR)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[llm-loop] {exc}", file=sys.stderr, flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
