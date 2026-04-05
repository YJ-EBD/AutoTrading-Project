from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import uvicorn
import pandas as pd
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse

from ..config import Settings
from ..data.ingestion import KlineIngestionService
from ..exchange.client import BinancePublicClient, ClientDependencies
from ..exchange.rate_limit import RateBudgetManager
from ..storage import DiskCache
from ..utils import dump_json, utc_now
from .runtime import HydraPaperRuntime


def hydra_repo_path(settings: Settings) -> Path:
    return Path(settings.hydra_compare.repo_path).resolve()


def hydra_benchmark_summary_path(settings: Settings) -> Path:
    return settings.resolve_path(settings.hydra_compare.summary_path)


def serve_hydra_runtime(settings: Settings) -> None:
    repo = hydra_repo_path(settings)
    _prepare_hydra_environment(settings)
    os.chdir(repo)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from hydra.main import create_app

    app = create_app()
    hydra_paper_runtime = HydraPaperRuntime(settings) if settings.hydra_compare.paper_enabled else None

    if hydra_paper_runtime is not None:
        app.state.hydra_paper_runtime = hydra_paper_runtime

        @app.get("/viewer")
        async def hydra_viewer() -> HTMLResponse:
            return HTMLResponse(_hydra_viewer_html())

        @app.get("/public/status")
        async def hydra_public_status() -> JSONResponse:
            return JSONResponse(
                {
                    "health": {"status": "ok"},
                    "service_status": hydra_paper_runtime.snapshot()["service_status"],
                    "runtime_status": hydra_paper_runtime.snapshot()["runtime_status"],
                    "stream_status": hydra_paper_runtime.snapshot()["stream_status"],
                }
            )

        @app.get("/public/paper/status")
        async def hydra_public_paper_status() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot())

        @app.get("/public/paper/overview")
        async def hydra_public_paper_overview() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot()["overview"])

        @app.get("/paper/status")
        async def hydra_paper_status() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot())

        @app.get("/paper/overview")
        async def hydra_paper_overview() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot()["overview"])

        @app.get("/paper/positions/active")
        async def hydra_paper_active_positions() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot()["active_positions"])

        @app.get("/paper/positions/closed")
        async def hydra_paper_closed_positions() -> JSONResponse:
            return JSONResponse(hydra_paper_runtime.snapshot()["closed_positions"])

        threading.Thread(
            target=lambda: asyncio.run(hydra_paper_runtime.serve()),
            name="hydra-paper-runtime",
            daemon=True,
        ).start()

    uvicorn.run(
        app,
        host=settings.hydra_compare.host,
        port=settings.hydra_compare.port,
        reload=False,
        log_level="info",
    )


def fetch_hydra_runtime_snapshot(settings: Settings) -> dict[str, Any]:
    base_url = f"http://{settings.hydra_compare.host}:{settings.hydra_compare.port}"
    health = _fetch_json(f"{base_url}/health")
    status = _fetch_json(f"{base_url}/status", api_key=settings.hydra_compare.api_key)
    pnl = _fetch_json(f"{base_url}/pnl", api_key=settings.hydra_compare.api_key)
    positions = _fetch_json(f"{base_url}/positions", api_key=settings.hydra_compare.api_key)
    paper_status = _fetch_json(f"{base_url}/paper/status", api_key=settings.hydra_compare.api_key)
    paper_overview = _fetch_json(f"{base_url}/paper/overview", api_key=settings.hydra_compare.api_key)
    paper_active_positions = _fetch_json(f"{base_url}/paper/positions/active", api_key=settings.hydra_compare.api_key)
    paper_closed_positions = _fetch_json(f"{base_url}/paper/positions/closed", api_key=settings.hydra_compare.api_key)
    return {
        "base_url": base_url,
        "health": health,
        "status": status,
        "pnl": pnl,
        "positions": positions,
        "paper_status": paper_status,
        "paper_overview": paper_overview,
        "paper_active_positions": paper_active_positions,
        "paper_closed_positions": paper_closed_positions,
        "available": all(not item.get("error") for item in [health, status, pnl, positions]),
        "paper_available": (
            not paper_status.get("error")
            and not paper_overview.get("error")
            and isinstance(paper_active_positions, list)
            and isinstance(paper_closed_positions, list)
        ),
        "fetched_at": utc_now().isoformat(),
    }


