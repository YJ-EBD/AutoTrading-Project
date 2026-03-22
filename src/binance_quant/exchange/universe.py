from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..config import Settings
from ..utils import dump_json, utc_now
from .client import BinancePublicClient
from .models import SymbolRecord


LOGGER = logging.getLogger(__name__)


class UniverseManager:
    def __init__(self, settings: Settings, client: BinancePublicClient):
        self.settings = settings
        self.client = client

    def discover(self, artifact_dir: Path | None = None) -> pd.DataFrame:
        exchange_info = self.client.get_json(
            "/fapi/v1/exchangeInfo",
            bucket="metadata",
            weight=1,
            cache_namespace="exchange",
            cache_key="exchangeInfo",
            ttl_seconds=self.settings.exchange.exchange_info_ttl_minutes * 60,
        )
        tickers = self.client.get_json(
            "/fapi/v1/ticker/24hr",
            bucket="metadata",
            weight=40,
            cache_namespace="exchange",
            cache_key="ticker24hr_all",
            ttl_seconds=self.settings.exchange.ticker_ttl_minutes * 60,
        )
        ticker_map = {item["symbol"]: item for item in tickers}
        records: list[SymbolRecord] = []

        for item in exchange_info["symbols"]:
            symbol = item["symbol"]
            ticker = ticker_map.get(symbol, {})
            record = SymbolRecord.from_payload(item, ticker)
            eligible, reason = self._is_eligible(record)
            records.append(
                SymbolRecord(
                    **{
                        **asdict(record),
                        "eligible": eligible,
                        "rejection_reason": reason,
                    }
                )
            )

        if not records:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "base_asset",
                    "contract_type",
                    "quote_asset",
                    "status",
                    "onboard_date",
                    "price_precision",
                    "quantity_precision",
                    "quote_volume_24h",
                    "last_price",
                    "eligible",
                    "rejection_reason",
                ]
            )

        frame = pd.DataFrame(asdict(record) for record in records).sort_values(
            by=["eligible", "quote_volume_24h"], ascending=[False, False]
        )
        eligible = frame[frame["eligible"]].copy()
        if self.settings.universe.unique_base_assets_only:
            eligible = eligible.drop_duplicates(subset=["base_asset"], keep="first")
        selected = eligible.head(self.settings.universe.max_symbols).copy()
        selected["selected_at"] = utc_now().isoformat()
        LOGGER.info("Universe discovery found %s eligible symbols", len(selected))

        if artifact_dir is not None:
            universe_dir = artifact_dir / "universe"
            universe_dir.mkdir(parents=True, exist_ok=True)
            frame.to_csv(universe_dir / "universe_full.csv", index=False)
            selected.to_csv(universe_dir / "universe_selected.csv", index=False)
            dump_json(
                universe_dir / "exchange_metadata_snapshot.json",
                {
                    "server_time": exchange_info.get("serverTime"),
                    "rate_limits": exchange_info.get("rateLimits", []),
                    "exchange_filters": exchange_info.get("exchangeFilters", []),
                },
            )
        return selected.reset_index(drop=True)

    def _is_eligible(self, record: SymbolRecord) -> tuple[bool, str | None]:
        now = datetime.now(UTC)
        if record.symbol in self.settings.universe.exclude_symbols:
            return False, "manually_excluded"
        if self.settings.universe.include_symbols and record.symbol not in self.settings.universe.include_symbols:
            return False, "not_in_include_list"
        if record.status != "TRADING":
            return False, "status_not_trading"
        if record.quote_asset not in self.settings.universe.allowed_quote_assets:
            return False, "quote_asset_not_allowed"
        if record.contract_type not in self.settings.universe.allowed_contract_types:
            return False, "contract_type_not_allowed"
        history_days = (now - record.onboard_date).days
        if history_days < self.settings.universe.min_history_days:
            return False, "insufficient_history"
        if record.quote_volume_24h < self.settings.universe.min_24h_quote_volume_usd:
            return False, "insufficient_quote_volume"
        if record.last_price < self.settings.universe.min_last_price:
            return False, "price_floor"
        return True, None
