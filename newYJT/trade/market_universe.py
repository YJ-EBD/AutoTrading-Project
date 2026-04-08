from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from logic.settings_env import load_settings_env, parse_bool, parse_float

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PAIR_SCORES_PATH = ROOT / "runtime" / "active_pair_scores.json"
FUTURES_TICKER_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
ANCHOR_PAIRS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "BNB/USDT:USDT",
]


def _load_universe_thresholds() -> dict[str, float | bool]:
    settings = load_settings_env(ROOT / "settings.env")
    return {
        "min_quote_volume_usdt": max(0.0, parse_float(settings.get("UNIVERSE_MIN_QUOTE_VOLUME_USDT"), 25_000_000.0)),
        "min_trade_count_24h": max(0.0, parse_float(settings.get("UNIVERSE_MIN_24H_TRADES"), 300_000.0)),
        "min_quality_score": max(0.0, min(parse_float(settings.get("UNIVERSE_MIN_QUALITY_SCORE"), 0.60), 1.0)),
        "min_price": max(0.0, parse_float(settings.get("UNIVERSE_MIN_PRICE"), 0.10)),
        "min_intraday_range_pct": max(0.0, parse_float(settings.get("UNIVERSE_MIN_INTRADAY_RANGE_PCT"), 2.0)),
        "max_intraday_range_pct": max(0.0, parse_float(settings.get("UNIVERSE_MAX_INTRADAY_RANGE_PCT"), 14.0)),
        "max_abs_change_pct": max(0.0, parse_float(settings.get("UNIVERSE_MAX_ABS_CHANGE_PCT"), 18.0)),
        "prefer_anchor_pairs": parse_bool(settings.get("UNIVERSE_PREFER_ANCHOR_PAIRS"), True),
    }