def load_hydra_benchmark_summary(settings: Settings) -> dict[str, Any]:
    path = hydra_benchmark_summary_path(settings)
    if not path.exists():
        return {
            "available": False,
            "path": str(path),
            "message": "Hydra benchmark summary not generated yet.",
        }
    return {
        "available": True,
        "path": str(path),
        **json.loads(path.read_text(encoding="utf-8")),
    }


def run_hydra_benchmark(settings: Settings) -> dict[str, Any]:
    summary = asyncio.run(_run_hydra_benchmark_async(settings))
    dump_json(hydra_benchmark_summary_path(settings), summary)
    return summary


async def _run_hydra_benchmark_async(settings: Settings) -> dict[str, Any]:
    repo = hydra_repo_path(settings)
    _prepare_hydra_environment(settings)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from hydra.backtest.runner import BacktestRunner
    from hydra.data.models import Candle
    from hydra.data.storage import create_store
    from hydra.indicator.calculator import IndicatorCalculator
    from hydra.regime.detector import RegimeDetector
    from hydra.strategy.signal import SignalGenerator

    store = create_store()
    await store.init()
    try:
        selected_symbols = _selected_symbols(settings)[: settings.hydra_compare.benchmark_symbols_limit]
        ingestion = _build_ingestion_service(settings)
        synced_symbols: list[str] = []
        symbol_results: list[dict[str, Any]] = []
        timeframe = settings.hydra_compare.timeframe
        lookback_days = settings.hydra_compare.benchmark_lookback_days
        bars_needed = _bars_for_lookback(timeframe, lookback_days, warmup_bars=260)

        for symbol in selected_symbols:
            frame = await asyncio.to_thread(ingestion.backfill_symbol, symbol)
            frame = frame.tail(bars_needed).copy()
            if frame.empty:
                continue
            candles = _frame_to_hydra_candles(frame, symbol, timeframe, Candle, settings.hydra_compare.market)
            await store.save(candles)
            synced_symbols.append(symbol)
            since = int(frame.index[-1].value // 10**6) - (lookback_days * 24 * 60 * 60 * 1000)
            until = int(frame.index[-1].value // 10**6)
            runner = BacktestRunner(
                store=store,
                calculator=IndicatorCalculator(),
                detector=RegimeDetector(),
                generator=SignalGenerator(),
                initial_capital=settings.hydra_compare.benchmark_initial_capital_usd,
                trade_amount_usd=settings.hydra_compare.benchmark_trade_amount_usd,
                commission_pct=settings.backtest.fee_bps_per_side / 10_000,
            )
            result = await runner.run(
                market=settings.hydra_compare.market,
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                until=until,
            )
            symbol_results.append(
                {
                    "symbol": symbol,
                    "initial_capital": result.initial_capital,
                    "final_equity": result.final_equity,
                    "trade_count": result.metrics.get("total_trades", 0),
                    "total_return_pct": result.metrics.get("total_return_pct", 0.0),
                    "win_rate": result.metrics.get("win_rate", 0.0),
                    "max_drawdown_pct": result.metrics.get("max_drawdown_pct", 0.0),
                    "sharpe_ratio": result.metrics.get("sharpe_ratio", 0.0),
                    "avg_pnl_usd": result.metrics.get("avg_pnl_usd", 0.0),
                    "since": result.since,
                    "until": result.until,
                }
            )

        aggregate = _aggregate_hydra_results(symbol_results)
        return {
            "generated_at": utc_now().isoformat(),
            "repo_path": str(repo),
            "market": settings.hydra_compare.market,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "symbol_limit": settings.hydra_compare.benchmark_symbols_limit,
            "synced_symbols": synced_symbols,
            "symbol_count": len(symbol_results),
            "aggregate": aggregate,
            "per_symbol": symbol_results,
        }
    finally:
        await store.close()


def _prepare_hydra_environment(settings: Settings) -> None:
    db_path = hydra_repo_path(settings) / "data" / "hydra.db"
    os.environ["HYDRA_API_KEY"] = settings.hydra_compare.api_key
    os.environ["HYDRA_PROFILE"] = "lite"
    os.environ["HYDRA_FAKE_REDIS"] = "1"
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["DB_URL"] = f"sqlite:///{db_path.as_posix()}"


def _build_ingestion_service(settings: Settings) -> KlineIngestionService:
    cache = DiskCache(settings.cache_root)
    rate_budget = RateBudgetManager(settings.exchange)
    client = BinancePublicClient(ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget))
    return KlineIngestionService(settings, client)


def _selected_symbols(settings: Settings) -> list[str]:
    if settings.deployment_manifest_path.exists():
        manifest = json.loads(settings.deployment_manifest_path.read_text(encoding="utf-8"))
        symbols = list(manifest.get("selected_symbols", []) or [])
        if symbols:
            return symbols
    latest_universe = settings.artifact_root / "latest" / "universe.csv"
    if latest_universe.exists():
        import pandas as pd

        frame = pd.read_csv(latest_universe)
        if "symbol" in frame.columns:
            return frame["symbol"].astype(str).tolist()
    return []


def _bars_for_lookback(timeframe: str, lookback_days: int, *, warmup_bars: int) -> int:
    per_day = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6, "1d": 1}.get(timeframe, 96)
    return (per_day * lookback_days) + warmup_bars


