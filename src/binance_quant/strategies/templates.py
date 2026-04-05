from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from .base import PineStrategyTemplate, SignalFrame, StrategyVariant
from .indicators import adx, atr, bollinger_bands, crossover, crossunder, ema, macd, minus_di, plus_di, rsi, sma, stoch_fast


class TrendEMAStrategy(PineStrategyTemplate):
    family = "trend_ema"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        variants: list[StrategyVariant] = []
        directions = search_space.get("directions", ["both"])
        for fast, slow, rsi_threshold, direction in product(
            search_space["fast_lengths"],
            search_space["slow_lengths"],
            search_space["rsi_thresholds"],
            directions,
        ):
            if fast >= slow:
                continue
            variants.append(
                StrategyVariant(
                    family=self.family,
                    name="ema_cross_rsi",
                    parameters={
                        "fast": int(fast),
                        "slow": int(slow),
                        "rsi_threshold": float(rsi_threshold),
                        "direction": str(direction),
                    },
                )
            )
        return variants

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        direction = str(variant.parameters.get("direction", "both"))
        fast = ema(frame["close"], int(variant.parameters["fast"]))
        slow = ema(frame["close"], int(variant.parameters["slow"]))
        strength = rsi(frame["close"], 14)
        entry_long = crossover(fast, slow) & (strength > variant.parameters["rsi_threshold"])
        entry_short = crossunder(fast, slow) & (strength < (100 - variant.parameters["rsi_threshold"]))
        exit_long = crossunder(fast, slow)
        exit_short = crossover(fast, slow)
        if direction == "long_only":
            entry_short = entry_short & False
            exit_short = exit_short & False
        elif direction == "short_only":
            entry_long = entry_long & False
            exit_long = exit_long & False
        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": (strength - 50).abs().fillna(0.0) / 50,
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
fast = ta.ema(close, {variant.parameters["fast"]})
slow = ta.ema(close, {variant.parameters["slow"]})
r = ta.rsi(close, 14)
longCondition = ta.crossover(fast, slow) and r > {variant.parameters["rsi_threshold"]}
shortCondition = ta.crossunder(fast, slow) and r < {100 - variant.parameters["rsi_threshold"]}
if longCondition and "{direction}" != "short_only"
    strategy.entry("Long", strategy.long)
if shortCondition and "{direction}" != "long_only"
    strategy.entry("Short", strategy.short)
if ta.crossunder(fast, slow)
    strategy.close("Long")
