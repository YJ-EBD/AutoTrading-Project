# Pure GitHub Mode

## Definition

For this workspace, "pure GitHub mode" means:

- the main trading or research runtime should come from vendored upstream repositories
- local files in `newYJT` should be launchers, configs, runbooks, and environment helpers only
- local custom strategy logic is not the primary engine

## Active Plan

### ML-first runtime

- Use `freqtrade` directly
- Prefer `FreqAI`-enabled futures dry-run / backtesting workflows

### DL / RL research runtime

- Use `FinRL-Trading` directly
- Use upstream backtest / paper entrypoints

### LLM support

- Run `binance-anthropic-trading-bot` directly in simulation mode as the active upstream LLM-style runtime
- Keep `FinGPT` and `PromptWizard` as additional pure upstream references
- Do not treat the old local custom LLM gate as the primary system in this mode

### Strategy source pool

- `ultimate-crypto-trading-bot`
- `nautilus_AItrader`
- `freqtrade` strategies and FreqAI examples

## Limit

No single public GitHub repo provides a proven all-in-one Binance futures stack with the universally highest verified real-world win rate.

This workspace therefore uses the strongest public upstream combination rather than pretending a mathematically proven single winner exists.
