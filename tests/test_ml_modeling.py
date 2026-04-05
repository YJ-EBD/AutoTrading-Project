from binance_quant.config import Settings
from binance_quant.ml.modeling import build_model_registry, clone_estimator


def test_model_registry_includes_mlp_when_requested() -> None:
    settings = Settings.load("newYJT/configs/base.yaml")
    registry = build_model_registry(settings)

    assert "mlp" in registry
    cloned = clone_estimator(registry["mlp"])
    assert cloned["model"].hidden_layer_sizes == (128, 64)
