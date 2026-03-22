from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings
from ..utils import dump_json
from .quality import assess_ohlcv_quality, timeframe_to_frequency
from ..exchange.client import BinancePublicClient


LOGGER = logging.getLogger(__name__)


class KlineIngestionService:
    KLINE_COLUMNS = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]

    def __init__(self, settings: Settings, client: BinancePublicClient):
        self.settings = settings
        self.client = client

    def backfill_symbol(self, symbol: str, artifact_dir: Path | None = None) -> pd.DataFrame:
        timeframe = self.settings.data.timeframe
        path = self.market_data_path(symbol, timeframe)
        existing = self._load_existing(path)
        start_time = self._determine_start_time(existing)
        end_time = datetime.now(UTC)
        all_parts: list[pd.DataFrame] = [existing] if not existing.empty else []

        while start_time < end_time:
            chunk_end = min(start_time + timedelta(days=self.settings.data.chunk_days), end_time)
            payload = self.client.get_json(
                "/fapi/v1/klines",
                params={
                    "symbol": symbol,
                    "interval": timeframe,
                    "startTime": int(start_time.timestamp() * 1000),
                    "endTime": int(chunk_end.timestamp() * 1000),
                    "limit": self.settings.exchange.kline_request_limit,
                },
                bucket="market_data",
                weight=5,
            )
            if not payload:
                start_time = chunk_end
                continue
            part = self._normalize(payload)
            all_parts.append(part)
            last_open_time = part.index.max().to_pydatetime()
            start_time = last_open_time + pd.Timedelta(timeframe_to_frequency(timeframe))

        combined = (
            pd.concat(all_parts)
            .sort_index()
            .loc[lambda frame: ~frame.index.duplicated(keep="last")]
        )
        quality = assess_ohlcv_quality(combined, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(path, compression=self.settings.data.parquet_compression)

        if artifact_dir is not None:
            quality_dir = artifact_dir / "data_quality"
            quality_dir.mkdir(parents=True, exist_ok=True)
            dump_json(quality_dir / f"{symbol}_{timeframe}.json", quality.__dict__)
        return combined

    def backfill_many(self, symbols: list[str], artifact_dir: Path | None = None) -> dict[str, pd.DataFrame]:
        return {symbol: self.backfill_symbol(symbol, artifact_dir=artifact_dir) for symbol in symbols}

    def market_data_path(self, symbol: str, timeframe: str) -> Path:
        return self.settings.market_data_root / "klines" / timeframe / f"{symbol}.parquet"

    def _load_existing(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        frame = pd.read_parquet(path)
        frame.index = pd.DatetimeIndex(frame.index, tz="UTC")
        return frame.sort_index()

    def _determine_start_time(self, existing: pd.DataFrame) -> datetime:
        if existing.empty:
            return datetime.now(UTC) - timedelta(days=self.settings.data.backfill_days)
        return existing.index.max().to_pydatetime() + pd.Timedelta(timeframe_to_frequency(self.settings.data.timeframe))

    def _normalize(self, payload: list[list[Any]]) -> pd.DataFrame:
        frame = pd.DataFrame(payload, columns=self.KLINE_COLUMNS)
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
        for column in numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="coerce").astype("Int64")
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
        frame = frame.set_index("open_time").drop(columns=["ignore"])
        return frame
