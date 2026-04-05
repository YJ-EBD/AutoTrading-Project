from pathlib import Path

from binance_quant.config import Settings
from binance_quant.ml.deployment import _selected_strategy_ids


def test_selected_strategy_ids_augments_when_only_one_strategy_is_selected(tmp_path: Path) -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    artifact_dir = tmp_path / "artifact"
    reports_dir = artifact_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "pre_screen.csv").write_text(
        "\n".join(
            [
                "strategy_id,family,selected_for_ml,survived,ml_candidate_survived,family_seed_survived,strict_survived,positive_symbol_count,expectancy,profit_factor,trade_count",
                "trend_ema__a,trend_ema,True,True,True,False,False,5,0.001,0.95,100",
                "trend_ema__b,trend_ema,False,False,False,False,False,4,0.0003,0.91,120",
                "trend_ema__c,trend_ema,False,False,False,False,False,1,-0.01,0.80,80",
            ]
        ),
        encoding="utf-8",
    )

    selected = _selected_strategy_ids(settings, artifact_dir)

    assert selected == ["trend_ema__a", "trend_ema__b"]


def test_selected_strategy_ids_respects_excluded_families(tmp_path: Path) -> None:
    settings = Settings.load(Path("configs/base.yaml"))
    settings.deployment.excluded_families = ["breakout"]
    artifact_dir = tmp_path / "artifact"
    reports_dir = artifact_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "pre_screen.csv").write_text(
        "\n".join(
            [
                "strategy_id,family,selected_for_ml,survived,ml_candidate_survived,family_seed_survived,strict_survived,positive_symbol_count,expectancy,profit_factor,trade_count",
                "breakout__a,breakout,True,True,True,False,False,6,0.002,1.20,120",
                "trend_ema__a,trend_ema,True,True,True,False,False,5,0.001,1.05,100",
                "trend_ema__b,trend_ema,False,False,False,False,False,4,0.0003,0.91,120",
            ]
        ),
        encoding="utf-8",
    )

    selected = _selected_strategy_ids(settings, artifact_dir)

    assert "breakout__a" not in selected
    assert selected[0] == "trend_ema__a"
