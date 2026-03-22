from __future__ import annotations

import logging
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..backtest.engine import VectorizedBacktester
from ..config import Settings
from ..data.ingestion import KlineIngestionService
from ..exchange.client import BinancePublicClient, ClientDependencies
from ..exchange.rate_limit import RateBudgetManager
from ..features.engine import enrich_ohlcv, feature_matrix
from ..labeling.triple_barrier import build_event_dataset
from ..storage import DiskCache
from ..strategies.base import StrategyVariant
from ..strategies.templates import build_strategy_templates
from ..utils import dump_json, load_json, seed_everything, utc_now
from .modeling import (
    ProbabilityCalibrator,
    build_model_registry,
    clone_estimator,
    predict_probabilities,
)


LOGGER = logging.getLogger(__name__)


@dataclass
class DeploymentManifest:
    built_at: str
    source_artifact: str
    model_name: str
    calibration_method: str
    threshold: float
    event_count: int
    feature_columns: list[str]
    selected_symbols: list[str]
    selected_strategy_ids: list[str]
    selected_variants: list[dict[str, Any]]


@dataclass
class PaperDeploymentBundle:
    manifest: DeploymentManifest
    estimator: Any
    calibrator: ProbabilityCalibrator | None

    def probability_from_event_frame(self, event_frame: pd.DataFrame) -> float:
        features, _ = feature_matrix(event_frame)
        aligned = features.reindex(columns=self.manifest.feature_columns, fill_value=0.0)
        raw = predict_probabilities(self.estimator, aligned)
        if self.calibrator is None:
            return float(raw[0])
        calibrated = self.calibrator.predict(raw)
        return float(calibrated[0])

    def probability_from_event(self, event_row: dict[str, Any]) -> float:
        return self.probability_from_event_frame(pd.DataFrame([event_row]))

    def save(self, bundle_path: Path, manifest_path: Path) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with bundle_path.open("wb") as handle:
            pickle.dump(self, handle)
        dump_json(manifest_path, asdict(self.manifest))


def load_deployment_bundle(bundle_path: Path) -> PaperDeploymentBundle:
    with bundle_path.open("rb") as handle:
        return pickle.load(handle)


def resolve_source_artifact(settings: Settings, source_artifact: str | Path | None = None) -> Path:
    source = str(source_artifact or settings.deployment.source_artifact)
    if source == "latest_accepted":
        candidates: list[Path] = []
        for child in settings.artifact_root.iterdir():
            if not child.is_dir() or child.name == "latest":
                continue
            summary_path = child / "research_summary.json"
            if not summary_path.exists():
                continue
            try:
                payload = load_json(summary_path)
            except Exception:
                continue
            if payload.get("status") == "accepted_for_paper":
                candidates.append(child)
        if not candidates:
            raise FileNotFoundError("No accepted_for_paper artifact found.")
        return sorted(candidates)[-1]
    if source == "latest":
        latest_summary = settings.artifact_root / "latest" / "research_summary.json"
        if not latest_summary.exists():
            raise FileNotFoundError("artifacts/latest/research_summary.json not found.")
        payload = load_json(latest_summary)
        artifact_dir = payload.get("artifact_dir")
        if artifact_dir:
            return Path(artifact_dir).resolve()
        raise FileNotFoundError("Latest research summary did not contain artifact_dir.")
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = (settings.project_root / candidate).resolve()
    return candidate


def build_deployment_bundle(settings: Settings, source_artifact: str | Path | None = None) -> PaperDeploymentBundle:
    seed_everything(settings.research.random_seed)
    artifact_dir = resolve_source_artifact(settings, source_artifact)
    manifest_payload = load_json(artifact_dir / "reports" / "best_model.json")
    selected_strategy_ids = _selected_strategy_ids(artifact_dir)
    selected_symbols = _selected_symbols(artifact_dir)
    variants = _selected_variants(settings, selected_strategy_ids)
    events = _rebuild_events(settings, selected_symbols, variants)
    if events.empty:
        raise RuntimeError(f"No events rebuilt for deployment source {artifact_dir}")

    estimator, calibrator, feature_columns = _fit_deployment_components(settings, events, manifest_payload)
    threshold = float(manifest_payload["aggregate_metrics"]["threshold_mean"])
    manifest = DeploymentManifest(
        built_at=utc_now().isoformat(),
        source_artifact=str(artifact_dir),
        model_name=str(manifest_payload["model_name"]),
        calibration_method=str(manifest_payload["calibration_method"]),
        threshold=threshold,
        event_count=int(len(events)),
        feature_columns=feature_columns,
        selected_symbols=selected_symbols,
        selected_strategy_ids=selected_strategy_ids,
        selected_variants=[asdict(variant) for variant in variants],
    )
    bundle = PaperDeploymentBundle(manifest=manifest, estimator=estimator, calibrator=calibrator)
    bundle.save(settings.deployment_bundle_path, settings.deployment_manifest_path)
    LOGGER.info(
        "Built deployment bundle from artifact=%s model=%s calibration=%s threshold=%.3f events=%s",
        artifact_dir,
        manifest.model_name,
        manifest.calibration_method,
        manifest.threshold,
        manifest.event_count,
    )
    return bundle


