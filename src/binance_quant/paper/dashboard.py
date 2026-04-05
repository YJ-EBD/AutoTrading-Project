from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import Settings
from ..hydra_compare import (
    fetch_hydra_runtime_snapshot,
    load_hydra_benchmark_summary,
    run_hydra_benchmark,
)
from .logging_utils import ensure_paper_log_handler, read_log_tail
from .repository import PaperTradeRepository
from .runtime import PaperTradingRuntime


DASHBOARD_UI = {
    "page_title": "\ubc14\uc774\ub0b8\uc2a4 \ud398\uc774\ud37c \ud3ec\ud2b8\ud3f4\ub9ac\uc624",
    "eyebrow": "\ud398\uc774\ud37c \ud2b8\ub808\uc774\ub529 \uad00\uc81c\ub300",
    "hero_title": "\uc9c0\ud45c \uc2dc\uadf8\ub110, ML \ud655\ub960, \ub85c\uceec LLM \ucd5c\uc885\ud310\ub2e8",
    "hero_subtitle": "\uc774 \ub300\uc2dc\ubcf4\ub4dc\ub294 \ubc14\uc774\ub0b8\uc2a4 USD-M \uc120\ubb3c 15\ubd84\ubd09 \uc2e0\ud638\ub97c \uae30\ubc18\uc73c\ub85c \ud398\uc774\ud37c \ud3ec\ud2b8\ud3f4\ub9ac\uc624\ub97c \ucd94\uc801\ud569\ub2c8\ub2e4. \uc9c4\uc785 \uc2dc\uc810\uc758 \ud604\uc7ac\uac00\ub97c \uc800\uc7a5\ud558\uace0, \uc775\uc808, \uc190\uc808, \uc2dc\uadf8\ub110 \uc885\ub8cc, \ubcf4\uc720\uae30\uac04 \uc885\ub8cc, \uac15\uc81c\uccad\uc0b0\uc774 \ubc1c\uc0dd\ud55c \uc2dc\uc810\uc758 \uad00\uce21 \uac00\uaca9\uc744 \ud568\uaed8 \uae30\ub85d\ud569\ub2c8\ub2e4.",
    "metric_active_positions": "\ud65c\uc131 \ud3ec\uc9c0\uc158",
    "metric_closed_positions": "\uc885\ub8cc \ud3ec\uc9c0\uc158",
    "metric_decision_count": "\uc758\uc0ac\uacb0\uc815 \uc218",
    "metric_realized_expectancy": "\uc2e4\ud604 \uae30\ub300\uac12",
    "metric_profit_factor": "\ud504\ub85c\ud54f \ud329\ud130",
    "metric_llm_available": "LLM \uc0ac\uc6a9 \uac00\ub2a5",
    "metric_account_base": "\uae30\uc900 \uacc4\uc88c",
    "metric_position_margin": "\ud3ec\uc9c0\uc158\ub2f9 \uc99d\uac70\uae08",
    "yes": "\uc608",
    "no": "\uc544\ub2c8\uc624",
    "runtime_heading": "\ub7f0\ud0c0\uc784 \uc0c1\ud0dc",
    "running_pill": "\uc2e4\ud589 \uc911",
    "stopped_pill": "\uc911\uc9c0",
    "last_updated": "\ub9c8\uc9c0\ub9c9 \uac31\uc2e0",
    "last_symbol": "\ub9c8\uc9c0\ub9c9 \uc2ec\ubcfc",
    "none_text": "\uc5c6\uc74c",
    "start_button": "\ub7f0\ud0c0\uc784 \uc2dc\uc791",
    "stop_button": "\ub7f0\ud0c0\uc784 \uc911\uc9c0",
    "status_pid": "\ud504\ub85c\uc138\uc2a4 PID",
    "status_runtime_task": "\ub7f0\ud0c0\uc784 \ud0dc\uc2a4\ud06c",
    "status_retune_task": "\uc7ac\ud29c\ub2dd \ud0dc\uc2a4\ud06c",
    "status_runtime_stage": "\ub7f0\ud0c0\uc784 \ub2e8\uacc4",
    "status_kill_switch": "\ud0ac \uc2a4\uc704\uce58",
    "task_running": "\ub3d9\uc791 \uc911",
    "task_stopped": "\uc815\uc9c0",
    "kill_switch_on": "\ud65c\uc131",
    "kill_switch_off": "\ube44\ud65c\uc131",
    "kill_switch_activate_button": "\ud0ac \uc2a4\uc704\uce58 \ud65c\uc131",
    "kill_switch_deactivate_button": "\ud0ac \uc2a4\uc704\uce58 \ud574\uc81c",
    "bundle_source": "\uc18c\uc2a4 \uc544\ud2f0\ud329\ud2b8",
    "bundle_model": "\ubaa8\ub378",
    "bundle_threshold": "\uc784\uacc4\uac12",
    "bundle_event_count": "\uc774\ubca4\ud2b8 \uc218",
    "bundle_symbols": "\uc120\ud0dd \uc2ec\ubcfc",
    "bundle_strategies": "\uc120\ud0dd \uc804\ub7b5",
    "bundle_missing": "\uc544\uc9c1 \ubc30\ud3ec \ubc88\ub4e4\uc774 \ub85c\ub4dc\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.",
    "retunes_heading": "\ucd5c\uadfc \uc7ac\ud29c\ub2dd",
    "table_started_at": "\uc2dc\uc791 \uc2dc\uac01",
    "table_status": "\uc0c1\ud0dc",
    "table_artifact": "\uc544\ud2f0\ud329\ud2b8",
    "no_retunes": "\uc544\uc9c1 \uc7ac\ud29c\ub2dd \uc774\ub825\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "stream_heading": "\uc6f9\uc18c\ucf13 \uc5f0\uacb0 \uc0c1\ud0dc",
    "stream_status": "\uc5f0\uacb0 \uc0c1\ud0dc",
    "stream_reconnect_count": "\uc7ac\uc5f0\uacb0 \ud69f\uc218",
    "stream_last_message": "\ub9c8\uc9c0\ub9c9 \uba54\uc2dc\uc9c0",
    "stream_last_error": "\ub9c8\uc9c0\ub9c9 \uc624\ub958",
    "logs_heading": "\uc2e4\ud589 \ub85c\uadf8 \ucf58\uc194",
    "logs_auto_refresh": "\uc790\ub3d9 \uac31\uc2e0 5\ucd08",
    "logs_file": "\ub85c\uadf8 \ud30c\uc77c",
    "no_logs": "\uc544\uc9c1 \uae30\ub85d\ub41c \ub85c\uadf8\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "active_positions_heading": "\ud65c\uc131 \ud3ec\uc9c0\uc158",
    "closed_positions_heading": "\ucd5c\uadfc \uc885\ub8cc \ud3ec\uc9c0\uc158",
    "decisions_heading": "\ucd5c\uadfc \uc758\uc0ac\uacb0\uc815",
    "table_symbol": "\uc2ec\ubcfc",
    "table_strategy": "\uc804\ub7b5",
    "table_side": "\ubc29\ud5a5",
    "table_opened_at": "\uc9c4\uc785 \uc2dc\uac01",
    "table_entry_price": "\uc9c4\uc785\uac00",
    "table_current_price": "\ud604\uc7ac\uac00",
    "table_target_stop": "\ubaa9\ud45c\uac00 / \uc190\uc808\uac00",
    "table_account_net_roi_percent": "\uacc4\uc88c \uae30\uc900 ROI %",
    "table_position_net_roi_percent": "\ud3ec\uc9c0\uc158 \uae30\uc900 ROI %",
    "table_net_pnl_usd": "\uc21c\uc218\uc775 \ub2ec\ub7ec",
    "table_closed_at": "\uc885\ub8cc \uc2dc\uac01",
    "table_exit_reason": "\uc885\ub8cc \uc0ac\uc720",
    "table_entry_exit_price": "\uc9c4\uc785\uac00 / \uc885\ub8cc\uac00",
    "table_time": "\uc2dc\uac01",
    "table_ml_probability": "ML \ud655\ub960",
    "table_threshold": "\uc784\uacc4\uac12",
    "table_llm": "LLM",
    "table_final_action": "\ucd5c\uc885 \uacb0\uc815",
    "table_reason": "\uc0ac\uc720",
    "no_active_positions": "\ud604\uc7ac \ud65c\uc131 \ud3ec\uc9c0\uc158\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "no_closed_positions": "\uc544\uc9c1 \uc885\ub8cc\ub41c \ud3ec\uc9c0\uc158\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "no_decisions": "\uc544\uc9c1 \uc758\uc0ac\uacb0\uc815 \ub85c\uadf8\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "footer_note": "\ud654\uba74\uc740 JSON API\ub97c \uc8fc\uae30\uc801\uc73c\ub85c \uc0c8\ub85c \uc77d\uc5b4 \uc0c1\ud0dc\uc640 \ub85c\uadf8\ub97c \uc790\ub3d9 \uac31\uc2e0\ud569\ub2c8\ub2e4.",
    "compare_page_title": "YJCOOPERATION vs HYDRA \ube44\uad50",
    "compare_heading": "\ud604\uc7ac \uad6c\uc870 vs HYDRA \uc131\ub2a5 \ube44\uad50",
    "compare_subtitle": "\ud604\uc7ac \ud398\uc774\ud37c \ub7f0\ud0c0\uc784 \uc131\uc801\uacfc Hydra \uc11c\ubc84 \uc0c1\ud0dc, Hydra \ubc31\ud14c\uc2a4\ud2b8 \ubca4\uce58\ub9c8\ud06c \uacb0\uacfc\ub97c \ub098\ub780\ud788 \ube44\uad50\ud569\ub2c8\ub2e4.",
    "compare_refresh_benchmark": "Hydra \ubca4\uce58\ub9c8\ud06c \uc0c8\ub85c\uace0\uce68",
    "compare_current_runtime": "\ud604\uc7ac \ub7f0\ud0c0\uc784",
    "compare_hydra_runtime": "Hydra \ub7f0\ud0c0\uc784",
    "compare_hydra_paper": "Hydra Paper \ub7f0\ud0c0\uc784",
    "compare_hydra_service": "Hydra \uc11c\ubc84 \uc0c1\ud0dc",
    "compare_hydra_closed": "Hydra Paper \ucd5c\uadfc \uc885\ub8cc \ud3ec\uc9c0\uc158",
    "compare_hydra_benchmark": "Hydra \ubca4\uce58\ub9c8\ud06c",
    "compare_metric_total_return": "\ub204\uc801 \uc218\uc775\ub960",
    "compare_metric_total_trades": "\ucd1d \uac70\ub798 \uc218",
    "compare_metric_win_rate": "\uc2b9\ub960",
    "compare_metric_profit_factor": "\ud504\ub85c\ud54f \ud329\ud130",
    "compare_metric_drawdown": "\ucd5c\ub300 \ub099\ud3ed",
    "compare_metric_symbol_count": "\uc2ec\ubcfc \uc218",
    "compare_metric_runtime_url": "\uc11c\ubc84 \uc8fc\uc18c",
    "compare_metric_status": "\uc0c1\ud0dc",
    "compare_metric_generated_at": "\uc0dd\uc131 \uc2dc\uac01",
    "compare_metric_realized_pnl": "\uc2e4\ud604 \uc190\uc775",
    "compare_metric_daily_pnl": "\uc77c\uac04 \uc190\uc775",
    "compare_metric_unrealized": "\ubbf8\uc2e4\ud604 \uc190\uc775",
    "compare_metric_profitable_symbols": "\uc218\uc775 \uc2ec\ubcfc",
    "compare_no_benchmark": "Hydra \ubca4\uce58\ub9c8\ud06c \uc694\uc57d\uc774 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4.",
    "side_long": "\ub871",
    "side_short": "\uc20f",
    "runtime_action_error": "\ub7f0\ud0c0\uc784 {action} \uc911 \uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.",
    "kill_switch_action_error": "\ud0ac \uc2a4\uc704\uce58 {action} \uc911 \uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.",
    "status_labels": {
        "idle": "\ub300\uae30",
        "starting": "\uc2dc\uc791 \uc911",
        "stopped": "\uc911\uc9c0",
        "bootstrapped": "\ucd08\uae30\ud654 \uc644\ub8cc",
        "warming_up": "\uc608\uc5f4 \uc911",
        "running": "\uc2e4\ud589 \uc911",
        "error": "\uc624\ub958",
        "connecting": "\uc5f0\uacb0 \uc911",
        "connected": "\uc5f0\uacb0\ub428",
        "interrupted": "\uc911\ub2e8\ub428",
        "retrying": "\uc7ac\uc2dc\ub3c4 \uc911",
        "rotating": "\uc5f0\uacb0 \uc21c\ud658 \uc911",
        "restarting": "\uc7ac\uc2dc\uc791 \uc911",
        "degraded": "\uc131\ub2a5 \uc800\ud558",
        "ok": "\uc815\uc0c1",
        "active": "\ubcf4\uc720 \uc911",
        "closed": "\uc885\ub8cc",
        "allow": "\ud5c8\uc6a9",
        "reject": "\uac70\ubd80",
        "defer": "\ubcf4\ub958",
        "accepted_for_paper": "\ud398\uc774\ud37c \ud569\uaca9",
        "needs_iteration": "\ucd94\uac00 \uac1c\uc120 \ud544\uc694",
    },
    "exit_reason_labels": {
        "target": "\uc775\uc808",
        "stop": "\uc190\uc808",
        "liquidation": "\uac15\uc81c\uccad\uc0b0",
        "signal_exit": "\uc2dc\uadf8\ub110 \uc885\ub8cc",
        "horizon": "\ubcf4\uc720\uae30\uac04 \uc885\ub8cc",
        "kill_switch": "\ud0ac \uc2a4\uc704\uce58",
    },
    "decision_reason_labels": {
        "ml_threshold": "ML \uc784\uacc4\uac12 \ubbf8\ub2ec",
        "ml_only": "ML \ud1b5\uacfc",
        "llm_allow": "LLM \ud5c8\uc6a9",
        "llm_optional": "LLM \uc120\ud0dd \uc0ac\uc6a9",
        "ml_override": "ML \uc6b0\uc120 \ud5c8\uc6a9",
        "max_concurrent_positions": "\ub3d9\uc2dc \ud3ec\uc9c0\uc158 \ud55c\ub3c4",
        "active_symbol_lock": "\ub3d9\uc77c \uc2ec\ubcfc \uc911\ubcf5 \ubc29\uc9c0",
        "max_trades_per_day": "\uc77c\uc77c \uac70\ub798 \uc218 \ud55c\ub3c4",
        "daily_loss_limit": "\uc77c\uc77c \uc190\uc2e4 \ud55c\ub3c4",
        "recent_symbol_loss_cooldown": "\ucd5c\uadfc \uc2ec\ubcfc \uc190\uc2e4 \ucffc\ub2e4\uc6b4",
        "recent_strategy_loss_cooldown": "\ucd5c\uadfc \uc804\ub7b5 \uc190\uc2e4 \ucffc\ub2e4\uc6b4",
        "recent_family_loss_cooldown": "\ucd5c\uadfc \uc804\ub7b5\uad70 \uc190\uc2e4 \ucffc\ub2e4\uc6b4",
        "strategy_performance_block": "\uc804\ub7b5 \uc2e4\uc804 \uc131\uacfc \ucc28\ub2e8",
        "symbol_performance_block": "\uc2ec\ubcfc \uc2e4\uc804 \uc131\uacfc \ucc28\ub2e8",
        "kill_switch_active": "\ud0ac \uc2a4\uc704\uce58 \ud65c\uc131 \uc911",
    },
}


