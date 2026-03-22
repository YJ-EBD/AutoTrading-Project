from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import suppress
from copy import deepcopy
from glob import glob

from ..config import Settings
from ..utils import dump_json
from .research_loop import ResearchLoop


def run_autonomous_loop(settings: Settings) -> dict[str, object]:
    best_result: dict[str, object] | None = None
    best_score = float("-inf")
    stale_iterations = 0
    run_summaries: list[dict[str, object]] = []

    for iteration, mutation_name in enumerate(settings.autoloop.mutation_sequence[: settings.autoloop.max_iterations], start=1):
        candidate_settings = apply_mutation(settings, mutation_name)
        hypothesis = f"Auto-loop iteration {iteration}: {mutation_name}"
        result = ResearchLoop(candidate_settings).run(hypothesis=hypothesis)
        score = score_result(result)
        summary = {
            "iteration": iteration,
            "mutation": mutation_name,
            "score": score,
            "status": result.get("status"),
            "artifact_dir": result.get("artifact_dir"),
        }
        run_summaries.append(summary)
        if score > best_score:
            best_score = score
            best_result = result
            stale_iterations = 0
        else:
            stale_iterations += 1
        if result.get("robustness", {}).get("all_gates_passed"):
            break
        if stale_iterations >= settings.autoloop.max_stale_iterations:
            break

    payload = {
        "best_score": best_score,
        "best_result": best_result,
        "runs": run_summaries,
    }
    dump_json(settings.artifact_root / "latest" / "auto_loop_summary.json", payload)
    return payload


def run_continuous_loop(settings: Settings) -> dict[str, object]:
    latest_dir = settings.artifact_root / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    state_path = latest_dir / "continuous_loop_state.json"
    stop_path = latest_dir / "STOP_AUTO_LOOP"
    lock_path = latest_dir / "continuous_loop.lock"
    acquire_lock(lock_path)
    try:
        state = load_state(state_path)
        sequence = settings.autoloop.mutation_sequence
        while True:
            if stop_path.exists():
                state["stopped_by_signal"] = True
                dump_json(state_path, state)
                return state
            iteration = int(state.get("total_iterations", 0)) + 1
            mutation_name = sequence[(iteration - 1) % len(sequence)]
            state["current_run"] = {
                "iteration": iteration,
                "mutation": mutation_name,
                "started_at": time.time(),
            }
            dump_json(state_path, state)
            candidate_settings = apply_mutation(settings, mutation_name)
            hypothesis = f"Continuous loop iteration {iteration}: {mutation_name}"
            result = ResearchLoop(candidate_settings).run(hypothesis=hypothesis)
            score = score_result(result)
            run_summary = {
                "iteration": iteration,
                "mutation": mutation_name,
                "score": score,
                "status": result.get("status"),
                "artifact_dir": result.get("artifact_dir"),
            }
            state["runs"].append(run_summary)
            state["total_iterations"] = iteration
            state["stopped_by_signal"] = False
            state["current_run"] = None
            if score > float(state.get("best_score", float("-inf"))):
                state["best_score"] = score
                state["best_result"] = result
                state["stale_iterations"] = 0
            else:
                state["stale_iterations"] = int(state.get("stale_iterations", 0)) + 1
            dump_json(state_path, state)
            if result.get("robustness", {}).get("all_gates_passed"):
                state["completed_with_promotion"] = True
                dump_json(state_path, state)
                return state
            time.sleep(settings.autoloop.sleep_seconds_between_iterations)
    finally:
        with suppress(FileNotFoundError):
            lock_path.unlink()


