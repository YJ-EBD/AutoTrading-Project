from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..utils import dump_json


def persist_dataframe(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def persist_report_bundle(artifact_dir: Path, reports: dict[str, Any]) -> None:
    report_dir = artifact_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in reports.items():
        if isinstance(payload, pd.DataFrame):
            persist_dataframe(payload, report_dir / f"{name}.csv")
        else:
            dump_json(
                report_dir / f"{name}.json",
                asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload,
            )


def build_markdown_summary(summary: dict[str, Any]) -> str:
    sections = [
        "# Research Milestone",
        "",
        "## Current hypothesis",
        str(summary["hypothesis"]),
        "",
        "## Universe",
        f"- eligible symbols: {summary['universe']['eligible_symbols']}",
        f"- selected symbols: {summary['universe']['selected_symbols']}",
        "",
        "## Pre-screen",
        f"- total candidates: {summary['pre_screen']['candidate_count']}",
        f"- survivors: {summary['pre_screen']['survivor_count']}",
        "",
        "## ML",
        f"- event count: {summary['ml']['event_count']}",
        f"- model evaluations: {summary['ml']['model_evaluations']}",
        "",
        "## Portfolio",
        f"- accepted trades: {summary['portfolio']['trade_count']}",
        f"- expectancy: {summary['portfolio']['expectancy']:.6f}",
        "",
        "## Status",
        str(summary["status"]),
    ]
    return "\n".join(sections)
