from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from binance_quant.config import Settings
from binance_quant.paper.dashboard import (
    _dashboard_context,
    _health_payload,
    _require_api_key,
    _runtime_payload,
    create_app,
)
from binance_quant.paper.models import PaperPosition
from binance_quant.paper.repository import PaperTradeRepository


def test_dashboard_runtime_payload_and_context(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()
    settings.paper_log_path.write_text("line-1\nline-2\n", encoding="utf-8")

    app = create_app(settings, start_runtime=False)

    runtime_payload = _runtime_payload(app)
    assert runtime_payload["service_status"] == {}
    assert runtime_payload["stream_status"] == {}
    assert runtime_payload["llm_available"] is False
    assert runtime_payload["kill_switch"]["active"] is False

    context = _dashboard_context(app)
    assert context["runtime_logs"] == ["line-1", "line-2"]
    assert context["overview"]["decision_count"] == 0
    assert context["overview"]["starting_equity_usd"] == 1000.0
    assert context["overview"]["position_margin_usd"] == 100.0


def test_dashboard_enriches_position_roi_and_pnl(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()

    repository = PaperTradeRepository(settings.paper_state_db)
    repository.open_position(
        PaperPosition(
            decision_id=1,
            symbol="BTCUSDT",
            strategy_id="demo_strategy",
            family="trend_ema",
            side="long",
            opened_at="2026-03-23T00:00:00+00:00",
            entry_observed_price=100.0,
            latest_observed_price=101.0,
            stop_price=98.0,
            target_price=105.0,
            liquidation_price=90.0,
            atr_value=1.0,
            model_probability=0.7,
            llm_action="allow",
            llm_confidence=0.8,
            metadata={},
        )
    )
    repository.update_active_mark(
        1,
        latest_observed_price=101.0,
        gross_return=0.012,
        net_return=0.01,
        max_adverse_excursion=0.001,
        max_favorable_excursion=0.013,
        bars_held=1,
    )

    app = create_app(settings, start_runtime=False)
    context = _dashboard_context(app)

    assert len(context["active_positions"]) == 1
    position = context["active_positions"][0]
    assert position["net_roi_percent"] == 1.0
    assert position["net_pnl_usd"] == 10.0
    assert position["account_net_roi_percent"] == 1.0
    assert position["position_margin_usd"] == 100.0
    assert position["position_net_roi_percent"] == 10.0


def test_dashboard_uses_position_specific_capital_fraction(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()

    repository = PaperTradeRepository(settings.paper_state_db)
    repository.open_position(
        PaperPosition(
            decision_id=2,
            symbol="ETHUSDT",
            strategy_id="demo_strategy_scaled",
            family="trend_ema",
            side="long",
            opened_at="2026-03-23T00:00:00+00:00",
            entry_observed_price=100.0,
            latest_observed_price=101.0,
            stop_price=98.0,
            target_price=105.0,
            liquidation_price=90.0,
            atr_value=1.0,
            model_probability=0.8,
            llm_action="allow",
            llm_confidence=0.9,
            metadata={"capital_fraction": 0.15, "confidence_bucket": "high"},
        )
    )
    repository.update_active_mark(
        1,
        latest_observed_price=101.0,
        gross_return=0.015,
        net_return=0.012,
        max_adverse_excursion=0.001,
        max_favorable_excursion=0.016,
        bars_held=1,
    )

    app = create_app(settings, start_runtime=False)
    context = _dashboard_context(app)
    position = context["active_positions"][0]

    assert position["position_margin_usd"] == 150.0
    assert position["confidence_bucket"] == "high"
    assert position["position_net_roi_percent"] == pytest.approx(8.0)


def test_health_endpoint_and_protected_runtime_controls(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.dashboard.api_key = "secret-key"
    settings.ensure_directories()

    app = create_app(settings, start_runtime=False)
    repository = PaperTradeRepository(settings.paper_state_db)
    repository.set_state("service_status", {"is_running": True})
    repository.set_state("runtime_status", {"status": "running"})
    repository.set_state("stream_status", {"status": "connected"})
    repository.set_state(
        "kill_switch_status",
        {
            "active": True,
            "reason": "manual_test",
            "source": "unit_test",
            "activated_at": "2026-03-31T00:00:00+00:00",
        },
    )

    health_payload = _health_payload(app)
    assert health_payload["status"] == "degraded"
    assert health_payload["kill_switch"]["active"] is True

    blocked_request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        _require_api_key(blocked_request, settings)
    assert exc_info.value.status_code == 403

    allowed_request = Request(
        {
            "type": "http",
            "headers": [(settings.dashboard.api_key_header.lower().encode("utf-8"), settings.dashboard.api_key.encode("utf-8"))],
        }
    )
    _require_api_key(allowed_request, settings)
