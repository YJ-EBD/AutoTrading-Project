from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..config import Settings
from ..data.ingestion import KlineIngestionService
from ..data.live import CombinedKlineStreamClient
from ..data.quality import timeframe_to_frequency
from ..exchange.client import BinancePublicClient, ClientDependencies
from ..exchange.rate_limit import RateBudgetManager
from ..features.engine import enrich_ohlcv
from ..llm.ollama import LLMDecision, OllamaDecisionClient
from ..ml.deployment import (
    PaperDeploymentBundle,
    build_deployment_bundle,
    load_deployment_bundle,
)
from ..orchestration.research_loop import ResearchLoop
from ..storage import DiskCache
from ..strategies.base import StrategyVariant
from ..strategies.templates import build_strategy_templates
from ..utils import utc_now
from .models import PaperDecision, PaperPosition, RetuneEvent
from .repository import PaperTradeRepository


LOGGER = logging.getLogger(__name__)


class RestartRuntimeStream(Exception):
    pass


class PaperTradingRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = PaperTradeRepository(settings.paper_state_db)
        cache = DiskCache(settings.cache_root)
        rate_budget = RateBudgetManager(settings.exchange)
        self.client = BinancePublicClient(ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget))
        self.ingestion = KlineIngestionService(settings, self.client)
        self.stream_client = CombinedKlineStreamClient(settings)
        self.raw_frames: dict[str, pd.DataFrame] = {}
        self.enriched_frames: dict[str, pd.DataFrame] = {}
        self.bundle: PaperDeploymentBundle | None = None
        self.template_lookup = {template.family: template for template in build_strategy_templates()}
        self.variants: list[StrategyVariant] = []
        self.stop_event = asyncio.Event()
        self._runtime_task: asyncio.Task[None] | None = None
        self._retune_task: asyncio.Task[None] | None = None
        self._llm_client: OllamaDecisionClient | None = None
        self._llm_available = False
        self._restart_stream_requested = False
        self._retune_delay_applied = False

    async def start(self) -> None:
        if self._runtime_task and not self._runtime_task.done():
            return
        if self.stop_event.is_set():
            self.stop_event = asyncio.Event()
        if self.bundle is None or not self.raw_frames:
            await self.bootstrap()
        self._runtime_task = asyncio.create_task(self.run_forever(), name="paper-runtime")
        if self.settings.paper.auto_retune and (self._retune_task is None or self._retune_task.done()):
            self._retune_delay_applied = False
            self._retune_task = asyncio.create_task(self.retune_forever(), name="paper-retune")
        self._set_service_status(
            is_running=True,
            started_at=utc_now().isoformat(),
            stopped_at=None,
        )
        self._set_stream_status(status="starting", last_error=None)
        LOGGER.info("Paper runtime started pid=%s", os.getpid())

    async def stop(self) -> None:
        if not self._runtime_task and not self._retune_task:
            self._set_service_status(is_running=False, stopped_at=utc_now().isoformat())
            self._set_stream_status(status="stopped")
            return
        self.stop_event.set()
        tasks = [task for task in [self._runtime_task, self._retune_task] if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._runtime_task = None
        self._retune_task = None
        self._set_service_status(is_running=False, stopped_at=utc_now().isoformat())
        self._set_stream_status(status="stopped")
        LOGGER.info("Paper runtime stopped pid=%s", os.getpid())

    async def bootstrap(self) -> None:
        await asyncio.to_thread(self._load_or_build_bundle)
        self._load_llm()
        await asyncio.to_thread(self._load_initial_frames)
        self.repository.set_state("deployment_manifest", asdict(self.bundle.manifest))
        self.repository.set_state(
            "runtime_status",
            {
                "status": "bootstrapped",
                "timestamp": utc_now().isoformat(),
                "log_path": str(self.settings.paper_log_path),
            },
        )
        self._set_stream_status(status="idle")

    async def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._restart_stream_requested = False
                symbols = self.bundle.manifest.selected_symbols if self.bundle else []
                if not symbols:
                    await asyncio.sleep(5)
                    continue
                async for payload in self.stream_client.stream_klines(
                    symbols,
                    self.settings.data.timeframe,
                    status_handler=self._handle_stream_event,
                ):
                    await self.process_stream_message(payload)
                    if self._restart_stream_requested:
                        raise RestartRuntimeStream
                    if self.stop_event.is_set():
                        break
            except RestartRuntimeStream:
                LOGGER.info("Restarting runtime stream to apply updated deployment universe.")
                self._set_stream_status(status="restarting")
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("Paper runtime loop failed: %s", exc)
                self.repository.set_state(
                    "runtime_status",
                    {"status": "error", "timestamp": utc_now().isoformat(), "message": str(exc)},
                )
                self._set_stream_status(status="error", last_error=str(exc))
                await asyncio.sleep(5)

    async def process_stream_message(self, payload: dict[str, Any]) -> None:
        stream_data = payload.get("data", payload)
        kline = stream_data.get("k")
        if not kline:
            return
        symbol = str(stream_data.get("s") or kline.get("s"))
        update = _normalize_kline(symbol, kline)
        if symbol not in self.raw_frames:
            return

        await asyncio.to_thread(self._mark_active_positions, symbol, update)

        if update["is_closed"]:
            await asyncio.to_thread(self._finalize_closed_candle, symbol, update)

    async def serve(self) -> None:
        await self.start()
        try:
            await self.stop_event.wait()
        finally:
            await self.stop()

    async def retune_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self._retune_delay_applied:
                    should_continue = await self._maybe_wait_initial_retune_delay()
                    self._retune_delay_applied = True
                    if not should_continue:
                        break
                await asyncio.to_thread(self._retune_if_due)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("Retune loop failed: %s", exc)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.settings.paper.retune_check_seconds)
            except asyncio.TimeoutError:
                continue

    def snapshot(self) -> dict[str, Any]:
        runtime_status = self.repository.get_state("runtime_status", {})
        service_status = self.repository.get_state("service_status", {})
        service_status.update(
            {
                "pid": os.getpid(),
                "runtime_task_running": bool(self._runtime_task and not self._runtime_task.done()),
                "retune_task_running": bool(self._retune_task and not self._retune_task.done()),
                "is_running": bool(self._runtime_task and not self._runtime_task.done()),
            }
        )
        return {
            "bundle_manifest": asdict(self.bundle.manifest) if self.bundle else None,
            "llm_available": self._llm_available,
            "overview": self.repository.overview(
                decision_limit=self.settings.dashboard.decision_log_limit,
                closed_trade_limit=self.settings.dashboard.closed_trade_limit,
            ),
            "runtime_status": runtime_status,
            "service_status": service_status,
            "stream_status": self.repository.get_state("stream_status", {}),
        }

    def _load_or_build_bundle(self) -> None:
        if self.settings.deployment_bundle_path.exists():
            self.bundle = load_deployment_bundle(self.settings.deployment_bundle_path)
        elif self.settings.deployment.auto_rebuild_on_start:
            self.bundle = build_deployment_bundle(self.settings)
        else:
            raise FileNotFoundError("Deployment bundle not found and auto rebuild is disabled.")
        self.variants = [
            StrategyVariant(
                family=str(item["family"]),
                name=str(item["name"]),
                parameters=dict(item["parameters"]),
            )
            for item in self.bundle.manifest.selected_variants
        ]

    def _load_llm(self) -> None:
        if not self.settings.local_llm.enabled:
            return
        self._llm_client = OllamaDecisionClient(self.settings.local_llm)
        self._llm_available = self._llm_client.ping()
        self.repository.set_state(
            "llm_status",
            {
                "enabled": True,
                "available": self._llm_available,
                "model": self.settings.local_llm.model,
                "checked_at": utc_now().isoformat(),
            },
        )

    def _load_initial_frames(self) -> None:
        self.raw_frames = {}
        self.enriched_frames = {}
        symbols = self.bundle.manifest.selected_symbols if self.bundle else []
        for symbol in symbols:
            frame = self.ingestion.backfill_symbol(symbol)
            frame = frame.tail(self.settings.paper.max_runtime_bars)
            self.raw_frames[symbol] = frame.copy()
            self.enriched_frames[symbol] = enrich_ohlcv(frame, self.settings)

    def _mark_active_positions(self, symbol: str, update: dict[str, Any]) -> None:
        positions = [item for item in self.repository.list_active_positions() if item["symbol"] == symbol]
        for position in positions:
            entry_price = float(position["entry_observed_price"])
            side = str(position["side"])
            gross_return = self._gross_return(side, entry_price, float(update["close"]))
            net_return = self._net_return(gross_return, "mark")
            adverse = max(
                float(position["max_adverse_excursion"]),
                self._gross_return(side, entry_price, float(update["low"] if side == "long" else update["high"])) * -1,
            )
            favorable = max(
                float(position["max_favorable_excursion"]),
                self._gross_return(side, entry_price, float(update["high"] if side == "long" else update["low"])),
            )
            bars_held = self._bars_held(str(position["opened_at"]), update["open_time"])
            self.repository.update_active_mark(
                int(position["position_id"]),
                latest_observed_price=float(update["close"]),
                gross_return=gross_return,
                net_return=net_return,
                max_adverse_excursion=adverse,
                max_favorable_excursion=favorable,
                bars_held=bars_held,
            )

            exit_reason, trigger_price = self._barrier_exit(position, update)
            if exit_reason is None:
                continue
            final_gross = self._gross_return(side, entry_price, float(update["close"]))
            final_net = self._net_return(final_gross, exit_reason)
            self.repository.close_position(
                int(position["position_id"]),
                closed_at=str(update["event_time"]),
                exit_observed_price=float(update["close"]),
                exit_trigger_price=trigger_price,
                exit_reason=exit_reason,
                gross_return=final_gross,
                net_return=final_net,
                max_adverse_excursion=adverse,
                max_favorable_excursion=favorable,
                bars_held=bars_held,
                metadata={"source": "kline_stream"},
            )
            LOGGER.info(
                "Closed paper position symbol=%s strategy=%s side=%s reason=%s observed_exit=%.6f trigger=%.6f net=%.5f",
                position["symbol"],
                position["strategy_id"],
                side,
                exit_reason,
                float(update["close"]),
                float(trigger_price) if trigger_price is not None else float("nan"),
                final_net,
            )

    def _finalize_closed_candle(self, symbol: str, update: dict[str, Any]) -> None:
        self._upsert_closed_candle(symbol, update)
        self._evaluate_signal_exits(symbol)
        self._evaluate_new_entries(symbol)

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
        frame = pd.concat([frame.loc[frame.index != row.index[0]], row]).sort_index().tail(self.settings.paper.max_runtime_bars)
        self.raw_frames[symbol] = frame
        self.enriched_frames[symbol] = enrich_ohlcv(frame, self.settings)
        self.repository.set_state(
            "runtime_status",
            {
                "status": "running",
                "timestamp": utc_now().isoformat(),
                "last_symbol": symbol,
                "last_candle_time": str(update["open_time"]),
                "log_path": str(self.settings.paper_log_path),
            },
        )

    def _evaluate_signal_exits(self, symbol: str) -> None:
        frame = self.enriched_frames[symbol]
        active_positions = [item for item in self.repository.list_active_positions() if item["symbol"] == symbol]
        if not active_positions:
            return
        for position in active_positions:
            variant = self._variant_by_strategy_id(str(position["strategy_id"]))
            template = self.template_lookup[variant.family]
            signal_frame = template.generate(frame, variant).signals
            latest = signal_frame.iloc[-1]
            close_price = float(frame["close"].iloc[-1])
            event_time = frame.index[-1]
            bars_held = self._bars_held(str(position["opened_at"]), event_time)
            should_close = False
            exit_reason = None
            if self.settings.paper.enable_signal_exit:
                if position["side"] == "long" and bool(latest["exit_long"]):
                    should_close = True
                    exit_reason = "signal_exit"
                if position["side"] == "short" and bool(latest["exit_short"]):
                    should_close = True
                    exit_reason = "signal_exit"
            if not should_close and bars_held >= self.settings.backtest.max_holding_bars:
                should_close = True
                exit_reason = "horizon"
            if not should_close:
                continue
            final_gross = self._gross_return(str(position["side"]), float(position["entry_observed_price"]), close_price)
            final_net = self._net_return(final_gross, str(exit_reason))
            self.repository.close_position(
                int(position["position_id"]),
                closed_at=str(event_time),
                exit_observed_price=close_price,
                exit_trigger_price=None,
                exit_reason=str(exit_reason),
                gross_return=final_gross,
                net_return=final_net,
                max_adverse_excursion=float(position["max_adverse_excursion"]),
                max_favorable_excursion=float(position["max_favorable_excursion"]),
                bars_held=bars_held,
                metadata={"source": "signal_exit"},
            )
            LOGGER.info(
                "Signal closed paper position symbol=%s strategy=%s side=%s reason=%s observed_exit=%.6f net=%.5f",
                position["symbol"],
                position["strategy_id"],
                position["side"],
                exit_reason,
                close_price,
                final_net,
            )

    def _evaluate_new_entries(self, symbol: str) -> None:
        frame = self.enriched_frames[symbol]
        latest_index = frame.index[-1]
        if pd.isna(frame["atr_14"].iloc[-1]):
            return

        for variant in self.variants:
            template = self.template_lookup[variant.family]
            signals = template.generate(frame, variant).signals
            latest = signals.iloc[-1]
            signal_strength = float(latest["signal_strength"])
            if bool(latest["entry_long"]):
                self._handle_candidate(symbol, variant, frame, latest_index, "long", signal_strength)
            if bool(latest["entry_short"]):
                self._handle_candidate(symbol, variant, frame, latest_index, "short", signal_strength)

    def _handle_candidate(
        self,
        symbol: str,
        variant: StrategyVariant,
        frame: pd.DataFrame,
        signal_time: pd.Timestamp,
        side: str,
        signal_strength: float,
    ) -> None:
        observed_price = float(frame.loc[signal_time, "close"])
        atr_value = float(frame.loc[signal_time, "atr_14"])
        event_frame = self._candidate_event_frame(symbol, variant, frame, signal_time, side, signal_strength)
        probability = self.bundle.probability_from_event_frame(event_frame)
        ml_threshold = float(self.bundle.manifest.threshold)
        ml_accepted = probability >= ml_threshold
        llm_decision = self._final_llm_decision(symbol, variant, side, signal_time, observed_price, atr_value, probability, signal_strength)
        final_action = "allow" if ml_accepted else "reject"
        portfolio_reason = "ml_threshold"
        if ml_accepted:
            final_action, portfolio_reason = self._portfolio_gate(
                symbol=symbol,
                side=side,
                probability=probability,
                llm_decision=llm_decision,
            )

        decision = PaperDecision(
            decided_at=utc_now().isoformat(),
            symbol=symbol,
            strategy_id=variant.strategy_id,
            family=variant.family,
            side=side,
            signal_time=str(signal_time),
            observed_price=observed_price,
            atr_value=atr_value,
            signal_strength=signal_strength,
            ml_probability=probability,
            ml_threshold=ml_threshold,
            ml_accepted=ml_accepted,
            llm_enabled=self._llm_available,
            llm_action=llm_decision.action if llm_decision else None,
            llm_confidence=llm_decision.confidence if llm_decision else None,
            llm_reason=llm_decision.reason if llm_decision else None,
            final_action=final_action,
            portfolio_reason=portfolio_reason,
            payload={
                "bundle_source_artifact": self.bundle.manifest.source_artifact,
                "model_name": self.bundle.manifest.model_name,
                "calibration_method": self.bundle.manifest.calibration_method,
            },
        )
        decision_id = self.repository.record_decision(decision)
        LOGGER.info(
            "Decision symbol=%s strategy=%s side=%s ml_prob=%.4f threshold=%.4f llm=%s final=%s reason=%s",
            symbol,
            variant.strategy_id,
            side,
            probability,
            ml_threshold,
            llm_decision.action if llm_decision else "none",
            final_action,
            portfolio_reason,
        )
        if final_action != "allow":
            return

        stop_price, target_price, liquidation_price = self._risk_levels(side, observed_price, atr_value)
        position = PaperPosition(
            decision_id=decision_id,
            symbol=symbol,
            strategy_id=variant.strategy_id,
            family=variant.family,
            side=side,
            opened_at=str(signal_time),
            entry_observed_price=observed_price,
            latest_observed_price=observed_price,
            stop_price=stop_price,
            target_price=target_price,
            liquidation_price=liquidation_price,
            atr_value=atr_value,
            model_probability=probability,
            llm_action=llm_decision.action if llm_decision else None,
            llm_confidence=llm_decision.confidence if llm_decision else None,
            metadata={"signal_strength": signal_strength},
        )
        self.repository.open_position(position)
        LOGGER.info(
            "Opened paper position symbol=%s strategy=%s side=%s entry=%.6f target=%.6f stop=%.6f probability=%.4f",
            symbol,
            variant.strategy_id,
            side,
            observed_price,
            target_price,
            stop_price,
            probability,
        )

    def _candidate_event_frame(
        self,
        symbol: str,
        variant: StrategyVariant,
        frame: pd.DataFrame,
        signal_time: pd.Timestamp,
        side: str,
        signal_strength: float,
    ) -> pd.DataFrame:
        recent_returns = self.repository.recent_closed_returns(symbol, side, limit=10)
        row = frame.loc[signal_time].to_dict()
        row.update(
            {
                "symbol": symbol,
                "strategy_id": variant.strategy_id,
                "family": variant.family,
                "entry_time": signal_time,
                "exit_time": signal_time,
                "side": side,
                "net_return": 0.0,
                "gross_return": 0.0,
                "exit_reason": "pending",
                "bars_held": 0,
                "signal_strength": signal_strength,
                "label_take": 0,
                "target_hit": False,
                "stop_hit": False,
                "horizon_hit": False,
                "mae": 0.0,
                "mfe": 0.0,
                "mae_limit_breached": 0,
                "recent_same_side_failures": int(sum(value <= 0 for value in recent_returns[:5])),
                "recent_same_side_mean_return": float(pd.Series(recent_returns[:10]).mean() if recent_returns else 0.0),
            }
        )
        return pd.DataFrame([row])

    def _final_llm_decision(
        self,
        symbol: str,
        variant: StrategyVariant,
        side: str,
        signal_time: pd.Timestamp,
        observed_price: float,
        atr_value: float,
        probability: float,
        signal_strength: float,
    ) -> LLMDecision | None:
        if not self._llm_available or self._llm_client is None:
            return None
        overview = self.repository.overview(
            decision_limit=self.settings.dashboard.decision_log_limit,
            closed_trade_limit=self.settings.dashboard.closed_trade_limit,
        )
        context = {
            "symbol": symbol,
            "strategy_id": variant.strategy_id,
            "family": variant.family,
            "side": side,
            "signal_time": str(signal_time),
            "observed_price": observed_price,
            "atr_value": atr_value,
            "ml_probability": probability,
            "ml_threshold": self.bundle.manifest.threshold,
            "signal_strength": signal_strength,
            "portfolio_overview": overview,
            "active_positions": self.repository.list_positions(status="active", limit=20),
            "recent_closed_positions": self.repository.list_positions(status="closed", limit=20),
        }
        try:
            return self._llm_client.decide(context)
        except Exception as exc:
            LOGGER.warning("LLM decision failed, falling back to ML-only final gate: %s", exc)
            return None

    def _portfolio_gate(
        self,
        *,
        symbol: str,
        side: str,
        probability: float,
        llm_decision: LLMDecision | None,
    ) -> tuple[str, str]:
        active_positions = self.repository.list_positions(status="active", limit=1000)
        if len(active_positions) >= self.settings.portfolio.max_concurrent_positions:
            return "reject", "max_concurrent_positions"
        if self.settings.paper.allow_one_position_per_symbol and any(item["symbol"] == symbol for item in active_positions):
            return "reject", "active_symbol_lock"
        daily_open_count = self._daily_open_count()
        if daily_open_count >= self.settings.portfolio.max_trades_per_day:
            return "reject", "max_trades_per_day"
        if self._daily_realized_return() <= -self.settings.portfolio.daily_loss_limit_fraction:
            return "reject", "daily_loss_limit"
        if llm_decision is None:
            return "allow", "ml_only"
        if not self.settings.local_llm.require_allow_action:
            return "allow", "llm_optional"
        if llm_decision.action == "allow":
            return "allow", "llm_allow"
        if llm_decision.action == "defer" and probability - self.bundle.manifest.threshold >= self.settings.local_llm.allow_reject_below_probability_delta:
            return "allow", "ml_override"
        return "reject", f"llm_{llm_decision.action}"

    def _retune_if_due(self) -> None:
        if not self.settings.paper.auto_retune:
            return
        last_completed = self.repository.get_state("last_retune_completed_at")
        if last_completed:
            completed_at = pd.Timestamp(last_completed)
            hours_since = (pd.Timestamp.utcnow() - completed_at).total_seconds() / 3600
            if hours_since < self.settings.paper.retune_interval_hours:
                return
        overview = self.repository.overview(
            decision_limit=self.settings.dashboard.decision_log_limit,
            closed_trade_limit=self.settings.dashboard.closed_trade_limit,
        )
        hypothesis = (
            "Daily paper retune with live portfolio feedback. "
            f"recent_active={overview['active_positions']} recent_closed={overview['closed_positions']} "
            f"realized_expectancy={overview['realized_expectancy']:.6f} "
            f"profit_factor={overview['profit_factor']:.3f}"
        )
        source_artifact = self.bundle.manifest.source_artifact if self.bundle else None
        retune_id = self.repository.record_retune_started(
            RetuneEvent(
                started_at=utc_now().isoformat(),
                status="running",
                hypothesis=hypothesis,
                source_artifact=source_artifact,
                summary={"overview": overview},
            )
        )
        LOGGER.info("Starting paper retune hypothesis=%s", hypothesis)
        result = ResearchLoop(self.settings).run(hypothesis=hypothesis)
        if result.get("status") == "accepted_for_paper" and self.settings.paper.auto_rebuild_deployment:
            self.bundle = build_deployment_bundle(self.settings, result["artifact_dir"])
            self.variants = [
                StrategyVariant(
                    family=str(item["family"]),
                    name=str(item["name"]),
                    parameters=dict(item["parameters"]),
                )
                for item in self.bundle.manifest.selected_variants
            ]
            self._load_initial_frames()
            self.repository.set_state("deployment_manifest", asdict(self.bundle.manifest))
            self._restart_stream_requested = True
        self.repository.complete_retune(retune_id, str(result.get("status", "unknown")), result)
        self.repository.set_state("last_retune_completed_at", utc_now().isoformat())
        LOGGER.info("Completed paper retune status=%s artifact=%s", result.get("status"), result.get("artifact_dir"))

    async def _maybe_wait_initial_retune_delay(self) -> bool:
        if self.settings.paper.initial_retune_delay_seconds <= 0:
            return True
        if self.repository.get_state("last_retune_completed_at"):
            return True
        delay_seconds = self.settings.paper.initial_retune_delay_seconds
        LOGGER.info("Waiting %s seconds before initial paper retune.", delay_seconds)
        self.repository.set_state(
            "runtime_status",
            {
                "status": "warming_up",
                "timestamp": utc_now().isoformat(),
                "message": f"Initial retune scheduled after {delay_seconds} seconds.",
                "log_path": str(self.settings.paper_log_path),
            },
        )
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=delay_seconds)
            return False
        except asyncio.TimeoutError:
            return True

    def _handle_stream_event(self, event: str, payload: dict[str, Any]) -> None:
        current = self.repository.get_state("stream_status", {"reconnect_count": 0})
        if event == "connecting":
            current.update(
                {
                    "status": "connecting",
                    "url": payload.get("url"),
                    "symbol_count": payload.get("symbol_count"),
                    "interval": payload.get("interval"),
                    "last_connect_attempt_at": utc_now().isoformat(),
                }
            )
        elif event == "connected":
            current.update(
                {
                    "status": "connected",
                    "url": payload.get("url"),
                    "last_connected_at": utc_now().isoformat(),
                    "last_error": None,
                    "retry_in_seconds": None,
                }
            )
        elif event == "message":
            current.update(
                {
                    "status": "connected",
                    "last_message_at": utc_now().isoformat(),
                }
            )
        elif event == "rotating":
            current.update(
                {
                    "status": "rotating",
                    "rotate_after_seconds": payload.get("rotate_after_seconds"),
                    "last_rotation_at": utc_now().isoformat(),
                }
            )
        elif event == "interrupted":
            current.update(
                {
                    "status": "interrupted",
                    "last_error": payload.get("error"),
                    "last_interrupted_at": utc_now().isoformat(),
                    "reconnect_count": int(current.get("reconnect_count", 0)) + 1,
                }
            )
        elif event == "retrying":
            current.update(
                {
                    "status": "retrying",
                    "retry_in_seconds": payload.get("retry_in_seconds"),
                }
            )
        self.repository.set_state("stream_status", current)

    def _variant_by_strategy_id(self, strategy_id: str) -> StrategyVariant:
        for variant in self.variants:
            if variant.strategy_id == strategy_id:
                return variant
        raise KeyError(f"Strategy variant not found: {strategy_id}")

    def _barrier_exit(self, position: dict[str, Any], update: dict[str, Any]) -> tuple[str | None, float | None]:
        side = str(position["side"])
        high = float(update["high"])
        low = float(update["low"])
        liquidation_price = float(position["liquidation_price"])
        stop_price = float(position["stop_price"])
        target_price = float(position["target_price"])
        if side == "long":
            if low <= liquidation_price:
                return "liquidation", liquidation_price
            if low <= stop_price:
                return "stop", stop_price
            if high >= target_price:
                return "target", target_price
        else:
            if high >= liquidation_price:
                return "liquidation", liquidation_price
            if high >= stop_price:
                return "stop", stop_price
            if low <= target_price:
                return "target", target_price
        return None, None

    def _risk_levels(self, side: str, observed_price: float, atr_value: float) -> tuple[float, float, float]:
        stop_multiple = self.settings.backtest.stop_atr_multiple * atr_value
        target_multiple = self.settings.backtest.target_atr_multiple * atr_value
        liquidation_move_fraction = (1 / self.settings.backtest.leverage) * self.settings.backtest.liquidation_buffer_fraction
        liquidation_price = observed_price * (1 - liquidation_move_fraction if side == "long" else 1 + liquidation_move_fraction)
        stop_price = observed_price - stop_multiple if side == "long" else observed_price + stop_multiple
        target_price = observed_price + target_multiple if side == "long" else observed_price - target_multiple
        return float(stop_price), float(target_price), float(liquidation_price)

    def _gross_return(self, side: str, entry_price: float, exit_price: float) -> float:
        raw = (exit_price - entry_price) / entry_price
        if side == "short":
            raw = -raw
        return raw * self.settings.backtest.leverage * self.settings.backtest.capital_fraction_per_trade

    def _net_return(self, gross_return: float, exit_reason: str) -> float:
        fees = (
            2
            * self.settings.backtest.fee_bps_per_side
            / 10_000
            * self.settings.backtest.leverage
            * self.settings.backtest.capital_fraction_per_trade
        )
        if exit_reason == "liquidation" or gross_return <= -self.settings.backtest.liquidation_loss_fraction:
            return -self.settings.backtest.liquidation_loss_fraction * self.settings.backtest.capital_fraction_per_trade
        return gross_return - fees

    def _bars_held(self, opened_at: str, current_time: pd.Timestamp) -> int:
        opened = pd.Timestamp(opened_at)
        delta = current_time - opened
        bar_delta = pd.Timedelta(timeframe_to_frequency(self.settings.data.timeframe))
        if bar_delta <= pd.Timedelta(0):
            return 0
        return max(int(delta / bar_delta), 0)

    def _daily_open_count(self) -> int:
        now = datetime.now(UTC)
        day_start = pd.Timestamp(now.replace(hour=0, minute=0, second=0, microsecond=0))
        positions = self.repository.list_positions(limit=500)
        return sum(pd.Timestamp(item["opened_at"]) >= day_start for item in positions)

    def _daily_realized_return(self) -> float:
        now = datetime.now(UTC)
        day_start = pd.Timestamp(now.replace(hour=0, minute=0, second=0, microsecond=0))
        positions = self.repository.list_positions(status="closed", limit=500)
        return float(
            sum(float(item["net_return"]) for item in positions if pd.Timestamp(item["closed_at"]) >= day_start)
        )

    def _set_service_status(self, **updates: Any) -> None:
        state = self.repository.get_state("service_status", {})
        state.update({"pid": os.getpid(), **updates})
        self.repository.set_state("service_status", state)

    def _set_stream_status(self, **updates: Any) -> None:
        state = self.repository.get_state("stream_status", {})
        state.update(updates)
        self.repository.set_state("stream_status", state)


def _normalize_kline(symbol: str, kline: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "open_time": pd.to_datetime(int(kline["t"]), unit="ms", utc=True),
        "close_time": pd.to_datetime(int(kline["T"]), unit="ms", utc=True),
        "event_time": pd.to_datetime(int(kline["T"]), unit="ms", utc=True),
        "open": float(kline["o"]),
        "high": float(kline["h"]),
        "low": float(kline["l"]),
        "close": float(kline["c"]),
        "volume": float(kline["v"]),
        "quote_asset_volume": float(kline["q"]),
        "trade_count": int(kline["n"]),
        "taker_buy_base_volume": float(kline["V"]),
        "taker_buy_quote_volume": float(kline["Q"]),
        "is_closed": bool(kline["x"]),
    }
