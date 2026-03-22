from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class SymbolRecord:
    symbol: str
    base_asset: str
    contract_type: str
    quote_asset: str
    status: str
    onboard_date: datetime
    price_precision: int
    quantity_precision: int
    quote_volume_24h: float
    last_price: float
    eligible: bool
    rejection_reason: str | None = None

    @classmethod
    def from_payload(cls, exchange_symbol: dict[str, Any], ticker: dict[str, Any]) -> "SymbolRecord":
        return cls(
            symbol=exchange_symbol["symbol"],
            base_asset=exchange_symbol["baseAsset"],
            contract_type=exchange_symbol["contractType"],
            quote_asset=exchange_symbol["quoteAsset"],
            status=exchange_symbol["status"],
            onboard_date=datetime.fromtimestamp(exchange_symbol["onboardDate"] / 1000, tz=UTC),
            price_precision=int(exchange_symbol["pricePrecision"]),
            quantity_precision=int(exchange_symbol["quantityPrecision"]),
            quote_volume_24h=float(ticker.get("quoteVolume", 0.0)),
            last_price=float(ticker.get("lastPrice", 0.0)),
            eligible=False,
        )
