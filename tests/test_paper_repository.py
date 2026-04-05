from pathlib import Path

from binance_quant.config import Settings
from binance_quant.paper.models import PaperPosition
from binance_quant.paper.repository import PaperTradeRepository


def test_overview_handles_zero_loss_denominator(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()

    repo = PaperTradeRepository(settings.paper_state_db)

    position_id = repo.open_position(
        PaperPosition(
            decision_id=1,
            symbol="BTCUSDT",
            strategy_id="demo",
            family="demo",
            side="long",
            opened_at="2026-03-31T00:00:00+00:00",
            entry_observed_price=100.0,
            latest_observed_price=100.0,
            stop_price=99.0,
            target_price=101.0,
            liquidation_price=90.0,
            atr_value=1.0,
            model_probability=1.0,
            llm_action=None,
            llm_confidence=None,
            metadata={},
        )
    )

    repo.close_position(
        position_id,
        closed_at="2026-03-31T00:15:00+00:00",
        exit_observed_price=100.0,
        exit_trigger_price=100.0,
        exit_reason="signal_exit",
        gross_return=0.0,
        net_return=0.0,
        max_adverse_excursion=0.0,
        max_favorable_excursion=0.0,
        bars_held=1,
        metadata={},
    )

    overview = repo.overview()

    assert overview["closed_positions"] == 1
    assert overview["profit_factor"] == 0.0
