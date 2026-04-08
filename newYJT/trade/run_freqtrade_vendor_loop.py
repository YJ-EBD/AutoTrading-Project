from __future__ import annotations

import os
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, parse_float, resolve_freqtrade_db_path, resolve_freqtrade_db_url
from model.registry import DEFAULT_TIMEFRAMES, FREQAI_MODEL_NAME, FREQAI_STRATEGY_NAME
from trade.llm_signal_bridge import sync_llm_runtime_pairs
from trade.market_universe import select_dynamic_active_pairs

PYTHON = ROOT / "runtime" / "freqtrade_venv" / "Scripts" / "python.exe"
CONFIG = ROOT / "runtime" / "freqtrade" / "config.binance_usdtm.freqai.json"
RESOLVED_CONFIG = ROOT / "runtime" / "freqtrade" / "config.binance_usdtm.freqai.resolved.json"
STRATEGY_PATH = ROOT / "runtime" / "freqtrade" / "user_data" / "strategies"
FREQAI_MODEL_PATH = ROOT / "runtime" / "freqtrade" / "user_data" / "freqaimodels"
USER_DATA_DIR = ROOT / "runtime" / "freqtrade" / "user_data"
RESOLVED_PAIRS_PATH = ROOT / "runtime" / "resolved_pairs.json"
ACTIVE_PAIRS_PATH = ROOT / "runtime" / "active_pairs.json"
ACTIVE_PAIR_LIMIT = 24
EXCLUDED_BASES = {
    "XAU",
    "XAG",
    "XAUT",
    "PAXG",
    "TSLA",
    "COIN",
    "MSTR",
    "INTC",
    "NVDA",
    "AMZN",
    "GOOGL",
    "PLTR",
    "HOOD",
    "EWY",
    "EWJ",
}


def _subprocess_kwargs() -> dict[str, int]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": creationflags} if creationflags else {}


def validate_runtime_imports() -> None:
    script = f"""
import sys
from pathlib import Path

root = Path(r"{ROOT}")
sys.path.insert(0, str(root / "runtime" / "freqtrade" / "user_data" / "strategies"))
sys.path.insert(0, str(root / "runtime" / "freqtrade" / "user_data" / "freqaimodels"))
sys.path.insert(0, str(root))
import {FREQAI_STRATEGY_NAME} as strategy_module
import {FREQAI_MODEL_NAME} as model_module
assert getattr(strategy_module, "{FREQAI_STRATEGY_NAME}", None) is not None
assert getattr(model_module, "{FREQAI_MODEL_NAME}", None) is not None
print("runtime imports ok")
"""
    completed = subprocess.run(
        [str(PYTHON), "-",],
        cwd=ROOT,
        check=False,
        input=script,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        **_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "runtime import validation failed:\n"
            + (completed.stdout or "")
            + (completed.stderr or "")
        )


def _load_dynamic_stake_ratio_pct() -> float:
    settings = load_settings_env(ROOT / "settings.env")
    return max(0.1, min(parse_float(settings.get("DYNAMIC_STAKE_RATIO_PCT"), 10.0), 100.0))


def _export_runtime_env_from_settings() -> None:
    settings = load_settings_env(ROOT / "settings.env")
    forwarded_keys = {
        "DEFAULT_LEVERAGE",
        "DEFAULT_STOP_LOSS_PCT",
        "DEFAULT_TAKE_PROFIT_PCT",
        "DYNAMIC_STAKE_RATIO_PCT",
    }
    forwarded_prefixes = ("AGGRESSIVE_", "LLM_")
    for key, value in settings.items():
        if key in forwarded_keys or key.startswith(forwarded_prefixes):
            os.environ[key] = value


def _load_active_pair_bounds() -> tuple[int, int]:
    settings = load_settings_env(ROOT / "settings.env")
    min_pairs = int(max(2, min(parse_float(settings.get("ACTIVE_PAIR_MIN"), 6.0), 30.0)))
    max_pairs = int(
        max(min_pairs, min(parse_float(settings.get("ACTIVE_PAIR_MAX"), float(ACTIVE_PAIR_LIMIT)), 30.0))
    )
    return min_pairs, max_pairs


