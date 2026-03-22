import pandas as pd

from binance_quant.backtest.engine import VectorizedBacktester
from binance_quant.config import BacktestConfig
from binance_quant.strategies.base import StrategyVariant


def test_backtester_produces_target_exit_trade() -> None:
    index = pd.date_range("2024-01-01", periods=6, freq="15min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100, 100, 101, 102, 103, 104],
            "high": [100.5, 101.5, 103.5, 104.0, 104.5, 105.0],
            "low": [99.5, 99.8, 100.5, 101.5, 102.5, 103.5],
            "close": [100, 101, 103, 103.5, 104, 104.5],
            "atr": [1, 1, 1, 1, 1, 1],
        },
        index=index,
    )
    signals = pd.DataFrame(
        {
            "entry_long": [False, True, False, False, False, False],
            "entry_short": [False, False, False, False, False, False],
            "exit_long": [False, False, False, False, False, False],
            "exit_short": [False, False, False, False, False, False],
            "signal_strength": [0, 1, 0, 0, 0, 0],
        },
        index=index,
    )
    variant = StrategyVariant("trend_ema", "test", {"fast": 2, "slow": 4})
    result = VectorizedBacktester(BacktestConfig(target_atr_multiple=1.0, stop_atr_multiple=1.0)).run(
        "BTCUSDT",
        frame,
        signals,
        variant,
    )
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_reason"] == "target"
    assert result.metrics["trade_count"] == 1.0
