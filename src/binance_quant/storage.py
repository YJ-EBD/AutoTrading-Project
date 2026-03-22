from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .utils import dump_json, load_json, utc_now


class DiskCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str, ttl_seconds: int) -> Any | None:
        path = self._entry_path(namespace, key)
        if not path.exists():
            return None
        age_seconds = utc_now().timestamp() - path.stat().st_mtime
        if age_seconds > ttl_seconds:
            return None
        return load_json(path)

    def set(self, namespace: str, key: str, payload: Any) -> None:
        path = self._entry_path(namespace, key)
        dump_json(path, payload)


class ExperimentRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    hypothesis TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    config_json TEXT NOT NULL,
                    metrics_json TEXT,
                    artifact_dir TEXT NOT NULL,
                    failure_summary TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_logs (
                    experiment_id TEXT NOT NULL,
                    logged_at TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )

    def start(self, experiment_id: str, hypothesis: str, config: Any, artifact_dir: Path) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO experiments (
                    experiment_id, hypothesis, status, started_at, config_json, artifact_dir
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    hypothesis,
                    "running",
                    utc_now().isoformat(),
                    json.dumps(asdict(config), default=str),
                    str(artifact_dir),
                ),
            )

    def log(self, experiment_id: str, phase: str, message: str) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO experiment_logs (experiment_id, logged_at, phase, message)
                VALUES (?, ?, ?, ?)
                """,
                (experiment_id, utc_now().isoformat(), phase, message),
            )

    def complete(
        self,
        experiment_id: str,
        status: str,
        metrics: dict[str, Any],
        failure_summary: str | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, completed_at = ?, metrics_json = ?, failure_summary = ?
                WHERE experiment_id = ?
                """,
                (
                    status,
                    utc_now().isoformat(),
                    json.dumps(metrics, default=str),
                    failure_summary,
                    experiment_id,
                ),
            )
