from pathlib import Path

from binance_quant.config import Settings


def test_settings_loads_and_resolves_paths() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    assert settings.project_root.name == "yjcooperation"
    assert settings.cache_root.name == "cache"
    assert settings.exchange.base_rest_url.startswith("https://")
    assert settings.exchange.websocket_ping_timeout_seconds >= settings.exchange.websocket_ping_interval_seconds
    assert settings.exchange.websocket_receive_timeout_seconds >= settings.exchange.websocket_ping_timeout_seconds
    assert settings.exchange.websocket_reconnect_delay_max_seconds >= settings.exchange.websocket_reconnect_delay_seconds
    assert settings.paper.initial_retune_delay_seconds >= 0
    assert settings.paper.starting_equity_usd == 1000.0
    assert settings.paper.retune_on_loss_trigger is True
    assert settings.paper.loss_trigger_loss_streak >= 2
    assert settings.paper.min_daily_trade_target >= 1
    assert settings.paper.max_daily_trade_target >= settings.paper.min_daily_trade_target
    assert settings.paper.min_live_threshold_floor < settings.paper.max_live_threshold_ceiling
    assert settings.paper.loss_retune_deployment_min_trade_count >= settings.portfolio.min_portfolio_trades
    assert settings.paper.loss_retune_deployment_min_expectancy > settings.research.min_expectancy
    assert settings.paper.throughput_candidate_min_trade_count >= settings.paper.emergency_candidate_min_trade_count
    assert settings.paper.throughput_candidate_min_distinct_symbols >= settings.paper.emergency_candidate_min_distinct_symbols
    assert settings.paper.throughput_candidate_min_precision >= 0.5
    assert settings.paper.kill_switch_enabled is True
    assert settings.paper.kill_switch_auto_daily_loss_fraction > 0
    assert settings.deployment.min_strategy_count >= 1
    assert settings.deployment.max_strategy_count >= settings.deployment.min_strategy_count
    assert settings.deployment.max_strategies_per_family >= 1
    assert settings.research.zero_survivor_seed_profit_factor_margin >= settings.research.family_seed_profit_factor_margin
    assert settings.dashboard.api_key_header.startswith("X-")
    assert settings.local_llm.model == "qwen3:8b"
    assert settings.local_llm.fallback_models[0] == "gemma3:4b"


def test_newyjt_settings_loads_and_uses_separate_project_root() -> None:
    settings = Settings.load(Path("newYJT/configs/base.yaml"))
    assert settings.project_root.name == "newYJT"
    assert settings.market_data_root.name == "market"
    assert settings.artifact_root.name == "artifacts"
    assert settings.dashboard.port == 8020
    assert "risk committee" in settings.local_llm.system_prompt.lower()
    assert "{context_json}" in settings.local_llm.prompt_template
