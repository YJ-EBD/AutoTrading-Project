from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, parse_bool, parse_float, resolve_live_mode_flags

SETTINGS_ENV_PATH = ROOT / "settings.env"
FREQTRADE_TEMPLATE_PATH = ROOT / "configs" / "freqtrade_binance_usdtm_freqai.json"
FREQTRADE_RUNTIME_PATH = ROOT / "runtime" / "freqtrade" / "config.binance_usdtm.freqai.json"
LLM_RUNTIME_PATH = ROOT / "runtime" / "llm" / "config.json"
SETTINGS_STATE_PATH = ROOT / "runtime" / "settings_state.json"


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> None:
    settings = load_settings_env(SETTINGS_ENV_PATH)

    binance_api_key = settings.get("BINANCE_API_KEY", "").strip()
    binance_secret_key = settings.get("BINANCE_SECRET_KEY", "").strip()
    anthropic_api_key = settings.get("ANTHROPIC_API_KEY", "").strip()
    llm_provider = str(settings.get("LLM_PROVIDER", "")).strip().lower() or ("anthropic" if anthropic_api_key else "ollama")
    if llm_provider not in {"anthropic", "ollama"}:
        llm_provider = "ollama"
    llm_model = str(settings.get("LLM_MODEL", "")).strip() or (
        "claude-3-5-sonnet-latest" if llm_provider == "anthropic" else "deepseek-r1:8b"
    )
    llm_fallback_model = str(settings.get("LLM_FALLBACK_MODEL", "")).strip()
    llm_base_url = str(settings.get("LLM_BASE_URL", "")).strip() or "http://127.0.0.1:11434"
    llm_market_type = str(settings.get("LLM_MARKET_TYPE", "")).strip().lower() or "futures"
    if llm_market_type not in {"spot", "futures"}:
        llm_market_type = "futures"
    llm_timeout_seconds = max(5, int(parse_float(settings.get("LLM_TIMEOUT_SECONDS"), 60.0)))

    live_flags = resolve_live_mode_flags(settings)
    live_requested = bool(live_flags["live_requested"])
    api_keys_present = bool(live_flags["api_keys_present"])
    order_submission_requested = bool(live_flags["order_submission_requested"])
    has_enable_order_submission = bool(live_flags["has_enable_order_submission"])
    has_block_real_order_submission = bool(live_flags["has_block_real_order_submission"])
    block_real_order_submission = bool(live_flags["block_real_order_submission"])
    order_submission_enabled = bool(live_flags["order_submission_enabled"])
    live_preflight_enabled = bool(live_flags["live_preflight_enabled"])

    # Keep the LLM vendor loop simulation-only by default to avoid duplicate live orders.
    llm_live_requested = parse_bool(settings.get("ENABLE_LLM_LIVE_TRADING"), False)
    llm_live_enabled = bool(api_keys_present and llm_live_requested)

    dry_run_wallet = parse_float(settings.get("DRY_RUN_WALLET"), 1000.0)
    stake_ratio_pct = max(0.1, min(parse_float(settings.get("DYNAMIC_STAKE_RATIO_PCT"), 10.0), 100.0))
    llm_trade_amount = parse_float(settings.get("LLM_TRADE_AMOUNT_USDT"), 100.0)
    default_leverage = max(1, int(parse_float(settings.get("DEFAULT_LEVERAGE"), 2.0)))
    default_stop_loss_pct = max(0.1, parse_float(settings.get("DEFAULT_STOP_LOSS_PCT"), 3.5))
    default_take_profit_pct = max(0.1, parse_float(settings.get("DEFAULT_TAKE_PROFIT_PCT"), 4.0))
    aggressive_base_stop_loss_pct = max(
        0.1,
        parse_float(settings.get("AGGRESSIVE_BASE_STOPLOSS_PCT"), default_stop_loss_pct),
    )

    freqtrade_config = json.loads(FREQTRADE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    freqtrade_config.setdefault("exchange", {})
    freqtrade_config["exchange"].setdefault("ccxt_config", {})
    freqtrade_config["exchange"].setdefault("ccxt_async_config", {})
    freqtrade_config["exchange"]["ccxt_config"]["enableRateLimit"] = True
    freqtrade_config["exchange"]["ccxt_async_config"]["enableRateLimit"] = True
    freqtrade_config["exchange"]["key"] = binance_api_key if order_submission_enabled else ""
    freqtrade_config["exchange"]["secret"] = binance_secret_key if order_submission_enabled else ""
    freqtrade_config["dry_run"] = not order_submission_enabled
    freqtrade_config["dry_run_wallet"] = dry_run_wallet
    freqtrade_config["stake_amount"] = "unlimited"
    freqtrade_config["stoploss"] = -(aggressive_base_stop_loss_pct / 100.0)
    freqtrade_config.setdefault("order_types", {})
    freqtrade_config["order_types"]["stoploss_on_exchange"] = True
    freqtrade_config["order_types"]["stoploss_on_exchange_interval"] = 30
    freqtrade_config["order_types"]["stoploss_price_type"] = "mark"

    FREQTRADE_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    FREQTRADE_RUNTIME_PATH.write_text(json.dumps(freqtrade_config, indent=2, ensure_ascii=False), encoding="utf-8")

    llm_config = {
        "api_key": binance_api_key if llm_live_enabled else "",
        "api_secret": binance_secret_key if llm_live_enabled else "",
        "claude_api_key": anthropic_api_key,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_fallback_model": llm_fallback_model,
        "llm_base_url": llm_base_url,
        "llm_market_type": llm_market_type,
        "llm_timeout_seconds": llm_timeout_seconds,
        "simulation_mode": not llm_live_enabled,
        "trading_pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "LINKUSDT", "AVAXUSDT"],
        "trade_amount_usdt": llm_trade_amount,
        "stop_loss_percentage": 1.5,
        "take_profit_percentage": 2.5,
        "evaluation_interval": 900,
        "analysis_interval": "15m",
        "analysis_lookback": 120,
        "min_pattern_size": 5,
        "confidence_threshold": 0.7,
        "risk_per_trade_percentage": 1.0,
        "max_daily_loss_usdt": 100,
        "max_position_size_usdt": 1000,
    }

    LLM_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_RUNTIME_PATH.write_text(json.dumps(llm_config, indent=2, ensure_ascii=False), encoding="utf-8")

    settings_state = {
        "settings_env_path": str(SETTINGS_ENV_PATH),
        "settings_env_present": SETTINGS_ENV_PATH.exists(),
        "api_keys_present": api_keys_present,
        "api_key_masked": _mask_secret(binance_api_key),
        "live_requested": live_requested,
        "order_submission_requested": order_submission_requested,
        "has_enable_order_submission": has_enable_order_submission,
        "order_submission_enabled": order_submission_enabled,
        "block_real_order_submission": block_real_order_submission,
        "has_block_real_order_submission": has_block_real_order_submission,
        "live_preflight_enabled": live_preflight_enabled,
        "live_trading_enabled": order_submission_enabled,
        "llm_live_requested": llm_live_requested,
        "llm_live_enabled": llm_live_enabled,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_fallback_model": llm_fallback_model,
        "llm_base_url": llm_base_url,
        "llm_market_type": llm_market_type,
        "mode": ("live" if order_submission_enabled else ("live_preflight" if live_preflight_enabled else "dry_run")),
        "anthropic_key_present": bool(anthropic_api_key),
        "stake_ratio_pct": stake_ratio_pct,
        "default_leverage": default_leverage,
        "default_stop_loss_pct": default_stop_loss_pct,
        "default_take_profit_pct": default_take_profit_pct,
        "aggressive_base_stop_loss_pct": aggressive_base_stop_loss_pct,
        "dry_run_wallet": dry_run_wallet,
    }
    SETTINGS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_STATE_PATH.write_text(json.dumps(settings_state, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "mode": settings_state["mode"],
        "live_trading_enabled": order_submission_enabled,
        "live_preflight_enabled": live_preflight_enabled,
        "block_real_order_submission": block_real_order_submission,
        "has_block_real_order_submission": has_block_real_order_submission,
        "api_keys_present": api_keys_present,
        "stake_ratio_pct": stake_ratio_pct,
        "llm_live_enabled": llm_live_enabled,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
