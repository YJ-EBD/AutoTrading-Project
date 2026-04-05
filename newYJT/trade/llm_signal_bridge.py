from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LLM_RUNTIME_CONFIG_PATH = ROOT / "runtime" / "llm" / "config.json"
LLM_VENDOR_CONFIG_PATH = ROOT / "vendor" / "binance-anthropic-trading-bot" / "config.json"
LLM_SIGNAL_SNAPSHOT_PATH = ROOT / "runtime" / "llm_signal_snapshot.json"
LLM_VENDOR_LOG_PATH = ROOT / "vendor" / "binance-anthropic-trading-bot" / "trading_bot.log"

_TAIL_BYTES = 512_000
_CACHE_TTL_SECONDS = 60
_SIGNAL_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+-\s+INFO\s+-\s+Final trading decision for (?P<symbol>[A-Z0-9]+): (?P<signal>BUY|SELL|HOLD)\s*$"
)
_CACHE: dict[str, Any] = {"loaded_at": None, "signals": {}}


def _pair_to_symbol(pair: str) -> str:
    base, quote = pair.split("/", 1)
    quote = quote.split(":", 1)[0]
    return f"{base}{quote}"


def _tail_text(path: Path, max_bytes: int = _TAIL_BYTES) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(size - max_bytes, 0))
        return handle.read().decode("utf-8", errors="replace")


def _load_recent_signals(max_age_minutes: int = 180) -> dict[str, dict[str, str]]:
    now = datetime.now()
    loaded_at = _CACHE.get("loaded_at")
    if isinstance(loaded_at, datetime) and (now - loaded_at).total_seconds() < _CACHE_TTL_SECONDS:
        return dict(_CACHE.get("signals", {}))

    signals: dict[str, dict[str, str]] = {}
    if LLM_VENDOR_LOG_PATH.exists():
        cutoff = now - timedelta(minutes=max_age_minutes)
        for raw_line in _tail_text(LLM_VENDOR_LOG_PATH).splitlines():
            match = _SIGNAL_PATTERN.match(raw_line.strip())
            if not match:
                continue
            timestamp = datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S")
            if timestamp < cutoff:
                continue
            symbol = match.group("symbol").upper()
            signals[symbol] = {
                "signal": match.group("signal").upper(),
                "timestamp": timestamp.isoformat(),
            }

    _CACHE["loaded_at"] = now
    _CACHE["signals"] = signals
    return dict(signals)


def refresh_signal_snapshot(max_age_minutes: int = 180) -> dict[str, dict[str, str]]:
    signals = _load_recent_signals(max_age_minutes=max_age_minutes)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "signals": signals,
    }
    LLM_SIGNAL_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_SIGNAL_SNAPSHOT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return signals


def llm_signal_for_pair(pair: str, max_age_minutes: int = 180) -> str | None:
    symbol = _pair_to_symbol(pair)
    signals = _load_recent_signals(max_age_minutes=max_age_minutes)
    record = signals.get(symbol)
    if not record:
        return None
    signal = str(record.get("signal") or "").upper()
    return signal or None


def sync_llm_runtime_pairs(pairs: list[str]) -> None:
    if not LLM_RUNTIME_CONFIG_PATH.exists():
        return

    try:
        config = json.loads(LLM_RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    symbols = [_pair_to_symbol(pair) for pair in pairs]
    if config.get("trading_pairs") == symbols:
        refresh_signal_snapshot()
        return

    config["trading_pairs"] = symbols
    serialized = json.dumps(config, indent=2, ensure_ascii=False)
    LLM_RUNTIME_CONFIG_PATH.write_text(serialized, encoding="utf-8")
    if LLM_VENDOR_CONFIG_PATH.exists():
        LLM_VENDOR_CONFIG_PATH.write_text(serialized, encoding="utf-8")
    refresh_signal_snapshot()
