# Runbook

## Install

```bash
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

## Install local LLM runtime

```powershell
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen3:14b
```

## Discover eligible symbols

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli discover-universe --config configs\base.yaml
```

Outputs:

- cached exchange metadata
- cached 24h ticker snapshot
- `artifacts/latest/universe/universe.csv`

## Backfill 15m data

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli backfill --config configs\base.yaml
```

Outputs:

- `data/market/klines/15m/*.parquet`
- per-symbol quality reports

## Run the baseline research loop

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli run-research --config configs\base.yaml
```

Outputs:

- experiment registry rows
- candidate pre-screen metrics
- event dataset snapshot
- model fold reports
- rejection reasons
- survivor list
- portfolio summary

## Weekly refresh

Schedule the following command weekly in Task Scheduler or the orchestrator of your choice:

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli weekly-refresh --config configs\base.yaml
```

## Autonomous improvement loop

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli auto-loop --config configs\base.yaml
```

This iterates through a small mutation sequence, records each run, and writes the best-so-far summary to `artifacts/latest/auto_loop_summary.json`.

## Continuous loop

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli continuous-loop --config configs\base.yaml
```

This keeps iterating until promotion gates pass or until `artifacts/latest/STOP_AUTO_LOOP` is created. Runtime state is written to `artifacts/latest/continuous_loop_state.json`.

## Build the paper deployment bundle

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli build-deployment --config configs\base.yaml
```

Outputs:

- `artifacts/deployment/paper_bundle.pkl`
- `artifacts/deployment/paper_manifest.json`

The deployment bundle rebuilds the promoted strategy set and retrains the best ML filter on a point-in-time-safe history slice. It excludes the leaked `mae_limit_breached` proxy from live features.

## Run the paper runtime without a dashboard

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli paper-runtime --config configs\base.yaml
```

This mode:

- listens to Binance 15m websocket klines
- runs `indicator signal -> ML probability -> local LLM final decision`
- opens paper positions at the observed current price on signal close
- records the observed current price when TP, SL, liquidation, horizon, or signal exit occurs
- persists decisions, positions, and retune history to `artifacts/paper/paper_state.sqlite3`

## Run the FastAPI portfolio dashboard

```bash
.\.venv\Scripts\python.exe -m binance_quant.cli serve-paper --config configs\base.yaml
```

Default dashboard URL:

- `http://127.0.0.1:8000`

Key endpoints:

- `/api/overview`
- `/api/positions/active`
- `/api/positions/closed`
- `/api/decisions`
- `/api/retunes`

## Safety notes

- Public market data only; no account or order credentials are required for baseline research mode.
- The client uses a soft request-weight cap below official limits and cools down on `429`.
- If websocket instability or high request error rate is detected, nonessential work should be paused before live trading is considered.
- Paper mode does not place Binance orders. It records observed market prices only.
