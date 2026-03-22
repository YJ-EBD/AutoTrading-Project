from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import MLConfig


@dataclass
class ThresholdSelection:
    threshold: float
    score: float
    acceptance_rate: float
    accepted_expectancy: float
    accepted_precision: float


def select_threshold(
    probabilities: pd.Series,
    labels: pd.Series,
    realized_returns: pd.Series,
    config: MLConfig,
) -> ThresholdSelection | None:
    best: ThresholdSelection | None = None
    for threshold in config.threshold_grid:
        accepted = probabilities >= threshold
        acceptance_rate = float(accepted.mean())
        if acceptance_rate < config.min_acceptance_rate or acceptance_rate > config.max_acceptance_rate:
            continue
        accepted_returns = realized_returns[accepted]
        if accepted_returns.empty:
            continue
        expectancy = float(accepted_returns.mean())
        precision = float(labels[accepted].mean())
        score = expectancy * (len(accepted_returns) ** 0.5) * max(precision, 0.01)
        candidate = ThresholdSelection(
            threshold=threshold,
            score=score,
            acceptance_rate=acceptance_rate,
            accepted_expectancy=expectancy,
            accepted_precision=precision,
        )
        if best is None or candidate.score > best.score:
            best = candidate
    return best