def create_app(settings: Settings, *, start_runtime: bool = True) -> FastAPI:
    ensure_paper_log_handler(settings)
    repository = PaperTradeRepository(settings.paper_state_db)
    runtime = PaperTradingRuntime(settings) if start_runtime else None
    template_dir = Path(__file__).resolve().parent / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if runtime is not None:
            await runtime.start()
        yield
        if runtime is not None:
            await runtime.stop()

    app = FastAPI(title="Binance Quant Paper Dashboard", lifespan=lifespan)
    app.state.settings = settings
    app.state.repository = repository
    app.state.runtime = runtime
    app.state.started_monotonic = time.monotonic()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        context = _dashboard_context(app)
        context["request"] = request
        return templates.TemplateResponse("dashboard.html", context)

    @app.get("/compare", response_class=HTMLResponse)
    async def compare(request: Request) -> HTMLResponse:
        context = {
            "ui": DASHBOARD_UI,
            "compare": _compare_payload(app),
            "request": request,
        }
        return templates.TemplateResponse("compare.html", context)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(_health_payload(app))

    @app.get("/api/overview")
    async def overview() -> JSONResponse:
        return JSONResponse(_dashboard_context(app))

    @app.get("/api/compare")
    async def compare_api() -> JSONResponse:
        return JSONResponse(_compare_payload(app))

    @app.get("/api/status")
    async def status() -> JSONResponse:
        return JSONResponse(_runtime_payload(app))

    @app.get("/api/logs")
    async def logs() -> JSONResponse:
        return JSONResponse(
            {
                "log_path": str(settings.paper_log_path),
                "lines": read_log_tail(settings.paper_log_path, settings.dashboard.log_tail_lines),
            }
        )

    @app.post("/api/runtime/start")
    async def start_runtime(request: Request) -> JSONResponse:
        _require_api_key(request, settings)
        if runtime is None:
            return JSONResponse({"error": "runtime_not_available"}, status_code=503)
        await runtime.start()
        return JSONResponse(_runtime_payload(app))

    @app.post("/api/runtime/stop")
    async def stop_runtime(request: Request) -> JSONResponse:
        _require_api_key(request, settings)
        if runtime is None:
            return JSONResponse({"error": "runtime_not_available"}, status_code=503)
        await runtime.stop()
        return JSONResponse(_runtime_payload(app))

    @app.get("/api/kill-switch")
    async def kill_switch() -> JSONResponse:
        return JSONResponse(_runtime_payload(app).get("kill_switch", _default_kill_switch_state()))

    @app.post("/api/kill-switch/activate")
    async def activate_kill_switch(request: Request) -> JSONResponse:
        _require_api_key(request, settings)
        if runtime is None:
            return JSONResponse({"error": "runtime_not_available"}, status_code=503)
        return JSONResponse(runtime.activate_kill_switch(reason="manual_activation", source="dashboard"))

    @app.post("/api/kill-switch/deactivate")
    async def deactivate_kill_switch(request: Request) -> JSONResponse:
        _require_api_key(request, settings)
        if runtime is None:
            return JSONResponse({"error": "runtime_not_available"}, status_code=503)
        return JSONResponse(runtime.deactivate_kill_switch(reason="manual_reset", source="dashboard"))

    @app.post("/api/compare/hydra-refresh")
    async def hydra_refresh(request: Request) -> JSONResponse:
        _require_api_key(request, settings)
        return JSONResponse(run_hydra_benchmark(settings))

    @app.get("/api/positions/active")
    async def active_positions() -> JSONResponse:
        return JSONResponse(_enrich_positions(repository.list_positions(status="active", limit=200), settings))

    @app.get("/api/positions/closed")
    async def closed_positions() -> JSONResponse:
        return JSONResponse(
            _enrich_positions(
                repository.list_positions(status="closed", limit=settings.dashboard.closed_trade_limit),
                settings,
            )
        )

    @app.get("/api/decisions")
    async def decisions() -> JSONResponse:
        return JSONResponse(repository.recent_decisions(limit=settings.dashboard.decision_log_limit))

    @app.get("/api/retunes")
    async def retunes() -> JSONResponse:
        return JSONResponse(repository.recent_retunes(limit=25))

    return app


