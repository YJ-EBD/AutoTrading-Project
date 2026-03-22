from binance_quant.config import MLConfig
from binance_quant.ml.splits import build_walk_forward_folds


def test_walk_forward_splits_are_ordered_and_disjoint() -> None:
    folds = build_walk_forward_folds(400, MLConfig())
    assert folds
    for fold in folds:
        assert fold.train_idx.max() < fold.calibration_idx.min()
        assert fold.calibration_idx.max() < fold.threshold_idx.min()
        assert fold.threshold_idx.max() < fold.test_idx.min()