def _frame_to_hydra_candles(frame, symbol: str, timeframe: str, candle_cls, market: str) -> list[Any]:
    candles = []
    for open_time, row in frame.iterrows():
        close_time = row.get("close_time")
        if hasattr(close_time, "value"):
            close_time_ms = int(close_time.value // 10**6)
        elif close_time is None:
            close_time_ms = int(open_time.value // 10**6)
        else:
            close_time_ms = int(pd.Timestamp(close_time).value // 10**6)  # type: ignore[name-defined]
        candles.append(
            candle_cls(
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                open_time=int(open_time.value // 10**6),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=close_time_ms,
            )
        )
    return candles


def _aggregate_hydra_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "initial_capital_total": 0.0,
            "final_equity_total": 0.0,
            "total_return_pct": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_symbol_return_pct": 0.0,
            "profitable_symbols": 0,
            "max_drawdown_pct": 0.0,
            "avg_sharpe_ratio": 0.0,
        }
    initial_total = sum(float(item["initial_capital"]) for item in results)
    final_total = sum(float(item["final_equity"]) for item in results)
    total_trades = sum(int(item["trade_count"]) for item in results)
    profitable_symbols = sum(float(item["total_return_pct"]) > 0 for item in results)
    win_rates = [float(item["win_rate"]) for item in results]
    returns = [float(item["total_return_pct"]) for item in results]
    drawdowns = [float(item["max_drawdown_pct"]) for item in results]
    sharpes = [float(item["sharpe_ratio"]) for item in results]
    return {
        "initial_capital_total": initial_total,
        "final_equity_total": final_total,
        "total_return_pct": ((final_total - initial_total) / initial_total * 100.0) if initial_total else 0.0,
        "total_trades": total_trades,
        "win_rate": (sum(win_rates) / len(win_rates)) if win_rates else 0.0,
        "avg_symbol_return_pct": (sum(returns) / len(returns)) if returns else 0.0,
        "profitable_symbols": profitable_symbols,
        "max_drawdown_pct": max(drawdowns) if drawdowns else 0.0,
        "avg_sharpe_ratio": (sum(sharpes) / len(sharpes)) if sharpes else 0.0,
    }


def _fetch_json(url: str, *, api_key: str | None = None, timeout: int = 5) -> dict[str, Any]:
    request = Request(url)
    if api_key:
        request.add_header("X-HYDRA-KEY", api_key)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"error": f"http_{exc.code}", "detail": body}
    except URLError as exc:
        return {"error": "unreachable", "detail": str(exc)}
    except Exception as exc:
        return {"error": "unexpected", "detail": str(exc)}


def _hydra_viewer_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hydra Viewer</title>
  <style>
    body { margin: 0; font-family: "Segoe UI", sans-serif; background: #f6f7f9; color: #172026; }
    main { width: min(1100px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }
    h1 { margin: 0 0 8px; font-size: 40px; }
    p { color: #5a6872; }
    .grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 16px; margin-top: 20px; }
    .card { grid-column: span 4; background: #fff; border: 1px solid #e5e7eb; border-radius: 18px; padding: 18px; box-shadow: 0 16px 40px rgba(0,0,0,.06); }
    .card.wide { grid-column: span 12; }
    .label { font-size: 12px; text-transform: uppercase; letter-spacing: .12em; color: #667085; }
    .value { margin-top: 6px; font-size: 24px; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #eceff3; }
    th { color: #667085; font-size: 11px; text-transform: uppercase; letter-spacing: .12em; }
    .good { color: #166534; }
    .bad { color: #b42318; }
    a { color: #0f766e; text-decoration: none; }
    @media (max-width: 900px) { .card { grid-column: span 12; } }
  </style>
</head>
<body>
  <main>
    <h1>Hydra Viewer</h1>
    <p>API 키 없이 볼 수 있는 읽기 전용 Hydra 상태 페이지입니다.</p>
    <p><a href="/health">/health</a> · <a href="/public/status">/public/status</a> · <a href="/public/paper/status">/public/paper/status</a></p>
    <section class="grid">
      <article class="card"><div class="label">Hydra 서버</div><div class="value" id="server-status">-</div></article>
      <article class="card"><div class="label">Paper 런타임</div><div class="value" id="runtime-status">-</div></article>
      <article class="card"><div class="label">스트림</div><div class="value" id="stream-status">-</div></article>
      <article class="card"><div class="label">활성 포지션</div><div class="value" id="active-count">-</div></article>
      <article class="card"><div class="label">종료 포지션</div><div class="value" id="closed-count">-</div></article>
      <article class="card"><div class="label">실현 손익</div><div class="value" id="realized-pnl">-</div></article>
      <article class="card wide">
        <h2>최근 종료 포지션</h2>
        <table>
          <thead>
            <tr><th>심볼</th><th>진입</th><th>청산</th><th>사유</th><th>ROI</th></tr>
          </thead>
          <tbody id="closed-body"><tr><td colspan="5">로딩 중...</td></tr></tbody>
        </table>
      </article>
    </section>
  </main>
  <script>
    function fmtPct(v) {
      const n = Number(v || 0);
      return `${n.toFixed(2)}%`;
    }
    function fmtUsd(v) {
      const n = Number(v || 0);
      return `$${n.toFixed(2)}`;
    }
    function cls(v) {
      return Number(v || 0) >= 0 ? "good" : "bad";
    }
    async function refresh() {
      const [serviceRes, paperRes] = await Promise.all([
        fetch('/public/status', { cache: 'no-store' }),
        fetch('/public/paper/status', { cache: 'no-store' }),
      ]);
      const service = await serviceRes.json();
      const paper = await paperRes.json();
      document.getElementById('server-status').textContent = service.health?.status || '-';
      document.getElementById('runtime-status').textContent = paper.service_status?.is_running ? 'running' : 'stopped';
      document.getElementById('stream-status').textContent = paper.stream_status?.status || '-';
      document.getElementById('active-count').textContent = String(paper.overview?.active_positions ?? 0);
      document.getElementById('closed-count').textContent = String(paper.overview?.closed_positions ?? 0);
      const pnl = paper.overview?.realized_net_pnl_usd ?? 0;
      const pnlEl = document.getElementById('realized-pnl');
      pnlEl.textContent = fmtUsd(pnl);
      pnlEl.className = `value ${cls(pnl)}`;
      const rows = Array.isArray(paper.closed_positions) && paper.closed_positions.length
        ? paper.closed_positions.map((item) => `
            <tr>
              <td>${item.symbol ?? '-'}</td>
              <td>${item.entry_observed_price ?? '-'}</td>
              <td>${item.exit_observed_price ?? '-'}</td>
              <td>${item.exit_reason ?? '-'}</td>
              <td class="${cls((Number(item.net_return || 0) * 100))}">${fmtPct(Number(item.net_return || 0) * 100)}</td>
            </tr>
          `).join('')
        : '<tr><td colspan="5">종료 포지션이 아직 없습니다.</td></tr>';
      document.getElementById('closed-body').innerHTML = rows;
    }
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>"""
