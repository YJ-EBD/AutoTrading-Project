from pathlib import Path

from binance_quant.config import Settings
from binance_quant.paper.models import PaperDecision, PaperPosition
from binance_quant.paper.runtime import PaperTradingRuntime


def test_manual_kill_switch_closes_active_positions(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()

    runtime = PaperTradingRuntime(settings)

    decision_id = runtime.repository.record_decision(
        PaperDecision(
            decided_at="2026-03-31T00:00:00+00:00",
            symbol="BTCUSDT",
            strategy_id="trend_ema__demo",
            family="trend_ema",
            side="long",
            signal_time="2026-03-31T00:00:00+00:00",
            observed_price=100.0,
            atr_value=2.0,
            signal_strength=0.8,
            ml_probability=0.7,
            ml_threshold=0.5,
            ml_accepted=True,
            llm_enabled=False,
            llm_action=None,
            llm_confidence=None,
            llm_reason=None,
            final_action="allow",
            portfolio_reason="ml_only",
            payload={},
        )
    )

    position_id = runtime.repository.open_position(
        PaperPosition(
            decision_id=decision_id,
            symbol="BTCUSDT",
            strategy_id="trend_ema__demo",
            family="trend_ema",
            side="long",
            opened_at="2026-03-31T00:00:00+00:00",
            entry_observed_price=100.0,
            latest_observed_price=101.0,
            stop_price=98.0,
            target_price=103.0,
            liquidation_price=90.0,
            atr_value=2.0,
            model_probability=0.7,
            llm_action=None,
            llm_confidence=None,
            metadata={},
        )
    )
    runtime.repository.update_active_mark(
        position_id,
        latest_observed_price=101.0,
        gross_return=0.01,
        net_return=0.009,
        max_adverse_excursion=0.002,
        max_favorable_excursion=0.012,
        bars_held=1,
    )

    state = runtime.activate_kill_switch(reason="manual_test", source="unit_test")

    closed_positions = runtime.repository.list_positions(status="closed", limit=10)
    assert state["active"] is True
    assert state["closed_position_count"] == 1
    assert "BTCUSDT" in state["closed_symbols"]
    assert len(closed_positions) == 1
    assert closed_positions[0]["exit_reason"] == "kill_switch"
    assert runtime.is_kill_switch_active() is True

    state = runtime.deactivate_kill_switch(reason="manual_reset", source="unit_test")
    assert state["active"] is False
    assert runtime.is_kill_switch_active() is False


def test_runtime_applies_confidence_sizing_and_trailing_logic(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()

    runtime = PaperTradingRuntime(settings)

    high_fraction = runtime._allocated_capital_fraction(0.78)
    low_fraction = runtime._allocated_capital_fraction(0.46)
    assert high_fraction > low_fraction
    assert high_fraction == settings.paper.max_position_capital_fraction
    assert runtime._target_atr_multiple(0.78) > runtime._target_atr_multiple(0.46)

    position = {
        "side": "long",
        "entry_observed_price": 100.0,
        "stop_price": 98.0,
        "target_price": 104.0,
        "metadata": {
            "trailing_active": False,
            "trailing_anchor_price": 100.0,
        },
    }
    update = {"high": 102.0, "low": 100.8, "close": 101.6}

    new_stop, metadata = runtime._maybe_update_trailing_stop(position, position["metadata"], update)

    assert metadata["trailing_active"] is True
    assert new_stop is not None
    assert new_stop > 98.0
