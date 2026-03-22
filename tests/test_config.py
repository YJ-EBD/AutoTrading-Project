from pathlib import Path

from binance_quant.config import Settings


def test_settings_loads_and_resolves_paths() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    assert settings.project_root.name == "yjcooperation"
    assert settings.cache_root.name == "cache"
    assert settings.exchange.base_rest_url.startswith("https://")
    assert settings.exchange.websocket_ping_timeout_seconds >= settings.exchange.websocket_ping_interval_seconds
    assert settings.paper.initial_retune_delay_seconds >= 0
