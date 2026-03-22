# Implementation Overview

## Current system scope

This repository contains a full research-to-paper-trading pipeline for Binance USD-M Futures with a strict default focus on 15-minute candles.

The implemented stack includes:

- dynamic exchange-safe universe discovery
- cached historical OHLCV ingestion to parquet
- Pine-style strategy generation with Python parity checks
- vectorized leveraged backtesting with fees, slippage, TP, SL, horizon, and liquidation handling
- leak-aware event labeling and feature engineering
- walk-forward ML filter training, calibration, and threshold selection
- robustness rejection and constrained portfolio construction
- experiment registry and artifact reporting
- deployment bundle generation for paper inference
- FastAPI paper portfolio dashboard
- local Ollama final decision gate
- automatic daily paper retuning and deployment refresh

## Signal and decision stack

The live paper workflow is:

1. strategy templates emit candidate entry and exit signals
2. the trained ML filter estimates whether the candidate signal should be taken
3. the local LLM optionally makes the final allow, reject, or defer judgment
4. the portfolio gate enforces concurrency, per-symbol lock, daily trade cap, and daily loss limit
5. paper positions are recorded without sending Binance orders

## Strategy layer

Current research families include:

- trend EMA cross with RSI confirmation
- trend pullback resumption
- breakout
- volatility squeeze
- mean reversion

Each family is parameterized and can be expanded across grids inside `configs/base.yaml`.

## Validation and anti-overfitting controls

Implemented validation guardrails include:

- time-ordered train, validation, calibration, and test slices
- embargo bars in the ML splitter
- fold-safe calibration
- threshold search on validation-only segments
- cost stress checks
- Monte Carlo perturbation checks
- symbol and strategy concentration gates
- minimum trade-count and breadth gates
- rejection of weak or unstable candidates before deployment

## Portfolio and execution assumptions

Default research assumptions:

- timeframe: `15m`
- leverage: `10x`
- capital fraction per trade: `10%`
- fee per side: `4 bps`
- slippage per side: `1.5 bps`
- stop: `1.5 ATR`
- target: `2.5 ATR`
- max holding: `48 bars`

Paper execution assumptions:

- positions open at the observed signal-time price
- positions close when the observed market reaches TP, SL, liquidation, horizon, or strategy exit
- no real exchange orders are placed

## Paper dashboard capabilities

The dashboard currently supports:

- portfolio overview metrics
- runtime process status
- websocket stream status and reconnect count
- active and closed position tables
- recent decision history
- retune history
- live log console
- runtime start and stop controls from the page

## Local LLM integration

The repository uses Ollama as a local final decision layer.

Current default model:

- `qwen3:14b`

The LLM is not the primary signal generator. It sits after the rules-based strategy signal and after the ML probability filter.

## Daily automatic retuning

The paper runtime now performs automated daily maintenance:

- waits for a short warm-up period after startup
- checks every 5 minutes whether a full retune is due
- reruns the research loop every 24 hours
- rebuilds the deployment bundle automatically if a new candidate reaches `accepted_for_paper`
- restarts the paper stream universe with the updated deployment bundle

## Local persistence model

The system writes local state to:

- parquet market data under `data/market`
- experiment artifacts under `artifacts/<timestamp>`
- latest summaries under `artifacts/latest`
- deployment bundle under `artifacts/deployment`
- paper decisions and positions under `artifacts/paper/paper_state.sqlite3`
- runtime logs under `artifacts/latest/paper_runtime.log`

## Current operational limitations

Important constraints to understand:

- this repository does not place live exchange orders
- paper positions are observational, not executable fills
- actual GitHub push still requires valid GitHub authentication on this machine
- the local virtual environment is intentionally excluded from version control
