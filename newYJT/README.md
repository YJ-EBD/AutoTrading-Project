# newYJT Pure GitHub Mode

`newYJT` has been rebuilt as a vendor-only workspace.

Goal:

- no custom local trading engine as the primary runtime
- use upstream GitHub projects directly
- treat `newYJT` as an operations shell around vendored GitHub code

## Core Repos

- `freqtrade`: primary crypto ML / FreqAI runtime candidate
- `FinRL-Trading`: primary DL / RL research and paper candidate
- `FinGPT`: finance LLM reference
- `PromptWizard`: prompt optimization reference
- `nautilus_AItrader`: execution heuristic reference
- `ultimate-crypto-trading-bot`: Pine strategy source with public README metrics
- `binance-anthropic-trading-bot`: AI decision architecture reference

## Important Truth

There is no honest way to prove an absolute universal "best win-rate repo on all of GitHub".

This workspace therefore does the strongest feasible version of the user's request:

- search trusted public GitHub repos
- vendor the strongest practical candidates
- run upstream repos directly wherever possible
- avoid using the old local custom engine as the main runtime

## Runtime Targets

- Freqtrade dry-run / backtest loop:
  - [scripts/setup_freqtrade_vendor_env.ps1](scripts/setup_freqtrade_vendor_env.ps1)
  - [scripts/run_freqtrade_vendor_loop.py](scripts/run_freqtrade_vendor_loop.py)
- FinRL-Trading DL / RL backtest loop:
  - [scripts/setup_finrl_vendor_env.ps1](scripts/setup_finrl_vendor_env.ps1)
  - [scripts/run_finrl_vendor_loop.py](scripts/run_finrl_vendor_loop.py)
- LLM vendor simulation loop:
  - [scripts/setup_llm_vendor_env.ps1](scripts/setup_llm_vendor_env.ps1)
  - [scripts/prepare_llm_runtime.ps1](scripts/prepare_llm_runtime.ps1)
  - [scripts/run_llm_vendor_loop.py](scripts/run_llm_vendor_loop.py)
- Single VS Code console launcher:
  - [scripts/run_newyjt_console.py](scripts/run_newyjt_console.py)

## Docs

- [docs/source_manifest.md](docs/source_manifest.md)
- [docs/github_scoreboard.md](docs/github_scoreboard.md)
- [docs/github_match_report.md](docs/github_match_report.md)
- [docs/pure_github_mode.md](docs/pure_github_mode.md)
- [docs/binance_futures_actual_metrics.md](docs/binance_futures_actual_metrics.md)
- [docs/execution_roles.md](docs/execution_roles.md)


## Live trading switch

`newYJT` now treats `settings.env`의 `ENABLE_LIVE_TRADING=true` as the single authoritative switch for the displayed freqtrade runtime.

- `false`: existing paper / dry-run behavior
- `true`: same freqtrade strategy logic, but real Binance USD-M order submission using the keys in `settings.env`

The LLM vendor loop remains simulation-only unless `ENABLE_LLM_LIVE_TRADING=true` is set, so the dashboarded freqtrade runtime can go live without duplicate orders from the LLM reference bot.
