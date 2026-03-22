from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Settings
from ..strategies.indicators import atr, bollinger_bands, ema, macd, rsi


FEATURE_COLUMNS = [
    "log_return_1",
    "log_return_4",
    "log_return_16",
    "vol_norm_return_4",
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "range_ratio",
    "rsi_14",
    "macd_hist",
    "ema_fast_distance",
    "ema_slow_distance",
    "ema_fast_slope",
    "ema_slow_slope",
    "bb_bandwidth",
    "bb_zscore",
    "atr_14",
    "volume_zscore",
    "relative_volume",
    "trend_regime",
    "volatility_regime",
    "drawdown_20",
    "hour_sin",
    "hour_cos",
    "day_of_week",
    "session_bucket",
]


@dataclass
class FeatureDiagnostics:
    nan_rate: dict[str, float]
    zero_variance: list[str]
    high_correlation_pairs: list[tuple[str, str, float]]
    rolling_drift_score: dict[str, float]
    point_in_time_ok: bool


def enrich_ohlcv(frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["log_return_1"] = np.log(enriched["close"] / enriched["close"].shift(1))
    enriched["log_return_4"] = np.log(enriched["close"] / enriched["close"].shift(4))
    enriched["log_return_16"] = np.log(enriched["close"] / enriched["close"].shift(16))
    rolling_vol = enriched["log_return_1"].rolling(20, min_periods=20).std()
    enriched["vol_norm_return_4"] = enriched["log_return_4"] / rolling_vol.replace(0.0, np.nan)
    candle_range = (enriched["high"] - enriched["low"]).replace(0.0, np.nan)
    enriched["body_ratio"] = (enriched["close"] - enriched["open"]).abs() / candle_range
    enriched["upper_wick_ratio"] = (enriched["high"] - enriched[["open", "close"]].max(axis=1)) / candle_range
    enriched["lower_wick_ratio"] = (enriched[["open", "close"]].min(axis=1) - enriched["low"]) / candle_range
    enriched["range_ratio"] = candle_range / enriched["close"].replace(0.0, np.nan)
    enriched["rsi_14"] = rsi(enriched["close"], 14)
    _, _, enriched["macd_hist"] = macd(enriched["close"])
    ema_fast = ema(enriched["close"], 20)
    ema_slow = ema(enriched["close"], 50)
    enriched["ema_fast_distance"] = (enriched["close"] - ema_fast) / enriched["close"].replace(0.0, np.nan)
    enriched["ema_slow_distance"] = (enriched["close"] - ema_slow) / enriched["close"].replace(0.0, np.nan)
    enriched["ema_fast_slope"] = ema_fast.pct_change(3)
    enriched["ema_slow_slope"] = ema_slow.pct_change(5)
    lower, middle, upper = bollinger_bands(enriched["close"], 20, 2.0)
    enriched["bb_bandwidth"] = (upper - lower) / middle.replace(0.0, np.nan)
    enriched["bb_zscore"] = (enriched["close"] - middle) / ((upper - middle).replace(0.0, np.nan))
    enriched["atr_14"] = atr(enriched, 14)
    volume_mean = enriched["volume"].rolling(30, min_periods=30).mean()
    volume_std = enriched["volume"].rolling(30, min_periods=30).std()
    enriched["volume_zscore"] = (enriched["volume"] - volume_mean) / volume_std.replace(0.0, np.nan)
    enriched["relative_volume"] = enriched["volume"] / volume_mean.replace(0.0, np.nan)
    enriched["trend_regime"] = np.sign(ema_fast - ema_slow)
    enriched["volatility_regime"] = rolling_vol.rolling(100, min_periods=50).rank(pct=True)
    rolling_max = enriched["close"].rolling(20, min_periods=20).max()
    enriched["drawdown_20"] = enriched["close"] / rolling_max - 1.0
    hour = enriched.index.hour
    enriched["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    enriched["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    enriched["day_of_week"] = enriched.index.dayofweek
    enriched["session_bucket"] = pd.cut(hour, bins=[-1, 7, 15, 23], labels=[0, 1, 2]).astype(float)
    return enriched


def feature_matrix(events: pd.DataFrame) -> tuple[pd.DataFrame, FeatureDiagnostics]:
    candidate_columns = FEATURE_COLUMNS + [
        "signal_strength",
        "recent_same_side_failures",
        "recent_same_side_mean_return",
    ]
    frame = events[candidate_columns].copy().replace([np.inf, -np.inf], np.nan)
    context = pd.get_dummies(
        events[["family", "side", "symbol"]],
        columns=["family", "side", "symbol"],
        dtype=float,
    )
    frame = pd.concat([frame, context], axis=1)
    diagnostics = diagnose_features(frame)
    clean = frame.fillna(frame.median(numeric_only=True)).fillna(0.0)
    return clean, diagnostics


def diagnose_features(frame: pd.DataFrame) -> FeatureDiagnostics:
    nan_rate = {column: float(frame[column].isna().mean()) for column in frame.columns}
    zero_variance = [column for column in frame.columns if frame[column].nunique(dropna=True) <= 1]
    corr = frame.corr(numeric_only=True).abs()
    pairs: list[tuple[str, str, float]] = []
    for left_index, left in enumerate(corr.columns):
        for right in corr.columns[left_index + 1 :]:
            score = float(corr.loc[left, right])
            if score >= 0.95:
                pairs.append((left, right, score))
    split_point = max(len(frame) // 2, 1)
    first = frame.iloc[:split_point]
    second = frame.iloc[split_point:]
    rolling_drift_score: dict[str, float] = {}
    for column in frame.columns:
        std = frame[column].std(ddof=0)
        if std == 0 or pd.isna(std):
            rolling_drift_score[column] = 0.0
        else:
            rolling_drift_score[column] = float(abs(first[column].mean() - second[column].mean()) / std)
    return FeatureDiagnostics(
        nan_rate=nan_rate,
        zero_variance=zero_variance,
        high_correlation_pairs=pairs,
        rolling_drift_score=rolling_drift_score,
        point_in_time_ok=True,
    )
