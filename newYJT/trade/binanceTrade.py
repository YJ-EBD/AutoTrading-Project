"""
binance_futures_console_fixed.py

수정 사항:
- Binance signature 생성/전송 방식 수정
- 서명한 query string 그대로 전송하도록 변경
- 입력값 검증 강화
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).with_suffix(".config.json")
SETTINGS_ENV_PATH = ROOT / "settings.env"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, parse_bool, parse_float, resolve_live_mode_flags


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def now_ms() -> int:
    return int(time.time() * 1000)


def round_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value // step) * step


def quantize_by_step_str(value: Decimal, step_str: str) -> str:
    step = dec(step_str)
    rounded = round_step(value, step)
    exponent = abs(step.as_tuple().exponent)
    return f"{rounded:.{exponent}f}"


def pretty(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def input_default(prompt: str, default: Optional[str] = None) -> str:
    if default is None or default == "":
        return input(f"{prompt}: ").strip()
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def input_bool(prompt: str, default: bool = True) -> bool:
    guide = "Y/n" if default else "y/N"
    raw = input(f"{prompt} ({guide}): ").strip().lower()
    if raw == "":
        return default
    return raw in ("y", "yes", "1", "true")


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class SymbolRules:
    symbol: str
    tick_size: str
    step_size: str
    market_step_size: str
    min_qty: str
    min_notional: str
    trigger_protect: str


@dataclass
class RuntimeTradeSettings:
    live_requested: bool
    order_submission_requested: bool
    block_real_order_submission: bool
    allow_mutating_requests: bool
    dynamic_stake_ratio_pct: float
    default_leverage: int
    default_stop_loss_pct: float
    default_take_profit_pct: float
    testnet: bool


def load_runtime_trade_settings(path: Path = SETTINGS_ENV_PATH) -> RuntimeTradeSettings:
    env = load_settings_env(path)
    live_flags = resolve_live_mode_flags(env)
    live_requested = bool(live_flags["live_requested"])
    order_submission_requested = bool(live_flags["order_submission_requested"])
    block_real_order_submission = bool(live_flags["block_real_order_submission"])
    allow_mutating_requests = bool(live_flags["allow_mutating_requests"])
    return RuntimeTradeSettings(
        live_requested=live_requested,
        order_submission_requested=order_submission_requested,
        block_real_order_submission=block_real_order_submission,
        allow_mutating_requests=allow_mutating_requests,
        dynamic_stake_ratio_pct=max(0.1, min(parse_float(env.get("DYNAMIC_STAKE_RATIO_PCT"), 10.0), 100.0)),
        default_leverage=max(1, int(parse_float(env.get("DEFAULT_LEVERAGE"), 1.0))),
        default_stop_loss_pct=max(0.1, parse_float(env.get("DEFAULT_STOP_LOSS_PCT"), 5.0)),
        default_take_profit_pct=max(0.1, parse_float(env.get("DEFAULT_TAKE_PROFIT_PCT"), 4.0)),
        testnet=parse_bool(env.get("BINANCE_USE_TESTNET"), False),
    )


def create_client_from_settings_env(path: Path = SETTINGS_ENV_PATH) -> tuple["BinanceFuturesClient", RuntimeTradeSettings]:
    env = load_settings_env(path)
    api_key = env.get("BINANCE_API_KEY", "").strip()
    api_secret = env.get("BINANCE_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("settings.env 에 BINANCE_API_KEY 와 BINANCE_SECRET_KEY 가 필요합니다.")
    runtime = load_runtime_trade_settings(path)
    client = BinanceFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=runtime.testnet,
        allow_mutating_requests=runtime.allow_mutating_requests,
    )
    return client, runtime


class BinanceFuturesClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        recv_window: int = 5000,
        timeout: int = 20,
        allow_mutating_requests: bool = False,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.recv_window = recv_window
        self.timeout = timeout
        self.base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        self.allow_mutating_requests = allow_mutating_requests
        self.time_offset_ms = 0
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": api_key})

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        method = method.upper()

        if method in {"POST", "PUT", "PATCH", "DELETE"} and not self.allow_mutating_requests and path != "/fapi/v1/order/test":
            return {
                "blocked": True,
                "method": method,
                "path": path,
                "params": params,
                "reason": "Real order submission is disabled by runtime flags",
            }

        if signed:
            if self.time_offset_ms == 0:
                self.sync_time()
            params["timestamp"] = now_ms() + self.time_offset_ms
            params["recvWindow"] = self.recv_window
            query_string = urlencode(params, doseq=True)
            signature = hmac.new(self.api_secret, query_string.encode("utf-8"), hashlib.sha256).hexdigest()
            payload = f"{query_string}&signature={signature}"
        else:
            payload = urlencode(params, doseq=True)

        url = f"{self.base_url}{path}"

        if method == "GET":
            final_url = f"{url}?{payload}" if payload else url
            resp = self.session.get(final_url, timeout=self.timeout)
        else:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            resp = self.session.request(method=method, url=url, data=payload, headers=headers, timeout=self.timeout)

        try:
            data = resp.json()
        except Exception:
            data = {"status_code": resp.status_code, "text": resp.text}

        if resp.status_code == 400 and isinstance(data, dict) and data.get("code") == -1021 and signed:
            self.sync_time()
            retry_params = dict(params)
            retry_params.pop("timestamp", None)
            retry_params.pop("recvWindow", None)
            return self._request(method, path, retry_params, signed=True)

        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {json.dumps(data, ensure_ascii=False)}")
        return data

    def ping(self) -> Any:
        return self._request("GET", "/fapi/v1/ping")

    def sync_time(self) -> int:
        payload = self._request("GET", "/fapi/v1/time")
        server_time = int(payload["serverTime"])
        self.time_offset_ms = server_time - now_ms()
        return self.time_offset_ms

    def exchange_info(self) -> Any:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def account_info_v3(self) -> Any:
        return self._request("GET", "/fapi/v3/account", signed=True)

    def balance_v2(self) -> Any:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def open_orders(self, symbol: Optional[str] = None) -> Any:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    def mark_price(self, symbol: str) -> Any:
        return self._request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol.upper()})

    def set_leverage(self, symbol: str, leverage: int) -> Any:
        return self._request("POST", "/fapi/v1/leverage", {"symbol": symbol.upper(), "leverage": leverage}, signed=True)

    def new_order(self, **params: Any) -> Any:
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def new_algo_order(self, **params: Any) -> Any:
        return self._request("POST", "/fapi/v1/algoOrder", params, signed=True)

    def cancel_all_algo_orders(self, symbol: str) -> Any:
        return self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol.upper()}, signed=True)

    def position_risk(self, symbol: Optional[str] = None) -> Any:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._request("GET", "/fapi/v3/positionRisk", params, signed=True)

    def user_trades(self, symbol: str, start_time: Optional[int] = None, end_time: Optional[int] = None, limit: int = 1000) -> Any:
        params: Dict[str, Any] = {"symbol": symbol.upper(), "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self._request("GET", "/fapi/v1/userTrades", params, signed=True)

    def symbol_rules(self, symbol: str) -> SymbolRules:
        symbol = symbol.upper()
        info = self.exchange_info()
        target = next((s for s in info["symbols"] if s["symbol"] == symbol), None)
        if not target:
            raise RuntimeError(f"Unknown symbol: {symbol}")
        filters = {f["filterType"]: f for f in target["filters"]}
        return SymbolRules(
            symbol=symbol,
            tick_size=filters["PRICE_FILTER"]["tickSize"],
            step_size=filters["LOT_SIZE"]["stepSize"],
            market_step_size=filters.get("MARKET_LOT_SIZE", filters["LOT_SIZE"])["stepSize"],
            min_qty=filters["LOT_SIZE"]["minQty"],
            min_notional=filters.get("MIN_NOTIONAL", {}).get("notional", "0"),
            trigger_protect=target.get("triggerProtect", "0"),
        )


class AppState:
    def __init__(self) -> None:
        self.client: Optional[BinanceFuturesClient] = None
        self.position_opened_at: Dict[str, int] = {}
        self.entry_orders: Dict[str, Any] = {}
        self.protection_orders: Dict[str, Any] = {}
        self.last_close_summary: Dict[str, Any] = {}


STATE = AppState()


def require_client() -> BinanceFuturesClient:
    if STATE.client is None:
        raise RuntimeError("먼저 1번 설정/연결을 실행하세요.")
    return STATE.client


def infer_exit_side(entry_side: str) -> str:
    return "SELL" if entry_side.upper() == "BUY" else "BUY"


def safe_avg_fill_price(order: Dict[str, Any], fallback_mark_price: str) -> str:
    avg_price = str(order.get("avgPrice", "0"))
    if dec(avg_price) > 0:
        return avg_price
    cum_quote = dec(order.get("cumQuote", "0"))
    executed_qty = dec(order.get("executedQty", "0"))
    if executed_qty > 0 and cum_quote > 0:
        return str(cum_quote / executed_qty)
    return fallback_mark_price


def summarize_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    realized = sum(dec(t.get("realizedPnl", "0")) for t in trades)
    commission = sum(dec(t.get("commission", "0")) for t in trades)
    qty = sum(dec(t.get("qty", "0")) for t in trades)
    quote_qty = sum(dec(t.get("quoteQty", "0")) for t in trades)
    return {
        "result": "WIN" if realized > 0 else "LOSS" if realized < 0 else "BREAKEVEN",
        "trade_count": len(trades),
        "total_realized_pnl": str(realized),
        "total_commission": str(commission),
        "total_qty": str(qty),
        "total_quote_qty": str(quote_qty),
        "first_trade_time": trades[0]["time"] if trades else None,
        "last_trade_time": trades[-1]["time"] if trades else None,
        "trades": trades,
    }


def setup_client() -> None:
    cfg = load_config()
    default_key = cfg.get("api_key", "")
    default_testnet = bool(cfg.get("testnet", True))

    print("\n[설정/연결]")
    api_key = input_default("API Key", default_key)
    api_secret = getpass.getpass("API Secret(입력 숨김): ").strip()
    if not api_secret and cfg.get("api_secret"):
        api_secret = cfg["api_secret"]

    runtime_settings = load_runtime_trade_settings() if SETTINGS_ENV_PATH.exists() else None
    default_allow_mutating = bool(runtime_settings.allow_mutating_requests) if runtime_settings else False
    default_testnet = bool(runtime_settings.testnet) if runtime_settings else default_testnet

    testnet = input_bool("Testnet 사용", default_testnet)
    allow_mutating_requests = input_bool("실제 주문 허용", default_allow_mutating)

    client = BinanceFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        allow_mutating_requests=allow_mutating_requests,
    )
    client.ping()
    STATE.client = client

    print("연결 성공")
    pretty({
        "testnet": testnet,
        "allow_mutating_requests": allow_mutating_requests,
    })
    if input_bool("이 설정을 로컬 파일에 저장", True):
        save_config({
            "api_key": api_key,
            "api_secret": api_secret,
            "testnet": testnet,
            "allow_mutating_requests": allow_mutating_requests,
        })
        print(f"저장 완료: {CONFIG_PATH}")


def normalize_working_type(raw: str) -> str:
    value = raw.strip().upper()
    aliases = {
        "MARKET_PRICE": "MARK_PRICE",
        "MARKPRICE": "MARK_PRICE",
        "CONTRACT": "CONTRACT_PRICE",
        "LAST_PRICE": "CONTRACT_PRICE",
    }
    value = aliases.get(value, value)
    if value not in ("MARK_PRICE", "CONTRACT_PRICE"):
        raise RuntimeError("트리거 기준은 MARK_PRICE 또는 CONTRACT_PRICE만 가능합니다.")
    return value


def enter_position() -> None:
    client = require_client()
    print("\n[포지션 진입]")
    symbol = input_default("심볼", "BTCUSDT").upper()
    side = input_default("방향(BUY/SELL)", "BUY").upper()
    if side not in ("BUY", "SELL"):
        raise RuntimeError("방향은 BUY 또는 SELL만 가능합니다.")

    quantity = dec(input_default("수량", "0.001"))
    order_type = input_default("주문타입(MARKET/LIMIT)", "MARKET").upper()
    if order_type not in ("MARKET", "LIMIT"):
        raise RuntimeError("주문타입은 MARKET 또는 LIMIT만 가능합니다.")

    limit_price = None
    if order_type == "LIMIT":
        limit_price = dec(input_default("지정가", "0"))
    leverage = int(input_default("레버리지", "10"))
    tp_raw = input_default("TP 가격(없으면 엔터)", "")
    sl_raw = input_default("SL 가격(없으면 엔터)", "")
    working_type = normalize_working_type(input_default("트리거 기준(MARK_PRICE/CONTRACT_PRICE)", "MARK_PRICE"))
    price_protect = input_bool("Price Protect 사용", False)

    rules = client.symbol_rules(symbol)
    client.set_leverage(symbol, leverage)

    qty_step = rules.market_step_size if order_type == "MARKET" else rules.step_size
    quantity_str = quantize_by_step_str(quantity, qty_step)
    if dec(quantity_str) < dec(rules.min_qty):
        raise RuntimeError(f"Quantity below minQty: {rules.min_qty}")

    order_params: Dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity_str,
        "newOrderRespType": "RESULT",
    }

    if order_type == "LIMIT":
        if limit_price is None or limit_price <= 0:
            raise RuntimeError("LIMIT 주문은 지정가가 필요합니다.")
        order_params["timeInForce"] = "GTC"
        order_params["price"] = quantize_by_step_str(limit_price, rules.tick_size)

    entry = client.new_order(**order_params)
    mark = client.mark_price(symbol)
    avg_fill_price = safe_avg_fill_price(entry, mark["markPrice"])
    protections: Dict[str, Any] = {}
    exit_side = infer_exit_side(side)

    if tp_raw:
        tp_price = dec(tp_raw)
        protections["tp"] = client.new_algo_order(
            algoType="CONDITIONAL",
            symbol=symbol,
            side=exit_side,
            type="TAKE_PROFIT_MARKET",
            triggerPrice=quantize_by_step_str(tp_price, rules.tick_size),
            workingType=working_type,
            closePosition="true",
            priceProtect="TRUE" if price_protect else "FALSE",
        )

    if sl_raw:
        sl_price = dec(sl_raw)
        protections["sl"] = client.new_algo_order(
            algoType="CONDITIONAL",
            symbol=symbol,
            side=exit_side,
            type="STOP_MARKET",
            triggerPrice=quantize_by_step_str(sl_price, rules.tick_size),
            workingType=working_type,
            closePosition="true",
            priceProtect="TRUE" if price_protect else "FALSE",
        )

    STATE.position_opened_at[symbol] = now_ms()
    STATE.entry_orders[symbol] = entry
    STATE.protection_orders[symbol] = protections

    print("\n진입 완료")
    pretty({
        "symbol": symbol,
        "entry_order": entry,
        "entry_avg_fill_price": avg_fill_price,
        "mark_price_at_entry": mark["markPrice"],
        "protection_orders": protections,
    })


def get_position() -> None:
    client = require_client()
    print("\n[포지션 조회]")
    symbol = input_default("심볼", "BTCUSDT").upper()

    positions = client.position_risk(symbol)
    position = next((p for p in positions if p["symbol"] == symbol), None) if isinstance(positions, list) else positions
    if not position:
        raise RuntimeError(f"No position data returned for {symbol}")

    opened_at = STATE.position_opened_at.get(symbol)
    trades = []
    if opened_at:
        try:
            trades = client.user_trades(symbol, start_time=opened_at, end_time=now_ms(), limit=1000)
        except Exception:
            trades = []

    commission_total = sum(dec(t.get("commission", "0")) for t in trades)
    realized_total = sum(dec(t.get("realizedPnl", "0")) for t in trades)

    entry_price = dec(position.get("entryPrice", "0"))
    mark_price = dec(position.get("markPrice", "0"))
    position_amt = dec(position.get("positionAmt", "0"))
    leverage = dec(position.get("leverage", "0"))
    unrealized = dec(position.get("unRealizedProfit", "0"))

    initial_margin = Decimal("0")
    if leverage > 0 and entry_price > 0 and abs(position_amt) > 0:
        initial_margin = (abs(position_amt) * entry_price) / leverage

    roi = Decimal("0")
    if initial_margin > 0:
        roi = (unrealized / initial_margin) * Decimal("100")

    print("\n현재 포지션")
    pretty({
        "symbol": symbol,
        "position": {
            "side": "LONG" if position_amt > 0 else "SHORT" if position_amt < 0 else "FLAT",
            "quantity": position.get("positionAmt"),
            "entry_price": position.get("entryPrice"),
            "mark_price": position.get("markPrice"),
            "liquidation_price": position.get("liquidationPrice"),
            "leverage": position.get("leverage"),
            "margin_type": position.get("marginType"),
            "unrealized_pnl": position.get("unRealizedProfit"),
            "notional": position.get("notional"),
            "break_even_price": position.get("breakEvenPrice"),
            "mark_vs_entry_diff": str(mark_price - entry_price),
        },
        "metrics": {
            "roi_percent_est": str(roi.quantize(Decimal("0.01"))),
            "estimated_commission": str(commission_total),
            "realized_pnl_since_open": str(realized_total),
        },
        "protection_orders": STATE.protection_orders.get(symbol, {}),
        "opened_at": opened_at,
    })


def close_position() -> None:
    client = require_client()
    print("\n[포지션 종료]")
    symbol = input_default("심볼", "BTCUSDT").upper()

    positions = client.position_risk(symbol)
    position = next((p for p in positions if p["symbol"] == symbol), None) if isinstance(positions, list) else positions
    if not position:
        raise RuntimeError(f"No position found for {symbol}")

    position_amt = dec(position.get("positionAmt", "0"))
    if position_amt == 0:
        raise RuntimeError("Position is already flat.")

    qty_raw = input_default("부분 종료 수량(전량이면 엔터)", "")
    cancel_tp_sl = input_bool("기존 TP/SL 취소", True)

    if cancel_tp_sl:
        try:
            client.cancel_all_algo_orders(symbol)
        except Exception as e:
            print(f"TP/SL 취소 경고: {e}")

    close_side = "SELL" if position_amt > 0 else "BUY"
    rules = client.symbol_rules(symbol)

    if qty_raw:
        req_qty = dec(qty_raw)
        qty_to_close = min(abs(position_amt), req_qty)
    else:
        qty_to_close = abs(position_amt)

    qty_str = quantize_by_step_str(qty_to_close, rules.market_step_size)

    close_order = client.new_order(
        symbol=symbol,
        side=close_side,
        type="MARKET",
        quantity=qty_str,
        reduceOnly="true",
        newOrderRespType="RESULT",
    )

    opened_at = STATE.position_opened_at.get(symbol)
    start_time = opened_at if opened_at else max(0, now_ms() - 7 * 24 * 60 * 60 * 1000)
    trades = client.user_trades(symbol, start_time=start_time, end_time=now_ms(), limit=1000)
    summary = summarize_trades(trades)
    STATE.last_close_summary[symbol] = summary

    print("\n종료 완료")
    pretty({
        "close_order": close_order,
        "history_summary": summary,
    })


def show_history() -> None:
    print("\n[종료 후 전적]")
    symbol = input_default("심볼", "BTCUSDT").upper()
    summary = STATE.last_close_summary.get(symbol)
    if not summary:
        raise RuntimeError("저장된 종료 전적이 없습니다.")
    pretty({"symbol": symbol, "history": summary})


def print_menu() -> None:
    print("\n" + "=" * 60)
    print(" Binance Futures Console (fixed)")
    print("=" * 60)
    print("1. 설정/연결")
    print("2. 포지션 진입")
    print("3. 포지션 조회")
    print("4. 포지션 종료")
    print("5. 종료 후 전적 조회")
    print("0. 종료")
    print("=" * 60)


def main() -> None:
    print("단일 파일 콘솔 버전 수정본입니다.")
    print(f"설정 저장 파일: {CONFIG_PATH}")
    while True:
        try:
            print_menu()
            choice = input("선택: ").strip()
            if choice == "1":
                setup_client()
            elif choice == "2":
                enter_position()
            elif choice == "3":
                get_position()
            elif choice == "4":
                close_position()
            elif choice == "5":
                show_history()
            elif choice == "0":
                print("종료합니다.")
                break
            else:
                print("올바른 번호를 입력하세요.")
        except KeyboardInterrupt:
            print("\n중단되었습니다.")
        except Exception as e:
            print(f"\n에러: {e}")


if __name__ == "__main__":
    main()
