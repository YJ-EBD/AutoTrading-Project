from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def ensure_paper_log_handler(settings: Settings) -> Path:
    log_path = settings.paper_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    target = str(log_path.resolve())
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if str(Path(handler.baseFilename).resolve()) == target:
                    return log_path
            except Exception:
                continue
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)
    return log_path


def read_log_tail(log_path: Path, limit: int) -> list[str]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]
