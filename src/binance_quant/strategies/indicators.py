from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    average_gain = up.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    average_loss = down.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = average_gain / average_loss.replace(0.0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def bollinger_bands(series: pd.Series, length: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mean = series.rolling(length, min_periods=length).mean()
    std = series.rolling(length, min_periods=length).std()
    upper = mean + num_std * std
    lower = mean - num_std * std
    return lower, mean, upper


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stoch_fast(frame: pd.DataFrame, length: int = 14, smooth_d: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest_low = frame["low"].rolling(length, min_periods=length).min()
    highest_high = frame["high"].rolling(length, min_periods=length).max()
    price_range = (highest_high - lowest_low).replace(0.0, np.nan)
    fast_k = 100 * (frame["close"] - lowest_low) / price_range
    fast_d = fast_k.rolling(smooth_d, min_periods=smooth_d).mean()
    return fast_k, fast_d


def plus_di(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    up_move = frame["high"].diff()
    down_move = -frame["low"].diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=frame.index,
    )
    atr_series = atr(frame, length)
    smoothed_plus_dm = plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return 100 * smoothed_plus_dm / atr_series.replace(0.0, np.nan)


def minus_di(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    up_move = frame["high"].diff()
    down_move = -frame["low"].diff()
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=frame.index,
    )
    atr_series = atr(frame, length)
    smoothed_minus_dm = minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return 100 * smoothed_minus_dm / atr_series.replace(0.0, np.nan)


def adx(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    plus = plus_di(frame, length)
    minus = minus_di(frame, length)
    dx = ((plus - minus).abs() / (plus + minus).replace(0.0, np.nan)) * 100
    return dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def crossover(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left > right) & (left.shift(1) <= right.shift(1))


def crossunder(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left < right) & (left.shift(1) >= right.shift(1))
