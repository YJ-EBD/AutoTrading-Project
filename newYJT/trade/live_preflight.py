from __future__ import annotations

import hashlib
import hmac
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, parse_float, resolve_live_mode_flags

SETTINGS_ENV_PATH = ROOT / "settings.env"
ACTIVE_PAIRS_PATH = ROOT / "runtime" / "active_pairs.json"
OUTPUT_PATH = ROOT / "runtime" / "live_preflight.json"

BASE_URL = "https://fapi.binance.com"


def _http_json(url: str, headers: dict[str, str] | None = None, method: str = "GET") -> dict | list:
    request = urllib.request.Request(url, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _signed_request(
    path: str,
    params: dict[str, str | int | float],
    api_key: str,
    secret_key: str,
    method: str = "GET",
) -> dict | list:
    query = urllib.parse.urlencode(params, doseq=True)
    signature = hmac.new(secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}{path}?{query}&signature={signature}"
    return _http_json(url, headers={"X-MBX-APIKEY": api_key}, method=method)


def _public_request(path: str, params: dict[str, str | int | float] | None = None) -> dict | list:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"
    return _http_json(url)


def _load_active_symbols() -> list[str]:
    if not ACTIVE_PAIRS_PATH.exists():
        return []
    try:
        payload = json.loads(ACTIVE_PAIRS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    pairs = payload.get("pairs", [])
    symbols: list[str] = []
    for pair in pairs if isinstance(pairs, list) else []:
        if isinstance(pair, str):
            symbols.append(pair.replace("/USDT:USDT", "USDT").replace("/", ""))
    return symbols


def _quantize_up(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.ceil(value / step) * step


def _fmt_qty(value: float, step: float) -> str:
    step_text = f"{step:.16f}".rstrip("0")
    decimals = len(step_text.split(".")[1]) if "." in step_text else 0
    return f"{value:.{decimals}f}"


def run_preflight() -> dict:
    settings = load_settings_env(SETTINGS_ENV_PATH)
    api_key = settings.get("BINANCE_API_KEY", "").strip()
    secret_key = settings.get("BINANCE_SECRET_KEY", "").strip()
    live_flags = resolve_live_mode_flags(settings)
    live_requested = bool(live_flags["live_requested"])
    order_submission_enabled = bool(live_flags["order_submission_enabled"])
    stake_ratio_pct = max(0.1, min(parse_float(settings.get("DYNAMIC_STAKE_RATIO_PCT"), 10.0), 100.0))

    result: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "skipped",
        "ready_for_live_checks": False,
        "live_requested": live_requested,
        "order_submission_enabled": order_submission_enabled,
        "issues": [],
        "checks": {},
    }

    if not api_key or not secret_key:
        result["issues"].append("BINANCE_API_KEY 또는 BINANCE_SECRET_KEY 가 비어 있습니다.")
        return result

    if not live_requested:
        result["issues"].append("ENABLE_LIVE_TRADING 이 false 여서 live preflight 를 건너뜁니다.")
        return result

    result["ready_for_live_checks"] = True

    try:
        server_time_payload = _public_request("/fapi/v1/time")
        server_time_ms = int(server_time_payload["serverTime"])
        local_time_ms = int(time.time() * 1000)
        offset_ms = server_time_ms - local_time_ms
        result["checks"]["server_time"] = {
            "server_time_ms": server_time_ms,
            "local_time_ms": local_time_ms,
            "offset_ms": offset_ms,
        }

        timestamp = int(time.time() * 1000) + offset_ms
        exchange_info = _public_request("/fapi/v1/exchangeInfo")
        result["checks"]["exchange_info"] = {
            "symbols": len(exchange_info.get("symbols", [])),
            "rate_limits": exchange_info.get("rateLimits", []),
        }

        account = _signed_request("/fapi/v3/account", {"timestamp": timestamp, "recvWindow": 5000}, api_key, secret_key)
        balance_rows = _signed_request("/fapi/v2/balance", {"timestamp": timestamp, "recvWindow": 5000}, api_key, secret_key)
        result["checks"]["account"] = {
            "available_balance": account.get("availableBalance"),
            "total_wallet_balance": account.get("totalWalletBalance"),
            "total_margin_balance": account.get("totalMarginBalance"),
            "positions_count": len(account.get("positions", [])),
        }

        usdt_row = next((row for row in balance_rows if row.get("asset") == "USDT"), None)
        if not usdt_row:
            result["issues"].append("USDT 잔고 행을 찾지 못했습니다.")
            result["status"] = "failed"
            return result

        available_balance = float(usdt_row.get("availableBalance", 0.0))
        dynamic_stake = available_balance * (stake_ratio_pct / 100.0)
        result["checks"]["usdt_balance"] = {
            "available_balance": round(available_balance, 8),
            "dynamic_stake": round(dynamic_stake, 8),
            "stake_ratio_pct": stake_ratio_pct,
        }

        active_symbols = _load_active_symbols()
        prices = _public_request("/fapi/v1/ticker/price")
        price_map = {}
        if isinstance(prices, list):
            price_map = {item["symbol"]: float(item["price"]) for item in prices if "symbol" in item and "price" in item}

        symbol_map = {item["symbol"]: item for item in exchange_info.get("symbols", [])}
        feasible_symbols: list[dict] = []
        blocked_symbols: list[dict] = []

        for symbol in active_symbols:
            info = symbol_map.get(symbol)
            price = price_map.get(symbol)
            if not info or not price:
                blocked_symbols.append({"symbol": symbol, "reason": "missing_exchange_info_or_price"})
                continue

            filters = {flt["filterType"]: flt for flt in info.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            market_lot = filters.get("MARKET_LOT_SIZE", lot)
            min_notional = float(filters.get("MIN_NOTIONAL", {}).get("notional", 0.0))
            min_qty = max(float(lot.get("minQty", 0.0)), float(market_lot.get("minQty", 0.0)))
            step_size = max(float(lot.get("stepSize", 0.0)), float(market_lot.get("stepSize", 0.0)))
            needed_qty = max(min_qty, _quantize_up((min_notional / price) if price > 0 else min_qty, step_size))
            notional = needed_qty * price

            if dynamic_stake + 1e-9 < min_notional:
                blocked_symbols.append(
                    {
                        "symbol": symbol,
                        "reason": "dynamic_stake_below_min_notional",
                        "min_notional": round(min_notional, 8),
                        "dynamic_stake": round(dynamic_stake, 8),
                    }
                )
                continue

            feasible_symbols.append(
                {
                    "symbol": symbol,
                    "price": round(price, 8),
                    "min_notional": round(min_notional, 8),
                    "min_qty": round(needed_qty, 8),
                    "test_order_qty": _fmt_qty(needed_qty, step_size if step_size > 0 else min_qty or 1.0),
                    "estimated_notional": round(notional, 8),
                }
            )

        result["checks"]["pair_feasibility"] = {
            "active_symbol_count": len(active_symbols),
            "feasible_symbol_count": len(feasible_symbols),
            "blocked_symbol_count": len(blocked_symbols),
            "sample_feasible": feasible_symbols[:5],
            "sample_blocked": blocked_symbols[:5],
        }

        if not feasible_symbols:
            result["issues"].append("현재 active pair 중 동적 스테이크로 최소 주문금액을 만족하는 심볼이 없습니다.")
            result["status"] = "failed"
            return result

        candidate = feasible_symbols[0]
        timestamp = int(time.time() * 1000) + offset_ms
        test_order_payload = {
            "symbol": candidate["symbol"],
            "side": "BUY",
            "type": "MARKET",
            "quantity": candidate["test_order_qty"],
            "timestamp": timestamp,
            "recvWindow": 5000,
        }
        _signed_request("/fapi/v1/order/test", test_order_payload, api_key, secret_key, method="POST")
        result["checks"]["test_order"] = {
            "status": "passed",
            "symbol": candidate["symbol"],
            "quantity": candidate["test_order_qty"],
            "estimated_notional": candidate["estimated_notional"],
            "order_submission_enabled": order_submission_enabled,
        }
        result["status"] = "passed"
        return result

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        result["issues"].append(f"HTTPError {exc.code}: {detail}")
        result["status"] = "failed"
        return result
    except Exception as exc:  # noqa: BLE001
        result["issues"].append(str(exc))
        result["status"] = "failed"
        return result


def main() -> None:
    result = run_preflight()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "issues": len(result["issues"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
