from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STATUS_PATH = ROOT / "runtime" / "status.json"
OUTPUT_PATH = ROOT / "runtime" / "binance_trade_shadow.json"

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade.binanceTrade import (  # noqa: E402
    create_client_from_settings_env,
    dec,
    quantize_by_step_str,
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _to_symbol(pair: str) -> str:
    return pair.replace("/USDT:USDT", "USDT").replace("/", "")


def _build_preview(pair: str, side: str, available_balance: float, stake_ratio_pct: float, leverage: int, stop_loss_pct: float, take_profit_pct: float, client) -> dict:
    symbol = _to_symbol(pair)
    mark = client.mark_price(symbol)
    rules = client.symbol_rules(symbol)
    price = dec(mark.get("markPrice", "0"))
    stake_amount = dec(available_balance) * dec(stake_ratio_pct) / dec("100")
    raw_qty = (stake_amount * dec(leverage)) / price if price > 0 else dec("0")
    qty = quantize_by_step_str(raw_qty, rules.market_step_size)
    qty_dec = dec(qty)
    side_upper = side.upper()

    if side_upper == "BUY":
        stop_price = price * (dec("1") - dec(stop_loss_pct) / dec("100"))
        take_price = price * (dec("1") + dec(take_profit_pct) / dec("100"))
    else:
        stop_price = price * (dec("1") + dec(stop_loss_pct) / dec("100"))
        take_price = price * (dec("1") - dec(take_profit_pct) / dec("100"))

    return {
        "symbol": symbol,
        "pair": pair,
        "side": side_upper,
        "mark_price": str(price),
        "stake_amount_usdt": str(stake_amount.quantize(dec("0.00000001"))),
        "leverage": leverage,
        "quantity": qty,
        "quantity_valid": qty_dec >= dec(rules.min_qty),
        "min_qty": rules.min_qty,
        "min_notional": rules.min_notional,
        "estimated_notional": str((qty_dec * price).quantize(dec("0.00000001")) if qty_dec > 0 else dec("0")),
        "take_profit_price": quantize_by_step_str(take_price, rules.tick_size),
        "stop_loss_price": quantize_by_step_str(stop_price, rules.tick_size),
        "blocked_before_order_submit": not bool(getattr(client, "allow_mutating_requests", False)),
    }


def _extract_trade_side(trade: dict) -> str:
    side = trade.get("side")
    if side:
        return str(side).upper()
    return "BUY" if trade.get("buyer") else "SELL"


def _fetch_recent_actual_trades(client, symbols: list[str], limit_per_symbol: int = 10) -> tuple[list[dict], dict]:
    trades: list[dict] = []
    realized_pnl_total = dec("0")
    commission_total = dec("0")

    for symbol in symbols[:4]:
        try:
            payload = client.user_trades(symbol, limit=limit_per_symbol)
        except Exception as exc:
            trades.append(
                {
                    "symbol": symbol,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        for trade in payload if isinstance(payload, list) else []:
            commission = dec(trade.get("commission", "0"))
            realized_pnl = dec(trade.get("realizedPnl", "0"))
            realized_pnl_total += realized_pnl
            commission_total += commission
            trades.append(
                {
                    "symbol": symbol,
                    "status": "filled",
                    "time": int(trade.get("time", 0) or 0),
                    "side": _extract_trade_side(trade),
                    "orderId": trade.get("orderId"),
                    "price": trade.get("price"),
                    "qty": trade.get("qty"),
                    "quoteQty": trade.get("quoteQty"),
                    "commission": str(commission),
                    "commissionAsset": trade.get("commissionAsset"),
                    "realizedPnl": str(realized_pnl),
                    "positionSide": trade.get("positionSide"),
                    "maker": bool(trade.get("maker", False)),
                }
            )

    filled_trades = [trade for trade in trades if trade.get("status") == "filled"]
    filled_trades.sort(key=lambda item: item.get("time", 0), reverse=True)
    return (
        filled_trades[:20],
        {
            "trades_count": len(filled_trades),
            "realized_pnl_total": str(realized_pnl_total),
            "commission_total": str(commission_total),
            "net_after_commission": str(realized_pnl_total - commission_total),
        },
    )


def build_shadow_status() -> dict:
    client, runtime = create_client_from_settings_env()
    status = _load_json(RUNTIME_STATUS_PATH)
    account = client.account_info_v3()
    balances = client.balance_v2()
    open_orders = client.open_orders()
    positions = client.position_risk()

    usdt = next((row for row in balances if row.get("asset") == "USDT"), {})
    available_balance = float(usdt.get("availableBalance", 0.0))

    actual_positions = []
    for item in positions:
        try:
            amt = float(item.get("positionAmt", 0) or 0)
        except Exception:
            amt = 0.0
        if abs(amt) > 1e-12:
            actual_positions.append(
                {
                    "symbol": item.get("symbol"),
                    "positionAmt": item.get("positionAmt"),
                    "entryPrice": item.get("entryPrice"),
                    "markPrice": item.get("markPrice"),
                    "unRealizedProfit": item.get("unRealizedProfit"),
                    "leverage": item.get("leverage"),
                    "positionSide": item.get("positionSide"),
                }
            )

    previews = []
    for position in status.get("open_positions", [])[:10]:
        side = "SELL" if position.get("side") == "short" else "BUY"
        previews.append(
            _build_preview(
                pair=position["pair"],
                side=side,
                available_balance=available_balance,
                stake_ratio_pct=runtime.dynamic_stake_ratio_pct,
                leverage=runtime.default_leverage,
                stop_loss_pct=runtime.default_stop_loss_pct,
                take_profit_pct=runtime.default_take_profit_pct,
                client=client,
            )
        )

    candidate_symbols = []
    candidate_symbols.extend(item.get("symbol") for item in actual_positions if item.get("symbol"))
    if isinstance(open_orders, list):
        candidate_symbols.extend(item.get("symbol") for item in open_orders if item.get("symbol"))
    candidate_symbols.extend(item.get("symbol") for item in previews if item.get("symbol"))
    seen: set[str] = set()
    deduped_symbols: list[str] = []
    for symbol in candidate_symbols:
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        deduped_symbols.append(symbol)

    actual_recent_trades, actual_trade_summary = _fetch_recent_actual_trades(client, deduped_symbols)

    return {
        "mode": "trade_live_bridge" if runtime.allow_mutating_requests else "trade_shadow",
        "live_requested": runtime.live_requested,
        "order_submission_requested": runtime.order_submission_requested,
        "block_real_order_submission": runtime.block_real_order_submission,
        "allow_mutating_requests": runtime.allow_mutating_requests,
        "defaults": {
            "dynamic_stake_ratio_pct": runtime.dynamic_stake_ratio_pct,
            "default_leverage": runtime.default_leverage,
            "default_stop_loss_pct": runtime.default_stop_loss_pct,
            "default_take_profit_pct": runtime.default_take_profit_pct,
        },
        "actual_account": {
            "available_balance": usdt.get("availableBalance"),
            "wallet_balance": usdt.get("balance"),
            "total_wallet_balance": account.get("totalWalletBalance"),
            "total_margin_balance": account.get("totalMarginBalance"),
            "positions_count": len(actual_positions),
            "open_orders_count": len(open_orders) if isinstance(open_orders, list) else 0,
        },
        "actual_positions": actual_positions,
        "actual_open_orders": open_orders[:10] if isinstance(open_orders, list) else [],
        "actual_recent_trades": actual_recent_trades,
        "actual_trade_summary": actual_trade_summary,
        "simulation_open_positions_count": len(status.get("open_positions", [])),
        "simulation_recent_closed_count": len(status.get("recent_closed", [])),
        "preview_orders_from_simulation": previews,
    }


def main() -> None:
    payload = build_shadow_status()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"mode": payload["mode"], "preview_orders": len(payload["preview_orders_from_simulation"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
