# Binance Quant Research

Production-oriented research infrastructure for Binance USD-M Futures with:

- dynamic universe discovery from exchange metadata
- exchange-safe market data ingestion with caching and request budgeting
- Pine-style signal generation with Python parity tests
- realistic 15m leveraged backtesting with fees, slippage, and liquidation handling
- leak-free meta-labeling and ML filtering
- time-series-safe walk-forward validation and reporting
- deployment bundle generation for paper trading inference
- FastAPI paper portfolio dashboard with live TP/SL tracking
- local Ollama-based LLM final decision gate
- experiment registry, artifact persistence, and weekly refresh entrypoints

## Quick start

```bash
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m binance_quant.cli discover-universe --config configs\base.yaml
.\.venv\Scripts\python.exe -m binance_quant.cli run-research --config configs\base.yaml
.\.venv\Scripts\python.exe -m binance_quant.cli build-deployment --config configs\base.yaml
.\.venv\Scripts\python.exe -m binance_quant.cli serve-paper --config configs\base.yaml
.\.venv\Scripts\python.exe -m pytest
```

## Current scope

This repository implements the first complete baseline loop:

1. Fetch exchange metadata and eligible symbols from Binance USD-M Futures.
2. Backfill and cache 15m klines to parquet with integrity checks.
3. Generate parameterized Pine-style strategy candidates.
4. Pre-screen candidates with a realistic leveraged backtester.
5. Build a meta-label event dataset from surviving signals.
6. Train calibrated ML filters with expanding-window validation.
7. Reject unstable candidates and assemble a constrained portfolio.
8. Persist experiment logs, reports, and artifacts for reproducibility.
9. Rebuild a paper deployment bundle from the latest promoted artifact.
10. Run a live paper runtime that records observed entry and TP/SL exit prices without sending orders.
11. Expose portfolio state, decisions, and retune history through FastAPI.

## Documentation

- [Architecture](docs/architecture.md)
- [Runbook](docs/runbook.md)