def serve_dashboard(settings: Settings, *, start_runtime: bool = True) -> None:
    app = create_app(settings, start_runtime=start_runtime)
    uvicorn.run(
        app,
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=settings.dashboard.reload,
        log_level="info",
    )


def _dashboard_context(app: FastAPI) -> dict:
    settings: Settings = app.state.settings
    repository: PaperTradeRepository = app.state.repository
    overview = repository.overview(
        decision_limit=settings.dashboard.decision_log_limit,
        closed_trade_limit=settings.dashboard.closed_trade_limit,
    )
    active_positions = _enrich_positions(repository.list_positions(status="active", limit=100), settings)
    closed_positions = _enrich_positions(
        repository.list_positions(status="closed", limit=settings.dashboard.closed_trade_limit),
        settings,
    )
    return {
        "ui": DASHBOARD_UI,
        "overview": _enrich_overview(overview, settings),
        "runtime": _runtime_payload(app),
        "runtime_logs": read_log_tail(settings.paper_log_path, settings.dashboard.log_tail_lines),
        "active_positions": active_positions,
        "closed_positions": closed_positions,
        "recent_decisions": repository.recent_decisions(limit=settings.dashboard.decision_log_limit),
        "recent_retunes": repository.recent_retunes(limit=20),
    }


def _runtime_payload(app: FastAPI) -> dict:
    repository: PaperTradeRepository = app.state.repository
    runtime: PaperTradingRuntime | None = app.state.runtime
    if runtime is not None:
        return runtime.snapshot()
    return {
        "runtime_status": repository.get_state("runtime_status", {}),
        "service_status": repository.get_state("service_status", {}),
        "stream_status": repository.get_state("stream_status", {}),
        "llm_available": False,
        "bundle_manifest": repository.get_state("deployment_manifest", {}),
        "kill_switch": repository.get_state("kill_switch_status", _default_kill_switch_state()),
    }


