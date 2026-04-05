# newYJT Execution Roles

This document lists the live role of each vendored GitHub repository in `newYJT`.

## Active pure-GitHub execution paths

### ML / Binance USD-M futures runtime

- GitHub: https://github.com/freqtrade/freqtrade
- Local path: [vendor/freqtrade](../vendor/freqtrade)
- Runtime launcher: [scripts/run_freqtrade_vendor_loop.py](../scripts/run_freqtrade_vendor_loop.py)
- Configuration: [configs/freqtrade_binance_usdtm_freqai.json](../configs/freqtrade_binance_usdtm_freqai.json)
- Current role:
  - Binance USD-M futures market-data download
  - FreqAI model training / retraining
  - dry-run futures trading loop
  - backtesting loop

### DL / RL research runtime

- GitHub: https://github.com/AI4Finance-Foundation/FinRL-Trading
- Local path: [vendor/FinRL-Trading](../vendor/FinRL-Trading)
- Runtime launcher: [scripts/run_finrl_vendor_loop.py](../scripts/run_finrl_vendor_loop.py)
- Current role:
  - upstream adaptive rotation backtesting loop
  - deep-learning / reinforcement-learning research path
  - separate from the Freqtrade futures runtime

### LLM / AI decision runtime

- GitHub: https://github.com/dmrrlc/binance-anthropic-trading-bot
- Local path: [vendor/binance-anthropic-trading-bot](../vendor/binance-anthropic-trading-bot)
- Runtime launcher: [scripts/run_llm_vendor_loop.py](../scripts/run_llm_vendor_loop.py)
- Config preparation: [scripts/prepare_llm_runtime.ps1](../scripts/prepare_llm_runtime.ps1)
- Current role:
  - upstream AI trading bot in simulation mode
  - pattern analysis + Claude decision path
  - if `ANTHROPIC_API_KEY` is unset, the upstream bot falls back to conservative `HOLD`

## Pure GitHub references kept alongside the live paths

### Pine / public strategy source

- GitHub: https://github.com/dextergocode/ultimate-crypto-trading-bot
- Local path: [vendor/ultimate-crypto-trading-bot](../vendor/ultimate-crypto-trading-bot)
- Reported README metrics:
  - `150+` trades
  - `65%` win rate
  - `Profit Factor 1.8`
  - `Sharpe 1.2`

### Finance LLM reference

- GitHub: https://github.com/AI4Finance-Foundation/FinGPT
- Local path: [vendor/FinGPT](../vendor/FinGPT)
- Current role:
  - pure upstream finance-LLM reference
  - not yet the primary live execution loop

### Prompt optimization reference

- GitHub: https://github.com/microsoft/PromptWizard
- Local path: [vendor/PromptWizard](../vendor/PromptWizard)
- Current role:
  - pure upstream prompt optimization reference
  - not yet the primary live execution loop

### Binance futures execution heuristic reference

- GitHub: https://github.com/Patrick-code-Bot/nautilus_AItrader
- Local path: [vendor/nautilus_AItrader](../vendor/nautilus_AItrader)
- Reported README metrics:
  - `60%~70%` win rate
  - weekly `0.5%~1.5%`
  - monthly `2%~6%`

### Local-LLM Binance futures candidate

- GitHub: https://github.com/Ganador1/FenixAI_tradingBot
- Local path: [vendor/FenixAI_tradingBot](../vendor/FenixAI_tradingBot)
- Current role:
  - upstream local-LLM Binance futures candidate with Ollama support
  - kept as the next pure-GitHub LLM upgrade path

## Single-console launcher

- Launcher: [scripts/run_newyjt_console.py](../scripts/run_newyjt_console.py)
- Purpose:
  - run setup steps
  - start the static HTTP server
  - start the Freqtrade loop
  - start the FinRL loop
  - start the LLM loop
  - stream all outputs into one VS Code terminal