def _pair_to_symbol(pair: str) -> str:
    base, quote = pair.split("/", 1)
    quote = quote.split(":", 1)[0]
    return f"{base}{quote}"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fetch_futures_ticker_snapshot() -> dict[str, dict]:
    request = urllib.request.Request(
        FUTURES_TICKER_24H_URL,
        headers={"Accept": "application/json", "User-Agent": "newYJT-market-universe"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {str(item.get("symbol")): item for item in payload if isinstance(item, dict)}


def _minmax_scale(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return [1.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _bounded_score(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 1.0
    if value < lower:
        return max(0.0, value / max(lower, 1e-9))
    if value > upper:
        if value <= 0:
            return 0.0
        return max(0.0, upper / value)
    midpoint = (lower + upper) / 2.0
    half_span = max((upper - lower) / 2.0, 1e-9)
    return max(0.0, 1.0 - abs(value - midpoint) / half_span)


def select_dynamic_active_pairs(
    resolved_pairs: list[str],
    *,
    min_pairs: int = 2,
    max_pairs: int = 24,
    excluded_bases: set[str] | None = None,
) -> dict:
    min_pairs = max(2, min(int(min_pairs), 30))
    max_pairs = max(min_pairs, min(int(max_pairs), 30))
    excluded_bases = excluded_bases or set()
    thresholds = _load_universe_thresholds()
    min_quote_volume_usdt = float(thresholds["min_quote_volume_usdt"])
    min_trade_count_24h = float(thresholds["min_trade_count_24h"])
    min_quality_score = float(thresholds["min_quality_score"])
    min_price = float(thresholds["min_price"])
    min_intraday_range_pct = float(thresholds["min_intraday_range_pct"])
    max_intraday_range_pct = float(thresholds["max_intraday_range_pct"])
    max_abs_change_pct = float(thresholds["max_abs_change_pct"])
    prefer_anchor_pairs = bool(thresholds["prefer_anchor_pairs"])

    candidates = []
    for pair in resolved_pairs:
        base = pair.split("/", 1)[0]
        if not base.isascii() or base in excluded_bases:
            continue
        if len(base) < 3 and pair not in ANCHOR_PAIRS:
            continue
        candidates.append(pair)

    try:
        snapshot = _fetch_futures_ticker_snapshot()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        snapshot = {}

    scored_rows: list[dict] = []
    for pair in candidates:
        symbol = _pair_to_symbol(pair)
        ticker = snapshot.get(symbol)
        if not ticker:
            continue
        last_price = max(_safe_float(ticker.get("lastPrice")), 1e-12)
        quote_volume = max(_safe_float(ticker.get("quoteVolume")), 0.0)
        trade_count = max(_safe_float(ticker.get("count")), 0.0)
        change_pct = abs(_safe_float(ticker.get("priceChangePercent")))
        high_price = _safe_float(ticker.get("highPrice"), last_price)
        low_price = _safe_float(ticker.get("lowPrice"), last_price)
        intraday_range_pct = max((high_price - low_price) / last_price * 100.0, 0.0)

        if last_price < min_price:
            continue
        if change_pct > max_abs_change_pct:
            continue
        if intraday_range_pct < min_intraday_range_pct or intraday_range_pct > max_intraday_range_pct:
            continue

        scored_rows.append(
            {
                "pair": pair,
                "symbol": symbol,
                "last_price": last_price,
                "quote_volume_usdt": quote_volume,
                "trade_count": trade_count,
                "abs_change_pct": change_pct,
                "intraday_range_pct": intraday_range_pct,
            }
        )

    if not scored_rows:
        selected_pairs = candidates[:min_pairs]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selection_source": "resolved_pairlist_fallback",
            "selected_count": len(selected_pairs),
            "selected_pairs": selected_pairs,
            "ranked_pairs": [{"pair": pair, "quality_score": None} for pair in candidates[:max_pairs]],
        }
        ACTIVE_PAIR_SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PAIR_SCORES_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    liquidity_scores = _minmax_scale([math.log1p(row["quote_volume_usdt"]) for row in scored_rows])
    activity_scores = _minmax_scale([math.log1p(row["trade_count"]) for row in scored_rows])

    for index, row in enumerate(scored_rows):
        volatility_score = _bounded_score(
            row["abs_change_pct"],
            max(1.5, min_intraday_range_pct),
            max(6.0, min(max_abs_change_pct, 12.0)),
        )
        range_score = _bounded_score(
            row["intraday_range_pct"],
            min_intraday_range_pct,
            max_intraday_range_pct,
        )
        row["liquidity_score"] = round(liquidity_scores[index], 4)
        row["activity_score"] = round(activity_scores[index], 4)
        row["volatility_score"] = round(volatility_score, 4)
        row["range_score"] = round(range_score, 4)
        row["quality_score"] = round(
            (row["liquidity_score"] * 0.55)
            + (row["activity_score"] * 0.25)
            + (row["volatility_score"] * 0.10)
            + (row["range_score"] * 0.10),
            4,
        )

    ranked_pairs = sorted(
        scored_rows,
        key=lambda row: (
            row["quality_score"],
            row["quote_volume_usdt"],
            row["trade_count"],
        ),
        reverse=True,
    )

    quality_candidates = [
        row
        for row in ranked_pairs
        if row["quality_score"] >= min_quality_score
        and row["quote_volume_usdt"] >= min_quote_volume_usdt
        and row["trade_count"] >= min_trade_count_24h
    ]
    dynamic_target = max(min_pairs, min(max_pairs, len(quality_candidates) or min_pairs))
    selected_pairs: list[str] = []
    available_pairs = {row["pair"] for row in ranked_pairs}
    if prefer_anchor_pairs:
        for anchor in ANCHOR_PAIRS:
            if anchor in available_pairs and anchor not in selected_pairs:
                selected_pairs.append(anchor)
    for row in ranked_pairs:
        if row["pair"] not in selected_pairs:
            selected_pairs.append(row["pair"])
        if len(selected_pairs) >= dynamic_target:
            break

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_source": "binance_futures_24h_ticker",
        "candidate_count": len(candidates),
        "scored_candidate_count": len(scored_rows),
        "selected_count": len(selected_pairs),
        "min_pairs": min_pairs,
        "max_pairs": max_pairs,
        "thresholds": thresholds,
        "selected_pairs": selected_pairs,
        "ranked_pairs": ranked_pairs[:max_pairs],
    }
    ACTIVE_PAIR_SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_PAIR_SCORES_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