def _health_payload(app: FastAPI) -> dict:
    payload = _runtime_payload(app)
    uptime_seconds = int(max(time.monotonic() - float(getattr(app.state, "started_monotonic", time.monotonic())), 0))
    status = "ok"
    service_status = payload.get("service_status", {})
    runtime_status = payload.get("runtime_status", {})
    stream_status = payload.get("stream_status", {})
    kill_switch = payload.get("kill_switch", _default_kill_switch_state())

    if kill_switch.get("active"):
        status = "degraded"
    elif runtime_status.get("status") == "error":
        status = "degraded"
    elif service_status.get("is_running") and stream_status.get("status") not in {"connected", "idle", "starting", "warming_up"}:
        status = "degraded"
    elif not service_status.get("is_running") and runtime_status:
        status = "stopped"

    return {
        "status": status,
        "uptime_seconds": uptime_seconds,
        "service_status": service_status,
        "runtime_status": runtime_status,
        "stream_status": stream_status,
        "kill_switch": kill_switch,
    }


def _compare_payload(app: FastAPI) -> dict:
    settings: Settings = app.state.settings
    repository: PaperTradeRepository = app.state.repository
    current_overview = _enrich_overview(
        repository.overview(
            decision_limit=settings.dashboard.decision_log_limit,
            closed_trade_limit=settings.dashboard.closed_trade_limit,
        ),
        settings,
    )
    runtime = _runtime_payload(app)
    hydra_runtime = fetch_hydra_runtime_snapshot(settings)
    hydra_benchmark = load_hydra_benchmark_summary(settings)
    return {
        "current": {
            "overview": current_overview,
            "runtime": runtime,
        },
        "hydra_runtime": hydra_runtime,
        "hydra_benchmark": hydra_benchmark,
    }