def _selected_strategy_ids(artifact_dir: Path) -> list[str]:
    pre_screen_path = artifact_dir / "reports" / "pre_screen.csv"
    pre_screen = pd.read_csv(pre_screen_path)
    if "selected_for_ml" in pre_screen.columns:
        selected = pre_screen.loc[pre_screen["selected_for_ml"].astype(bool), "strategy_id"].astype(str).tolist()
        if selected:
            return selected
    return (
        pre_screen.loc[pre_screen["survived"].astype(bool), "strategy_id"]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )


def _selected_symbols(artifact_dir: Path) -> list[str]:
    universe = pd.read_csv(artifact_dir / "universe" / "universe_selected.csv")
    return universe.loc[universe["eligible"].astype(bool), "symbol"].astype(str).tolist()


def _selected_variants(settings: Settings, strategy_ids: list[str]) -> list[StrategyVariant]:
    wanted = set(strategy_ids)
    selected: list[StrategyVariant] = []
    for template in build_strategy_templates():
        search_space = getattr(settings.strategy_search, template.family)
        for variant in template.parameter_grid(search_space):
            if variant.strategy_id in wanted:
                selected.append(variant)
    missing = wanted - {variant.strategy_id for variant in selected}
    if missing:
        raise ValueError(f"Unable to resolve strategy variants for deployment: {sorted(missing)}")
    return selected


def _rebuild_events(settings: Settings, symbols: list[str], variants: list[StrategyVariant]) -> pd.DataFrame:
    cache = DiskCache(settings.cache_root)
    rate_budget = RateBudgetManager(settings.exchange)
    client = BinancePublicClient(ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget))
    ingestion = KlineIngestionService(settings, client)
    backtester = VectorizedBacktester(settings.backtest)

    enriched_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frame = ingestion.backfill_symbol(symbol)
        enriched_by_symbol[symbol] = enrich_ohlcv(frame, settings)

    templates_by_family = {template.family: template for template in build_strategy_templates()}
    strategy_lookup = {variant.strategy_id: variant.family for variant in variants}
    all_trades: list[pd.DataFrame] = []

    for variant in variants:
        template = templates_by_family[variant.family]
        for symbol in symbols:
            frame = enriched_by_symbol[symbol]
            signal_frame = template.generate(frame, variant)
            frame_for_backtest = frame.copy()
            frame_for_backtest["atr"] = frame["atr_14"].ffill().fillna(frame["close"] * 0.01)
            result = backtester.run(symbol, frame_for_backtest, signal_frame.signals, variant)
            if result.trades.empty:
                continue
            trades = result.trades.copy()
            strength = signal_frame.signals.reindex(trades["entry_time"])["signal_strength"].fillna(0.0).to_numpy()
            trades["signal_strength"] = strength
            all_trades.append(trades)

    if not all_trades:
        return pd.DataFrame()
    trade_frame = pd.concat(all_trades).sort_values("entry_time").reset_index(drop=True)
    return build_event_dataset(trade_frame, enriched_by_symbol, strategy_lookup, settings.labeling)


def _fit_deployment_components(
    settings: Settings,
    events: pd.DataFrame,
    manifest_payload: dict[str, Any],
) -> tuple[Any, ProbabilityCalibrator | None, list[str]]:
    registry = build_model_registry(settings)
    model_name = str(manifest_payload["model_name"])
    calibration_method = str(manifest_payload["calibration_method"])
    if model_name not in registry:
        raise KeyError(f"Model {model_name} is not available in the current registry.")

    features, _ = feature_matrix(events)
    labels = events["label_take"].astype(int)
    estimator = clone_estimator(registry[model_name])
    calibration_events = min(
        max(settings.deployment.minimum_calibration_events, int(len(events) * settings.deployment.calibration_fraction)),
        max(len(events) - 1, 1),
    )
    train_cutoff = max(len(events) - calibration_events, 1)
    estimator.fit(features.iloc[:train_cutoff], labels.iloc[:train_cutoff])

    calibrator: ProbabilityCalibrator | None = None
    if train_cutoff < len(events):
        calibrator = ProbabilityCalibrator(calibration_method)
        raw = predict_probabilities(estimator, features.iloc[train_cutoff:])
        calibrator.fit(raw, labels.iloc[train_cutoff:].to_numpy())
    return estimator, calibrator, features.columns.tolist()
