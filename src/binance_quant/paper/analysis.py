from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings
from ..features.engine import enrich_ohlcv
from ..strategies.templates import build_strategy_templates
from ..utils import dump_json, utc_now


def summarize_paper_performance(
    *,
    positions: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    settings: Settings,
    base_threshold: float | None = None,
) -> dict[str, Any]:
    closed_positions = sorted(
        [dict(item) for item in positions if item.get("status") == "closed"],
        key=lambda item: str(item.get("closed_at") or ""),
    )
    active_positions = [dict(item) for item in positions if item.get("status") == "active"]
    decision_frame = pd.DataFrame(decisions) if decisions else pd.DataFrame()
    position_frame = pd.DataFrame(positions) if positions else pd.DataFrame()

    closed_returns = [float(item.get("net_return", 0.0)) for item in closed_positions]
    wins = [value for value in closed_returns if value > 0]
    losses = [value for value in closed_returns if value <= 0]
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (1.0 if wins else 0.0)

    loss_streak = 0
    for item in reversed(closed_positions):
        if float(item.get("net_return", 0.0)) <= 0:
            loss_streak += 1
        else:
            break

    base_equity = settings.paper.starting_equity_usd
    position_margin_usd = base_equity * settings.backtest.capital_fraction_per_trade
    realized_net_return_sum = float(sum(closed_returns))
    realized_net_pnl_usd = realized_net_return_sum * base_equity
    lookback_cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=settings.paper.trade_target_lookback_hours)
    recent_open_count = 0
    recent_allow_count = 0
    recent_signal_count = 0
    if not position_frame.empty and "opened_at" in position_frame.columns:
        opened_at = pd.to_datetime(position_frame["opened_at"], utc=True, errors="coerce")
        recent_open_count = int((opened_at >= lookback_cutoff).sum())
    if not decision_frame.empty and "decided_at" in decision_frame.columns:
        decided_at = pd.to_datetime(decision_frame["decided_at"], utc=True, errors="coerce")
        recent_signal_count = int((decided_at >= lookback_cutoff).sum())
        if "final_action" in decision_frame.columns:
            recent_allow_count = int(((decided_at >= lookback_cutoff) & (decision_frame["final_action"] == "allow")).sum())
    threshold_offset = min(
        loss_streak * settings.paper.adaptive_threshold_loss_step,
        settings.paper.adaptive_threshold_max_offset,
    )
    heuristic_threshold = float(base_threshold + threshold_offset) if base_threshold is not None else None
    counterfactual_analysis = analyze_counterfactual_decisions(decisions, settings, base_threshold=base_threshold)
    llm_diagnostics = build_llm_diagnostics(decisions, counterfactual_analysis)
    recommended_threshold = counterfactual_analysis.get("recommended_threshold")
    if recommended_threshold is None:
        recommended_threshold = heuristic_threshold
    recommended_threshold_source = counterfactual_analysis.get("recommended_threshold_source")
    if recommended_threshold_source is None and recommended_threshold is not None:
        recommended_threshold_source = "heuristic_loss_streak"

    loss_by_symbol = _group_pnl(closed_positions, "symbol", base_equity)
    loss_by_strategy = _group_pnl(closed_positions, "strategy_id", base_equity)

    retune_triggered = bool(
        settings.paper.retune_on_loss_trigger
        and len(closed_positions) >= settings.paper.loss_trigger_min_closed_positions
        and (
            loss_streak >= settings.paper.loss_trigger_loss_streak
            or realized_net_return_sum <= settings.paper.loss_trigger_net_return_fraction
        )
    )

    return {
        "generated_at": utc_now().isoformat(),
        "starting_equity_usd": base_equity,
        "position_margin_usd": position_margin_usd,
        "decision_count": len(decisions),
        "decision_breakdown": dict(Counter(str(item.get("final_action", "unknown")) for item in decisions)),
        "decision_reason_breakdown": dict(Counter(str(item.get("portfolio_reason", "unknown")) for item in decisions)),
        "closed_position_count": len(closed_positions),
        "active_position_count": len(active_positions),
        "win_count": len(wins),
        "loss_count": len(losses),
        "loss_streak": loss_streak,
        "profit_factor": float(profit_factor),
        "realized_net_return_sum": realized_net_return_sum,
        "realized_net_pnl_usd": realized_net_pnl_usd,
        "avg_closed_net_return": (realized_net_return_sum / len(closed_positions)) if closed_positions else 0.0,
        "recent_open_count_lookback": recent_open_count,
        "recent_allow_count_lookback": recent_allow_count,
        "recent_signal_count_lookback": recent_signal_count,
        "trade_target_lookback_hours": settings.paper.trade_target_lookback_hours,
        "min_daily_trade_target": settings.paper.min_daily_trade_target,
        "max_daily_trade_target": settings.paper.max_daily_trade_target,
        "base_threshold": base_threshold,
        "recommended_threshold_offset": threshold_offset,
        "heuristic_threshold": heuristic_threshold,
        "recommended_threshold": recommended_threshold,
        "recommended_threshold_source": recommended_threshold_source,
        "retune_triggered": retune_triggered,
        "counterfactual_analysis": counterfactual_analysis,
        "llm_diagnostics": llm_diagnostics,
        "recent_closed_positions": [_serialize_trade(item, base_equity, position_margin_usd) for item in closed_positions[-10:][::-1]],
        "worst_symbols": loss_by_symbol[:5],
        "worst_families": _group_pnl(closed_positions, "family", base_equity)[:5],
        "worst_strategies": loss_by_strategy[:5],
        "open_positions": [_serialize_trade(item, base_equity, position_margin_usd) for item in active_positions],
    }