if ta.crossover(fast, slow)
    strategy.close("Short")
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class BreakoutStrategy(PineStrategyTemplate):
    family = "breakout"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        return [
            StrategyVariant(
                family=self.family,
                name="donchian_breakout",
                parameters={"window": int(window), "atr_filter": float(atr_filter), "direction": str(direction)},
            )
            for window, atr_filter, direction in product(
                search_space["windows"],
                search_space["atr_filters"],
                search_space.get("directions", ["both"]),
            )
        ]

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        direction = str(variant.parameters.get("direction", "both"))
        window = int(variant.parameters["window"])
        atr_filter = float(variant.parameters["atr_filter"])
        highest = frame["high"].rolling(window, min_periods=window).max().shift(1)
        lowest = frame["low"].rolling(window, min_periods=window).min().shift(1)
        atr_series = atr(frame, 14)
        range_ratio = (frame["high"] - frame["low"]) / atr_series
        trend_fast = ema(frame["close"], 20)
        trend_slow = ema(frame["close"], 55)
        volume_mean = frame["volume"].rolling(30, min_periods=30).mean()
        entry_long = (frame["close"] > highest) & (range_ratio > atr_filter) & (trend_fast > trend_slow) & (frame["volume"] > volume_mean)
        entry_short = (frame["close"] < lowest) & (range_ratio > atr_filter) & (trend_fast < trend_slow) & (frame["volume"] > volume_mean)
        exit_long = (frame["close"] < ema(frame["close"], max(10, window // 2))) | crossunder(trend_fast, trend_slow)
        exit_short = (frame["close"] > ema(frame["close"], max(10, window // 2))) | crossover(trend_fast, trend_slow)
        if direction == "long_only":
            entry_short = entry_short & False
            exit_short = exit_short & False
        elif direction == "short_only":
            entry_long = entry_long & False
            exit_long = exit_long & False
        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": range_ratio.clip(lower=0).fillna(0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
breakoutHigh = ta.highest(high, {window})[1]
breakoutLow = ta.lowest(low, {window})[1]
atr14 = ta.atr(14)
rangeRatio = (high - low) / atr14
trendFast = ta.ema(close, 20)
trendSlow = ta.ema(close, 55)
volMean = ta.sma(volume, 30)
longCondition = close > breakoutHigh and rangeRatio > {atr_filter} and trendFast > trendSlow and volume > volMean
shortCondition = close < breakoutLow and rangeRatio > {atr_filter} and trendFast < trendSlow and volume > volMean
if longCondition and "{direction}" != "short_only"
    strategy.entry("Long", strategy.long)
if shortCondition and "{direction}" != "long_only"
    strategy.entry("Short", strategy.short)
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class TrendPullbackStrategy(PineStrategyTemplate):
    family = "trend_pullback"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        variants: list[StrategyVariant] = []
        for fast, slow, pullback_rsi in product(
            search_space["fast_lengths"],
            search_space["slow_lengths"],
            search_space["pullback_rsi_levels"],
        ):
            if fast >= slow:
                continue
            variants.append(
                StrategyVariant(
                    family=self.family,
                    name="ema_pullback_resume",
                    parameters={
                        "fast": int(fast),
                        "slow": int(slow),
                        "pullback_rsi": float(pullback_rsi),
                    },
                )
            )
        return variants

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        fast = ema(frame["close"], int(variant.parameters["fast"]))
        slow = ema(frame["close"], int(variant.parameters["slow"]))
        current_rsi = rsi(frame["close"], 14)
        uptrend = fast > slow
        downtrend = fast < slow
        long_resume = (frame["close"] > fast) & (frame["close"].shift(1) <= fast.shift(1))
        short_resume = (frame["close"] < fast) & (frame["close"].shift(1) >= fast.shift(1))
        long_pullback = current_rsi.shift(1) < variant.parameters["pullback_rsi"]
        short_pullback = current_rsi.shift(1) > (100 - variant.parameters["pullback_rsi"])
        entry_long = uptrend & long_pullback & long_resume
        entry_short = downtrend & short_pullback & short_resume
        exit_long = crossunder(frame["close"], fast) | crossunder(fast, slow)
        exit_short = crossover(frame["close"], fast) | crossover(fast, slow)
        distance = ((frame["close"] - fast).abs() / frame["close"].replace(0, pd.NA)).fillna(0.0)
        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": distance,
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
fast = ta.ema(close, {variant.parameters["fast"]})
slow = ta.ema(close, {variant.parameters["slow"]})
r = ta.rsi(close, 14)
uptrend = fast > slow
downtrend = fast < slow
longResume = close > fast and close[1] <= fast[1]
shortResume = close < fast and close[1] >= fast[1]
longCondition = uptrend and r[1] < {variant.parameters["pullback_rsi"]} and longResume
shortCondition = downtrend and r[1] > {100 - variant.parameters["pullback_rsi"]} and shortResume
if longCondition
    strategy.entry("Long", strategy.long)
if shortCondition
    strategy.entry("Short", strategy.short)
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class VolSqueezeStrategy(PineStrategyTemplate):
    family = "vol_squeeze"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        return [
            StrategyVariant(
                family=self.family,
                name="bb_squeeze_breakout",
                parameters={
                    "window": int(window),
                    "squeeze_threshold": float(squeeze_threshold),
                    "volume_z_threshold": float(volume_z_threshold),
                },
            )
            for window, squeeze_threshold, volume_z_threshold in product(
                search_space["windows"],
                search_space["squeeze_thresholds"],
                search_space["volume_z_thresholds"],
            )
        ]

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        window = int(variant.parameters["window"])
        squeeze_threshold = float(variant.parameters["squeeze_threshold"])
        volume_z_threshold = float(variant.parameters["volume_z_threshold"])
        lower, middle, upper = bollinger_bands(frame["close"], window, 2.0)
        bandwidth = (upper - lower) / middle.replace(0, pd.NA)
        squeeze = bandwidth.rolling(80, min_periods=40).rank(pct=True) < squeeze_threshold
        trend_fast = ema(frame["close"], 20)
        trend_slow = ema(frame["close"], 55)
        volume_mean = frame["volume"].rolling(30, min_periods=30).mean()
        volume_std = frame["volume"].rolling(30, min_periods=30).std()
        volume_z = (frame["volume"] - volume_mean) / volume_std.replace(0, pd.NA)
        highest = frame["high"].rolling(window, min_periods=window).max().shift(1)
        lowest = frame["low"].rolling(window, min_periods=window).min().shift(1)
        entry_long = squeeze.shift(1) & (frame["close"] > highest) & (volume_z > volume_z_threshold) & (trend_fast > trend_slow)
        entry_short = squeeze.shift(1) & (frame["close"] < lowest) & (volume_z > volume_z_threshold) & (trend_fast < trend_slow)
        exit_long = (frame["close"] < middle) | crossunder(trend_fast, trend_slow)
        exit_short = (frame["close"] > middle) | crossover(trend_fast, trend_slow)
        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": (volume_z.fillna(0.0) + bandwidth.fillna(0.0)).clip(lower=0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
basis = ta.sma(close, {window})
dev = ta.stdev(close, {window}) * 2.0
upper = basis + dev
lower = basis - dev
bandwidth = (upper - lower) / basis
squeeze = ta.percentrank(bandwidth, 80) < {squeeze_threshold * 100}
volZ = (volume - ta.sma(volume, 30)) / ta.stdev(volume, 30)
breakoutHigh = ta.highest(high, {window})[1]
breakoutLow = ta.lowest(low, {window})[1]
trendFast = ta.ema(close, 20)
trendSlow = ta.ema(close, 55)
longCondition = squeeze[1] and close > breakoutHigh and volZ > {volume_z_threshold} and trendFast > trendSlow
shortCondition = squeeze[1] and close < breakoutLow and volZ > {volume_z_threshold} and trendFast < trendSlow
if longCondition
    strategy.entry("Long", strategy.long)
if shortCondition
    strategy.entry("Short", strategy.short)
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class MeanReversionStrategy(PineStrategyTemplate):
    family = "mean_reversion"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        return [
            StrategyVariant(
                family=self.family,
                name="bb_rsi_reversion",
                parameters={
                    "bb_window": int(bb_window),
                    "z_score": float(z_score),
                    "rsi_threshold": float(rsi_threshold),
                },
            )
            for bb_window, z_score, rsi_threshold in product(
                search_space["bb_windows"],
                search_space["z_scores"],
                search_space["rsi_thresholds"],
            )
        ]

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        bb_window = int(variant.parameters["bb_window"])
        z_score = float(variant.parameters["z_score"])
        rsi_threshold = float(variant.parameters["rsi_threshold"])
        lower, middle, upper = bollinger_bands(frame["close"], bb_window, z_score)
        current_rsi = rsi(frame["close"], 14)
        trend_spread = ((ema(frame["close"], 20) - ema(frame["close"], 50)).abs() / frame["close"].replace(0, pd.NA)).fillna(0.0)
        range_regime = trend_spread < 0.02
        entry_long = (frame["close"] < lower) & (current_rsi < rsi_threshold) & range_regime
        entry_short = (frame["close"] > upper) & (current_rsi > (100 - rsi_threshold)) & range_regime
        exit_long = frame["close"] >= middle
        exit_short = frame["close"] <= middle
        band_width = (upper - lower) / middle.replace(0, pd.NA)
        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": band_width.fillna(0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
basis = ta.sma(close, {bb_window})
dev = ta.stdev(close, {bb_window}) * {z_score}
upper = basis + dev
lower = basis - dev
r = ta.rsi(close, 14)
trendSpread = math.abs(ta.ema(close, 20) - ta.ema(close, 50)) / close
longCondition = close < lower and r < {rsi_threshold} and trendSpread < 0.02
shortCondition = close > upper and r > {100 - rsi_threshold} and trendSpread < 0.02
if longCondition
    strategy.entry("Long", strategy.long)
if shortCondition
    strategy.entry("Short", strategy.short)
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class ScalpMomentumStrategy(PineStrategyTemplate):
    family = "scalp_momentum"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        variants: list[StrategyVariant] = []
        directions = search_space.get("directions", ["both"])
        for fast, slow, breakout_window, volume_z_threshold, direction in product(
            search_space["fast_lengths"],
            search_space["slow_lengths"],
            search_space["breakout_windows"],
            search_space["volume_z_thresholds"],
            directions,
        ):
            if fast >= slow:
                continue
            variants.append(
                StrategyVariant(
                    family=self.family,
                    name="ema_micro_breakout",
                    parameters={
                        "fast": int(fast),
                        "slow": int(slow),
                        "breakout_window": int(breakout_window),
                        "volume_z_threshold": float(volume_z_threshold),
                        "direction": str(direction),
                    },
                )
            )
        return variants

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        direction = str(variant.parameters.get("direction", "both"))
        fast = ema(frame["close"], int(variant.parameters["fast"]))
        slow = ema(frame["close"], int(variant.parameters["slow"]))
        breakout_window = int(variant.parameters["breakout_window"])
        volume_z_threshold = float(variant.parameters["volume_z_threshold"])
        local_high = frame["high"].rolling(breakout_window, min_periods=breakout_window).max().shift(1)
        local_low = frame["low"].rolling(breakout_window, min_periods=breakout_window).min().shift(1)
        volume_mean = frame["volume"].rolling(20, min_periods=20).mean()
        volume_std = frame["volume"].rolling(20, min_periods=20).std()
        volume_z = ((frame["volume"] - volume_mean) / volume_std.replace(0, pd.NA)).fillna(0.0)
        trend_up = fast > slow
        trend_down = fast < slow
        micro_extension = ((frame["close"] - fast).abs() / frame["close"].replace(0, pd.NA)).fillna(0.0)

        entry_long = trend_up & (frame["close"] > local_high) & (volume_z >= volume_z_threshold)
        entry_short = trend_down & (frame["close"] < local_low) & (volume_z >= volume_z_threshold)
        exit_long = (frame["close"] < fast) | crossunder(fast, slow)
        exit_short = (frame["close"] > fast) | crossover(fast, slow)

        if direction == "long_only":
            entry_short = entry_short & False
            exit_short = exit_short & False
        elif direction == "short_only":
            entry_long = entry_long & False
            exit_long = exit_long & False

        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": (volume_z.abs() + micro_extension).clip(lower=0.0).fillna(0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
fast = ta.ema(close, {variant.parameters["fast"]})
slow = ta.ema(close, {variant.parameters["slow"]})
breakoutHigh = ta.highest(high, {breakout_window})[1]
breakoutLow = ta.lowest(low, {breakout_window})[1]
volZ = (volume - ta.sma(volume, 20)) / ta.stdev(volume, 20)
longCondition = fast > slow and close > breakoutHigh and volZ >= {volume_z_threshold}
shortCondition = fast < slow and close < breakoutLow and volZ >= {volume_z_threshold}
if longCondition and "{direction}" != "short_only"
    strategy.entry("Long", strategy.long)
if shortCondition and "{direction}" != "long_only"
    strategy.entry("Short", strategy.short)
if close < fast
    strategy.close("Long")
if close > fast
    strategy.close("Short")
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class FreqtradeADXStrategy(PineStrategyTemplate):
    family = "freqtrade_adx"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        variants: list[StrategyVariant] = []
        directions = search_space.get("directions", ["both"])
        for buy_rsi_threshold, sell_rsi_threshold, buy_plus_di_threshold, sell_minus_di_threshold, direction in product(
            search_space["buy_rsi_thresholds"],
            search_space["sell_rsi_thresholds"],
            search_space["buy_plus_di_thresholds"],
            search_space["sell_minus_di_thresholds"],
            directions,
        ):
            variants.append(
                StrategyVariant(
                    family=self.family,
                    name="freqtrade_rsi_adx_di",
                    parameters={
                        "buy_rsi_threshold": float(buy_rsi_threshold),
                        "sell_rsi_threshold": float(sell_rsi_threshold),
                        "buy_plus_di_threshold": float(buy_plus_di_threshold),
                        "sell_minus_di_threshold": float(sell_minus_di_threshold),
                        "direction": str(direction),
                    },
                )
            )
        return variants

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        direction = str(variant.parameters.get("direction", "both"))
        current_rsi = rsi(frame["close"], 14)
        current_adx = adx(frame, 14)
        current_plus_di = (plus_di(frame, 14) / 100.0).fillna(0.0)
        current_minus_di = (minus_di(frame, 14) / 100.0).fillna(0.0)
        _, fast_d = stoch_fast(frame, 14, 3)

        buy_rsi_threshold = float(variant.parameters["buy_rsi_threshold"])
        sell_rsi_threshold = float(variant.parameters["sell_rsi_threshold"])
        buy_plus_di_threshold = float(variant.parameters["buy_plus_di_threshold"])
        sell_minus_di_threshold = float(variant.parameters["sell_minus_di_threshold"])

        entry_long = (
            (
                (current_rsi < buy_rsi_threshold)
                & (fast_d < 35)
                & (current_adx > 30)
                & (current_plus_di > buy_plus_di_threshold)
            )
            | ((current_adx > 65) & (current_plus_di > buy_plus_di_threshold))
        )
        entry_short = crossunder(current_rsi, pd.Series(sell_rsi_threshold, index=frame.index))
        exit_long = (
            ((crossover(current_rsi, pd.Series(sell_rsi_threshold, index=frame.index))) | crossover(fast_d, pd.Series(70.0, index=frame.index)))
            & (current_adx > 10)
            & (current_minus_di > sell_minus_di_threshold)
        ) | ((current_adx > 70) & (current_minus_di > sell_minus_di_threshold))
        exit_short = crossover(current_rsi, pd.Series(buy_rsi_threshold, index=frame.index))

        if direction == "long_only":
            entry_short = entry_short & False
            exit_short = exit_short & False
        elif direction == "short_only":
            entry_long = entry_long & False
            exit_long = exit_long & False

        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": ((current_adx / 100.0) + (current_plus_di - current_minus_di).abs()).clip(lower=0.0).fillna(0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
r = ta.rsi(close, 14)
adx14 = ta.adx(14)
plusDi = ta.plus_di(14) / 100.0
minusDi = ta.minus_di(14) / 100.0
fastD = ta.sma(ta.stoch(high, low, close, 14), 3)
longCondition = ((r < {buy_rsi_threshold} and fastD < 35 and adx14 > 30 and plusDi > {buy_plus_di_threshold}) or (adx14 > 65 and plusDi > {buy_plus_di_threshold}))
shortCondition = ta.crossunder(r, {sell_rsi_threshold})
exitLong = (((ta.crossover(r, {sell_rsi_threshold}) or ta.crossover(fastD, 70)) and adx14 > 10 and minusDi > {sell_minus_di_threshold}) or (adx14 > 70 and minusDi > {sell_minus_di_threshold}))
exitShort = ta.crossover(r, {buy_rsi_threshold})
if longCondition and "{direction}" != "short_only"
    strategy.entry("Long", strategy.long)
if shortCondition and "{direction}" != "long_only"
    strategy.entry("Short", strategy.short)
if exitLong
    strategy.close("Long")
if exitShort
    strategy.close("Short")
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


class UltimateCryptoStrategy(PineStrategyTemplate):
    family = "ultimate_crypto"

    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        variants: list[StrategyVariant] = []
        directions = search_space.get("directions", ["both"])
        for fast, slow, long_ma, volume_threshold, volatility_threshold, direction in product(
            search_space["fast_lengths"],
            search_space["slow_lengths"],
            search_space["long_ma_lengths"],
            search_space["volume_thresholds"],
            search_space["volatility_thresholds"],
            directions,
        ):
            if fast >= slow:
                continue
            variants.append(
                StrategyVariant(
                    family=self.family,
                    name="ultimate_crypto_bot",
                    parameters={
                        "fast": int(fast),
                        "slow": int(slow),
                        "long_ma": int(long_ma),
                        "volume_threshold": float(volume_threshold),
                        "volatility_threshold": float(volatility_threshold),
                        "direction": str(direction),
                    },
                )
            )
        return variants

    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        direction = str(variant.parameters.get("direction", "both"))
        fast_period = int(variant.parameters["fast"])
        slow_period = int(variant.parameters["slow"])
        long_period = int(variant.parameters["long_ma"])
        volume_threshold = float(variant.parameters["volume_threshold"])
        volatility_threshold = float(variant.parameters["volatility_threshold"])

        fast = sma(frame["close"], fast_period)
        slow = sma(frame["close"], slow_period)
        long_ma = sma(frame["close"], long_period)
        current_rsi = rsi(frame["close"], 14)
        macd_line, signal_line, histogram = macd(frame["close"], 12, 26, 9)
        _, bb_middle, bb_upper = bollinger_bands(frame["close"], 20, 2.0)
        bb_lower, _, _ = bollinger_bands(frame["close"], 20, 2.0)
        volume_ma = frame["volume"].rolling(20, min_periods=20).mean()
        volume_confirm = (frame["volume"] > volume_ma * volume_threshold) | (frame["volume"] > volume_ma * 1.2)
        atr_value = atr(frame, 14)
        volatility = (atr_value / frame["close"].replace(0.0, np.nan) * 100.0).replace([np.inf, -np.inf], np.nan)
        k, d = stoch_fast(frame, 14, 3)

        highest_high = frame["high"].shift(1).rolling(10, min_periods=10).max()
        lowest_low = frame["low"].shift(1).rolling(10, min_periods=10).min()
        uptrend_structure = (frame["high"] > highest_high) & (frame["low"] > lowest_low)
        downtrend_structure = (frame["high"] < highest_high) & (frame["low"] < lowest_low)

        bullish_trend = (fast > slow) & (frame["close"] > long_ma)
        bearish_trend = (fast < slow) & (frame["close"] < long_ma)
        rsi_bullish = (current_rsi > 40) & (current_rsi < 80)
        rsi_bearish = (current_rsi < 60) & (current_rsi > 20)
        macd_bullish = (macd_line > signal_line) & (histogram > histogram.shift(1))
        macd_bearish = (macd_line < signal_line) & (histogram < histogram.shift(1))
        stoch_bullish = (k > d) & (k > 20) & (k < 80)
        stoch_bearish = (k < d) & (k > 20) & (k < 80)
        low_volatility = volatility < volatility_threshold

        entry_long = bullish_trend & rsi_bullish & macd_bullish & stoch_bullish & uptrend_structure & volume_confirm & low_volatility
        entry_short = bearish_trend & rsi_bearish & macd_bearish & stoch_bearish & downtrend_structure & volume_confirm & low_volatility
        exit_long = bearish_trend & (current_rsi > 70)
        exit_short = bullish_trend & (current_rsi < 30)

        if direction == "long_only":
            entry_short = entry_short & False
            exit_short = exit_short & False
        elif direction == "short_only":
            entry_long = entry_long & False
            exit_long = exit_long & False

        bandwidth = (
            (bb_upper - bb_lower) / bb_middle.replace(0.0, np.nan)
        ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        strength = (
            ((fast - slow).abs() / frame["close"].replace(0.0, np.nan)).fillna(0.0)
            + histogram.abs().fillna(0.0)
            + bandwidth
        ).clip(lower=0.0)

        signals = pd.DataFrame(
            {
                "entry_long": entry_long.fillna(False),
                "entry_short": entry_short.fillna(False),
                "exit_long": exit_long.fillna(False),
                "exit_short": exit_short.fillna(False),
                "signal_strength": strength.fillna(0.0),
            },
            index=frame.index,
        )
        pine = f"""
//@version=5
strategy("{variant.strategy_id}", overlay=true, process_orders_on_close=true)
maFast = ta.sma(close, {fast_period})
maSlow = ta.sma(close, {slow_period})
maLong = ta.sma(close, {long_period})
r = ta.rsi(close, 14)
[macdLine, signalLine, histogram] = ta.macd(close, 12, 26, 9)
[bbUpper, bbMiddle, bbLower] = ta.bb(close, 20, 2.0)
volumeMa = ta.sma(volume, 20)
volumeConfirm = volume > volumeMa * {volume_threshold} or volume > volumeMa * 1.2
atr14 = ta.atr(14)
volatility = atr14 / close * 100
k = ta.stoch(close, high, low, 14)
d = ta.sma(k, 3)
uptrendStructure = high > ta.highest(high[1], 10) and low > ta.lowest(low[1], 10)
downtrendStructure = high < ta.highest(high[1], 10) and low < ta.lowest(low[1], 10)
bullishTrend = maFast > maSlow and close > maLong
bearishTrend = maFast < maSlow and close < maLong
longSignal = bullishTrend and r > 40 and r < 80 and macdLine > signalLine and histogram > histogram[1] and k > d and k > 20 and k < 80 and uptrendStructure and volumeConfirm and volatility < {volatility_threshold}
shortSignal = bearishTrend and r < 60 and r > 20 and macdLine < signalLine and histogram < histogram[1] and k < d and k > 20 and k < 80 and downtrendStructure and volumeConfirm and volatility < {volatility_threshold}
exitLong = bearishTrend and r > 70
exitShort = bullishTrend and r < 30
if longSignal and "{direction}" != "short_only"
    strategy.entry("Long", strategy.long)
if shortSignal and "{direction}" != "long_only"
    strategy.entry("Short", strategy.short)
if exitLong
    strategy.close("Long")
if exitShort
    strategy.close("Short")
"""
        return SignalFrame(signals=signals, pine_script=pine.strip())


def build_strategy_templates() -> list[PineStrategyTemplate]:
    return [
        TrendEMAStrategy(),
        ScalpMomentumStrategy(),
        FreqtradeADXStrategy(),
        UltimateCryptoStrategy(),
        TrendPullbackStrategy(),
        BreakoutStrategy(),
        VolSqueezeStrategy(),
        MeanReversionStrategy(),
    ]
