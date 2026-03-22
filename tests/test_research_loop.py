import pandas as pd

from binance_quant.config import Settings
from binance_quant.orchestration.research_loop import ResearchLoop


def build_loop() -> ResearchLoop:
    loop = ResearchLoop.__new__(ResearchLoop)
    loop.settings = Settings.load("configs/base.yaml")
    return loop


def test_family_seed_rescue_adds_near_threshold_new_family() -> None:
    loop = build_loop()
    settings = loop.settings
    pre_screen = pd.DataFrame(
        [
            {
                "strategy_id": "trend_a",
                "family": "trend_ema",
                "trade_count": 200.0,
                "expectancy": 0.001,
                "profit_factor": 1.05,
                "max_drawdown": 0.2,
                "positive_symbol_count": 4,
                "strict_survived": True,
                "ml_candidate_survived": True,
                "family_seed_survived": False,
                "survived": True,
                "survival_tier": "strict",
            },
            {
                "strategy_id": "breakout_a",
                "family": "breakout",
                "trade_count": float(settings.research.min_candidate_trades + 10),
                "expectancy": settings.research.relaxed_min_expectancy - 0.0001,
                "profit_factor": settings.research.relaxed_min_profit_factor - 0.01,
                "max_drawdown": settings.research.relaxed_max_drawdown_fraction + 0.01,
                "positive_symbol_count": max(1, settings.research.relaxed_min_positive_symbols - 1),
                "strict_survived": False,
                "ml_candidate_survived": False,
                "family_seed_survived": False,
                "survived": False,
                "survival_tier": "rejected",
            },
        ]
    )

    rescued = loop._apply_family_seed_rescue(pre_screen)
    breakout_row = rescued.loc[rescued["strategy_id"] == "breakout_a"].iloc[0]

    assert bool(breakout_row["survived"]) is True
    assert bool(breakout_row["family_seed_survived"]) is True
    assert breakout_row["survival_tier"] == "family_seed"


def test_select_diversified_survivors_drops_high_overlap_same_family() -> None:
    loop = build_loop()
    survivors = pd.DataFrame(
        [
            {
                "strategy_id": "trend_a",
                "family": "trend_ema",
                "trade_count": 200.0,
                "expectancy": 0.001,
                "profit_factor": 1.05,
                "positive_symbol_count": 4,
                "strict_survived": True,
                "family_seed_survived": False,
                "survived": True,
            },
            {
                "strategy_id": "trend_b",
                "family": "trend_ema",
                "trade_count": 180.0,
                "expectancy": 0.0008,
                "profit_factor": 1.02,
                "positive_symbol_count": 4,
                "strict_survived": False,
                "family_seed_survived": False,
                "survived": True,
            },
            {
                "strategy_id": "breakout_a",
                "family": "breakout",
                "trade_count": 160.0,
                "expectancy": 0.0003,
                "profit_factor": 0.93,
                "positive_symbol_count": 3,
                "strict_survived": False,
                "family_seed_survived": True,
                "survived": True,
            },
        ]
    )
    duplicate_signals = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "entry_time": "2024-01-01T00:00:00+00:00",
                "side": "long",
            },
            {
                "symbol": "BBBUSDT",
                "entry_time": "2024-01-01T00:15:00+00:00",
                "side": "long",
            },
        ]
    )
    candidate_trade_map = {
        "trend_a": duplicate_signals.copy(),
        "trend_b": duplicate_signals.copy(),
        "breakout_a": pd.DataFrame(
            [
                {
                    "symbol": "CCCUSDT",
                    "entry_time": "2024-01-01T00:30:00+00:00",
                    "side": "long",
                }
            ]
        ),
    }

    selected = loop._select_diversified_survivors(survivors, candidate_trade_map)

    assert "trend_a" in selected
    assert "breakout_a" in selected
    assert "trend_b" not in selected