def persist_loss_analysis(
    settings: Settings,
    summary: dict[str, Any],
    *,
    report_path: Path | None = None,
    summary_path: Path | None = None,
) -> tuple[Path, Path]:
    report_target = report_path or settings.paper_loss_analysis_report_path
    summary_target = summary_path or settings.paper_loss_analysis_summary_path
    dump_json(summary_target, summary)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(build_loss_analysis_markdown(summary), encoding="utf-8")
    return report_target, summary_target


def build_loss_analysis_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Paper Loss Analysis",
        "",
        f"- Generated at: `{summary.get('generated_at', '-')}`",
        f"- Decisions: `{summary.get('decision_count', 0)}`",
        f"- Closed positions: `{summary.get('closed_position_count', 0)}`",
        f"- Active positions: `{summary.get('active_position_count', 0)}`",
        f"- Loss streak: `{summary.get('loss_streak', 0)}`",
        f"- Win / loss: `{summary.get('win_count', 0)} / {summary.get('loss_count', 0)}`",
        f"- Profit factor: `{summary.get('profit_factor', 0.0):.4f}`",
        f"- Realized net return: `{summary.get('realized_net_return_sum', 0.0):.6f}`",
        f"- Realized net PnL USD: `${summary.get('realized_net_pnl_usd', 0.0):.2f}`",
        f"- Base threshold: `{_format_optional(summary.get('base_threshold'))}`",
        f"- Heuristic threshold: `{_format_optional(summary.get('heuristic_threshold'))}`",
        f"- Recommended threshold: `{_format_optional(summary.get('recommended_threshold'))}`",
        f"- Recommended threshold source: `{summary.get('recommended_threshold_source', '-')}`",
        f"- Retune triggered: `{summary.get('retune_triggered', False)}`",
        "",
        "## Decision Breakdown",
    ]

    for key, value in sorted(summary.get("decision_breakdown", {}).items()):
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Decision Reasons"])
    for key, value in sorted(summary.get("decision_reason_breakdown", {}).items()):
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Worst Symbols"])
    if summary.get("worst_symbols"):
        for item in summary["worst_symbols"]:
            lines.append(
                f"- `{item['key']}`: net `{item['net_return_sum']:.6f}` / `${item['net_pnl_usd']:.2f}` across `{item['trade_count']}` trades"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Worst Strategies"])
    if summary.get("worst_strategies"):
        for item in summary["worst_strategies"]:
            lines.append(
                f"- `{item['key']}`: net `{item['net_return_sum']:.6f}` / `${item['net_pnl_usd']:.2f}` across `{item['trade_count']}` trades"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Worst Families"])
    if summary.get("worst_families"):
        for item in summary["worst_families"]:
            lines.append(
                f"- `{item['key']}`: net `{item['net_return_sum']:.6f}` / `${item['net_pnl_usd']:.2f}` across `{item['trade_count']}` trades"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Recent Closed Positions"])
    if summary.get("recent_closed_positions"):
        for item in summary["recent_closed_positions"]:
            lines.append(
                f"- `{item['symbol']}` `{item['strategy_id']}` `{item['side']}` `{item.get('exit_reason', '-')}` "
                f"net `{item['account_net_roi_percent']:.2f}%` / position `{item['position_net_roi_percent']:.2f}%` / `${item['net_pnl_usd']:.2f}`"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## LLM Diagnostics"])
    llm = summary.get("llm_diagnostics", {})
    lines.append(f"- Evaluated decisions: `{llm.get('llm_evaluated_count', 0)}`")
    lines.append(f"- Decisive rejects on ML-approved signals: `{llm.get('llm_decisive_reject_count', 0)}`")
    lines.append(f"- Rejected-signal counterfactual wins: `{llm.get('rejected_counterfactual_positive_count', 0)}`")
    lines.append(
        f"- Rejected-signal counterfactual mean return: `{float(llm.get('rejected_counterfactual_mean_net_return', 0.0)):.6f}`"
    )

    lines.extend(["", "## Counterfactual Threshold Sweep"])
    counterfactual = summary.get("counterfactual_analysis", {})
    threshold_rows = counterfactual.get("threshold_candidates", [])
    if threshold_rows:
        for item in threshold_rows:
            lines.append(
                f"- `>= {item['threshold']:.3f}` trades `{item['accepted_count']}` wins `{item['wins']}` losses `{item['losses']}` "
                f"mean `{item['mean_net_return']:.6f}` sum `{item['sum_net_return']:.6f}`"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Recommendations"])
    if summary.get("retune_triggered"):
        lines.append(
            f"- Trigger immediate retune with effective threshold near `{_format_optional(summary.get('recommended_threshold'))}`."
        )
    else:
        lines.append("- Monitor further trades before forcing a retune.")
    if summary.get("loss_streak", 0) > 0:
        lines.append("- Keep blocking recently losing symbols/strategies during cooldown windows.")
    return "\n".join(lines) + "\n"


def effective_live_threshold(base_threshold: float, settings: Settings, summary: dict[str, Any]) -> float:
    recommended = summary.get("recommended_threshold")
    threshold = float(recommended) if recommended is not None else None
    if threshold is None:
        offset = min(
            float(summary.get("loss_streak", 0)) * settings.paper.adaptive_threshold_loss_step,
            settings.paper.adaptive_threshold_max_offset,
        )
        threshold = float(base_threshold + offset)

    recent_open_count = int(summary.get("recent_open_count_lookback", 0) or 0)
    min_target = settings.paper.min_daily_trade_target
    max_target = settings.paper.max_daily_trade_target
    step = settings.paper.trade_target_threshold_step

    if recent_open_count < min_target:
        threshold -= (min_target - recent_open_count) * step
    elif recent_open_count > max_target:
        threshold += (recent_open_count - max_target) * step

    return float(min(max(threshold, settings.paper.min_live_threshold_floor), settings.paper.max_live_threshold_ceiling))


def should_trigger_loss_retune(
    summary: dict[str, Any],
    settings: Settings,
    *,
    last_attempt_at: str | None = None,
    now: pd.Timestamp | None = None,
) -> bool:
    if not summary.get("retune_triggered"):
        return False
    if not last_attempt_at:
        return True
    now_ts = now or pd.Timestamp.utcnow()
    last_attempt = pd.Timestamp(last_attempt_at)
    cooldown = pd.Timedelta(minutes=settings.paper.loss_trigger_cooldown_minutes)
    return now_ts - last_attempt >= cooldown


def recent_loss_cooldown_reason(
    positions: list[dict[str, Any]],
    *,
    symbol: str,
    strategy_id: str,
    signal_time: pd.Timestamp,
    settings: Settings,
) -> str | None:
    closed_losses = [
        dict(item)
        for item in positions
        if item.get("status") == "closed" and float(item.get("net_return", 0.0)) <= 0
    ]
    if not closed_losses:
        return None

    symbol_cutoff = pd.Timedelta(hours=settings.paper.same_symbol_loss_cooldown_hours)
    strategy_cutoff = pd.Timedelta(hours=settings.paper.same_strategy_loss_cooldown_hours)

    for item in sorted(closed_losses, key=lambda row: str(row.get("closed_at") or ""), reverse=True):
        closed_at = pd.Timestamp(item.get("closed_at"))
        if item.get("symbol") == symbol and signal_time - closed_at <= symbol_cutoff:
            return "recent_symbol_loss_cooldown"
        if item.get("strategy_id") == strategy_id and signal_time - closed_at <= strategy_cutoff:
            return "recent_strategy_loss_cooldown"
    return None


def recent_family_loss_cooldown_reason(
    positions: list[dict[str, Any]],
    *,
    family: str,
    signal_time: pd.Timestamp,
    settings: Settings,
) -> str | None:
    closed_positions = [
        dict(item)
        for item in positions
        if item.get("status") == "closed" and str(item.get("family")) == family
    ]
    if len(closed_positions) < settings.paper.family_loss_block_min_closed_trades:
        return None

    cutoff = signal_time - pd.Timedelta(hours=settings.paper.same_family_loss_cooldown_hours)
    recent = [
        item
        for item in closed_positions
        if pd.Timestamp(item.get("closed_at")) >= cutoff
    ]
    if len(recent) < settings.paper.family_loss_block_min_closed_trades:
        return None

    net_return_sum = float(sum(float(item.get("net_return", 0.0)) for item in recent))
    win_count = sum(float(item.get("net_return", 0.0)) > 0 for item in recent)
    win_rate = win_count / len(recent) if recent else 0.0
    if (
        net_return_sum <= settings.paper.family_loss_block_net_return_fraction
        and win_rate <= settings.paper.family_loss_block_max_win_rate
    ):
        return "recent_family_loss_cooldown"
    return None


def strategy_performance_block_reason(
    positions: list[dict[str, Any]],
    *,
    strategy_id: str,
    signal_time: pd.Timestamp,
    settings: Settings,
) -> str | None:
    closed_positions = [
        dict(item)
        for item in positions
        if item.get("status") == "closed" and str(item.get("strategy_id")) == strategy_id
    ]
    if len(closed_positions) < settings.paper.strategy_performance_block_min_closed_trades:
        return None

    cutoff = signal_time - pd.Timedelta(days=settings.paper.strategy_performance_block_lookback_days)
    recent = [
        item
        for item in closed_positions
        if pd.Timestamp(item.get("closed_at")) >= cutoff
    ]
    if len(recent) < settings.paper.strategy_performance_block_min_closed_trades:
        return None

    net_return_sum = float(sum(float(item.get("net_return", 0.0)) for item in recent))
    win_count = sum(float(item.get("net_return", 0.0)) > 0 for item in recent)
    win_rate = win_count / len(recent) if recent else 0.0
    if (
        net_return_sum <= settings.paper.strategy_performance_block_net_return_fraction
        and win_rate <= settings.paper.strategy_performance_block_max_win_rate
    ):
        return "strategy_performance_block"
    return None


def symbol_performance_block_reason(
    positions: list[dict[str, Any]],
    *,
    symbol: str,
    signal_time: pd.Timestamp,
    settings: Settings,
) -> str | None:
    closed_positions = [
        dict(item)
        for item in positions
        if item.get("status") == "closed" and str(item.get("symbol")) == symbol
    ]
    if len(closed_positions) < settings.paper.symbol_performance_block_min_closed_trades:
        return None

    cutoff = signal_time - pd.Timedelta(days=settings.paper.symbol_performance_block_lookback_days)
    recent = [
        item
        for item in closed_positions
        if pd.Timestamp(item.get("closed_at")) >= cutoff
    ]
    if len(recent) < settings.paper.symbol_performance_block_min_closed_trades:
        return None

    net_return_sum = float(sum(float(item.get("net_return", 0.0)) for item in recent))
    win_count = sum(float(item.get("net_return", 0.0)) > 0 for item in recent)
    win_rate = win_count / len(recent) if recent else 0.0
    if (
        net_return_sum <= settings.paper.symbol_performance_block_net_return_fraction
        and win_rate <= settings.paper.symbol_performance_block_max_win_rate
    ):
        return "symbol_performance_block"
    return None


def adaptive_deployment_gate(
    result: dict[str, Any],
    settings: Settings,
    *,
    loss_triggered: bool,
    performance_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    portfolio = dict(result.get("portfolio", {}) or {})
    robustness = dict(result.get("robustness", {}) or {})
    ml_metrics = dict(((result.get("ml") or {}).get("best_model") or {}).get("aggregate_metrics", {}) or {})
    performance_summary = dict(performance_summary or {})

    portfolio_trade_count = float(portfolio.get("trade_count", robustness.get("portfolio_trade_count", 0.0)) or 0.0)
    portfolio_expectancy = float(portfolio.get("expectancy", 0.0) or 0.0)
    portfolio_precision = float(
        portfolio.get(
            "precision",
            ml_metrics.get("precision_mean", 0.0),
        )
        or 0.0
    )
    distinct_symbols = int(robustness.get("distinct_symbols", 0) or 0)
    distinct_families = int(robustness.get("distinct_families", 0) or 0)
    top_symbol_share = float(robustness.get("top_symbol_share", 1.0) or 1.0)
    recent_open_count = int(performance_summary.get("recent_open_count_lookback", 0) or 0)
    trade_shortfall = recent_open_count < settings.paper.min_daily_trade_target
    selected_families = _selected_families_from_result(result)
    current_worst_family = None
    if performance_summary.get("worst_families"):
        current_worst_family = str(performance_summary["worst_families"][0].get("key") or "")

    status_ok = result.get("status") == "accepted_for_paper"
    gates = {
        "status_ok": status_ok,
        "robustness_ok": bool(robustness.get("all_gates_passed", False)),
        "base_trade_count_ok": portfolio_trade_count >= settings.portfolio.min_portfolio_trades,
        "base_expectancy_ok": portfolio_expectancy >= settings.research.min_expectancy,
    }
    emergency_mode = False
    throughput_mode = False
    if loss_triggered:
        gates.update(
            {
                "loss_mode_trade_count_ok": portfolio_trade_count >= settings.paper.loss_retune_deployment_min_trade_count,
                "loss_mode_symbol_breadth_ok": distinct_symbols >= settings.paper.loss_retune_deployment_min_distinct_symbols,
                "loss_mode_family_breadth_ok": distinct_families >= settings.paper.loss_retune_deployment_min_distinct_families,
                "loss_mode_expectancy_ok": portfolio_expectancy >= settings.paper.loss_retune_deployment_min_expectancy,
                "loss_mode_precision_ok": portfolio_precision >= settings.paper.loss_retune_deployment_min_precision,
            }
        )

        emergency_candidate_gates = {
            "candidate_status_ok": result.get("status") in {"accepted_for_paper", "needs_iteration"},
            "candidate_trade_count_ok": portfolio_trade_count >= settings.paper.emergency_candidate_min_trade_count,
            "candidate_symbol_breadth_ok": distinct_symbols >= settings.paper.emergency_candidate_min_distinct_symbols,
            "candidate_family_breadth_ok": distinct_families >= settings.paper.emergency_candidate_min_distinct_families,
            "candidate_expectancy_ok": portfolio_expectancy >= settings.paper.emergency_candidate_min_expectancy,
            "candidate_precision_ok": portfolio_precision >= settings.paper.emergency_candidate_min_precision,
            "candidate_fold_expectancy_ok": bool(robustness.get("gates", {}).get("positive_fold_expectancy", False)),
            "candidate_threshold_stable_ok": bool(robustness.get("gates", {}).get("threshold_stable", False)),
            "candidate_cost_stress_ok": bool(robustness.get("gates", {}).get("cost_stress_positive", False)),
            "candidate_monte_carlo_ok": bool(robustness.get("gates", {}).get("monte_carlo_ok", False)),
        }
        gates.update(emergency_candidate_gates)
        emergency_mode = (
            settings.paper.emergency_candidate_deployment_enabled
            and not status_ok
            and all(emergency_candidate_gates.values())
        )

        throughput_candidate_gates = {
            "throughput_shortfall_ok": trade_shortfall,
            "throughput_status_ok": result.get("status") in {"accepted_for_paper", "needs_iteration"},
            "throughput_trade_count_ok": portfolio_trade_count >= settings.paper.throughput_candidate_min_trade_count,
            "throughput_symbol_breadth_ok": distinct_symbols >= settings.paper.throughput_candidate_min_distinct_symbols,
            "throughput_expectancy_ok": portfolio_expectancy >= settings.paper.throughput_candidate_min_expectancy,
            "throughput_precision_ok": portfolio_precision >= settings.paper.throughput_candidate_min_precision,
            "throughput_top_symbol_share_ok": top_symbol_share <= settings.portfolio.max_symbol_weight,
            "throughput_fold_expectancy_ok": bool(robustness.get("gates", {}).get("positive_fold_expectancy", False)),
            "throughput_threshold_stable_ok": bool(robustness.get("gates", {}).get("threshold_stable", False)),
            "throughput_cost_stress_ok": bool(robustness.get("gates", {}).get("cost_stress_positive", False)),
            "throughput_monte_carlo_ok": bool(robustness.get("gates", {}).get("monte_carlo_ok", False)),
            "throughput_not_live_worst_family_only": not (
                current_worst_family
                and len(selected_families) == 1
                and current_worst_family in selected_families
            ),
        }
        gates.update(throughput_candidate_gates)
        throughput_mode = (
            settings.paper.throughput_candidate_deployment_enabled
            and not status_ok
            and not emergency_mode
            and all(throughput_candidate_gates.values())
        )

    deploy = all(gates.values()) if status_ok else (emergency_mode or throughput_mode)
    deployment_mode = (
        "standard"
        if status_ok and deploy
        else "emergency_candidate"
        if emergency_mode
        else "throughput_candidate"
        if throughput_mode
        else "blocked"
    )
    return {
        "loss_triggered": loss_triggered,
        "trade_shortfall": trade_shortfall,
        "recent_open_count": recent_open_count,
        "portfolio_trade_count": portfolio_trade_count,
        "portfolio_expectancy": portfolio_expectancy,
        "portfolio_precision": portfolio_precision,
        "distinct_symbols": distinct_symbols,
        "distinct_families": distinct_families,
        "selected_families": selected_families,
        "deployment_mode": deployment_mode,
        "gates": gates,
        "deploy": deploy,
    }


def _selected_families_from_result(result: dict[str, Any]) -> list[str]:
    artifact_dir = result.get("artifact_dir")
    if not artifact_dir:
        return []
    pre_screen_path = Path(str(artifact_dir)) / "reports" / "pre_screen.csv"
    if not pre_screen_path.exists():
        return []
    try:
        pre_screen = pd.read_csv(pre_screen_path)
    except Exception:
        return []
    if "selected_for_ml" in pre_screen.columns:
        selected = pre_screen.loc[pre_screen["selected_for_ml"].astype(bool)]
        if not selected.empty and "family" in selected.columns:
            return sorted(selected["family"].astype(str).dropna().unique().tolist())
    if "survived" in pre_screen.columns and "family" in pre_screen.columns:
        survived = pre_screen.loc[pre_screen["survived"].astype(bool), "family"].astype(str).dropna().unique().tolist()
        return sorted(survived)
    return []


def analyze_counterfactual_decisions(
    decisions: list[dict[str, Any]],
    settings: Settings,
    *,
    base_threshold: float | None = None,
) -> dict[str, Any]:
    if not decisions:
        return {
            "decision_count": 0,
            "counterfactual_count": 0,
            "recommended_threshold": None,
            "recommended_threshold_source": None,
            "threshold_candidates": [],
            "decision_rows": [],
        }

    frame_cache: dict[str, pd.DataFrame] = {}
    template_lookup = {template.family: template for template in build_strategy_templates()}
    variant_lookup: dict[str, Any] = {}
    counterfactual_rows: list[dict[str, Any]] = []

    for decision in decisions:
        simulated = _simulate_counterfactual_decision(
            decision,
            settings,
            frame_cache=frame_cache,
            template_lookup=template_lookup,
            variant_lookup=variant_lookup,
        )
        if simulated is not None:
            counterfactual_rows.append(simulated)

    if not counterfactual_rows:
        return {
            "decision_count": len(decisions),
            "counterfactual_count": 0,
            "recommended_threshold": None,
            "recommended_threshold_source": None,
            "threshold_candidates": [],
            "decision_rows": [],
        }

    thresholds = sorted(
        {
            float(value)
            for value in ([base_threshold] if base_threshold is not None else []) + list(settings.ml.threshold_grid)
            if value is not None
        }
    )
    threshold_candidates = evaluate_counterfactual_thresholds(counterfactual_rows, settings, thresholds)
    recommended_threshold = base_threshold
    recommended_source = "base_threshold" if base_threshold is not None else None
    if threshold_candidates:
        recommended = _select_best_threshold(threshold_candidates, base_threshold=base_threshold)
        recommended_threshold = float(recommended["threshold"])
        recommended_source = "counterfactual_threshold_sweep"
    return {
        "decision_count": len(decisions),
        "counterfactual_count": len(counterfactual_rows),
        "recommended_threshold": recommended_threshold,
        "recommended_threshold_source": recommended_source,
        "threshold_candidates": threshold_candidates,
        "decision_rows": counterfactual_rows,
    }


def evaluate_counterfactual_thresholds(
    decision_rows: list[dict[str, Any]],
    settings: Settings,
    thresholds: list[float],
) -> list[dict[str, Any]]:
    if not decision_rows:
        return []
    frame = pd.DataFrame(decision_rows).sort_values(["signal_time", "decision_id"]).reset_index(drop=True)
    results: list[dict[str, Any]] = []
    for threshold in thresholds:
        accepted: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            signal_time = pd.Timestamp(row["signal_time"])
            active = [item for item in active if pd.Timestamp(item["exit_time"]) > signal_time]
            if float(row["ml_probability"]) < threshold:
                continue
            if settings.paper.allow_one_position_per_symbol and any(item["symbol"] == row["symbol"] for item in active):
                continue
            if len(active) >= settings.portfolio.max_concurrent_positions:
                continue
            accepted.append(row)
            active.append(row)
        accepted_frame = pd.DataFrame(accepted)
        if accepted_frame.empty:
            results.append(
                {
                    "threshold": float(threshold),
                    "accepted_count": 0,
                    "wins": 0,
                    "losses": 0,
                    "mean_net_return": 0.0,
                    "sum_net_return": 0.0,
                    "accepted_ids": [],
                }
            )
            continue
        net_returns = accepted_frame["net_return_cf"].astype(float)
        results.append(
            {
                "threshold": float(threshold),
                "accepted_count": int(len(accepted_frame)),
                "wins": int((net_returns > 0).sum()),
                "losses": int((net_returns <= 0).sum()),
                "mean_net_return": float(net_returns.mean()),
                "sum_net_return": float(net_returns.sum()),
                "accepted_ids": accepted_frame["decision_id"].astype(int).tolist(),
            }
        )
    return results


def build_llm_diagnostics(
    decisions: list[dict[str, Any]],
    counterfactual_analysis: dict[str, Any],
) -> dict[str, Any]:
    decision_frame = pd.DataFrame(decisions) if decisions else pd.DataFrame()
    decision_rows = counterfactual_analysis.get("decision_rows", [])
    simulated_frame = pd.DataFrame(decision_rows) if decision_rows else pd.DataFrame()

    llm_actions = decision_frame["llm_action"].fillna("none") if not decision_frame.empty and "llm_action" in decision_frame else pd.Series(dtype="object")
    llm_evaluated = decision_frame[decision_frame["llm_action"].notna()] if not decision_frame.empty and "llm_action" in decision_frame else pd.DataFrame()
    llm_decisive_rejects = 0
    if not decision_frame.empty and {"ml_accepted", "final_action", "llm_action"}.issubset(decision_frame.columns):
        llm_decisive_rejects = int(
            (
                (decision_frame["ml_accepted"].astype(int) == 1)
                & (decision_frame["final_action"] == "reject")
                & decision_frame["llm_action"].isin(["reject", "defer"])
            ).sum()
        )

    rejected_counterfactual = simulated_frame[simulated_frame["final_action"] == "reject"] if not simulated_frame.empty else pd.DataFrame()
    allowed_counterfactual = simulated_frame[simulated_frame["final_action"] == "allow"] if not simulated_frame.empty else pd.DataFrame()

    return {
        "llm_action_breakdown": dict(Counter(str(value) for value in llm_actions)) if not llm_actions.empty else {},
        "llm_evaluated_count": int(len(llm_evaluated)),
        "llm_decisive_reject_count": llm_decisive_rejects,
        "rejected_counterfactual_count": int(len(rejected_counterfactual)),
        "rejected_counterfactual_positive_count": int((rejected_counterfactual["net_return_cf"] > 0).sum()) if not rejected_counterfactual.empty else 0,
        "rejected_counterfactual_mean_net_return": float(rejected_counterfactual["net_return_cf"].mean()) if not rejected_counterfactual.empty else 0.0,
        "allowed_counterfactual_count": int(len(allowed_counterfactual)),
        "allowed_counterfactual_mean_net_return": float(allowed_counterfactual["net_return_cf"].mean()) if not allowed_counterfactual.empty else 0.0,
    }


def _select_best_threshold(
    threshold_candidates: list[dict[str, Any]],
    *,
    base_threshold: float | None = None,
) -> dict[str, Any]:
    positive = [
        item
        for item in threshold_candidates
        if item["accepted_count"] >= 3 and item["sum_net_return"] > 0
    ]
    pool = positive if positive else threshold_candidates
    return max(
        pool,
        key=lambda item: (
            item["sum_net_return"],
            item["mean_net_return"],
            item["wins"] - item["losses"],
            item["accepted_count"],
            -abs(float(item["threshold"]) - float(base_threshold if base_threshold is not None else item["threshold"])),
        ),
    )


def _simulate_counterfactual_decision(
    decision: dict[str, Any],
    settings: Settings,
    *,
    frame_cache: dict[str, pd.DataFrame],
    template_lookup: dict[str, Any],
    variant_lookup: dict[str, Any],
) -> dict[str, Any] | None:
    symbol = str(decision.get("symbol", ""))
    family = str(decision.get("family", ""))
    strategy_id = str(decision.get("strategy_id", ""))
    if not symbol or not family or not strategy_id:
        return None
    frame = _load_enriched_frame(symbol, settings, frame_cache)
    if frame is None:
        return None
    variant = _variant_for_strategy_id(strategy_id, family, settings, template_lookup, variant_lookup)
    if variant is None:
        return None
    template = template_lookup[family]
    signals = template.generate(frame, variant).signals
    signal_time = pd.Timestamp(decision["signal_time"])
    subsequent = frame.loc[frame.index > signal_time]
    if subsequent.empty:
        return None

    side = str(decision["side"])
    entry_price = float(decision["observed_price"])
    atr_value = float(decision["atr_value"])
    stop_price, target_price, liquidation_price = _risk_levels(settings, side, entry_price, atr_value)
    exit_time = subsequent.index[-1]
    exit_reason = "open"
    net_return = _net_return(
        settings,
        _gross_return(settings, side, entry_price, float(subsequent["close"].iloc[-1])),
        "mark",
    )

    for idx, row in subsequent.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        if side == "long":
            if low <= liquidation_price:
                exit_time = idx
                exit_reason = "liquidation"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break
            if low <= stop_price:
                exit_time = idx
                exit_reason = "stop"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break
            if high >= target_price:
                exit_time = idx
                exit_reason = "target"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break
        else:
            if high >= liquidation_price:
                exit_time = idx
                exit_reason = "liquidation"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break
            if high >= stop_price:
                exit_time = idx
                exit_reason = "stop"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break
            if low <= target_price:
                exit_time = idx
                exit_reason = "target"
                net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
                break

        latest = signals.loc[idx]
        bars_held = max(int((idx - signal_time) / pd.Timedelta("15min")), 0)
        signal_exit = None
        if settings.paper.enable_signal_exit:
            if side == "long" and bool(latest["exit_long"]):
                signal_exit = "signal_exit"
            if side == "short" and bool(latest["exit_short"]):
                signal_exit = "signal_exit"
        if signal_exit is None and bars_held >= settings.backtest.max_holding_bars:
            signal_exit = "horizon"
        if signal_exit is not None:
            exit_time = idx
            exit_reason = signal_exit
            net_return = _net_return(settings, _gross_return(settings, side, entry_price, close), exit_reason)
            break

    payload = dict(decision)
    payload.update(
        {
            "signal_time": str(signal_time),
            "exit_time": str(exit_time),
            "exit_reason_cf": exit_reason,
            "net_return_cf": float(net_return),
        }
    )
    return payload


def _load_enriched_frame(
    symbol: str,
    settings: Settings,
    frame_cache: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    if symbol in frame_cache:
        return frame_cache[symbol]
    path = settings.market_data_root / "klines" / settings.data.timeframe / f"{symbol}.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    if not isinstance(frame.index, pd.DatetimeIndex):
        if "open_time" in frame.columns:
            frame.index = pd.to_datetime(frame["open_time"], utc=True)
        else:
            return None
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    else:
        frame.index = frame.index.tz_convert("UTC")
    enriched = enrich_ohlcv(frame, settings)
    frame_cache[symbol] = enriched
    return enriched


def _variant_for_strategy_id(
    strategy_id: str,
    family: str,
    settings: Settings,
    template_lookup: dict[str, Any],
    variant_lookup: dict[str, Any],
) -> Any | None:
    if strategy_id in variant_lookup:
        return variant_lookup[strategy_id]
    template = template_lookup.get(family)
    if template is None:
        return None
    search_space = getattr(settings.strategy_search, family, {})
    for variant in template.parameter_grid(search_space):
        if variant.strategy_id == strategy_id:
            variant_lookup[strategy_id] = variant
            return variant
    return None


def _risk_levels(settings: Settings, side: str, observed_price: float, atr_value: float) -> tuple[float, float, float]:
    stop_multiple = settings.backtest.stop_atr_multiple * atr_value
    target_multiple = settings.backtest.target_atr_multiple * atr_value
    liquidation_move_fraction = (1 / settings.backtest.leverage) * settings.backtest.liquidation_buffer_fraction
    liquidation_price = observed_price * (1 - liquidation_move_fraction if side == "long" else 1 + liquidation_move_fraction)
    stop_price = observed_price - stop_multiple if side == "long" else observed_price + stop_multiple
    target_price = observed_price + target_multiple if side == "long" else observed_price - target_multiple
    return float(stop_price), float(target_price), float(liquidation_price)


def _gross_return(settings: Settings, side: str, entry_price: float, exit_price: float) -> float:
    raw = (exit_price - entry_price) / entry_price
    if side == "short":
        raw = -raw
    return raw * settings.backtest.leverage * settings.backtest.capital_fraction_per_trade


def _net_return(settings: Settings, gross_return: float, exit_reason: str) -> float:
    fees = (
        2
        * settings.backtest.fee_bps_per_side
        / 10_000
        * settings.backtest.leverage
        * settings.backtest.capital_fraction_per_trade
    )
    if exit_reason == "liquidation" or gross_return <= -settings.backtest.liquidation_loss_fraction:
        return -settings.backtest.liquidation_loss_fraction * settings.backtest.capital_fraction_per_trade
    return gross_return - fees


def _group_pnl(positions: list[dict[str, Any]], key: str, base_equity: float) -> list[dict[str, Any]]:
    if not positions:
        return []
    frame = pd.DataFrame(positions)
    if key not in frame.columns:
        return []
    grouped = (
        frame.groupby(key, dropna=False)
        .agg(trade_count=("net_return", "size"), net_return_sum=("net_return", "sum"))
        .reset_index()
        .sort_values("net_return_sum", ascending=True)
    )
    results: list[dict[str, Any]] = []
    for item in grouped.to_dict(orient="records"):
        results.append(
            {
                "key": str(item[key]),
                "trade_count": int(item["trade_count"]),
                "net_return_sum": float(item["net_return_sum"]),
                "net_pnl_usd": float(item["net_return_sum"]) * base_equity,
            }
        )
    return results


def _serialize_trade(position: dict[str, Any], base_equity: float, position_margin_usd: float) -> dict[str, Any]:
    payload = dict(position)
    net_return = float(payload.get("net_return", 0.0))
    payload["net_pnl_usd"] = net_return * base_equity
    payload["account_net_roi_percent"] = net_return * 100.0
    payload["position_net_roi_percent"] = (payload["net_pnl_usd"] / position_margin_usd) * 100.0 if position_margin_usd else 0.0
    return payload


def _format_optional(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}"
