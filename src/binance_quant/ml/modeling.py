from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import Settings
from ..utils import seed_everything
from .splits import build_walk_forward_folds
from .thresholds import select_threshold

try:  # pragma: no cover
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover
    XGBClassifier = None


LOGGER = logging.getLogger(__name__)


@dataclass
class FoldEvaluation:
    model_name: str
    fold_id: int
    calibration_method: str
    threshold: float
    acceptance_rate: float
    precision: float
    expectancy: float
    trade_count: int


@dataclass
class ModelEvaluation:
    model_name: str
    calibration_method: str
    threshold_mean: float
    fold_results: list[FoldEvaluation]
    aggregate_metrics: dict[str, float]
    feature_importance: dict[str, float]
    accepted_events: pd.DataFrame


class ProbabilityCalibrator:
    def __init__(self, method: str):
        self.method = method
        self.model: Any | None = None

    def fit(self, raw_probabilities: np.ndarray, labels: np.ndarray) -> None:
        clipped = np.clip(raw_probabilities, 1e-6, 1 - 1e-6)
        if self.method == "platt":
            self.model = LogisticRegression()
            self.model.fit(clipped.reshape(-1, 1), labels)
        elif self.method == "isotonic":
            self.model = IsotonicRegression(out_of_bounds="clip")
            self.model.fit(clipped, labels)
        else:
            raise ValueError(f"Unsupported calibration method: {self.method}")

    def predict(self, raw_probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(raw_probabilities, 1e-6, 1 - 1e-6)
        if self.method == "platt":
            return self.model.predict_proba(clipped.reshape(-1, 1))[:, 1]
        return self.model.predict(clipped)


def build_model_registry(settings: Settings) -> dict[str, Any]:
    registry: dict[str, Any] = {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(max_iter=2000, random_state=settings.research.random_seed)),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=10,
            max_depth=6,
            random_state=settings.research.random_seed,
            n_jobs=1,
        ),
        "mlp": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    MLPClassifier(
                        hidden_layer_sizes=(128, 64),
                        activation="relu",
                        alpha=1e-4,
                        learning_rate_init=1e-3,
                        max_iter=400,
                        early_stopping=True,
                        validation_fraction=0.1,
                        n_iter_no_change=20,
                        random_state=settings.research.random_seed,
                    ),
                ),
            ]
        ),
    }
    if XGBClassifier is not None:
        registry["xgboost"] = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=settings.research.random_seed,
            n_jobs=1,
        )
    return {name: model for name, model in registry.items() if name in settings.ml.models}


