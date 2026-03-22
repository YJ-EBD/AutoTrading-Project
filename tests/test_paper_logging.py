from pathlib import Path

from binance_quant.config import Settings
from binance_quant.paper.logging_utils import read_log_tail


def test_read_log_tail_returns_latest_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "paper.log"
    log_path.write_text("a\nb\nc\nd\n", encoding="utf-8")

    lines = read_log_tail(log_path, 2)

    assert lines == ["c", "d"]


def test_settings_exposes_paper_log_path() -> None:
    settings = Settings.load("configs/base.yaml")

    assert settings.paper_log_path.name == "paper_runtime.log"
