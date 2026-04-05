from pathlib import Path

import pandas as pd
import pytest

from binance_quant.config import Settings
from binance_quant.paper.analysis import (
    adaptive_deployment_gate,
    effective_live_threshold,
    evaluate_counterfactual_thresholds,
    recent_family_loss_cooldown_reason,
    recent_loss_cooldown_reason,
    strategy_performance_block_reason,
    symbol_performance_block_reason,
    should_trigger_loss_retune,
    summarize_paper_performance,
)


def test_loss_summary_triggers_retune_and_threshold_boost() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    positions = [
        {
            "status": "closed",
            "symbol": "TAOUSDT",
            "strategy_id": "trend_ema_fast12",
            "side": "long",
            "closed_at": "2026-03-23T06:44:59+00:00",
            "net_return": -0.015,
        },
        {
            "status": "closed",
            "symbol": "BTCUSDT",
            "strategy_id": "trend_pullback_21_55",
            "side": "short",
            "closed_at": "2026-03-23T07:44:59+00:00",
            "net_return": -0.01,
        },
    ]
    decisions = [{"final_action": "allow", "portfolio_reason": "llm_allow"}]

    summary = summarize_paper_performance(
        positions=positions,
        decisions=decisions,
        settings=settings,
        base_threshold=0.625,
    )

    assert summary["loss_streak"] == 2
    assert summary["retune_triggered"] is True
    assert summary["realized_net_pnl_usd"] == -25.0
    assert summary["recommended_threshold"] == 0.725
    assert effective_live_threshold(0.625, settings, summary) == pytest.approx(0.1)
    assert should_trigger_loss_retune(summary, settings, last_attempt_at=None) is True


def test_recent_loss_cooldown_reason_detects_symbol_and_strategy() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    positions = [
        {
            "status": "closed",
            "symbol": "BTCUSDT",
            "strategy_id": "trend_ema_fast9",
            "side": "long",
            "closed_at": "2026-03-23T00:00:00+00:00",
            "net_return": -0.01,
        },
        {
            "status": "closed",
            "symbol": "ETHUSDT",
            "strategy_id": "trend_pullback_21_55",
            "side": "short",
            "closed_at": "2026-03-23T00:00:00+00:00",
            "net_return": -0.02,
        },
    ]

    same_symbol_reason = recent_loss_cooldown_reason(
        positions,
        symbol="BTCUSDT",
        strategy_id="another_strategy",
        signal_time=pd.Timestamp("2026-03-23T00:30:00+00:00"),
        settings=settings,
    )
    same_strategy_reason = recent_loss_cooldown_reason(
        positions,
        symbol="SOLUSDT",
        strategy_id="trend_pullback_21_55",
        signal_time=pd.Timestamp("2026-03-23T02:00:00+00:00"),
        settings=settings,
    )

    assert same_symbol_reason == "recent_symbol_loss_cooldown"
    assert same_strategy_reason == "recent_strategy_loss_cooldown"


def test_adaptive_deployment_gate_tightens_after_loss_trigger() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    result = {
        "status": "accepted_for_paper",
        "portfolio": {"trade_count": 10, "expectancy": 0.011, "precision": 0.59},
        "robustness": {"all_gates_passed": True, "distinct_symbols": 4, "distinct_families": 2},
    }

    normal_gate = adaptive_deployment_gate(result, settings, loss_triggered=False)
    loss_gate = adaptive_deployment_gate(result, settings, loss_triggered=True)

    assert normal_gate["deploy"] is True
    assert loss_gate["deploy"] is False
    assert loss_gate["gates"]["loss_mode_trade_count_ok"] is False
    assert loss_gate["gates"]["loss_mode_expectancy_ok"] is False
    assert loss_gate["gates"]["loss_mode_precision_ok"] is False


def test_adaptive_deployment_gate_can_allow_emergency_candidate_for_paper() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    result = {
        "status": "needs_iteration",
        "portfolio": {"trade_count": 9, "expectancy": 0.02, "precision": 0.8},
        "robustness": {
            "all_gates_passed": False,
            "distinct_symbols": 4,
            "distinct_families": 2,
            "gates": {
                "positive_fold_expectancy": True,
                "threshold_stable": True,
                "cost_stress_positive": True,
                "monte_carlo_ok": True,
            },
        },
    }

    gate = adaptive_deployment_gate(result, settings, loss_triggered=True)

    assert gate["deploy"] is True
    assert gate["deployment_mode"] == "emergency_candidate"
    assert gate["gates"]["candidate_status_ok"] is True


