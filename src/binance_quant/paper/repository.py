from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..utils import utc_now
from .models import PaperDecision, PaperPosition, RetuneEvent


class PaperTradeRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decided_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    family TEXT NOT NULL,
                    side TEXT NOT NULL,
                    signal_time TEXT NOT NULL,
                    observed_price REAL NOT NULL,
                    atr_value REAL NOT NULL,
                    signal_strength REAL NOT NULL,
                    ml_probability REAL NOT NULL,
                    ml_threshold REAL NOT NULL,
                    ml_accepted INTEGER NOT NULL,
                    llm_enabled INTEGER NOT NULL,
                    llm_action TEXT,
                    llm_confidence REAL,
                    llm_reason TEXT,
                    final_action TEXT NOT NULL,
                    portfolio_reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_time ON decisions(decided_at DESC);
                CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol, decided_at DESC);

                CREATE TABLE IF NOT EXISTS positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    family TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    entry_observed_price REAL NOT NULL,
                    latest_observed_price REAL NOT NULL,
                    exit_observed_price REAL,
                    stop_price REAL NOT NULL,
                    target_price REAL NOT NULL,
                    liquidation_price REAL NOT NULL,
                    exit_trigger_price REAL,
                    exit_reason TEXT,
                    bars_held INTEGER NOT NULL DEFAULT 0,
                    gross_return REAL NOT NULL DEFAULT 0.0,
                    net_return REAL NOT NULL DEFAULT 0.0,
                    max_adverse_excursion REAL NOT NULL DEFAULT 0.0,
                    max_favorable_excursion REAL NOT NULL DEFAULT 0.0,
                    atr_value REAL NOT NULL,
                    model_probability REAL NOT NULL,
                    llm_action TEXT,
                    llm_confidence REAL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status, opened_at DESC);
                CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol, status, opened_at DESC);

                CREATE TABLE IF NOT EXISTS retune_events (
                    retune_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    source_artifact TEXT,
                    summary_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_retune_events_time ON retune_events(started_at DESC);

                CREATE TABLE IF NOT EXISTS runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def record_decision(self, decision: PaperDecision) -> int:
        payload = asdict(decision)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO decisions (
                    decided_at, symbol, strategy_id, family, side, signal_time, observed_price, atr_value,
                    signal_strength, ml_probability, ml_threshold, ml_accepted, llm_enabled, llm_action,
                    llm_confidence, llm_reason, final_action, portfolio_reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decided_at,
                    decision.symbol,
                    decision.strategy_id,
                    decision.family,
                    decision.side,
                    decision.signal_time,
                    decision.observed_price,
                    decision.atr_value,
                    decision.signal_strength,
                    decision.ml_probability,
                    decision.ml_threshold,
                    int(decision.ml_accepted),
                    int(decision.llm_enabled),
                    decision.llm_action,
                    decision.llm_confidence,
                    decision.llm_reason,
                    decision.final_action,
                    decision.portfolio_reason,
                    json.dumps(payload, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def open_position(self, position: PaperPosition) -> int:
        payload = asdict(position)
        metadata_payload = dict(position.metadata)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO positions (
                    decision_id, symbol, strategy_id, family, side, status, opened_at,
                    entry_observed_price, latest_observed_price, stop_price, target_price,
                    liquidation_price, atr_value, model_probability, llm_action, llm_confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.decision_id,
                    position.symbol,
                    position.strategy_id,
                    position.family,
                    position.side,
                    "active",
                    position.opened_at,
                    position.entry_observed_price,
                    position.latest_observed_price,
                    position.stop_price,
                    position.target_price,
                    position.liquidation_price,
                    position.atr_value,
                    position.model_probability,
                    position.llm_action,
                    position.llm_confidence,
                    json.dumps(metadata_payload, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def list_active_positions(self) -> list[dict[str, Any]]:
        return self._query_rows(
            "SELECT * FROM positions WHERE status = 'active' ORDER BY opened_at ASC"
        )

    def has_active_symbol(self, symbol: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM positions WHERE status = 'active' AND symbol = ?",
                (symbol,),
            ).fetchone()
            return bool(row["count"])

    def recent_closed_returns(self, symbol: str, side: str, limit: int = 10) -> list[float]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT net_return FROM positions
                WHERE status = 'closed' AND symbol = ? AND side = ?
                ORDER BY closed_at DESC
                LIMIT ?
                """,
                (symbol, side, limit),
            ).fetchall()
        return [float(row["net_return"]) for row in rows]

    def update_active_mark(
        self,
        position_id: int,
        latest_observed_price: float,
        gross_return: float,
        net_return: float,
        max_adverse_excursion: float,
        max_favorable_excursion: float,
        bars_held: int,
        stop_price: float | None = None,
        target_price: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata_json = json.dumps(metadata, default=str) if metadata is not None else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE positions
                SET latest_observed_price = ?,
                    gross_return = ?,
                    net_return = ?,
                    max_adverse_excursion = ?,
                    max_favorable_excursion = ?,
                    bars_held = ?,
                    stop_price = COALESCE(?, stop_price),
                    target_price = COALESCE(?, target_price),
                    metadata_json = COALESCE(?, metadata_json)
                WHERE position_id = ?
                """,
                (
                    latest_observed_price,
                    gross_return,
                    net_return,
                    max_adverse_excursion,
                    max_favorable_excursion,
                    bars_held,
                    stop_price,
                    target_price,
                    metadata_json,
                    position_id,
                ),
            )

    def close_position(
        self,
        position_id: int,
        *,
        closed_at: str,
        exit_observed_price: float,
        exit_trigger_price: float | None,
        exit_reason: str,
        gross_return: float,
        net_return: float,
        max_adverse_excursion: float,
        max_favorable_excursion: float,
        bars_held: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE positions
                SET status = 'closed',
                    closed_at = ?,
                    latest_observed_price = ?,
                    exit_observed_price = ?,
                    exit_trigger_price = ?,
                    exit_reason = ?,
                    gross_return = ?,
                    net_return = ?,
                    max_adverse_excursion = ?,
                    max_favorable_excursion = ?,
                    bars_held = ?,
                    metadata_json = ?
                WHERE position_id = ?
                """,
                (
                    closed_at,
                    exit_observed_price,
                    exit_observed_price,
                    exit_trigger_price,
                    exit_reason,
                    gross_return,
                    net_return,
                    max_adverse_excursion,
                    max_favorable_excursion,
                    bars_held,
                    json.dumps(metadata or {}, default=str),
                    position_id,
                ),
            )

    def list_positions(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM positions"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?"
        params.append(limit)
        return self._query_rows(query, tuple(params))

    def recent_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._query_rows(
            "SELECT * FROM decisions ORDER BY decided_at DESC LIMIT ?",
            (limit,),
        )

    def record_retune_started(self, event: RetuneEvent) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO retune_events (started_at, status, hypothesis, source_artifact, summary_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.started_at,
                    event.status,
                    event.hypothesis,
                    event.source_artifact,
                    json.dumps(event.summary, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def complete_retune(self, retune_id: int, status: str, summary: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE retune_events
                SET completed_at = ?, status = ?, summary_json = ?
                WHERE retune_id = ?
                """,
                (utc_now().isoformat(), status, json.dumps(summary, default=str), retune_id),
            )

    def mark_running_retunes_stale(self, status: str = "interrupted") -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE retune_events
                SET completed_at = ?, status = ?
                WHERE status = 'running' AND completed_at IS NULL
                """,
                (utc_now().isoformat(), status),
            )
            return int(cursor.rowcount or 0)

    def recent_retunes(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._query_rows(
            "SELECT * FROM retune_events ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )

    def set_state(self, key: str, value: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value = excluded.state_value,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, default=str), utc_now().isoformat()),
            )

    def get_state(self, key: str, default: Any | None = None) -> Any:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_value FROM runtime_state WHERE state_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return default
        return json.loads(row["state_value"])

    def overview(self, *, decision_limit: int = 100, closed_trade_limit: int = 100) -> dict[str, Any]:
        active_positions = self.list_positions(status="active", limit=1000)
        recent_closed = self.list_positions(status="closed", limit=closed_trade_limit)
        recent_decisions = self.recent_decisions(limit=decision_limit)
        realized_returns = [float(item["net_return"]) for item in recent_closed]
        wins = [value for value in realized_returns if value > 0]
        losses = [value for value in realized_returns if value <= 0]
        loss_denominator = abs(sum(losses))
        if not losses:
            profit_factor = float(len(wins) > 0)
        elif loss_denominator == 0:
            profit_factor = float("inf") if wins else 0.0
        else:
            profit_factor = sum(wins) / loss_denominator
        return {
            "active_positions": len(active_positions),
            "closed_positions": len(recent_closed),
            "decision_count": len(recent_decisions),
            "realized_expectancy": (sum(realized_returns) / len(realized_returns)) if realized_returns else 0.0,
            "realized_net_return_sum": sum(realized_returns),
            "win_rate": (len(wins) / len(realized_returns)) if realized_returns else 0.0,
            "profit_factor": profit_factor,
            "active_symbols": sorted({item["symbol"] for item in active_positions}),
        }

    def _query_rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        aliases = {
            "payload_json": "payload",
            "metadata_json": "metadata",
            "summary_json": "summary",
        }
        for key, alias in aliases.items():
            if key in payload and payload[key]:
                payload[key] = json.loads(payload[key])
                payload[alias] = payload[key]
        return payload
