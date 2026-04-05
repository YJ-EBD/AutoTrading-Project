from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "vendor" / "binance-anthropic-trading-bot"
ACTIVE_PAIRS_PATH = ROOT / "runtime" / "active_pairs.json"
LLM_CONFIG_PATH = ROOT / "runtime" / "llm" / "config.json"
OUTPUT_DIR = ROOT / "runtime" / "benchmarks" / "llm"

if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from trading_bot import TradingBot  # type: ignore  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _pair_to_symbol(pair: str) -> str:
    base, quote = pair.split("/", 1)
    quote = quote.split(":", 1)[0]
    return f"{base}{quote}"


def _pattern_bias(patterns: list[Any]) -> str:
    if not patterns:
        return "HOLD"
    top_pattern = max(patterns, key=lambda pattern: float(getattr(pattern, "confidence", 0.0)))
    direction = str(getattr(top_pattern, "direction", "")).lower()
    if direction == "bullish":
        return "BUY"
    if direction == "bearish":
        return "SELL"
    return "HOLD"


def _latency_summary(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"avg_seconds": 0.0, "median_seconds": 0.0, "p95_seconds": 0.0}
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * 0.95)))
    return {
        "avg_seconds": round(sum(samples) / len(samples), 4),
        "median_seconds": round(statistics.median(samples), 4),
        "p95_seconds": round(ordered[p95_index], 4),
    }


def benchmark_model(model_name: str, symbols: list[str]) -> dict[str, Any]:
    config = _load_json(LLM_CONFIG_PATH)
    if not config:
        raise RuntimeError(f"missing config: {LLM_CONFIG_PATH}")

    config["llm_provider"] = "ollama"
    config["llm_model"] = model_name
    config["llm_market_type"] = "futures"
    bot = TradingBot(config)

    records: list[dict[str, Any]] = []
    latencies: list[float] = []
    valid_count = 0
    agreement_count = 0
    agreement_candidates = 0

    for symbol in symbols:
        pair_started = time.perf_counter()
        market_data, historical_data = bot.get_market_data(symbol)
        if not market_data or historical_data is None:
            records.append(
                {
                    "symbol": symbol,
                    "status": "error",
                    "error": "market_data_unavailable",
                }
            )
            continue

        patterns = bot.pattern_analyzer.analyze_patterns(historical_data)
        pattern_signal = bot.pattern_analyzer.get_trading_signal(patterns, current_position=False)
        bias_signal = _pattern_bias(patterns)

        llm_started = time.perf_counter()
        llm_signal = bot.ask_llm(symbol, market_data, patterns)
        llm_latency = time.perf_counter() - llm_started
        latencies.append(llm_latency)

        if llm_signal in {"BUY", "SELL", "HOLD"}:
            valid_count += 1
        if bias_signal in {"BUY", "SELL"}:
            agreement_candidates += 1
            if llm_signal == bias_signal:
                agreement_count += 1

        records.append(
            {
                "symbol": symbol,
                "status": "ok",
                "pattern_count": len(patterns),
                "pattern_signal": pattern_signal,
                "pattern_bias": bias_signal,
                "llm_signal": llm_signal,
                "llm_latency_seconds": round(llm_latency, 4),
                "total_pair_seconds": round(time.perf_counter() - pair_started, 4),
            }
        )

    buys = sum(1 for record in records if record.get("llm_signal") == "BUY")
    sells = sum(1 for record in records if record.get("llm_signal") == "SELL")
    holds = sum(1 for record in records if record.get("llm_signal") == "HOLD")
    total = len(records)
    valid_rate = (valid_count / total) if total else 0.0
    agreement_rate = (agreement_count / agreement_candidates) if agreement_candidates else 0.0

    summary = {
        "model": model_name,
        "evaluated_symbols": len(symbols),
        "successful_symbols": sum(1 for record in records if record.get("status") == "ok"),
        "valid_rate": round(valid_rate, 4),
        "agreement_rate_on_directional_patterns": round(agreement_rate, 4),
        "latency": _latency_summary(latencies),
        "signals": {
            "buy": buys,
            "sell": sells,
            "hold": holds,
        },
        "records": records,
    }
    return summary


def _rank_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        return []

    fastest_median = min(result["latency"]["median_seconds"] or 1e-9 for result in results if result["latency"]["median_seconds"] >= 0)
    ranked: list[dict[str, Any]] = []
    for result in results:
        median_seconds = result["latency"]["median_seconds"] or 9999.0
        speed_score = (fastest_median / median_seconds) if median_seconds > 0 else 1.0
        composite_score = (
            (result["valid_rate"] * 0.45)
            + (result["agreement_rate_on_directional_patterns"] * 0.35)
            + (speed_score * 0.20)
        )
        ranked.append(
            {
                **result,
                "speed_score": round(speed_score, 4),
                "composite_score": round(composite_score, 4),
            }
        )
    ranked.sort(key=lambda item: item["composite_score"], reverse=True)
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["deepseek-r1:8b", "qwen3:8b"])
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()

    active_pairs = _load_json(ACTIVE_PAIRS_PATH).get("pairs", [])
    if not isinstance(active_pairs, list) or not active_pairs:
        raise RuntimeError(f"no active pairs found in {ACTIVE_PAIRS_PATH}")

    symbols = [_pair_to_symbol(pair) for pair in active_pairs[: max(1, args.limit)]]
    results = [benchmark_model(model_name, symbols) for model_name in args.models]
    ranked = _rank_results(results)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "symbols": symbols,
        "ranked_results": ranked,
        "selected_model": ranked[0]["model"] if ranked else None,
        "selection_method": "0.45*valid_rate + 0.35*directional_pattern_agreement + 0.20*speed_score",
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = OUTPUT_DIR / "latest.json"
    latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
