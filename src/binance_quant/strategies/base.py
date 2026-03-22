from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class StrategyVariant:
    family: str
    name: str
    parameters: dict[str, Any]

    @property
    def strategy_id(self) -> str:
        suffix = "_".join(f"{key}{value}" for key, value in sorted(self.parameters.items()))
        return f"{self.family}__{suffix}"


@dataclass
class SignalFrame:
    signals: pd.DataFrame
    pine_script: str


class PineStrategyTemplate(ABC):
    family: str

    @abstractmethod
    def parameter_grid(self, search_space: dict[str, list[int | float]]) -> list[StrategyVariant]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, frame: pd.DataFrame, variant: StrategyVariant) -> SignalFrame:
        raise NotImplementedError
