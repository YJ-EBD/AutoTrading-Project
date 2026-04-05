from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "runtime" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except OSError:
        pass


SETUP_COMMANDS = [
    ("setup-freqtrade", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "setup_freqtrade_vendor_env.ps1")]),
    ("setup-finrl", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "setup_finrl_vendor_env.ps1")]),
    ("setup-llm", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "setup_llm_vendor_env.ps1")]),
    ("prepare-freqtrade", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "prepare_freqtrade_runtime.ps1")]),
    ("prepare-finrl", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "prepare_finrl_runtime.ps1")]),
    ("prepare-llm", ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "prepare_llm_runtime.ps1")]),
]


RUNTIME_COMMANDS = [
    (
        "http",
        [sys.executable, "-m", "http.server", "8000", "--directory", str(ROOT)],
        LOG_DIR / "http_console.log",
    ),
    (
        "freqtrade",
        [sys.executable, str(ROOT / "trade" / "run_freqtrade_vendor_loop.py")],
        LOG_DIR / "freqtrade_console.log",
    ),
    (
        "finrl",
        [sys.executable, str(ROOT / "logic" / "run_finrl_vendor_loop.py")],
        LOG_DIR / "finrl_console.log",
    ),
    (
        "llm",
        [sys.executable, str(ROOT / "logic" / "run_llm_vendor_loop.py")],
        LOG_DIR / "llm_console.log",
    ),
    (
        "status",
        [sys.executable, str(ROOT / "logic" / "run_status_loop.py")],
        LOG_DIR / "status_console.log",
    ),
    (
        "live-preflight",
        [sys.executable, str(ROOT / "trade" / "run_live_preflight_loop.py")],
        LOG_DIR / "live_preflight_console.log",
    ),
    (
        "trade-shadow",
        [sys.executable, str(ROOT / "trade" / "run_binance_trade_shadow_loop.py")],
        LOG_DIR / "trade_shadow_console.log",
    ),
]


def _stream_output(name: str, pipe, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log_file:
        for raw_line in iter(pipe.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue
            formatted = f"[{name}] {line}"
            console_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_formatted = formatted.encode(console_encoding, errors="replace").decode(console_encoding, errors="replace")
            print(safe_formatted, flush=True)
            log_file.write(formatted + "\n")
            log_file.flush()


def run_setup() -> None:
    for name, command in SETUP_COMMANDS:
        print(f"[supervisor] running {name}: {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"[supervisor] setup failed: {name} returned {completed.returncode}")


def start_runtime(name: str, command: list[str], log_path: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("OMP_NUM_THREADS", "1")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    thread = threading.Thread(target=_stream_output, args=(name, process.stdout, log_path), daemon=True)
    thread.start()
    return process


def main() -> None:
    run_setup()

    children: dict[str, tuple[subprocess.Popen[str], list[str], Path]] = {}
    stop_requested = False

    def shutdown(*_args) -> None:
        nonlocal stop_requested
        stop_requested = True
        for proc, _, _ in children.values():
            if proc.poll() is None:
                proc.terminate()
        time.sleep(2)
        for proc, _, _ in children.values():
            if proc.poll() is None:
                proc.kill()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    for name, command, log_path in RUNTIME_COMMANDS:
        print(f"[supervisor] starting {name}: {' '.join(command)}", flush=True)
        children[name] = (start_runtime(name, command, log_path), command, log_path)

    while not stop_requested:
        time.sleep(5)
        for name, (proc, command, log_path) in list(children.items()):
            if proc.poll() is not None and not stop_requested:
                print(f"[supervisor] restarting {name} after exit code {proc.returncode}", flush=True)
                time.sleep(3)
                children[name] = (start_runtime(name, command, log_path), command, log_path)


if __name__ == "__main__":
    main()
