from __future__ import annotations

from ..config import Settings
from .research_loop import ResearchLoop


def run_weekly_refresh(settings: Settings) -> dict[str, object]:
    hypothesis = "Weekly refresh of Pine survivors with refreshed data, validation, and promotion gates."
    return ResearchLoop(settings).run(hypothesis=hypothesis)
