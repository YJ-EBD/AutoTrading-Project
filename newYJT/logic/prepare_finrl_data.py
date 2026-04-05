from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import yfinance as yf
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "vendor" / "FinRL-Trading" / "src" / "strategies" / "AdaptiveRotationConf_v1.2.1.yaml"
OUTPUT_DIR = ROOT / "vendor" / "FinRL-Trading" / "data" / "fmp_daily"


def collect_symbols(config: dict) -> list[str]:
    symbols: set[str] = set()

    benchmark = config.get("benchmark", {}).get("excess_return_benchmark")
    if benchmark:
        symbols.add(str(benchmark))

    fallback = config.get("portfolio", {}).get("fallback", {}).get("symbols", [])
    for symbol in fallback:
        symbols.add(str(symbol))

    for group in config.get("asset_groups", {}).values():
        for symbol in group.get("symbols", []):
            symbols.add(str(symbol))

    symbols.update({"^GSPC", "^VIX"})
    return sorted(symbols)


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    renamed = frame.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in renamed.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    cleaned = renamed[required].copy()
    cleaned.index = pd.to_datetime(cleaned.index).tz_localize(None)
    cleaned = cleaned.reset_index().rename(columns={"Date": "date", "index": "date"})
    cleaned["date"] = pd.to_datetime(cleaned["date"]).dt.strftime("%Y-%m-%d")
    return cleaned


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"[prepare-finrl-data] config not found: {CONFIG_PATH}")
        return 1

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    symbols = collect_symbols(config)
    start_date = str(config.get("dates", {}).get("start_date") or "2017-01-01")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[prepare-finrl-data] downloading {len(symbols)} symbols from {start_date} into {OUTPUT_DIR}")

    failures: list[tuple[str, str]] = []
    for symbol in symbols:
        try:
            frame = yf.download(
                symbol,
                start=start_date,
                progress=False,
                auto_adjust=False,
                interval="1d",
                threads=False,
            )
            if frame.empty:
                raise ValueError("empty dataframe returned")
            normalized = normalize_frame(frame)
            output_path = OUTPUT_DIR / f"{symbol}_daily.csv"
            normalized.to_csv(output_path, index=False)
            print(f"[prepare-finrl-data] wrote {symbol} -> {output_path.name} ({len(normalized)} rows)")
        except Exception as exc:  # noqa: BLE001
            failures.append((symbol, str(exc)))
            print(f"[prepare-finrl-data] failed {symbol}: {exc}")

    if failures:
        print("[prepare-finrl-data] completed with failures:")
        for symbol, reason in failures:
            print(f"  - {symbol}: {reason}")
        return 1

    print("[prepare-finrl-data] completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