def test_adaptive_deployment_gate_can_allow_throughput_candidate_when_trade_flow_is_short(tmp_path: Path) -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    artifact_dir = tmp_path / "artifact"
    reports_dir = artifact_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "pre_screen.csv").write_text(
        "strategy_id,family,selected_for_ml,survived\n"
        "trend_ema__directionlong_only_fast21_rsi_threshold58.0_slow89,trend_ema,True,True\n",
        encoding="utf-8",
    )
    result = {
        "artifact_dir": str(artifact_dir),
        "status": "needs_iteration",
        "portfolio": {"trade_count": 45, "expectancy": 0.022, "precision": 0.82},
        "robustness": {
            "all_gates_passed": False,
            "distinct_symbols": 7,
            "distinct_families": 1,
            "top_symbol_share": 0.2,
            "gates": {
                "positive_fold_expectancy": True,
                "threshold_stable": True,
                "cost_stress_positive": True,
                "monte_carlo_ok": True,
            },
        },
    }

    gate = adaptive_deployment_gate(
        result,
        settings,
        loss_triggered=True,
        performance_summary={
            "recent_open_count_lookback": 1,
            "worst_families": [{"key": "trend_pullback"}],
        },
    )

    assert gate["deploy"] is True
    assert gate["deployment_mode"] == "throughput_candidate"
    assert gate["gates"]["throughput_shortfall_ok"] is True
    assert gate["gates"]["throughput_not_live_worst_family_only"] is True


def test_effective_live_threshold_lowers_when_trade_flow_is_below_target() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    summary = {
        "recommended_threshold": 0.45,
        "recent_open_count_lookback": 1,
    }

    threshold = effective_live_threshold(0.625, settings, summary)

    assert threshold == settings.paper.min_live_threshold_floor


def test_counterfactual_threshold_sweep_prefers_lower_threshold_when_recent_live_outcomes_support_it() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    decision_rows = [
        {
            "decision_id": 1,
            "signal_time": "2026-03-23T00:00:00+00:00",
            "exit_time": "2026-03-23T01:00:00+00:00",
            "symbol": "BTCUSDT",
            "ml_probability": 0.49,
            "net_return_cf": 0.02,
        },
        {
            "decision_id": 2,
            "signal_time": "2026-03-23T00:15:00+00:00",
            "exit_time": "2026-03-23T01:15:00+00:00",
            "symbol": "ETHUSDT",
            "ml_probability": 0.48,
            "net_return_cf": 0.01,
        },
        {
            "decision_id": 3,
            "signal_time": "2026-03-23T00:30:00+00:00",
            "exit_time": "2026-03-23T01:30:00+00:00",
            "symbol": "SOLUSDT",
            "ml_probability": 0.70,
            "net_return_cf": -0.02,
        },
    ]

    thresholds = evaluate_counterfactual_thresholds(decision_rows, settings, [0.45, 0.625])

    low = next(item for item in thresholds if item["threshold"] == 0.45)
    high = next(item for item in thresholds if item["threshold"] == 0.625)

    assert low["sum_net_return"] > high["sum_net_return"]
    assert low["accepted_count"] == 3
    assert high["accepted_count"] == 1


def test_recent_family_loss_cooldown_reason_detects_bad_family_cluster() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    positions = [
        {
            "status": "closed",
            "family": "trend_pullback",
            "closed_at": "2026-03-25T02:30:00+00:00",
            "net_return": -0.015,
        },
        {
            "status": "closed",
            "family": "trend_pullback",
            "closed_at": "2026-03-25T04:30:00+00:00",
            "net_return": -0.012,
        },
    ]

    reason = recent_family_loss_cooldown_reason(
        positions,
        family="trend_pullback",
        signal_time=pd.Timestamp("2026-03-25T06:00:00+00:00"),
        settings=settings,
    )

    assert reason == "recent_family_loss_cooldown"


def test_strategy_performance_block_reason_detects_live_underperformer() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    positions = [
        {
            "status": "closed",
            "strategy_id": "trend_pullback__fast21_pullback_rsi45.0_slow55",
            "closed_at": "2026-03-24T00:00:00+00:00",
            "net_return": -0.021,
        },
        {
            "status": "closed",
            "strategy_id": "trend_pullback__fast21_pullback_rsi45.0_slow55",
            "closed_at": "2026-03-26T00:00:00+00:00",
            "net_return": -0.016,
        },
        {
            "status": "closed",
            "strategy_id": "trend_pullback__fast21_pullback_rsi45.0_slow55",
            "closed_at": "2026-03-28T00:00:00+00:00",
            "net_return": -0.012,
        },
    ]

    reason = strategy_performance_block_reason(
        positions,
        strategy_id="trend_pullback__fast21_pullback_rsi45.0_slow55",
        signal_time=pd.Timestamp("2026-03-29T00:00:00+00:00"),
        settings=settings,
    )

    assert reason == "strategy_performance_block"


def test_symbol_performance_block_reason_detects_live_underperformer_symbol() -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    positions = [
        {
            "status": "closed",
            "symbol": "TAOUSDT",
            "closed_at": "2026-03-24T00:00:00+00:00",
            "net_return": -0.019,
        },
        {
            "status": "closed",
            "symbol": "TAOUSDT",
            "closed_at": "2026-03-26T00:00:00+00:00",
            "net_return": -0.017,
        },
        {
            "status": "closed",
            "symbol": "TAOUSDT",
            "closed_at": "2026-03-28T00:00:00+00:00",
            "net_return": -0.014,
        },
    ]

    reason = symbol_performance_block_reason(
        positions,
        symbol="TAOUSDT",
        signal_time=pd.Timestamp("2026-03-29T00:00:00+00:00"),
        settings=settings,
    )

    assert reason == "symbol_performance_block"