def _enrich_overview(overview: dict, settings: Settings) -> dict:
    base_equity = settings.paper.starting_equity_usd
    position_margin_usd = base_equity * settings.backtest.capital_fraction_per_trade
    enriched = dict(overview)
    enriched["starting_equity_usd"] = base_equity
    enriched["position_margin_usd"] = position_margin_usd
    enriched["realized_expectancy_usd"] = float(overview.get("realized_expectancy", 0.0)) * base_equity
    enriched["realized_net_pnl_usd"] = float(overview.get("realized_net_return_sum", 0.0)) * base_equity
    return enriched


def _enrich_positions(positions: list[dict], settings: Settings) -> list[dict]:
    base_equity = settings.paper.starting_equity_usd
    default_position_margin_usd = base_equity * settings.backtest.capital_fraction_per_trade
    enriched_positions: list[dict] = []
    for position in positions:
        enriched = dict(position)
        metadata = enriched.get("metadata") or enriched.get("metadata_json") or {}
        if "capital_fraction" not in metadata and isinstance(metadata.get("metadata"), dict):
            metadata = metadata["metadata"]
        capital_fraction = float(metadata.get("capital_fraction", settings.backtest.capital_fraction_per_trade))
        position_margin_usd = base_equity * capital_fraction
        net_return = float(enriched.get("net_return", 0.0))
        gross_return = float(enriched.get("gross_return", 0.0))
        account_net_roi_percent = net_return * 100.0
        gross_account_roi_percent = gross_return * 100.0
        enriched["net_pnl_usd"] = net_return * base_equity
        enriched["gross_pnl_usd"] = gross_return * base_equity
        enriched["starting_equity_usd"] = base_equity
        enriched["position_margin_usd"] = position_margin_usd
        enriched["default_position_margin_usd"] = default_position_margin_usd
        enriched["capital_fraction"] = capital_fraction
        enriched["size_multiplier"] = (
            capital_fraction / settings.backtest.capital_fraction_per_trade
            if settings.backtest.capital_fraction_per_trade
            else 0.0
        )
        enriched["confidence_bucket"] = metadata.get("confidence_bucket", "medium")
        enriched["trailing_active"] = bool(metadata.get("trailing_active", False))
        enriched["trailing_anchor_price"] = metadata.get("trailing_anchor_price")
        enriched["account_net_roi_percent"] = account_net_roi_percent
        enriched["account_gross_roi_percent"] = gross_account_roi_percent
        enriched["position_net_roi_percent"] = (
            (enriched["net_pnl_usd"] / position_margin_usd) * 100.0 if position_margin_usd else 0.0
        )
        enriched["position_gross_roi_percent"] = (
            (enriched["gross_pnl_usd"] / position_margin_usd) * 100.0 if position_margin_usd else 0.0
        )
        enriched["net_roi_percent"] = account_net_roi_percent
        enriched["gross_roi_percent"] = gross_account_roi_percent
        enriched_positions.append(enriched)
    return enriched_positions


def _default_kill_switch_state() -> dict:
    return {
        "active": False,
        "reason": None,
        "source": None,
        "activated_at": None,
        "deactivated_at": None,
        "closed_position_count": 0,
        "closed_symbols": [],
        "last_updated_at": None,
    }


def _require_api_key(request: Request, settings: Settings) -> None:
    if not settings.dashboard.api_key:
        return
    provided = request.headers.get(settings.dashboard.api_key_header)
    if provided != settings.dashboard.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
