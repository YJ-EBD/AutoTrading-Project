# File Reference

## Root files

- `README.md`: short project introduction, quick start commands, and entry links to the main docs.
- `pyproject.toml`: package metadata, Python dependency list, setuptools layout, template packaging, and pytest configuration.
- `protocol`: local operator scratchpad with frequently used PowerShell commands.
- `.gitignore`: Git tracking rules for excluding the local virtual environment and Python cache outputs.

## Config and docs

- `configs/base.yaml`: the central runtime and research configuration for exchange, backtest, ML, portfolio, deployment, paper mode, dashboard, LLM, and auto-loop settings.
- `docs/architecture.md`: concise architectural layer overview and validation philosophy.
- `docs/runbook.md`: operational commands for research, deployment, paper runtime, dashboard, and loops.
- `docs/usage_guide.md`: step-by-step usage instructions for setup, research, deployment, paper mode, and daily retuning.
- `docs/implementation_overview.md`: current feature inventory, workflow explanation, assumptions, and operational limits.
- `docs/file_reference.md`: per-file responsibility reference for the tracked project files.

## Source package root

- `src/binance_quant/__init__.py`: package marker for the main project namespace.
- `src/binance_quant/cli.py`: command-line entrypoint for research, deployment, paper runtime, dashboard, and loop commands.
- `src/binance_quant/config.py`: dataclass-based configuration schema, YAML loading, and path resolution helpers.
- `src/binance_quant/storage.py`: disk cache and storage helpers used by the data and exchange layers.
- `src/binance_quant/utils.py`: general utility helpers such as UTC timestamp helpers.

## Backtest layer

- `src/binance_quant/backtest/__init__.py`: package marker for backtest components.
- `src/binance_quant/backtest/engine.py`: vectorized trade simulation with leverage, TP, SL, horizon, fees, slippage, and liquidation logic.
- `src/binance_quant/backtest/metrics.py`: backtest and trade-level performance metric calculations.

## Data layer

- `src/binance_quant/data/__init__.py`: package marker for data components.
- `src/binance_quant/data/ingestion.py`: historical kline backfill, incremental updates, parquet persistence, and integrity checks.
- `src/binance_quant/data/live.py`: combined websocket kline stream client with reconnect handling, rotation, and runtime status callbacks.
- `src/binance_quant/data/quality.py`: candle quality checks, alignment validation, and timeframe helpers.

## Exchange layer

- `src/binance_quant/exchange/__init__.py`: package marker for exchange components.
- `src/binance_quant/exchange/client.py`: public Binance REST client with retry, timeout, caching, and request-budget integration.
- `src/binance_quant/exchange/models.py`: typed exchange-domain structures used across exchange and universe code.
- `src/binance_quant/exchange/rate_limit.py`: centralized request-weight budget manager and cooldown logic.
- `src/binance_quant/exchange/universe.py`: universe discovery, symbol eligibility filtering, and local metadata snapshots.

## Feature and labeling layer

- `src/binance_quant/features/__init__.py`: package marker for feature components.
- `src/binance_quant/features/engine.py`: point-in-time feature enrichment for OHLCV frames and event-level ML inputs.
- `src/binance_quant/labeling/__init__.py`: package marker for labeling components.
- `src/binance_quant/labeling/triple_barrier.py`: event labeling, meta-label construction, and triple-barrier style outcome logic.

## LLM layer

- `src/binance_quant/llm/__init__.py`: package marker for local LLM support.
- `src/binance_quant/llm/ollama.py`: Ollama client, prompt packaging, and parsed allow, reject, defer decision output handling.

## ML layer

- `src/binance_quant/ml/__init__.py`: package marker for ML components.
- `src/binance_quant/ml/deployment.py`: deployment-bundle creation, bundle loading, and paper inference packaging.
- `src/binance_quant/ml/modeling.py`: walk-forward training, calibration, model comparison, fold evaluation, and best-model selection.
- `src/binance_quant/ml/splits.py`: time-series-safe split generation with embargo-aware train, validation, calibration, and test boundaries.
- `src/binance_quant/ml/thresholds.py`: threshold search utilities for take, skip filtering policies.

