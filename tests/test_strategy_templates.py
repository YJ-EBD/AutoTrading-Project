import pandas as pd

from binance_quant.strategies.base import StrategyVariant
from binance_quant.strategies.templates import (
    FreqtradeADXStrategy,
    ScalpMomentumStrategy,
    UltimateCryptoStrategy,
    build_strategy_templates,
)


def test_build_strategy_templates_includes_scalp_momentum() -> None:
    families = [template.family for template in build_strategy_templates()]
    assert "scalp_momentum" in families
    assert "freqtrade_adx" in families
    assert "ultimate_crypto" in families


def test_scalp_momentum_strategy_emits_standard_signal_columns() -> None:
    closes = [100.0, 100.2, 100.4, 100.8, 101.1, 101.5, 101.9, 102.4, 102.8, 103.0, 103.3, 103.7, 104.0, 104.4, 104.8, 105.3, 105.9, 106.5, 107.1, 107.8, 108.4, 109.1, 109.9, 110.6, 111.2]
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.4 for value in closes],
            "low": [value - 0.4 for value in closes],
            "close": closes,
            "volume": [100 + index * 3 for index in range(len(closes))],
        },
        index=pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC"),
    )
    variant = StrategyVariant(
        family="scalp_momentum",
        name="ema_micro_breakout",
        parameters={
            "fast": 5,
            "slow": 13,
            "breakout_window": 3,
            "volume_z_threshold": 0.0,
            "direction": "both",
        },
    )

    signal_frame = ScalpMomentumStrategy().generate(frame, variant)

    assert {"entry_long", "entry_short", "exit_long", "exit_short", "signal_strength"}.issubset(
        signal_frame.signals.columns
    )
    assert "strategy.entry" in signal_frame.pine_script


def test_freqtrade_adx_strategy_emits_standard_signal_columns() -> None:
    closes = [100.0, 100.3, 100.7, 100.4, 100.9, 101.5, 101.1, 101.9, 102.6, 102.2, 103.0, 103.8, 103.4, 104.1, 104.9, 105.4, 106.0, 105.5, 106.2, 106.9, 107.5, 108.0, 108.7, 109.3, 109.8, 110.4, 111.0, 111.5, 112.1, 112.8]
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.6 for value in closes],
            "low": [value - 0.6 for value in closes],
            "close": closes,
            "volume": [120 + index * 4 for index in range(len(closes))],
        },
        index=pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC"),
    )
    variant = StrategyVariant(
        family="freqtrade_adx",
        name="freqtrade_rsi_adx_di",
        parameters={
            "buy_rsi_threshold": 30.0,
            "sell_rsi_threshold": 70.0,
            "buy_plus_di_threshold": 0.4,
            "sell_minus_di_threshold": 0.2,
            "direction": "both",
        },
    )

    signal_frame = FreqtradeADXStrategy().generate(frame, variant)

    assert {"entry_long", "entry_short", "exit_long", "exit_short", "signal_strength"}.issubset(
        signal_frame.signals.columns
    )
    assert "ta.adx" in signal_frame.pine_script


def test_ultimate_crypto_strategy_emits_standard_signal_columns() -> None:
    closes = [100.0, 100.4, 100.8, 101.2, 101.0, 101.5, 102.0, 102.6, 103.1, 103.7, 104.2, 104.8, 105.4, 106.0, 106.7, 107.3, 108.0, 108.8, 109.6, 110.4, 111.1, 111.8, 112.6, 113.3, 114.0, 114.8, 115.5, 116.1, 116.8, 117.6, 118.3, 119.0, 119.8, 120.6, 121.3, 122.1, 122.9, 123.7, 124.6, 125.5, 126.4, 127.2, 128.0, 128.9, 129.8, 130.7, 131.5, 132.4, 133.2, 134.1, 135.0, 135.9, 136.7, 137.6, 138.5, 139.4, 140.2, 141.1, 142.0, 142.9, 143.7, 144.6, 145.5, 146.4, 147.2, 148.1, 149.0, 149.9, 150.7, 151.6, 152.5, 153.4, 154.2, 155.1, 156.0, 156.9, 157.7, 158.6, 159.5, 160.4, 161.2, 162.1, 163.0, 163.9, 164.7, 165.6, 166.5, 167.4, 168.2, 169.1, 170.0, 170.9, 171.7, 172.6, 173.5, 174.4, 175.2, 176.1, 177.0, 177.9, 178.7, 179.6, 180.5, 181.4, 182.2, 183.1, 184.0, 184.9, 185.7, 186.6, 187.5, 188.4, 189.2, 190.1, 191.0, 191.9, 192.7, 193.6, 194.5, 195.4, 196.2, 197.1, 198.0, 198.9, 199.7, 200.6, 201.5, 202.4, 203.2, 204.1, 205.0]
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.8 for value in closes],
            "low": [value - 0.8 for value in closes],
            "close": closes,
            "volume": [200 + index * 5 for index in range(len(closes))],
        },
        index=pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC"),
    )
    variant = StrategyVariant(
        family="ultimate_crypto",
        name="ultimate_crypto_bot",
        parameters={
            "fast": 9,
            "slow": 21,
            "long_ma": 144,
            "volume_threshold": 1.2,
            "volatility_threshold": 2.0,
            "direction": "both",
        },
    )
    signal_frame = UltimateCryptoStrategy().generate(frame, variant)
    assert {"entry_long", "entry_short", "exit_long", "exit_short", "signal_strength"}.issubset(
        signal_frame.signals.columns
    )
    assert "ta.macd" in signal_frame.pine_script
