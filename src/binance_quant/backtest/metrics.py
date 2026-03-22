from __future__ import annotations

import math

import numpy as np
import pandas as pd


def profit_factor(returns: pd.Series) -> float:
    gains = returns[returns > 0].sum()
    losses = returns[returns < 0].abs().sum()
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return float(gains / losses)


def max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def sharpe_like(returns: pd.Series) -> float:
    if returns.std(ddof=0) == 0:
        return 0.0
    return float(np.sqrt(len(returns)) * returns.mean() / returns.std(ddof=0))


def sortino_like(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if downside.std(ddof=0) == 0:
        return 0.0
    return float(np.sqrt(len(returns)) * returns.mean() / downside.std(ddof=0))
