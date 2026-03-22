from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import BacktestConfig
from ..strategies.base import StrategyVariant
from .metrics import max_drawdown, profit_factor, sharpe_like, sortino_like


@dataclass
class TradeRecord:
    symbol: str
    strategy_id: str
    family: str
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    bars_held: int
    exit_reason: str
    gross_return: float
    net_return: float
    mae: float
    mfe: float


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    metrics: dict[str, float]


class VectorizedBacktester:
    def __init__(self, config: BacktestConfig):
        self.config = config

    def run(
        self,
        symbol: str,
        frame: pd.DataFrame,
        signals: pd.DataFrame,
        variant: StrategyVariant,
    ) -> BacktestResult:
        trades: list[TradeRecord] = []
        position: dict[str, object] | None = None

        for i in range(1, len(frame) - 1):
            timestamp = frame.index[i]
            row = frame.iloc[i]
            next_row = frame.iloc[i + 1]
            signal_row = signals.iloc[i]

            if position is None:
                if signal_row["entry_long"]:
                    position = self._open_position("long", frame.index[i + 1], i + 1, next_row["open"], row["atr"])
                elif signal_row["entry_short"]:
                    position = self._open_position("short", frame.index[i + 1], i + 1, next_row["open"], row["atr"])
                continue

            side = position["side"]
            bars_held = i - position["entry_index"]
            exit_price, exit_reason, mae, mfe = self._evaluate_open_position(position, row, signal_row, bars_held)
            if exit_price is None:
                continue

            gross_return = self._gross_return(side, position["entry_price"], exit_price)
            net_return = self._net_return(gross_return, exit_reason)
            trades.append(
                TradeRecord(
                    symbol=symbol,
                    strategy_id=variant.strategy_id,
                    family=variant.family,
                    side=side,
                    entry_time=position["entry_time"],
                    exit_time=timestamp,
                    entry_price=float(position["entry_price"]),
                    exit_price=float(exit_price),
                    bars_held=int(bars_held),
                    exit_reason=exit_reason,
                    gross_return=float(gross_return),
                    net_return=float(net_return),
                    mae=float(mae),
                    mfe=float(mfe),
                )
            )
            position = None

        trade_frame = pd.DataFrame([trade.__dict__ for trade in trades])
        if trade_frame.empty:
            return BacktestResult(
                trades=trade_frame,
                metrics={
                    "trade_count": 0.0,
                    "expectancy": 0.0,
                    "profit_factor": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_like": 0.0,
                    "sortino_like": 0.0,
                    "win_rate": 0.0,
                },
            )
        returns = trade_frame["net_return"]
        equity_curve = (1.0 + returns.clip(lower=-0.99)).cumprod()
        metrics = {
            "trade_count": float(len(trade_frame)),
            "expectancy": float(returns.mean()),
            "profit_factor": profit_factor(returns),
            "max_drawdown": abs(max_drawdown(equity_curve)),
            "sharpe_like": sharpe_like(returns),
            "sortino_like": sortino_like(returns),
            "win_rate": float((returns > 0).mean()),
        }
        return BacktestResult(trades=trade_frame, metrics=metrics)

    def _open_position(
        self,
        side: str,
        timestamp: pd.Timestamp,
        entry_index: int,
        raw_entry_price: float,
        atr_value: float,
    ) -> dict[str, object]:
        slippage_multiplier = 1 + (self.config.slippage_bps_per_side / 10_000) * (1 if side == "long" else -1)
        entry_price = raw_entry_price * slippage_multiplier
        stop_multiple = self.config.stop_atr_multiple * atr_value
        target_multiple = self.config.target_atr_multiple * atr_value
        liquidation_move_fraction = (1 / self.config.leverage) * self.config.liquidation_buffer_fraction
        liquidation_price = entry_price * (1 - liquidation_move_fraction if side == "long" else 1 + liquidation_move_fraction)
        stop_price = entry_price - stop_multiple if side == "long" else entry_price + stop_multiple
        target_price = entry_price + target_multiple if side == "long" else entry_price - target_multiple
        return {
            "side": side,
            "entry_time": timestamp,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "liquidation_price": liquidation_price,
            "entry_index": entry_index,
            "mae": 0.0,
            "mfe": 0.0,
        }

    def _evaluate_open_position(
        self,
        position: dict[str, object],
        row: pd.Series,
        signal_row: pd.Series,
        bars_held: int,
    ) -> tuple[float | None, str | None, float, float]:
        side = str(position["side"])
        entry_price = float(position["entry_price"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        mae = max(float(position["mae"]), self._gross_return(side, entry_price, low if side == "long" else high) * -1)
        mfe = max(float(position["mfe"]), self._gross_return(side, entry_price, high if side == "long" else low))
        position["mae"] = mae
        position["mfe"] = mfe

        if side == "long":
            if low <= float(position["liquidation_price"]):
                return float(position["liquidation_price"]), "liquidation", mae, mfe
            if low <= float(position["stop_price"]):
                return float(position["stop_price"]), "stop", mae, mfe
            if high >= float(position["target_price"]):
                return float(position["target_price"]), "target", mae, mfe
            if signal_row["exit_long"]:
                return close, "signal_exit", mae, mfe
        else:
            if high >= float(position["liquidation_price"]):
                return float(position["liquidation_price"]), "liquidation", mae, mfe
            if high >= float(position["stop_price"]):
                return float(position["stop_price"]), "stop", mae, mfe
            if low <= float(position["target_price"]):
                return float(position["target_price"]), "target", mae, mfe
            if signal_row["exit_short"]:
                return close, "signal_exit", mae, mfe

        if bars_held >= self.config.max_holding_bars:
            return close, "horizon", mae, mfe
        return None, None, mae, mfe

    def _gross_return(self, side: str, entry_price: float, exit_price: float) -> float:
        raw = (exit_price - entry_price) / entry_price
        if side == "short":
            raw = -raw
        return raw * self.config.leverage * self.config.capital_fraction_per_trade

    def _net_return(self, gross_return: float, exit_reason: str) -> float:
        fees = 2 * self.config.fee_bps_per_side / 10_000 * self.config.leverage * self.config.capital_fraction_per_trade
        if exit_reason == "liquidation" or gross_return <= -self.config.liquidation_loss_fraction:
            return -self.config.liquidation_loss_fraction * self.config.capital_fraction_per_trade
        return gross_return - fees