def apply_mutation(settings: Settings, mutation_name: str) -> Settings:
    candidate = deepcopy(settings)
    if mutation_name == "base":
        return candidate
    if mutation_name == "broader_trend_grid":
        candidate.strategy_search.trend_ema["fast_lengths"] = sorted(
            set(candidate.strategy_search.trend_ema["fast_lengths"] + [34])
        )
        candidate.strategy_search.trend_ema["slow_lengths"] = sorted(
            set(candidate.strategy_search.trend_ema["slow_lengths"] + [144])
        )
        candidate.strategy_search.trend_ema["rsi_thresholds"] = sorted(
            set(candidate.strategy_search.trend_ema["rsi_thresholds"] + [50, 60])
        )
        return candidate
    if mutation_name == "breakout_expansion":
        candidate.strategy_search.breakout["windows"] = sorted(
            set(candidate.strategy_search.breakout["windows"] + [15, 40])
        )
        candidate.strategy_search.breakout["atr_filters"] = sorted(
            set(candidate.strategy_search.breakout["atr_filters"] + [1.4])
        )
        return candidate
    if mutation_name == "reversion_expansion":
        candidate.strategy_search.mean_reversion["bb_windows"] = sorted(
            set(candidate.strategy_search.mean_reversion["bb_windows"] + [40])
        )
        candidate.strategy_search.mean_reversion["z_scores"] = sorted(
            set(candidate.strategy_search.mean_reversion["z_scores"] + [2.5])
        )
        candidate.strategy_search.mean_reversion["rsi_thresholds"] = sorted(
            set(candidate.strategy_search.mean_reversion["rsi_thresholds"] + [25, 40])
        )
        candidate.strategy_search.vol_squeeze["squeeze_thresholds"] = sorted(
            set(candidate.strategy_search.vol_squeeze["squeeze_thresholds"] + [0.2, 0.45])
        )
        candidate.strategy_search.vol_squeeze["volume_z_thresholds"] = sorted(
            set(candidate.strategy_search.vol_squeeze["volume_z_thresholds"] + [1.5])
        )
        return candidate
    if mutation_name == "narrower_universe":
        candidate.universe.max_symbols = max(4, candidate.universe.max_symbols - 2)
        return candidate
    if mutation_name == "wider_universe":
        candidate.universe.max_symbols = min(16, candidate.universe.max_symbols + 4)
        return candidate
    if mutation_name == "diversified_candidates":
        candidate.universe.max_symbols = min(12, candidate.universe.max_symbols + 2)
        candidate.research.relaxed_min_positive_symbols = min(
            candidate.universe.max_symbols,
            candidate.research.relaxed_min_positive_symbols + 1,
        )
        return candidate
    if mutation_name == "stricter_costs":
        candidate.backtest.fee_bps_per_side += 0.5
        candidate.backtest.slippage_bps_per_side += 0.5
        return candidate
    if mutation_name == "higher_candidate_bar":
        candidate.research.min_profit_factor += 0.01
        candidate.research.min_expectancy += 0.0002
        return candidate
    return candidate


def score_result(result: dict[str, object]) -> float:
    if result.get("status") in {"rejected", "failed"}:
        return -10.0
    portfolio = result.get("portfolio", {})
    robustness = result.get("robustness", {})
    gates = robustness.get("gates", {})
    score = float(portfolio.get("expectancy", 0.0))
    score += 0.5 * float(result.get("ml", {}).get("best_model", {}).get("aggregate_metrics", {}).get("expectancy_mean", 0.0))
    score += 0.1 * float(result.get("ml", {}).get("best_model", {}).get("aggregate_metrics", {}).get("precision_mean", 0.0))
    score -= max(0.0, float(robustness.get("top_symbol_share", 0.0)) - 0.5)
    score -= max(0.0, float(robustness.get("top_family_share", 0.0)) - 0.7)
    score -= 0.5 if not gates.get("enough_fold_coverage", False) else 0.0
    score -= 0.5 if not gates.get("positive_oos_expectancy", False) else 0.0
    score -= 0.5 if not gates.get("cost_stress_positive", False) else 0.0
    score -= 0.5 if not gates.get("trade_count_ok", False) else 0.0
    score -= 0.3 if not gates.get("symbol_breadth_ok", False) else 0.0
    score -= 0.3 if not gates.get("family_breadth_ok", False) else 0.0
    score -= 0.3 if not gates.get("symbol_concentration_ok", False) else 0.0
    score -= 0.3 if not gates.get("family_concentration_ok", False) else 0.0
    if robustness.get("all_gates_passed"):
        score += 1.0
    return score


def load_state(state_path):
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["stopped_by_signal"] = False
        state["current_run"] = None
        if state.get("best_result") is not None:
            return state
    state = {
        "total_iterations": 0,
        "stale_iterations": 0,
        "best_score": float("-inf"),
        "best_result": None,
        "current_run": None,
        "runs": [],
    }
    seeded = seed_best_from_history(state_path.parent.parent)
    if seeded is not None:
        state["best_score"] = seeded["score"]
        state["best_result"] = seeded["result"]
    return state


def acquire_lock(lock_path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text(encoding="utf-8").strip())
            if process_is_alive(existing_pid):
                raise RuntimeError(f"Continuous loop already running: {lock_path}")
            with suppress(FileNotFoundError):
                lock_path.unlink()
        except (ValueError, RuntimeError):
            raise
        except Exception:
            with suppress(FileNotFoundError):
                lock_path.unlink()
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Continuous loop already running: {lock_path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def seed_best_from_history(artifact_root) -> dict[str, object] | None:
    best: dict[str, object] | None = None
    for path in glob(str(artifact_root / "2026*" / "research_summary.json")):
        with suppress(Exception):
            result = json.loads(open(path, "r", encoding="utf-8").read())
            score = score_result(result)
            if best is None or score > best["score"]:
                best = {"score": score, "result": result}
    return best