## Orchestration layer

- `src/binance_quant/orchestration/__init__.py`: package marker for orchestration components.
- `src/binance_quant/orchestration/auto_loop.py`: bounded auto-improvement loop over mutation sequences.
- `src/binance_quant/orchestration/research_loop.py`: main end-to-end research engine from sanity checks to reporting and promotion gates.
- `src/binance_quant/orchestration/weekly_refresh.py`: scheduled refresh helper for periodic research reruns.

## Paper trading layer

- `src/binance_quant/paper/__init__.py`: package marker for paper-trading components.
- `src/binance_quant/paper/dashboard.py`: FastAPI application factory, dashboard routes, status endpoints, and log endpoints.
- `src/binance_quant/paper/logging_utils.py`: paper runtime file logging setup and log-tail reader helpers.
- `src/binance_quant/paper/models.py`: dataclasses for paper decisions, positions, and retune events.
- `src/binance_quant/paper/repository.py`: SQLite repository for decisions, positions, retune history, and runtime state.
- `src/binance_quant/paper/runtime.py`: live paper runtime, daily retune scheduler, websocket handling, decision pipeline, and portfolio state updates.
- `src/binance_quant/paper/templates/dashboard.html`: dashboard UI template with Korean labels, runtime controls, stream status, and log console.

## Portfolio layer

- `src/binance_quant/portfolio/__init__.py`: package marker for portfolio components.
- `src/binance_quant/portfolio/engine.py`: portfolio assembly, trade selection, diversification constraints, and aggregate portfolio evaluation.

## Reporting layer

- `src/binance_quant/reporting/__init__.py`: package marker for reporting components.
- `src/binance_quant/reporting/reports.py`: JSON, CSV, and Markdown report generation for experiments and deployment summaries.

## Strategy layer

- `src/binance_quant/strategies/__init__.py`: package marker for strategy components.
- `src/binance_quant/strategies/base.py`: common strategy result and variant abstractions.
- `src/binance_quant/strategies/indicators.py`: reusable indicator calculations used across strategy families.
- `src/binance_quant/strategies/parity.py`: Pine-versus-Python signal parity verification helpers.
- `src/binance_quant/strategies/templates.py`: parameterized Pine-style strategy families and signal-generation logic.

## Tests

- `tests/test_backtest_engine.py`: verifies backtest fills, exits, and metric behavior.
- `tests/test_config.py`: verifies configuration loading and key runtime defaults.
- `tests/test_features.py`: verifies feature-engine output and anti-leakage expectations.
- `tests/test_paper_dashboard.py`: verifies dashboard context and runtime payload helpers.
- `tests/test_paper_logging.py`: verifies log-tail reading and resolved paper log paths.
- `tests/test_paper_repository.py`: verifies SQLite decision and position persistence.
- `tests/test_portfolio_engine.py`: verifies portfolio assembly and concentration constraints.
- `tests/test_research_loop.py`: verifies research-loop selection and rejection logic.
- `tests/test_splits.py`: verifies time-series split ordering and embargo behavior.
- `tests/test_strategy_parity.py`: verifies semantic parity between Pine-style and Python strategy signals.

## Runtime data directories

- `data/market/klines/15m/*.parquet`: local historical candle store used for research and paper bootstrapping.
- `data/cache/*`: local exchange and request cache for safe API usage.
- `artifacts/<timestamp>/*`: reproducible experiment outputs such as reports, summaries, diagnostics, progress, and data-quality snapshots.
- `artifacts/latest/*`: latest pointers, runtime logs, live paper state snapshots, and most recent research status.
- `artifacts/deployment/*`: paper deployment bundle and manifest used by the runtime.
- `artifacts/paper/paper_state.sqlite3`: persistent SQLite database for paper decisions, positions, retunes, and service status.
