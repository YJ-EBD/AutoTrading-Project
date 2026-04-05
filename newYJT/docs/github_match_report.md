# Pure GitHub Match Report

This report maps each major system role in `newYJT` to an upstream GitHub repository.

| Category | Selected upstream repo | Local path | Binance futures fit | Public metric used | Current role |
| --- | --- | --- | --- | --- | --- |
| Strategy runtime | `freqtrade` | `vendor/freqtrade` | direct | no fixed universal win rate published | Primary Binance USD-M dry-run runtime |
| ML models | `freqtrade` FreqAI | `vendor/freqtrade/freqtrade/freqai/prediction_models` | direct | no fixed universal win rate published | XGBoost / LightGBM / RandomForest classifier pool |
| DL / RL runtime | `FinRL-Trading` | `vendor/FinRL-Trading` | indirect | README paper trading `+19.76%`, `64.89%` win rate, `Sharpe 1.96` | DL / RL benchmark loop |
| LLM finance reference | `FinGPT` | `vendor/FinGPT` | indirect | no public fixed trading win rate | Finance LLM reference |
| Prompt optimization | `PromptWizard` | `vendor/PromptWizard` | indirect | no public fixed trading win rate | Prompt optimization reference |
| Binance futures execution heuristics | `nautilus_AItrader` | `vendor/nautilus_AItrader` | direct | README `60-70%` win rate, weekly `0.5%-1.5%`, monthly `2%-6%` | Binance-perpetual execution / risk reference |
| Pine strategy source | `ultimate-crypto-trading-bot` | `vendor/ultimate-crypto-trading-bot` | indirect | README `65%` win rate, `PF 1.8`, `Sharpe 1.2`, `150+` trades | Public-metric strategy reference |
| AI decision architecture | `binance-anthropic-trading-bot` | `vendor/binance-anthropic-trading-bot` | direct | no fixed public win rate | Active GitHub LLM decision runtime |
| Local-LLM Binance futures candidate | `FenixAI_tradingBot` | `vendor/FenixAI_tradingBot` | direct | README says `not yet profitable`; no fixed public win-rate table | Next pure-GitHub local-LLM upgrade path |
| Ollama-enabled trading agent candidate | `trading-gpt` | `vendor/trading-gpt` | indirect | no fixed public win rate | Ollama-capable agent framework reference |

## Current practical selection

For Binance USD-M futures, the strongest practical stack is:

1. `freqtrade` for direct Binance futures execution and ML / FreqAI
2. `nautilus_AItrader` for Binance-perpetual execution heuristics with public claimed win-rate ranges
3. `ultimate-crypto-trading-bot` for public-metric crypto strategy ideas
4. `FinRL-Trading` for DL / RL benchmarking
5. `FenixAI_tradingBot` as the strongest local-LLM Binance futures candidate
6. `FinGPT` + `PromptWizard` for finance-LLM and prompt optimization references

## Truthfulness note

No public GitHub repo honestly proves a universal highest real-world win rate across all markets and exchanges.
This report therefore maps:

- the strongest public upstreams with disclosed metrics,
- the strongest Binance futures-compatible runtimes,
- and the strongest finance LLM / prompt references.
