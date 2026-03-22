from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ..config import Settings


@dataclass
class PortfolioResult:
    accepted_trades: pd.DataFrame
    metrics: dict[str, float]
    survivor_groups: pd.DataFrame


def build_portfolio(accepted_events: pd.DataFrame, settings: Settings) -> PortfolioResult:
    if accepted_events.empty:
        return PortfolioResult(
            accepted_trades=accepted_events,
            metrics={"trade_count": 0.0, "expectancy": 0.0, "daily_loss_limit_triggered": 0.0},
            survivor_groups=pd.DataFrame(),
        )

    candidates = _prepare_candidates(accepted_events)
    grouped = _rank_candidate_groups(candidates)
    selected_group_keys = _select_candidate_groups(grouped, settings)
    grouped["selected_group"] = grouped["group_key"].isin(selected_group_keys)
    chosen = candidates[candidates["group_key"].isin(selected_group_keys)].copy()
    portfolio = _assemble_trade_stream(chosen, settings)

    if portfolio.empty:
        return PortfolioResult(
            accepted_trades=portfolio,
            metrics={"trade_count": 0.0, "expectancy": 0.0, "daily_loss_limit_triggered": 0.0},
            survivor_groups=grouped,
        )

    daily_returns = portfolio.groupby(portfolio["entry_time"].dt.normalize())["net_return"].sum()
    metrics = {
        "trade_count": float(len(portfolio)),
        "expectancy": float(portfolio["net_return"].mean()),
        "precision": float(portfolio["label_take"].mean()),
        "profit_factor": float(
            portfolio.loc[portfolio["net_return"] > 0, "net_return"].sum()
            / max(abs(portfolio.loc[portfolio["net_return"] < 0, "net_return"].sum()), 1e-9)
        ),
        "daily_loss_limit_triggered": float((daily_returns <= -settings.portfolio.daily_loss_limit_fraction).sum()),
    }
    return PortfolioResult(accepted_trades=portfolio, metrics=metrics, survivor_groups=grouped)


def _prepare_candidates(accepted_events: pd.DataFrame) -> pd.DataFrame:
    candidates = accepted_events.copy()
    candidates["entry_time"] = pd.to_datetime(candidates["entry_time"], utc=True)
    candidates["exit_time"] = pd.to_datetime(candidates["exit_time"], utc=True)
    candidates["probability"] = pd.to_numeric(candidates["probability"], errors="coerce").fillna(0.0)
    if "signal_strength" not in candidates:
        candidates["signal_strength"] = 0.0
    candidates["signal_strength"] = pd.to_numeric(candidates["signal_strength"], errors="coerce").fillna(0.0)
    candidates["group_key"] = (
        candidates["symbol"].astype(str)
        + "|"
        + candidates["family"].astype(str)
        + "|"
        + candidates["strategy_id"].astype(str)
    )
    return (
        candidates.sort_values(["probability", "signal_strength", "entry_time"], ascending=[False, False, True])
        .drop_duplicates(subset=["symbol", "entry_time", "side"], keep="first")
        .sort_values(["entry_time", "probability", "signal_strength"], ascending=[True, False, False])
        .reset_index(drop=True)
    )


def _rank_candidate_groups(candidates: pd.DataFrame) -> pd.DataFrame:
    return (
        candidates.groupby(["group_key", "symbol", "family", "strategy_id"], as_index=False)
        .agg(
            trade_count=("net_return", "count"),
            avg_probability=("probability", "mean"),
            median_probability=("probability", "median"),
            max_probability=("probability", "max"),
            avg_signal_strength=("signal_strength", "mean"),
        )
        .sort_values(
            ["avg_probability", "max_probability", "trade_count", "avg_signal_strength"],
            ascending=[False, False, False, False],
        )
        .reset_index(drop=True)
    )


