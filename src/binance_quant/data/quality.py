from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class QualityReport:
    rows: int
    duplicate_rows: int
    missing_intervals: int
    first_timestamp: str | None
    last_timestamp: str | None
    complete_alignment: bool


def assess_ohlcv_quality(frame: pd.DataFrame, timeframe: str) -> QualityReport:
    if frame.empty:
        return QualityReport(0, 0, 0, None, None, False)
    duplicate_rows = int(frame.index.duplicated().sum())
    freq = timeframe_to_frequency(timeframe)
    expected = pd.date_range(frame.index.min(), frame.index.max(), freq=freq, tz="UTC")
    missing_intervals = len(expected.difference(frame.index))
    return QualityReport(
        rows=len(frame),
        duplicate_rows=duplicate_rows,
        missing_intervals=missing_intervals,
        first_timestamp=frame.index.min().isoformat(),
        last_timestamp=frame.index.max().isoformat(),
        complete_alignment=missing_intervals == 0 and duplicate_rows == 0,
    )


def timeframe_to_frequency(timeframe: str) -> str:
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return mapping[timeframe]
