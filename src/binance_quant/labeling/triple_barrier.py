from __future__ import annotations

import pandas as pd

from ..config import LabelingConfig


def build_event_dataset(
    trades: pd.DataFrame,
    enriched_frames: dict[str, pd.DataFrame],
    strategy_lookup: dict[str, str],
    config: LabelingConfig,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    sorted_trades = trades.sort_values("entry_time").reset_index(drop=True)
    prior_by_key: dict[tuple[str, str], list[float]] = {}

    for _, trade in sorted_trades.iterrows():
        symbol = str(trade["symbol"])
        entry_time = pd.Timestamp(trade["entry_time"])
        feature_row = enriched_frames[symbol].loc[entry_time].to_dict()
        key = (symbol, str(trade["side"]))
        prior_returns = prior_by_key.get(key, [])
        rows.append(
            {
                "symbol": symbol,
                "strategy_id": str(trade["strategy_id"]),
                "family": strategy_lookup[str(trade["strategy_id"])],
                "entry_time": entry_time,
                "exit_time": pd.Timestamp(trade["exit_time"]),
                "side": str(trade["side"]),
                "net_return": float(trade["net_return"]),
                "gross_return": float(trade["gross_return"]),
                "exit_reason": str(trade["exit_reason"]),
                "bars_held": int(trade["bars_held"]),
                "signal_strength": float(trade.get("signal_strength", 0.0)),
                "label_take": int(float(trade["net_return"]) > 0 and str(trade["exit_reason"]) != "liquidation"),
                "target_hit": str(trade["exit_reason"]) == "target",
                "stop_hit": str(trade["exit_reason"]) == "stop",
                "horizon_hit": str(trade["exit_reason"]) == "horizon",
                "mae": float(trade["mae"]),
                "mfe": float(trade["mfe"]),
                "mae_limit_breached": int(float(trade["mae"]) > config.max_adverse_excursion_limit),
                "recent_same_side_failures": int(sum(ret <= 0 for ret in prior_returns[-5:])),
                "recent_same_side_mean_return": float(pd.Series(prior_returns[-10:]).mean() if prior_returns else 0.0),
                **feature_row,
            }
        )
        prior_by_key.setdefault(key, []).append(float(trade["net_return"]))
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
