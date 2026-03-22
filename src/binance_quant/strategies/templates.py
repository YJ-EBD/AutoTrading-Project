from __future__ import annotations

from itertools import product

import pandas as pd

from .base import PineStrategyTemplate, SignalFrame, StrategyVariant
from .indicators import atr, bollinger_bands, crossover, crossunder, ema, rsi


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


def build_strategy_templates() -> list[PineStrategyTemplate]:
    return [
        TrendEMAStrategy(),
        TrendPullbackStrategy(),
        BreakoutStrategy(),
        VolSqueezeStrategy(),
        MeanReversionStrategy(),
    ]