def _load_pair_refresh_minutes() -> int:
    settings = load_settings_env(ROOT / "settings.env")
    return int(max(15, min(parse_float(settings.get("PAIR_UNIVERSE_REFRESH_MINUTES"), 60.0), 240.0)))


def _load_pair_refresh_open_trade_policy() -> tuple[bool, int]:
    settings = load_settings_env(ROOT / "settings.env")
    defer_refresh = str(settings.get("PAIR_REFRESH_DEFER_IF_OPEN_TRADES", "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    max_defer_minutes = int(
        max(15, min(parse_float(settings.get("PAIR_REFRESH_MAX_DEFER_MINUTES"), 360.0), 1440.0))
    )
    return defer_refresh, max_defer_minutes


def _resolve_db_runtime() -> tuple[Path, str]:
    settings = load_settings_env(ROOT / "settings.env")
    db_path = resolve_freqtrade_db_path(ROOT, settings)
    db_url = resolve_freqtrade_db_url(ROOT, settings)
    return db_path, db_url


def run_command(args: list[str]) -> None:
    completed = subprocess.run(args, cwd=ROOT, check=False, **_subprocess_kwargs())
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def _count_open_trades(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            cursor = connection.cursor()
            row = cursor.execute("SELECT COUNT(*) FROM trades WHERE is_open = 1").fetchone()
            return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def run_trade_command(
    args: list[str],
    refresh_minutes: int,
    *,
    db_path: Path,
    defer_refresh_if_open_trades: bool,
    max_defer_minutes: int,
) -> None:
    process = subprocess.Popen(args, cwd=ROOT, **_subprocess_kwargs())
    waited_minutes = 0
    refresh_chunk_minutes = max(15, refresh_minutes)
    try:
        while True:
            try:
                process.wait(timeout=refresh_chunk_minutes * 60)
                break
            except subprocess.TimeoutExpired:
                waited_minutes += refresh_chunk_minutes
                open_trade_count = _count_open_trades(db_path)
                if defer_refresh_if_open_trades and open_trade_count > 0 and waited_minutes < max_defer_minutes:
                    print(
                        f"[freqtrade-loop] deferring universe refresh because open_trades={open_trade_count} waited_minutes={waited_minutes}/{max_defer_minutes}",
                        flush=True,
                    )
                    refresh_chunk_minutes = 15
                    continue

                print(
                    f"[freqtrade-loop] refreshing active universe after waited_minutes={waited_minutes} open_trades={open_trade_count}",
                    flush=True,
                )
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
                return
    finally:
        pass

    if process.returncode != 0:
        raise RuntimeError(f"trade command failed with exit code {process.returncode}: {' '.join(args)}")


def _load_cached_pairs() -> list[str]:
    if not RESOLVED_PAIRS_PATH.exists():
        return []
    try:
        payload = json.loads(RESOLVED_PAIRS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    pairs = payload.get("pairs", [])
    return pairs if isinstance(pairs, list) else []


def resolve_pairs() -> list[str]:
    for _attempt in range(3):
        try:
            completed = subprocess.run(
                [
                    str(PYTHON),
                    "-X",
                    "utf8",
                    "-m",
                    "freqtrade",
                    "test-pairlist",
                    "--user-data-dir",
                    str(USER_DATA_DIR),
                    "--config",
                    str(CONFIG),
                    "--print-json",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                **_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired:
            cached_pairs = _load_cached_pairs()
            if cached_pairs:
                print("[freqtrade-loop] pairlist resolution timed out, using cached pairlist", flush=True)
                return cached_pairs
            print("[freqtrade-loop] pairlist resolution timed out, retrying", flush=True)
            time.sleep(5)
            continue
        if completed.returncode == 0:
            pair_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip().startswith("[")]
            if pair_lines:
                pairs = json.loads(pair_lines[0])
                RESOLVED_PAIRS_PATH.parent.mkdir(parents=True, exist_ok=True)
                RESOLVED_PAIRS_PATH.write_text(json.dumps({"generated_at": time.time(), "pairs": pairs}, indent=2), encoding="utf-8")
                return pairs
        time.sleep(5)

    cached_pairs = _load_cached_pairs()
    if cached_pairs:
        print("[freqtrade-loop] using cached resolved pairlist after resolution failure", flush=True)
        return cached_pairs
    raise RuntimeError("pairlist resolution failed and no cached pairlist is available")


def write_resolved_config(active_pairs: list[str]) -> Path:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config.setdefault("exchange", {})["pair_whitelist"] = active_pairs
    config["pairlists"] = [{"method": "StaticPairList"}]
    RESOLVED_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    RESOLVED_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    ACTIVE_PAIRS_PATH.write_text(json.dumps({"generated_at": time.time(), "pairs": active_pairs}, indent=2), encoding="utf-8")
    return RESOLVED_CONFIG


def _timerange(days: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(days=days)
    return start.strftime("%Y%m%d-")


def main() -> None:
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    os.environ["NO_COLOR"] = "1"
    _export_runtime_env_from_settings()
    os.environ["NEWYJT_STAKE_RATIO_PCT"] = str(_load_dynamic_stake_ratio_pct())
    min_active_pairs, max_active_pairs = _load_active_pair_bounds()
    refresh_minutes = _load_pair_refresh_minutes()
    defer_refresh_if_open_trades, max_defer_minutes = _load_pair_refresh_open_trade_policy()
    print(
        "[freqtrade-loop] starting trade-only loop "
        f"active_range={min_active_pairs}-{max_active_pairs} "
        f"refresh_minutes={refresh_minutes} "
        f"defer_refresh_if_open_trades={defer_refresh_if_open_trades} "
        f"max_defer_minutes={max_defer_minutes} "
        f"excluded_bases={sorted(EXCLUDED_BASES)}",
        flush=True,
    )

    while True:
        try:
            db_path, db_url = _resolve_db_runtime()
            print(f"[freqtrade-loop] using db {db_path.name}", flush=True)
            render_configs_result = subprocess.run(
                [sys.executable, str(ROOT / "logic" / "render_runtime_configs.py")],
                cwd=ROOT,
                check=False,
                **_subprocess_kwargs(),
            )
            if render_configs_result.returncode != 0:
                raise RuntimeError(f"render_runtime_configs failed with exit code {render_configs_result.returncode}")
            pairs = resolve_pairs()
            if not pairs:
                raise RuntimeError("resolved pairlist is empty")
            universe = select_dynamic_active_pairs(
                pairs,
                min_pairs=min_active_pairs,
                max_pairs=max_active_pairs,
                excluded_bases=EXCLUDED_BASES,
            )
            active_pairs = universe.get("selected_pairs", [])
            if not active_pairs:
                raise RuntimeError("dynamic active pair selection returned an empty list")
            print(
                f"[freqtrade-loop] selected {len(active_pairs)} active pairs from {universe.get('scored_candidate_count', 0)} scored candidates",
                flush=True,
            )
            sync_llm_runtime_pairs(active_pairs)
            resolved_config = write_resolved_config(active_pairs)
            download_timerange = _timerange(30)
            validate_runtime_imports()

            try:
                run_command(
                    [
                        str(PYTHON),
                        "-X",
                        "utf8",
                        "-m",
                        "freqtrade",
                        "download-data",
                        "--no-color",
                        "--user-data-dir",
                        str(USER_DATA_DIR),
                        "--config",
                        str(resolved_config),
                        "--trading-mode",
                        "futures",
                        "--timeframes",
                        *DEFAULT_TIMEFRAMES,
                        "--timerange",
                        download_timerange,
                    ]
                )
            except Exception as exc:
                print(f"[freqtrade-loop] download warning: {exc}", file=sys.stderr, flush=True)
            run_trade_command(
                [
                    str(PYTHON),
                    "-X",
                    "utf8",
                    "-m",
                    "freqtrade",
                    "trade",
                    "--no-color",
                    "--user-data-dir",
                    str(USER_DATA_DIR),
                    "--config",
                    str(resolved_config),
                    "--strategy",
                    FREQAI_STRATEGY_NAME,
                    "--strategy-path",
                    str(STRATEGY_PATH),
                    "--freqaimodel",
                    FREQAI_MODEL_NAME,
                    "--freqaimodel-path",
                    str(FREQAI_MODEL_PATH),
                    "--db-url",
                    db_url,
                ],
                refresh_minutes=refresh_minutes,
                db_path=db_path,
                defer_refresh_if_open_trades=defer_refresh_if_open_trades,
                max_defer_minutes=max_defer_minutes,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[freqtrade-loop] {exc}", file=sys.stderr, flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
