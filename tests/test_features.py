import pandas as pd

from binance_quant.features.engine import FEATURE_COLUMNS, feature_matrix


def test_feature_matrix_excludes_future_trade_outcome_proxy() -> None:
    row = {column: 0.0 for column in FEATURE_COLUMNS}
    row.update(
        {
            "symbol": "BTCUSDT",
            "family": "trend_ema",
            "strategy_id": "trend_ema__example",
            "entry_time": "2024-01-01T00:00:00+00:00",
            "exit_time": "2024-01-01T01:00:00+00:00",
            "side": "long",
            "net_return": 0.01,
            "gross_return": 0.011,
            "exit_reason": "target",
            "bars_held": 4,
            "signal_strength": 0.7,
            "label_take": 1,
            "target_hit": True,
            "stop_hit": False,
            "horizon_hit": False,
            "mae": 0.01,
            "mfe": 0.03,
            "mae_limit_breached": 1,
            "recent_same_side_failures": 2,
            "recent_same_side_mean_return": -0.01,
        }
    )
    features, diagnostics = feature_matrix(pd.DataFrame([row]))

    assert "mae_limit_breached" not in features.columns
    assert "signal_strength" in features.columns
    assert "family_trend_ema" in features.columns
    assert diagnostics.point_in_time_ok is True