def evaluate_models(features: pd.DataFrame, events: pd.DataFrame, settings: Settings) -> list[ModelEvaluation]:
    seed_everything(settings.research.random_seed)
    folds = build_walk_forward_folds(len(events), settings.ml)
    if not folds:
        return []

    X = features
    y = events["label_take"].astype(int)
    realized_returns = events["net_return"].astype(float)
    registry = build_model_registry(settings)
    evaluations: list[ModelEvaluation] = []

    for model_name, estimator in registry.items():
        for calibration_method in settings.ml.calibration_methods:
            LOGGER.info("Evaluating model=%s calibration=%s across %s folds", model_name, calibration_method, len(folds))
            accepted_rows: list[pd.DataFrame] = []
            fold_results: list[FoldEvaluation] = []
            thresholds: list[float] = []
            importance = {column: 0.0 for column in X.columns}
            for fold_id, fold in enumerate(folds):
                model = clone_estimator(estimator)
                model.fit(X.iloc[fold.train_idx], y.iloc[fold.train_idx])
                raw_calibration = predict_probabilities(model, X.iloc[fold.calibration_idx])
                calibrator = ProbabilityCalibrator(calibration_method)
                calibrator.fit(raw_calibration, y.iloc[fold.calibration_idx].to_numpy())
                threshold_prob = calibrator.predict(predict_probabilities(model, X.iloc[fold.threshold_idx]))
                selection = select_threshold(
                    pd.Series(threshold_prob),
                    y.iloc[fold.threshold_idx].reset_index(drop=True),
                    realized_returns.iloc[fold.threshold_idx].reset_index(drop=True),
                    settings.ml,
                )
                if selection is None:
                    LOGGER.info(
                        "Skipping fold=%s for model=%s calibration=%s because no threshold met acceptance constraints",
                        fold_id,
                        model_name,
                        calibration_method,
                    )
                    continue
                test_prob = calibrator.predict(predict_probabilities(model, X.iloc[fold.test_idx]))
                test_frame = events.iloc[fold.test_idx].copy()
                test_frame["probability"] = test_prob
                test_frame["accepted"] = test_frame["probability"] >= selection.threshold
                accepted = test_frame[test_frame["accepted"]].copy()
                accepted_rows.append(accepted)
                thresholds.append(selection.threshold)
                fold_evaluation = FoldEvaluation(
                    model_name=model_name,
                    fold_id=fold_id,
                    calibration_method=calibration_method,
                    threshold=selection.threshold,
                    acceptance_rate=float(test_frame["accepted"].mean()),
                    precision=float(accepted["label_take"].mean()) if not accepted.empty else 0.0,
                    expectancy=float(accepted["net_return"].mean()) if not accepted.empty else 0.0,
                    trade_count=int(len(accepted)),
                )
                fold_results.append(fold_evaluation)
                LOGGER.info(
                    "Completed fold=%s for model=%s calibration=%s threshold=%.3f acceptance=%.3f precision=%.3f expectancy=%.5f trades=%s",
                    fold_id,
                    model_name,
                    calibration_method,
                    fold_evaluation.threshold,
                    fold_evaluation.acceptance_rate,
                    fold_evaluation.precision,
                    fold_evaluation.expectancy,
                    fold_evaluation.trade_count,
                )
                importance = model_feature_importance(model, X.columns)
            if not fold_results:
                continue
            accepted_events = pd.concat(accepted_rows).sort_values("entry_time").reset_index(drop=True)
            aggregate = {
                "folds": float(len(fold_results)),
                "threshold_mean": float(np.mean(thresholds)),
                "acceptance_rate_mean": float(np.mean([item.acceptance_rate for item in fold_results])),
                "precision_mean": float(np.mean([item.precision for item in fold_results])),
                "expectancy_mean": float(np.mean([item.expectancy for item in fold_results])),
                "trade_count": float(sum(item.trade_count for item in fold_results)),
            }
            evaluations.append(
                ModelEvaluation(
                    model_name=model_name,
                    calibration_method=calibration_method,
                    threshold_mean=aggregate["threshold_mean"],
                    fold_results=fold_results,
                    aggregate_metrics=aggregate,
                    feature_importance=importance,
                    accepted_events=accepted_events,
                )
            )
            LOGGER.info(
                "Finished model=%s calibration=%s folds=%s precision=%.3f expectancy=%.5f trades=%s",
                model_name,
                calibration_method,
                len(fold_results),
                aggregate["precision_mean"],
                aggregate["expectancy_mean"],
                int(aggregate["trade_count"]),
            )
    return evaluations


def clone_estimator(estimator: Any) -> Any:
    if isinstance(estimator, Pipeline):
        model = estimator["model"]
        if isinstance(model, LogisticRegression):
            return Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("model", LogisticRegression(max_iter=model.max_iter, random_state=model.random_state)),
                ]
            )
        if isinstance(model, MLPClassifier):
            return Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        MLPClassifier(
                            hidden_layer_sizes=model.hidden_layer_sizes,
                            activation=model.activation,
                            alpha=model.alpha,
                            learning_rate_init=model.learning_rate_init,
                            max_iter=model.max_iter,
                            early_stopping=model.early_stopping,
                            validation_fraction=model.validation_fraction,
                            n_iter_no_change=model.n_iter_no_change,
                            random_state=model.random_state,
                        ),
                    ),
                ]
            )
    if isinstance(estimator, RandomForestClassifier):
        return RandomForestClassifier(
            n_estimators=estimator.n_estimators,
            min_samples_leaf=estimator.min_samples_leaf,
            max_depth=estimator.max_depth,
            random_state=estimator.random_state,
            n_jobs=estimator.n_jobs,
        )
    if XGBClassifier is not None and isinstance(estimator, XGBClassifier):
        return XGBClassifier(**estimator.get_params())
    raise TypeError(f"Unsupported estimator type: {type(estimator)!r}")


def predict_probabilities(model: Any, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def model_feature_importance(model: Any, columns: pd.Index) -> dict[str, float]:
    if isinstance(model, Pipeline):
        inner = model["model"]
        if hasattr(inner, "coef_"):
            coefficients = np.abs(inner.coef_[0])
            total = coefficients.sum() or 1.0
            return {column: float(weight / total) for column, weight in zip(columns, coefficients)}
        if hasattr(inner, "coefs_") and inner.coefs_:
            first_layer = np.asarray(inner.coefs_[0], dtype=float)
            weights = np.mean(np.abs(first_layer), axis=1)
            total = weights.sum() or 1.0
            return {column: float(weight / total) for column, weight in zip(columns, weights)}
        return {column: 0.0 for column in columns}
    if hasattr(model, "feature_importances_"):
        importances = np.asarray(model.feature_importances_, dtype=float)
        total = importances.sum() or 1.0
        return {column: float(weight / total) for column, weight in zip(columns, importances)}
    return {column: 0.0 for column in columns}
