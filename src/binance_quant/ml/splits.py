from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import MLConfig


@dataclass
class WalkForwardFold:
    train_idx: np.ndarray
    calibration_idx: np.ndarray
    threshold_idx: np.ndarray
    test_idx: np.ndarray


def build_walk_forward_folds(length: int, config: MLConfig) -> list[WalkForwardFold]:
    if length < 20:
        return []
    test_size = max(int(length * config.test_fraction), 20)
    validation_size = max(int(length * config.validation_fraction), 20)
    calibration_size = max(int(validation_size * config.calibration_fraction_of_validation), 10)
    threshold_size = max(validation_size - calibration_size, 10)
    min_train_size = max(int(length * config.train_fraction), 40)
    step = max((length - min_train_size - validation_size - test_size) // max(config.folds - 1, 1), 1)
    folds: list[WalkForwardFold] = []

    for fold_id in range(config.folds):
        train_end = min_train_size + fold_id * step
        calibration_start = train_end + config.embargo_bars
        calibration_end = calibration_start + calibration_size
        threshold_start = calibration_end
        threshold_end = threshold_start + threshold_size
        test_start = threshold_end + config.embargo_bars
        test_end = test_start + test_size
        if test_end > length:
            break
        folds.append(
            WalkForwardFold(
                train_idx=np.arange(0, train_end),
                calibration_idx=np.arange(calibration_start, calibration_end),
                threshold_idx=np.arange(threshold_start, threshold_end),
                test_idx=np.arange(test_start, test_end),
            )
        )
    return folds
