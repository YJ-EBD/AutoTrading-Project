from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings
from ..data.ingestion import KlineIngestionService
from ..data.live import CombinedKlineStreamClient
from ..exchange.client import BinancePublicClient, ClientDependencies
from ..exchange.rate_limit import RateBudgetManager
from ..paper.logging_utils import ensure_file_log_handler
from ..paper.models import PaperDecision, PaperPosition
from ..paper.repository import PaperTradeRepository
from ..storage import DiskCache
from ..utils import utc_now
from ..paper.runtime import _normalize_kline


LOGGER = logging.getLogger(__name__)


class HydraPaperRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = PaperTradeRepository(settings.hydra_paper_state_db)
        cache = DiskCache(settings.cache_root)
        rate_budget = RateBudgetManager(settings.exchange)
        self.client = BinancePublicClient(ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget))
        self.ingestion = KlineIngestionService(settings, self.client)
        self.stream_client = CombinedKlineStreamClient(settings)
        self.stop_event = asyncio.Event()
        self._runtime_task: asyncio.Task[None] | None = None
        self.raw_frames: dict[str, pd.DataFrame] = {}
        self.symbols: list[str] = []
        self._indicator_calculator: Any | None = None
        self._regime_detector: Any | None = None
        self._signal_generator: Any | None = None
        self._candle_cls: Any | None = None

    async def start(self) -> None:
        if self._runtime_task and not self._runtime_task.done():
            return
        if self.stop_event.is_set():
            self.stop_event = asyncio.Event()
        ensure_file_log_handler(self.settings.hydra_paper_log_path)
        await asyncio.to_thread(self._bootstrap)
        self._runtime_task = asyncio.create_task(self.run_forever(), name="hydra-paper-runtime")
        self._set_service_status(is_running=True, started_at=utc_now().isoformat(), stopped_at=None)
        LOGGER.info("Hydra paper runtime started pid=%s symbols=%s", os.getpid(), len(self.symbols))

    async def stop(self) -> None:
        if self._runtime_task is None:
            self._set_service_status(is_running=False, stopped_at=utc_now().isoformat())
            self._set_stream_status(status="stopped")
            return
        self.stop_event.set()
        self._runtime_task.cancel()
        try:
            await self._runtime_task
        except asyncio.CancelledError:
            pass
        self._runtime_task = None
        self._set_service_status(is_running=False, stopped_at=utc_now().isoformat())
        self._set_stream_status(status="stopped")
        LOGGER.info("Hydra paper runtime stopped pid=%s", os.getpid())

    async def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self.symbols:
                    await asyncio.sleep(5)
                    continue
                async for payload in self.stream_client.stream_klines(
                    self.symbols,
                    self.settings.hydra_compare.timeframe,
                    status_handler=self._handle_stream_event,
                ):
                    await self.process_stream_message(payload)
                    if self.stop_event.is_set():
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("Hydra paper runtime loop failed: %s", exc)
                self.repository.set_state(
                    "runtime_status",
                    {"status": "error", "timestamp": utc_now().isoformat(), "message": str(exc)},
                )
                self._set_stream_status(status="error", last_error=str(exc))
                await asyncio.sleep(5)

    async def serve(self) -> None:
        await self.start()
        try:
            await self.stop_event.wait()
        finally:
            await self.stop()

    async def process_stream_message(self, payload: dict[str, Any]) -> None:
        stream_data = payload.get("data", payload)
        kline = stream_data.get("k")
        if not kline:
            return
        symbol = str(stream_data.get("s") or kline.get("s"))
        if symbol not in self.raw_frames:
            return
        update = _normalize_kline(symbol, kline)
        await asyncio.to_thread(self._mark_active_positions, symbol, update)
        if update["is_closed"]:
            await asyncio.to_thread(self._finalize_closed_candle, symbol, update)

    def snapshot(self) -> dict[str, Any]:
        overview = self.repository.overview(decision_limit=200, closed_trade_limit=200)
        starting_equity = self.settings.hydra_compare.benchmark_initial_capital_usd
        overview = {
            **overview,
            "starting_equity_usd": starting_equity,
            "trade_amount_usd": self.settings.hydra_compare.benchmark_trade_amount_usd,
            "realized_expectancy_usd": float(overview.get("realized_expectancy", 0.0)) * starting_equity,
            "realized_net_pnl_usd": float(overview.get("realized_net_return_sum", 0.0)) * starting_equity,
            "selected_symbols": list(self.symbols),
        }
        service_status = self.repository.get_state("service_status", {})
        service_status.update(
            {
                "pid": os.getpid(),
                "runtime_task_running": bool(self._runtime_task and not self._runtime_task.done()),
                "is_running": bool(self._runtime_task and not self._runtime_task.done()),
            }
        )
        self.repository.set_state("service_status", service_status)
        return {
            "overview": overview,
            "runtime_status": self.repository.get_state("runtime_status", {}),
            "service_status": service_status,
            "stream_status": self.repository.get_state("stream_status", {}),
            "active_positions": self.repository.list_positions(status="active", limit=50),
            "closed_positions": self.repository.list_positions(status="closed", limit=20),
        }

    def _bootstrap(self) -> None:
        self._prepare_hydra_imports()
        self.symbols = self._selected_symbols()[: self.settings.hydra_compare.paper_symbols_limit]
        self.raw_frames = {}
        for symbol in self.symbols:
            frame = self.ingestion.backfill_symbol(symbol)
            self.raw_frames[symbol] = frame.tail(self.settings.hydra_compare.paper_max_runtime_bars).copy()
        self.repository.set_state(
            "runtime_status",
            {
                "status": "bootstrapped",
                "timestamp": utc_now().isoformat(),
                "symbol_count": len(self.symbols),
                "symbols": list(self.symbols),
                "log_path": str(self.settings.hydra_paper_log_path),
            },
        )
        self._set_stream_status(status="idle", symbol_count=len(self.symbols), interval=self.settings.hydra_compare.timeframe)

    def _prepare_hydra_imports(self) -> None:
        repo = Path(self.settings.hydra_compare.repo_path).resolve()
        db_path = repo / "data" / "hydra.db"
        os.environ["HYDRA_API_KEY"] = self.settings.hydra_compare.api_key
        os.environ["HYDRA_PROFILE"] = "lite"
        os.environ["HYDRA_FAKE_REDIS"] = "1"
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        os.environ["DB_URL"] = f"sqlite:///{db_path.as_posix()}"
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from hydra.data.models import Candle
        from hydra.indicator.calculator import IndicatorCalculator
        from hydra.regime.detector import RegimeDetector
        from hydra.strategy.signal import SignalGenerator

        self._candle_cls = Candle
        self._indicator_calculator = IndicatorCalculator()
        self._regime_detector = RegimeDetector()
        self._signal_generator = SignalGenerator()

    def _selected_symbols(self) -> list[str]:
        manifest_path = self.settings.deployment_manifest_path
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            symbols = list(manifest.get("selected_symbols", []) or [])
            if symbols:
                return symbols
        latest_universe = self.settings.artifact_root / "latest" / "universe.csv"
        if latest_universe.exists():
            frame = pd.read_csv(latest_universe)
            if "symbol" in frame.columns:
                return frame["symbol"].astype(str).tolist()
        return []

    def _mark_active_positions(self, symbol: str, update: dict[str, Any]) -> None:
        positions = [item for item in self.repository.list_active_positions() if item["symbol"] == symbol]
        for position in positions:
            metadata = dict(position.get("metadata_json") or {})
            qty = float(metadata.get("qty", 0.0))
            if qty <= 0:
                continue
            entry_price = float(position["entry_observed_price"])
            gross_pnl_usd = (float(update["close"]) - entry_price) * qty
            net_pnl_usd = gross_pnl_usd - self._round_trip_fees_usd(entry_price, float(update["close"]), qty)
            gross_return = gross_pnl_usd / self.settings.hydra_compare.benchmark_initial_capital_usd
            net_return = net_pnl_usd / self.settings.hydra_compare.benchmark_initial_capital_usd
            adverse_pnl = (float(update["low"]) - entry_price) * qty
            favorable_pnl = (float(update["high"]) - entry_price) * qty
            self.repository.update_active_mark(
                int(position["position_id"]),
                latest_observed_price=float(update["close"]),
                gross_return=gross_return,
                net_return=net_return,
                max_adverse_excursion=min(float(position["max_adverse_excursion"]), adverse_pnl / self.settings.hydra_compare.benchmark_initial_capital_usd),
                max_favorable_excursion=max(float(position["max_favorable_excursion"]), favorable_pnl / self.settings.hydra_compare.benchmark_initial_capital_usd),
                bars_held=self._bars_held(str(position["opened_at"]), update["open_time"]),
            )

    def _finalize_closed_candle(self, symbol: str, update: dict[str, Any]) -> None:
        self._upsert_closed_candle(symbol, update)
        signal = self._latest_signal(symbol)
        if signal is None:
            return
        if signal["signal"] == "BUY":
            self._handle_buy_signal(symbol, update, signal)
        elif signal["signal"] == "SELL":
            self._handle_sell_signal(symbol, update, signal)

    def _upsert_closed_candle(self, symbol: str, update: dict[str, Any]) -> None:
        row = pd.DataFrame(
            [
                {
                    "open": update["open"],
                    "high": update["high"],
                    "low": update["low"],
                    "close": update["close"],
                    "volume": update["volume"],
                    "close_time": update["close_time"],
                    "quote_asset_volume": update["quote_asset_volume"],
                    "trade_count": update["trade_count"],
                    "taker_buy_base_volume": update["taker_buy_base_volume"],
                    "taker_buy_quote_volume": update["taker_buy_quote_volume"],
                }
            ],
            index=pd.DatetimeIndex([update["open_time"]], tz="UTC"),
        )
        frame = self.raw_frames[symbol]
        frame = pd.concat([frame.loc[frame.index != row.index[0]], row]).sort_index().tail(self.settings.hydra_compare.paper_max_runtime_bars)
        self.raw_frames[symbol] = frame
        self.repository.set_state(
            "runtime_status",
            {
                "status": "running",
                "timestamp": utc_now().isoformat(),
                "last_symbol": symbol,
                "last_candle_time": str(update["open_time"]),
                "log_path": str(self.settings.hydra_paper_log_path),
            },
        )

    def _latest_signal(self, symbol: str) -> dict[str, Any] | None:
        frame = self.raw_frames[symbol]
        if frame.empty or len(frame) < 210:
            return None
        candles = [
            self._candle_cls(
                market=self.settings.hydra_compare.market,
                symbol=symbol,
                timeframe=self.settings.hydra_compare.timeframe,
                open_time=int(index.value // 10**6),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=int(pd.Timestamp(row["close_time"]).value // 10**6),
            )
            for index, row in frame.tail(max(210, self.settings.hydra_compare.paper_initial_lookback_bars)).iterrows()
        ]
        indicators = self._indicator_calculator.compute(candles)
        if not indicators:
            return None
        close = float(frame["close"].iloc[-1])
        regime = self._regime_detector.detect(indicators, close)
        signal = self._signal_generator.generate(indicators, regime, close)
        return {
            "signal": str(signal.signal),
            "reason": str(signal.reason),
            "price": float(signal.price),
            "ts": int(signal.ts),
            "atr": float(indicators.get("ATR_14") or 0.0),
            "regime": regime,
        }

    def _handle_buy_signal(self, symbol: str, update: dict[str, Any], signal: dict[str, Any]) -> None:
        if self.repository.has_active_symbol(symbol):
            return
        if len(self.repository.list_active_positions()) >= self.settings.portfolio.max_concurrent_positions:
            return
        observed_price = float(update["close"])
        decision = PaperDecision(
            decided_at=utc_now().isoformat(),
            symbol=symbol,
            strategy_id="hydra_signal_generator",
            family="hydra",
            side="long",
            signal_time=str(update["open_time"]),
            observed_price=observed_price,
            atr_value=float(signal["atr"]),
            signal_strength=1.0,
            ml_probability=1.0,
            ml_threshold=0.0,
            ml_accepted=True,
            llm_enabled=False,
            llm_action=None,
            llm_confidence=None,
            llm_reason=None,
            final_action="allow",
            portfolio_reason="hydra_buy_signal",
            payload={"reason": signal["reason"], "regime": signal["regime"]},
        )
        decision_id = self.repository.record_decision(decision)
        qty = self.settings.hydra_compare.benchmark_trade_amount_usd / observed_price if observed_price else 0.0
        atr_value = float(signal["atr"])
        position_id = self.repository.open_position(
            PaperPosition(
                decision_id=decision_id,
                symbol=symbol,
                strategy_id="hydra_signal_generator",
                family="hydra",
                side="long",
                opened_at=str(update["open_time"]),
                entry_observed_price=observed_price,
                latest_observed_price=observed_price,
                stop_price=observed_price - atr_value if atr_value else observed_price,
                target_price=observed_price + atr_value if atr_value else observed_price,
                liquidation_price=0.0,
                atr_value=atr_value,
                model_probability=1.0,
                llm_action=None,
                llm_confidence=None,
                metadata={
                    "qty": qty,
                    "entry_reason": signal["reason"],
                    "regime": signal["regime"],
                },
            )
        )
        LOGGER.info(
            "Hydra paper opened position id=%s symbol=%s price=%.6f qty=%.6f reason=%s",
            position_id,
            symbol,
            observed_price,
            qty,
            signal["reason"],
        )

    def _handle_sell_signal(self, symbol: str, update: dict[str, Any], signal: dict[str, Any]) -> None:
        positions = [item for item in self.repository.list_active_positions() if item["symbol"] == symbol]
        if not positions:
            return
        for position in positions:
            metadata = dict(position.get("metadata_json") or {})
            qty = float(metadata.get("qty", 0.0))
            exit_price = float(update["close"])
            entry_price = float(position["entry_observed_price"])
            gross_pnl_usd = (exit_price - entry_price) * qty
            net_pnl_usd = gross_pnl_usd - self._round_trip_fees_usd(entry_price, exit_price, qty)
            gross_return = gross_pnl_usd / self.settings.hydra_compare.benchmark_initial_capital_usd
            net_return = net_pnl_usd / self.settings.hydra_compare.benchmark_initial_capital_usd
            self.repository.close_position(
                int(position["position_id"]),
                closed_at=str(update["open_time"]),
                exit_observed_price=exit_price,
                exit_trigger_price=exit_price,
                exit_reason="signal_exit",
                gross_return=gross_return,
                net_return=net_return,
                max_adverse_excursion=float(position["max_adverse_excursion"]),
                max_favorable_excursion=float(position["max_favorable_excursion"]),
                bars_held=self._bars_held(str(position["opened_at"]), update["open_time"]),
                metadata={"source": "hydra_signal", "exit_reason": signal["reason"]},
            )
            LOGGER.info(
                "Hydra paper closed position symbol=%s exit=%.6f pnl_usd=%.4f reason=%s",
                symbol,
                exit_price,
                net_pnl_usd,
                signal["reason"],
            )

    def _round_trip_fees_usd(self, entry_price: float, exit_price: float, qty: float) -> float:
        commission_pct = self.settings.backtest.fee_bps_per_side / 10_000
        entry_fee = entry_price * qty * commission_pct
        exit_fee = exit_price * qty * commission_pct
        return entry_fee + exit_fee

    def _bars_held(self, opened_at: str, current_time: pd.Timestamp) -> int:
        opened = pd.Timestamp(opened_at)
        delta = current_time - opened
        bar_delta = pd.Timedelta("15min")
        return max(int(delta / bar_delta), 0)

    async def _handle_stream_event(self, event: str, payload: dict[str, Any]) -> None:
        state = self.repository.get_state("stream_status", {})
        state.update(payload)
        state["status"] = event
        if event == "message":
            state["last_message_at"] = utc_now().isoformat()
        elif event == "interrupted":
            state["last_interrupted_at"] = utc_now().isoformat()
            state["last_error"] = payload.get("error")
            state["reconnect_count"] = int(state.get("reconnect_count", 0) or 0) + 1
        elif event == "connected":
            state["last_connected_at"] = utc_now().isoformat()
            state["last_error"] = None
        elif event == "retrying":
            state["retry_in_seconds"] = payload.get("retry_in_seconds")
        self.repository.set_state("stream_status", state)

    def _set_service_status(self, **updates: Any) -> None:
        state = self.repository.get_state("service_status", {})
        state.update({"pid": os.getpid(), **updates})
        self.repository.set_state("service_status", state)

    def _set_stream_status(self, **updates: Any) -> None:
        state = self.repository.get_state("stream_status", {})
        state.update(updates)
        self.repository.set_state("stream_status", state)
