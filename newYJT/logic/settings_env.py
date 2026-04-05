from __future__ import annotations

from pathlib import Path


def load_settings_env(path: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    if not path.exists():
        return settings

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        settings[key] = value
    return settings


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def resolve_live_mode_flags(settings: dict[str, str]) -> dict[str, bool | str]:
    """
    Single-source-of-truth for the workspace live / dry-run switch.

    ENABLE_LIVE_TRADING is treated as the primary switch.
    Legacy flags are still supported for backward compatibility:
    - ENABLE_ORDER_SUBMISSION can explicitly force on/off mutating requests.
    - BLOCK_REAL_ORDER_SUBMISSION can explicitly hard-block real orders.
    """
    api_keys_present = bool(
        settings.get("BINANCE_API_KEY", "").strip()
        and settings.get("BINANCE_SECRET_KEY", "").strip()
    )
    live_requested = parse_bool(settings.get("ENABLE_LIVE_TRADING"), False)

    has_enable_order_submission = "ENABLE_ORDER_SUBMISSION" in settings
    has_block_real_order_submission = "BLOCK_REAL_ORDER_SUBMISSION" in settings

    legacy_order_submission_requested = parse_bool(
        settings.get("ENABLE_ORDER_SUBMISSION"),
        live_requested,
    )
    legacy_block_real_order_submission = parse_bool(
        settings.get("BLOCK_REAL_ORDER_SUBMISSION"),
        False,
    )

    order_submission_requested = live_requested and legacy_order_submission_requested
    block_real_order_submission = legacy_block_real_order_submission
    live_preflight_enabled = bool(api_keys_present and live_requested)
    live_trading_enabled = bool(
        api_keys_present
        and order_submission_requested
        and not block_real_order_submission
    )
    order_submission_enabled = bool(live_trading_enabled)
    allow_mutating_requests = bool(live_trading_enabled)
    mode = "live" if live_trading_enabled else ("live_preflight" if live_preflight_enabled else "dry_run")

    return {
        "api_keys_present": api_keys_present,
        "live_requested": live_requested,
        "order_submission_requested": order_submission_requested,
        "legacy_order_submission_requested": legacy_order_submission_requested,
        "has_enable_order_submission": has_enable_order_submission,
        "legacy_block_real_order_submission": legacy_block_real_order_submission,
        "has_block_real_order_submission": has_block_real_order_submission,
        "block_real_order_submission": block_real_order_submission,
        "live_preflight_enabled": live_preflight_enabled,
        "live_trading_enabled": live_trading_enabled,
        "order_submission_enabled": order_submission_enabled,
        "allow_mutating_requests": allow_mutating_requests,
        "mode": mode,
    }


def resolve_freqtrade_db_path(root: Path, settings: dict[str, str] | None = None) -> Path:
    if settings is None:
        settings = load_settings_env(root / "settings.env")
    live_flags = resolve_live_mode_flags(settings)
    db_name = "tradesv3.sqlite" if bool(live_flags["live_trading_enabled"]) else "tradesv3.dryrun.sqlite"
    return root / "runtime" / "freqtrade" / db_name


def resolve_freqtrade_db_url(root: Path, settings: dict[str, str] | None = None) -> str:
    return "sqlite:///" + resolve_freqtrade_db_path(root, settings).as_posix()
