from pathlib import Path

from binance_quant.config import Settings
from binance_quant.paper.dashboard import _dashboard_context, _runtime_payload, create_app


def test_dashboard_runtime_payload_and_context(tmp_path: Path) -> None:
    settings = Settings.load("configs/base.yaml")
    settings.project_root = tmp_path
    settings.ensure_directories()
    settings.paper_log_path.write_text("line-1\nline-2\n", encoding="utf-8")

    app = create_app(settings, start_runtime=False)

    runtime_payload = _runtime_payload(app)
    assert runtime_payload["service_status"] == {}
    assert runtime_payload["stream_status"] == {}
    assert runtime_payload["llm_available"] is False

    context = _dashboard_context(app)
    assert context["runtime_logs"] == ["line-1", "line-2"]
    assert context["overview"]["decision_count"] == 0
