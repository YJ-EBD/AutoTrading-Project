import pandas as pd

from binance_quant.config import Settings
from binance_quant.portfolio.engine import build_portfolio


def test_portfolio_deduplicates_same_symbol_bar_signals() -> None:
    settings = Settings.load("configs/base.yaml")
    events = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "family": "trend_ema",
                "strategy_id": "s1",
                "entry_time": "2024-01-01T00:00:00+00:00",
                "exit_time": "2024-01-01T01:00:00+00:00",
                "side": "long",
                "probability": 0.8,
                "net_return": 0.02,
                "label_take": 1,
            },
            {
                "symbol": "AAAUSDT",
                "family": "trend_ema",
                "strategy_id": "s2",
                "entry_time": "2024-01-01T00:00:00+00:00",
                "exit_time": "2024-01-01T01:00:00+00:00",
                "side": "long",
                "probability": 0.7,
                "net_return": 0.01,
                "label_take": 1,
            },
            {
                "symbol": "BBBUSDT",
                "family": "trend_ema",
                "strategy_id": "s3",
                "entry_time": "2024-01-01T00:15:00+00:00",
                "exit_time": "2024-01-01T01:15:00+00:00",
                "side": "long",
                "probability": 0.75,
                "net_return": 0.015,
                "label_take": 1,
            },
        ]
    )
    portfolio = build_portfolio(events, settings)
    assert len(portfolio.accepted_trades) == 2
    assert portfolio.accepted_trades["symbol"].tolist().count("AAAUSDT") == 1


def test_portfolio_group_selection_does_not_depend_on_realized_returns() -> None:
    settings = Settings.load("configs/base.yaml")
    events = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "family": "trend_ema",
                "strategy_id": "s1",
                "entry_time": "2024-01-01T00:00:00+00:00",
                "exit_time": "2024-01-01T01:00:00+00:00",
                "side": "long",
                "probability": 0.81,
                "signal_strength": 0.9,
                "net_return": 0.10,
                "label_take": 1,
            },
            {
                "symbol": "BBBUSDT",
                "family": "breakout",
                "strategy_id": "s2",
                "entry_time": "2024-01-01T00:15:00+00:00",
                "exit_time": "2024-01-01T01:15:00+00:00",
                "side": "long",
                "probability": 0.79,
                "signal_strength": 0.8,
                "net_return": -0.05,
                "label_take": 0,
            },
            {
                "symbol": "CCCUSDT",
                "family": "trend_ema",
                "strategy_id": "s3",
                "entry_time": "2024-01-01T00:30:00+00:00",
                "exit_time": "2024-01-01T01:30:00+00:00",
                "side": "long",
                "probability": 0.78,
                "signal_strength": 0.7,
                "net_return": 0.03,
                "label_take": 1,
            },
            {
                "symbol": "DDDUSDT",
                "family": "breakout",
                "strategy_id": "s4",
                "entry_time": "2024-01-01T00:45:00+00:00",
                "exit_time": "2024-01-01T01:45:00+00:00",
                "side": "long",
                "probability": 0.77,
                "signal_strength": 0.6,
                "net_return": 0.01,
                "label_take": 1,
            },
        ]
    )
    permuted = events.copy()
    permuted["net_return"] = [-0.10, 0.08, -0.03, 0.02]
    permuted["label_take"] = [0, 1, 0, 1]

    left = build_portfolio(events, settings).accepted_trades[
        ["symbol", "family", "strategy_id", "entry_time", "side"]
    ].reset_index(drop=True)
    right = build_portfolio(permuted, settings).accepted_trades[
        ["symbol", "family", "strategy_id", "entry_time", "side"]
    ].reset_index(drop=True)

    pd.testing.assert_frame_equal(left, right)


def test_portfolio_respects_strategy_weight_when_alternatives_exist() -> None:
    settings = Settings.load("configs/base.yaml")
    events = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "family": "trend_ema",
                "strategy_id": "t1",
                "entry_time": "2024-01-01T00:00:00+00:00",
                "exit_time": "2024-01-01T00:30:00+00:00",
                "side": "long",
                "probability": 0.85,
                "signal_strength": 0.9,
                "net_return": 0.02,
                "label_take": 1,
            },
            {
                "symbol": "BBBUSDT",
                "family": "breakout",
                "strategy_id": "b1",
                "entry_time": "2024-01-01T00:15:00+00:00",
                "exit_time": "2024-01-01T00:45:00+00:00",
                "side": "long",
                "probability": 0.84,
                "signal_strength": 0.85,
                "net_return": 0.01,
                "label_take": 1,
            },
            {
                "symbol": "CCCUSDT",
                "family": "trend_ema",
                "strategy_id": "t2",
                "entry_time": "2024-01-01T00:30:00+00:00",
                "exit_time": "2024-01-01T01:00:00+00:00",
                "side": "long",
                "probability": 0.83,
                "signal_strength": 0.8,
                "net_return": 0.03,
                "label_take": 1,
            },
            {
                "symbol": "DDDUSDT",
                "family": "breakout",
                "strategy_id": "b2",
                "entry_time": "2024-01-01T00:45:00+00:00",
                "exit_time": "2024-01-01T01:15:00+00:00",
                "side": "long",
                "probability": 0.82,
                "signal_strength": 0.75,
                "net_return": 0.015,
                "label_take": 1,
            },
        ]
    )

    portfolio = build_portfolio(events, settings)
    family_share = portfolio.accepted_trades["family"].value_counts(normalize=True).max()

    assert set(portfolio.accepted_trades["family"]) == {"trend_ema", "breakout"}
    assert family_share <= settings.portfolio.max_strategy_weight


def test_portfolio_weight_caps_do_not_block_growth_before_trade_floor() -> None:
    settings = Settings.load("configs/base.yaml")
    rows: list[dict[str, object]] = []
    base_symbols = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"]
    for index in range(10):
        family = "trend_ema" if index % 2 == 0 else "breakout"
        symbol = base_symbols[index % len(base_symbols)]
        rows.append(
            {
                "symbol": symbol,
                "family": family,
                "strategy_id": f"{family}_{index}",
                "entry_time": pd.Timestamp("2024-01-01T00:00:00+00:00") + pd.Timedelta(minutes=15 * index),
                "exit_time": pd.Timestamp("2024-01-01T00:05:00+00:00") + pd.Timedelta(minutes=15 * index),
                "side": "long",
                "probability": 0.9 - index * 0.01,
                "signal_strength": 1.0 - index * 0.01,
                "net_return": 0.01 + index * 0.001,
                "label_take": 1,
            }
        )

    events = pd.DataFrame(rows)
    portfolio = build_portfolio(events, settings)

    assert len(portfolio.accepted_trades) >= settings.portfolio.min_portfolio_trades
    assert portfolio.accepted_trades["family"].value_counts(normalize=True).max() <= settings.portfolio.max_strategy_weight
    assert portfolio.accepted_trades["symbol"].value_counts(normalize=True).max() <= settings.portfolio.max_symbol_weight