def _select_candidate_groups(grouped: pd.DataFrame, settings: Settings) -> set[str]:
    if grouped.empty:
        return set()

    portfolio_settings = settings.portfolio
    available_symbol_count = int(grouped["symbol"].nunique())
    available_family_count = int(grouped["family"].nunique())
    target_group_count = min(
        len(grouped),
        max(
            portfolio_settings.max_concurrent_positions * 3,
            portfolio_settings.min_distinct_symbols + portfolio_settings.min_distinct_families,
        ),
    )
    max_symbol_groups = max(1, math.ceil(target_group_count * portfolio_settings.max_symbol_weight))
    max_family_groups = max(1, math.ceil(target_group_count * portfolio_settings.max_strategy_weight))

    selected_keys: list[str] = []
    selected_symbols: set[str] = set()
    selected_families: set[str] = set()
    symbol_group_counts: dict[str, int] = {}
    family_group_counts: dict[str, int] = {}

    def try_add(row) -> bool:
        if row.group_key in selected_keys:
            return False
        if available_symbol_count > 1 and symbol_group_counts.get(row.symbol, 0) >= max_symbol_groups:
            return False
        if available_family_count > 1 and family_group_counts.get(row.family, 0) >= max_family_groups:
            return False
        selected_keys.append(row.group_key)
        selected_symbols.add(row.symbol)
        selected_families.add(row.family)
        symbol_group_counts[row.symbol] = symbol_group_counts.get(row.symbol, 0) + 1
        family_group_counts[row.family] = family_group_counts.get(row.family, 0) + 1
        return True

    for row in grouped.itertuples(index=False):
        if len(selected_symbols) >= portfolio_settings.min_distinct_symbols:
            break
        if row.symbol in symbol_group_counts:
            continue
        try_add(row)

    for row in grouped.itertuples(index=False):
        if len(selected_families) >= portfolio_settings.min_distinct_families:
            break
        if row.family in family_group_counts:
            continue
        try_add(row)

    for row in grouped.itertuples(index=False):
        if len(selected_keys) >= target_group_count:
            break
        try_add(row)

    if not selected_keys:
        selected_keys.append(str(grouped.iloc[0]["group_key"]))
    return set(selected_keys)


def _assemble_trade_stream(chosen: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    if chosen.empty:
        return chosen

    portfolio_settings = settings.portfolio
    available_symbol_count = int(chosen["symbol"].nunique())
    available_family_count = int(chosen["family"].nunique())
    symbol_seed = min(portfolio_settings.min_distinct_symbols, available_symbol_count)
    family_seed = min(portfolio_settings.min_distinct_families, available_family_count)
    symbol_cap_feasible = available_symbol_count >= math.ceil(1 / portfolio_settings.max_symbol_weight)
    family_cap_feasible = available_family_count >= math.ceil(1 / portfolio_settings.max_strategy_weight)
    target_trade_floor = min(
        len(chosen),
        max(
            portfolio_settings.min_portfolio_trades,
            symbol_seed,
            family_seed,
            math.ceil(1 / portfolio_settings.max_symbol_weight),
            math.ceil(1 / portfolio_settings.max_strategy_weight),
        ),
    )

    active_until: list[pd.Timestamp] = []
    daily_trade_counts: dict[pd.Timestamp, int] = {}
    symbol_trade_counts: dict[str, int] = {}
    family_trade_counts: dict[str, int] = {}
    portfolio_rows: list[dict[str, object]] = []

    for row in chosen.itertuples(index=False):
        entry_time = pd.Timestamp(row.entry_time)
        exit_time = pd.Timestamp(row.exit_time)
        day = entry_time.normalize()
        active_until = [item for item in active_until if item > entry_time]

        if len(active_until) >= portfolio_settings.max_concurrent_positions:
            continue
        if daily_trade_counts.get(day, 0) >= portfolio_settings.max_trades_per_day:
            continue

        prospective_total = len(portfolio_rows) + 1
        symbol_count = symbol_trade_counts.get(row.symbol, 0)
        family_count = family_trade_counts.get(row.family, 0)

        if prospective_total <= symbol_seed and symbol_count > 0:
            continue
        if prospective_total <= family_seed and family_count > 0:
            continue

        effective_total = max(prospective_total, target_trade_floor)
        prospective_symbol_share = (symbol_count + 1) / effective_total
        prospective_family_share = (family_count + 1) / effective_total
        if (
            available_symbol_count > 1
            and symbol_cap_feasible
            and prospective_total >= symbol_seed
            and prospective_symbol_share > portfolio_settings.max_symbol_weight
        ):
            continue
        if (
            available_family_count > 1
            and family_cap_feasible
            and prospective_total >= family_seed
            and prospective_family_share > portfolio_settings.max_strategy_weight
        ):
            continue

        active_until.append(exit_time)
        daily_trade_counts[day] = daily_trade_counts.get(day, 0) + 1
        symbol_trade_counts[row.symbol] = symbol_count + 1
        family_trade_counts[row.family] = family_count + 1
        portfolio_rows.append(row._asdict())

    if not portfolio_rows:
        return pd.DataFrame(columns=chosen.columns)

    return pd.DataFrame(portfolio_rows).sort_values(["entry_time", "probability"], ascending=[True, False]).reset_index(drop=True)
