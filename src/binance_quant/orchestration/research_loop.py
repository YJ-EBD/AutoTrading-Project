from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd

from ..backtest.engine import VectorizedBacktester
from ..config import Settings
from ..data.ingestion import KlineIngestionService
from ..exchange.client import BinancePublicClient, ClientDependencies
from ..exchange.rate_limit import RateBudgetManager
from ..exchange.universe import UniverseManager
from ..features.engine import enrich_ohlcv, feature_matrix
from ..labeling.triple_barrier import build_event_dataset
from ..ml.modeling import evaluate_models
from ..portfolio.engine import build_portfolio
from ..reporting.reports import build_markdown_summary, persist_report_bundle
from ..storage import DiskCache, ExperimentRegistry
from ..strategies.parity import run_semantic_parity_checks
from ..strategies.templates import build_strategy_templates
from ..utils import dump_json, seed_everything


LOGGER = logging.getLogger(__name__)


class ResearchLoop:
    def __init__(self, settings: Settings):
        self.settings = settings
        cache = DiskCache(settings.cache_root)
        rate_budget = RateBudgetManager(settings.exchange)
        dependencies = ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget)
        self.client = BinancePublicClient(dependencies)
        self.universe_manager = UniverseManager(settings, self.client)
        self.ingestion = KlineIngestionService(settings, self.client)
        self.backtester = VectorizedBacktester(settings.backtest)
        self.registry = ExperimentRegistry(settings.registry_db)
        self.rate_budget = rate_budget

    def run(self, hypothesis: str = "Baseline diversified Pine pool with meta-label filter.") -> dict[str, object]:
        seed_everything(self.settings.research.random_seed)
        experiment_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        artifact_dir = self.settings.artifact_root / experiment_id
        latest_dir = self.settings.artifact_root / "latest"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        latest_dir.mkdir(parents=True, exist_ok=True)
        self.registry.start(experiment_id, hypothesis, self.settings, artifact_dir)
        self.registry.log(experiment_id, "hypothesis", hypothesis)
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="starting",
            experiment_id=experiment_id,
            hypothesis=hypothesis,
        )

        parity_results = run_semantic_parity_checks()
        if not all(item.passed for item in parity_results):
            failure = "Pine/Python parity checks failed."
            self.registry.complete(experiment_id, "failed", {"parity_passed": False}, failure)
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="failed",
                experiment_id=experiment_id,
                failure=failure,
            )
            raise RuntimeError(failure)
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="parity_passed",
            experiment_id=experiment_id,
            parity_checks=len(parity_results),
        )

        universe = self.universe_manager.discover(artifact_dir=artifact_dir)
        symbols = universe["symbol"].tolist()
        if not symbols:
            metrics = {"eligible_symbols": 0.0}
            self.registry.complete(experiment_id, "rejected", metrics, "No eligible symbols found.")
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="rejected",
                experiment_id=experiment_id,
                reason="No eligible symbols found.",
            )
            return {"status": "rejected", "reason": "No eligible symbols found.", "artifact_dir": str(artifact_dir)}
        self.registry.log(experiment_id, "universe", f"Selected symbols: {symbols}")
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="universe_ready",
            experiment_id=experiment_id,
            symbol_count=len(symbols),
            symbols=symbols,
        )

        enriched_by_symbol: dict[str, pd.DataFrame] = {}
        for index, symbol in enumerate(symbols, start=1):
            raw = self.ingestion.backfill_symbol(symbol, artifact_dir=artifact_dir)
            enriched_by_symbol[symbol] = enrich_ohlcv(raw, self.settings)
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="ingesting_market_data",
                experiment_id=experiment_id,
                completed_symbols=index,
                total_symbols=len(symbols),
                current_symbol=symbol,
            )

        templates = build_strategy_templates()
        pre_screen_rows: list[dict[str, object]] = []
        candidate_trade_map: dict[str, pd.DataFrame] = {}
        strategy_lookup: dict[str, str] = {}

        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="pre_screen_started",
            experiment_id=experiment_id,
            template_count=len(templates),
        )
        for template_index, template in enumerate(templates, start=1):
            search_space = getattr(self.settings.strategy_search, template.family)
            variant_count = 0
            for variant in template.parameter_grid(search_space):
                variant_count += 1
                strategy_lookup[variant.strategy_id] = variant.family
                aggregate_trades: list[pd.DataFrame] = []
                aggregate_metrics: list[dict[str, float]] = []
                symbol_metric_rows: list[dict[str, float | str]] = []
                pine_script = None
                for symbol, frame in enriched_by_symbol.items():
                    signal_frame = template.generate(frame, variant)
                    pine_script = pine_script or signal_frame.pine_script
                    frame_for_backtest = frame.copy()
                    frame_for_backtest["atr"] = frame["atr_14"].ffill().fillna(frame["close"] * 0.01)
                    result = self.backtester.run(symbol, frame_for_backtest, signal_frame.signals, variant)
                    if not result.trades.empty:
                        result.trades["signal_strength"] = (
                            signal_frame.signals.reindex(result.trades["entry_time"])["signal_strength"].to_numpy()
                        )
                        aggregate_trades.append(result.trades)
                    aggregate_metrics.append(result.metrics)
                    symbol_metric_rows.append(
                        {
                            "symbol": symbol,
                            "trade_count": float(result.metrics["trade_count"]),
                            "expectancy": float(result.metrics["expectancy"]),
                            "profit_factor": float(result.metrics["profit_factor"]),
                            "max_drawdown": float(result.metrics["max_drawdown"]),
                        }
                    )
                if aggregate_trades:
                    candidate_trade_map[variant.strategy_id] = pd.concat(aggregate_trades).reset_index(drop=True)
                metrics_frame = pd.DataFrame(aggregate_metrics)
                if metrics_frame.empty:
                    continue
                symbol_metrics = pd.DataFrame(symbol_metric_rows)
                summary = {
                    "strategy_id": variant.strategy_id,
                    "family": variant.family,
                    "trade_count": float(metrics_frame["trade_count"].sum()),
                    "expectancy": float(metrics_frame["expectancy"].mean()),
                    "profit_factor": float(metrics_frame["profit_factor"].mean()),
                    "max_drawdown": float(metrics_frame["max_drawdown"].max()),
                    "positive_symbol_count": int((symbol_metrics["expectancy"] > 0).sum()) if not symbol_metrics.empty else 0,
                    "non_negative_symbol_count": int((symbol_metrics["expectancy"] >= 0).sum()) if not symbol_metrics.empty else 0,
                    "pine_script": pine_script,
                }
                strict_survived = bool(
                    summary["trade_count"] >= self.settings.research.min_candidate_trades
                    and summary["expectancy"] >= self.settings.research.min_expectancy
                    and summary["profit_factor"] >= self.settings.research.min_profit_factor
                    and summary["max_drawdown"] <= self.settings.research.max_drawdown_fraction
                )
                relaxed_survived = bool(
                    summary["trade_count"] >= self.settings.research.min_candidate_trades
                    and summary["expectancy"] >= self.settings.research.relaxed_min_expectancy
                    and summary["profit_factor"] >= self.settings.research.relaxed_min_profit_factor
                    and summary["max_drawdown"] <= self.settings.research.relaxed_max_drawdown_fraction
                    and summary["positive_symbol_count"] >= self.settings.research.relaxed_min_positive_symbols
                )
                summary["strict_survived"] = strict_survived
                summary["ml_candidate_survived"] = relaxed_survived
                summary["survived"] = strict_survived or relaxed_survived
                summary["family_seed_survived"] = False
                summary["survival_tier"] = (
                    "strict" if strict_survived else "ml_candidate" if relaxed_survived else "rejected"
                )
                pre_screen_rows.append(summary)
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="pre_screen_family_complete",
                experiment_id=experiment_id,
                completed_templates=template_index,
                total_templates=len(templates),
                family=template.family,
                family_variant_count=variant_count,
                survivors_so_far=sum(1 for row in pre_screen_rows if row.get("survived")),
            )

        if pre_screen_rows:
            pre_screen = pd.DataFrame(pre_screen_rows).sort_values(["survived", "expectancy"], ascending=[False, False])
        else:
            pre_screen = pd.DataFrame(
                columns=[
                    "strategy_id",
                    "family",
                    "trade_count",
                    "expectancy",
                    "profit_factor",
                    "max_drawdown",
                    "positive_symbol_count",
                    "non_negative_symbol_count",
                    "strict_survived",
                    "ml_candidate_survived",
                    "family_seed_survived",
                    "survival_tier",
                    "survived",
                ]
            )
        pre_screen = self._apply_family_seed_rescue(pre_screen)
        selected_strategy_ids = self._select_diversified_survivors(pre_screen, candidate_trade_map)
        pre_screen["selected_for_ml"] = pre_screen["strategy_id"].isin(selected_strategy_ids)
        persist_report_bundle(artifact_dir, {"pre_screen": pre_screen})
        if not selected_strategy_ids:
            metrics = {"candidate_count": float(len(pre_screen)), "survivor_count": 0.0}
            self.registry.complete(experiment_id, "rejected", metrics, "No strategies passed pre-screen.")
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="rejected",
                experiment_id=experiment_id,
                reason="No strategies passed pre-screen.",
                candidate_count=len(pre_screen),
            )
            return {"status": "rejected", "reason": "No strategies passed pre-screen.", "artifact_dir": str(artifact_dir)}

        survivor_trades = [candidate_trade_map[strategy_id] for strategy_id in selected_strategy_ids if strategy_id in candidate_trade_map]
        if not survivor_trades:
            metrics = {"candidate_count": float(len(pre_screen)), "survivor_count": float(len(selected_strategy_ids))}
            self.registry.complete(experiment_id, "rejected", metrics, "No trade data remained after survivor diversification.")
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="rejected",
                experiment_id=experiment_id,
                reason="No trade data remained after survivor diversification.",
                candidate_count=len(pre_screen),
            )
            return {
                "status": "rejected",
                "reason": "No trade data remained after survivor diversification.",
                "artifact_dir": str(artifact_dir),
            }

        trades = pd.concat(survivor_trades).sort_values("entry_time").reset_index(drop=True)
        events = build_event_dataset(trades, enriched_by_symbol, strategy_lookup, self.settings.labeling)
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="event_dataset_ready",
            experiment_id=experiment_id,
            event_count=len(events),
            survivor_count=int(pre_screen["survived"].sum()),
        )
        if len(events) < self.settings.ml.min_events:
            metrics = {"candidate_count": float(len(pre_screen)), "survivor_count": float(pre_screen["survived"].sum())}
            self.registry.complete(experiment_id, "rejected", metrics, "Insufficient event count for ML validation.")
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="rejected",
                experiment_id=experiment_id,
                reason="Insufficient event count for ML validation.",
                event_count=len(events),
            )
            return {
                "status": "rejected",
                "reason": "Insufficient event count for ML validation.",
                "artifact_dir": str(artifact_dir),
            }

        features, diagnostics = feature_matrix(events)
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="model_evaluation_started",
            experiment_id=experiment_id,
            feature_count=len(features.columns),
            event_count=len(events),
        )
        model_evaluations = evaluate_models(features, events, self.settings)
        if not model_evaluations:
            metrics = {"event_count": float(len(events)), "model_evaluations": 0.0}
            self.registry.complete(experiment_id, "rejected", metrics, "No model/calibration pairs passed threshold selection.")
            self._write_progress(
                artifact_dir,
                latest_dir,
                stage="rejected",
                experiment_id=experiment_id,
                reason="No model/calibration pairs passed threshold selection.",
                event_count=len(events),
            )
            return {
                "status": "rejected",
                "reason": "No model/calibration pairs passed threshold selection.",
                "artifact_dir": str(artifact_dir),
            }

        best_model = max(
            model_evaluations,
            key=lambda item: (
                item.aggregate_metrics["expectancy_mean"],
                item.aggregate_metrics["precision_mean"],
                item.aggregate_metrics["trade_count"],
            ),
        )
        portfolio = build_portfolio(best_model.accepted_events, self.settings)
        robustness = self._robustness_report(best_model, portfolio)

        status = "accepted_for_paper" if robustness["all_gates_passed"] else "needs_iteration"
        milestone = {
            "hypothesis": hypothesis,
            "status": status,
            "artifact_dir": str(artifact_dir),
            "universe": {"eligible_symbols": int(len(universe)), "selected_symbols": symbols},
            "pre_screen": {"candidate_count": int(len(pre_screen)), "survivor_count": int(pre_screen["survived"].sum())},
            "ml": {
                "event_count": int(len(events)),
                "model_evaluations": int(len(model_evaluations)),
                "best_model": {
                    "model_name": best_model.model_name,
                    "calibration_method": best_model.calibration_method,
                    "aggregate_metrics": best_model.aggregate_metrics,
                },
            },
            "portfolio": portfolio.metrics,
            "robustness": robustness,
        }

        dump_json(artifact_dir / "research_summary.json", milestone)
        dump_json(artifact_dir / "feature_diagnostics.json", asdict(diagnostics))
        persist_report_bundle(
            artifact_dir,
            {
                "events": events,
                "accepted_events": best_model.accepted_events,
                "portfolio_trades": portfolio.accepted_trades,
                "survivor_groups": portfolio.survivor_groups,
                "robustness": robustness,
                "best_model": {
                    "model_name": best_model.model_name,
                    "calibration_method": best_model.calibration_method,
                    "aggregate_metrics": best_model.aggregate_metrics,
                    "feature_importance": best_model.feature_importance,
                    "fold_results": [item.__dict__ for item in best_model.fold_results],
                },
                "api_telemetry": self.rate_budget.snapshot(),
            },
        )
        summary_markdown = build_markdown_summary(milestone)
        (artifact_dir / "research_summary.md").write_text(summary_markdown, encoding="utf-8")
        (latest_dir / "research_summary.md").write_text(summary_markdown, encoding="utf-8")
        dump_json(latest_dir / "research_summary.json", milestone)
        self._write_progress(
            artifact_dir,
            latest_dir,
            stage="completed",
            experiment_id=experiment_id,
            status=status,
            trade_count=portfolio.metrics.get("trade_count", 0),
            portfolio_expectancy=portfolio.metrics.get("expectancy", 0.0),
        )

        self.registry.complete(experiment_id, status, milestone)
        return milestone

    def _apply_family_seed_rescue(self, pre_screen: pd.DataFrame) -> pd.DataFrame:
        if pre_screen.empty:
            return pre_screen

        frame = pre_screen.copy()
        if "family_seed_survived" not in frame:
            frame["family_seed_survived"] = False
        survived_families = set(frame.loc[frame["survived"], "family"].astype(str))
        target_families = self.settings.portfolio.min_distinct_families
        if len(survived_families) >= target_families:
            return frame

        rescue_mask = (
            (~frame["survived"].astype(bool))
            & (frame["trade_count"] >= self.settings.research.min_candidate_trades)
            & (
                frame["expectancy"]
                >= self.settings.research.relaxed_min_expectancy - self.settings.research.family_seed_expectancy_margin
            )
            & (
                frame["profit_factor"]
                >= self.settings.research.relaxed_min_profit_factor - self.settings.research.family_seed_profit_factor_margin
            )
            & (
                frame["max_drawdown"]
                <= self.settings.research.relaxed_max_drawdown_fraction + self.settings.research.family_seed_max_drawdown_buffer
            )
            & (frame["positive_symbol_count"] >= max(1, self.settings.research.relaxed_min_positive_symbols - 1))
        )
        rescue_candidates = frame[rescue_mask].copy()
        if rescue_candidates.empty:
            return frame

        for family in rescue_candidates["family"].drop_duplicates().tolist():
            if len(survived_families) >= target_families:
                break
            if family in survived_families:
                continue
            family_rows = rescue_candidates[rescue_candidates["family"] == family].sort_values(
                ["positive_symbol_count", "profit_factor", "expectancy", "trade_count"],
                ascending=[False, False, False, False],
            )
            if family_rows.empty:
                continue
            strategy_id = family_rows.iloc[0]["strategy_id"]
            frame.loc[frame["strategy_id"] == strategy_id, "ml_candidate_survived"] = True
            frame.loc[frame["strategy_id"] == strategy_id, "family_seed_survived"] = True
            frame.loc[frame["strategy_id"] == strategy_id, "survived"] = True
            frame.loc[frame["strategy_id"] == strategy_id, "survival_tier"] = "family_seed"
            survived_families.add(str(family))

        return frame.sort_values(["survived", "family_seed_survived", "expectancy"], ascending=[False, False, False]).reset_index(drop=True)

    def _select_diversified_survivors(
        self,
        pre_screen: pd.DataFrame,
        candidate_trade_map: dict[str, pd.DataFrame],
    ) -> list[str]:
        if pre_screen.empty:
            return []

        survivors = pre_screen[pre_screen["survived"]].copy()
        if survivors.empty:
            return []
        survivors["selection_priority"] = survivors["strict_survived"].astype(int) * 2 + survivors["family_seed_survived"].astype(int)
        survivors = survivors.sort_values(
            [
                "selection_priority",
                "positive_symbol_count",
                "profit_factor",
                "expectancy",
                "trade_count",
            ],
            ascending=[False, False, False, False, False],
        )

        selected_ids: list[str] = []
        family_counts: dict[str, int] = {}
        family_signal_sets: dict[str, list[set[tuple[str, str, str]]]] = {}

        for row in survivors.itertuples(index=False):
            strategy_id = str(row.strategy_id)
            trades = candidate_trade_map.get(strategy_id)
            if trades is None or trades.empty:
                continue
            family = str(row.family)
            if family_counts.get(family, 0) >= self.settings.research.max_survivors_per_family:
                continue
            signal_set = {
                (str(item.symbol), str(pd.Timestamp(item.entry_time)), str(item.side))
                for item in trades[["symbol", "entry_time", "side"]].itertuples(index=False)
            }
            overlap_too_high = False
            for existing in family_signal_sets.get(family, []):
                union = signal_set | existing
                if not union:
                    continue
                similarity = len(signal_set & existing) / len(union)
                if similarity >= self.settings.research.max_signal_overlap:
                    overlap_too_high = True
                    break
            if overlap_too_high:
                continue
            selected_ids.append(strategy_id)
            family_counts[family] = family_counts.get(family, 0) + 1
            family_signal_sets.setdefault(family, []).append(signal_set)

        return selected_ids

    def _write_progress(
        self,
        artifact_dir,
        latest_dir,
        *,
        stage: str,
        experiment_id: str,
        **details: object,
    ) -> None:
        payload = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "experiment_id": experiment_id,
            "stage": stage,
            **details,
        }
        dump_json(artifact_dir / "progress.json", payload)
        dump_json(latest_dir / "research_progress.json", payload)
        LOGGER.info("Research progress stage=%s details=%s", stage, details)

    def _robustness_report(self, best_model, portfolio) -> dict[str, object]:
        fold_expectancies = [item.expectancy for item in best_model.fold_results]
        fold_precisions = [item.precision for item in best_model.fold_results]
        thresholds = [item.threshold for item in best_model.fold_results]
        threshold_std = float(pd.Series(thresholds).std(ddof=0) if thresholds else 0.0)
        cost_penalty = 2 * self.settings.ml.cost_stress_bps_per_side / 10_000 * self.settings.backtest.leverage
        stressed_expectancy = float(portfolio.accepted_trades["net_return"].mean() - cost_penalty) if not portfolio.accepted_trades.empty else 0.0
        portfolio_trade_count = int(len(portfolio.accepted_trades))
        distinct_symbols = int(portfolio.accepted_trades["symbol"].nunique()) if not portfolio.accepted_trades.empty else 0
        distinct_families = int(portfolio.accepted_trades["family"].nunique()) if not portfolio.accepted_trades.empty else 0
        top_symbol_share = (
            float(portfolio.accepted_trades["symbol"].value_counts(normalize=True).iloc[0])
            if not portfolio.accepted_trades.empty
            else 0.0
        )
        top_family_share = (
            float(portfolio.accepted_trades["family"].value_counts(normalize=True).iloc[0])
            if not portfolio.accepted_trades.empty
            else 0.0
        )
        monte_carlo = self._monte_carlo_negative_rate(portfolio.accepted_trades["net_return"]) if not portfolio.accepted_trades.empty else 1.0
        gates = {
            "enough_fold_coverage": len(fold_expectancies) >= 2,
            "positive_oos_expectancy": portfolio.metrics["expectancy"] > 0,
            "positive_fold_expectancy": sum(value > 0 for value in fold_expectancies) >= max(1, len(fold_expectancies) - 1),
            "threshold_stable": threshold_std <= 0.1,
            "cost_stress_positive": stressed_expectancy > 0,
            "trade_count_ok": portfolio_trade_count >= self.settings.portfolio.min_portfolio_trades,
            "symbol_breadth_ok": distinct_symbols >= self.settings.portfolio.min_distinct_symbols,
            "family_breadth_ok": distinct_families >= self.settings.portfolio.min_distinct_families,
            "symbol_concentration_ok": top_symbol_share <= self.settings.portfolio.max_symbol_weight,
            "family_concentration_ok": top_family_share <= self.settings.portfolio.max_strategy_weight,
            "precision_ok": float(pd.Series(fold_precisions).mean()) >= 0.5,
            "monte_carlo_ok": monte_carlo <= 0.4,
        }
        return {
            "fold_expectancies": fold_expectancies,
            "threshold_std": threshold_std,
            "stressed_expectancy": stressed_expectancy,
            "portfolio_trade_count": portfolio_trade_count,
            "distinct_symbols": distinct_symbols,
            "distinct_families": distinct_families,
            "top_symbol_share": top_symbol_share,
            "top_family_share": top_family_share,
            "monte_carlo_negative_rate": monte_carlo,
            "gates": gates,
            "all_gates_passed": all(gates.values()),
        }

    def _monte_carlo_negative_rate(self, returns: pd.Series) -> float:
        if returns.empty:
            return 1.0
        samples = [float(returns.sample(frac=1.0, replace=True).mean()) for _ in range(self.settings.research.monte_carlo_iterations)]
        return float((pd.Series(samples) <= 0).mean())
