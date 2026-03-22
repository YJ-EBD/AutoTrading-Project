# Usage Guide

## 1. Environment setup

```powershell
cd C:\yjcooperation
python -m pip install -e .[dev]
```

This project targets Python `3.12+` and installs as the package `binance_quant`.

## 2. Local LLM setup

The paper runtime can use Ollama as a final decision gate after the indicator signal and ML filter.

```powershell
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen3:14b
```

Quick checks:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty Content
```

## 3. Core research workflow

### Discover the Binance USD-M universe

```powershell
python -m binance_quant.cli discover-universe --config configs\base.yaml
```

Outputs:

- `artifacts/latest/universe/*`
- cached exchange metadata and ticker snapshots

### Backfill 15m historical data

```powershell
python -m binance_quant.cli backfill --config configs\base.yaml
```

Outputs:

- `data/market/klines/15m/*.parquet`
- symbol quality reports under each experiment artifact

### Run the research loop

```powershell
python -m binance_quant.cli run-research --config configs\base.yaml
```

This runs:

1. Pine/Python parity checks
2. universe discovery
3. market-data ingestion
4. strategy generation and pre-screening
5. event labeling and feature engineering
6. walk-forward ML training and calibration
7. threshold selection
8. robustness rejection
9. constrained portfolio assembly
10. artifact and report generation

### Build the paper deployment bundle

```powershell
python -m binance_quant.cli build-deployment --config configs\base.yaml
```

Outputs:

- `artifacts/deployment/paper_bundle.pkl`
- `artifacts/deployment/paper_manifest.json`

## 4. Paper trading runtime

### Run the paper runtime only

```powershell
python -m binance_quant.cli paper-runtime --config configs\base.yaml
```

This mode:

- listens to Binance 15m websocket klines
- evaluates indicator signals
- scores candidate trades with the trained ML filter
- optionally runs the Ollama final decision gate
- opens paper positions at the observed signal-time price
- closes paper positions on TP, SL, liquidation, horizon, or signal exit
- saves all decisions and positions to SQLite

### Run the FastAPI dashboard

```powershell
python -m binance_quant.cli serve-paper --config configs\base.yaml
```

Dashboard URL:

- `http://127.0.0.1:8000`

Useful endpoints:

- `/api/overview`
- `/api/status`
- `/api/logs`
- `/api/positions/active`
- `/api/positions/closed`
- `/api/decisions`
- `/api/retunes`
- `/api/runtime/start`
- `/api/runtime/stop`

## 5. Autonomous refresh loops

### Weekly refresh

```powershell
python -m binance_quant.cli weekly-refresh --config configs\base.yaml
```

### Bounded auto-loop

```powershell
python -m binance_quant.cli auto-loop --config configs\base.yaml
```

### Continuous loop

```powershell
python -m binance_quant.cli continuous-loop --config configs\base.yaml
```

The continuous loop iterates until promotion gates pass or until `artifacts/latest/STOP_AUTO_LOOP` is created.

## 6. Daily retuning and retraining

The paper runtime includes automatic daily retuning.

Current defaults in `configs/base.yaml`:

- `paper.auto_retune: true`
- `paper.retune_interval_hours: 24`
- `paper.retune_check_seconds: 300`
- `paper.initial_retune_delay_seconds: 90`
- `paper.auto_rebuild_deployment: true`

This means:

1. the runtime checks every 5 minutes whether 24 hours have passed since the last completed retune
2. if due, it launches the full research loop again
3. if a new candidate passes paper promotion gates, the deployment bundle is rebuilt automatically
4. the live paper runtime restarts its stream universe with the updated deployment bundle

## 7. Logs and state

Main local persistence locations:

- `artifacts/paper/paper_state.sqlite3`
- `artifacts/latest/paper_runtime.log`
- `artifacts/deployment/paper_manifest.json`
- `artifacts/deployment/paper_bundle.pkl`
- `artifacts/latest/research_summary.json`
- `artifacts/latest/research_progress.json`

## 8. Test commands

```powershell
python -m pytest
python -m compileall src
```

## 9. Git sync notes

For GitHub sync, the meaningful project files are intended to be versioned. The local virtual environment is excluded via `.gitignore` because it contains large binary files that exceed GitHub limits and should be rebuilt locally instead.
