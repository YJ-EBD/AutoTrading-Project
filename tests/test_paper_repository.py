from pathlib import Path

from binance_quant.paper.models import PaperDecision, PaperPosition
from binance_quant.paper.repository import PaperTradeRepository


def test_paper_repository_tracks_decisions_and_positions(tmp_path: Path) -> None:
    repository = PaperTradeRepository(tmp_path / "paper.sqlite3")

    decision_id = repository.record_decision(
        PaperDecision(
            decided_at="2024-01-01T00:00:00+00:00",
            symbol="BTCUSDT",
            strategy_id="trend_ema__demo",
            family="trend_ema",
            side="long",
            signal_time="2024-01-01T00:00:00+00:00",
            observed_price=42000.0,
            atr_value=120.0,
            signal_strength=0.8,
            ml_probability=0.72,
            ml_threshold=0.62,
            ml_accepted=True,
            llm_enabled=False,
            llm_action=None,
            llm_confidence=None,
            llm_reason=None,
            final_action="allow",
            portfolio_reason="ml_only",
            payload={"source": "test"},
        )
    )

    position_id = repository.open_position(
        PaperPosition(
            decision_id=decision_id,
            symbol="BTCUSDT",
            strategy_id="trend_ema__demo",
            family="trend_ema",
            side="long",
            opened_at="2024-01-01T00:00:00+00:00",
            entry_observed_price=42000.0,
            latest_observed_price=42000.0,
            stop_price=41820.0,
            target_price=42300.0,
            liquidation_price=38220.0,
            atr_value=120.0,
            model_probability=0.72,
            llm_action=None,
            llm_confidence=None,
            metadata={"signal_strength": 0.8},
        )
    )

    repository.update_active_mark(
        position_id,
        latest_observed_price=42120.0,
        gross_return=0.02,
        net_return=0.019,
        max_adverse_excursion=0.004,
        max_favorable_excursion=0.021,
        bars_held=1,
    )
    repository.close_position(
        position_id,
        closed_at="2024-01-01T00:15:00+00:00",
        exit_observed_price=42320.0,
        exit_trigger_price=42300.0,
        exit_reason="target",
        gross_return=0.03,
        net_return=0.029,
        max_adverse_excursion=0.004,
        max_favorable_excursion=0.031,
        bars_held=1,
        metadata={"source": "test"},
    )

    active_positions = repository.list_positions(status="active", limit=10)
    closed_positions = repository.list_positions(status="closed", limit=10)
    recent_decisions = repository.recent_decisions(limit=10)
    overview = repository.overview()

    assert active_positions == []
    assert len(closed_positions) == 1
    assert len(recent_decisions) == 1
    assert overview["closed_positions"] == 1
    assert overview["win_rate"] == 1.0
