# Binance Futures GitHub Shortlist With Public Metrics

This shortlist keeps only repositories that either:

- explicitly support Binance Futures / perpetual futures, or
- publish concrete win-rate / return metrics that are strong enough to remain in the candidate pool.

## Highest-Confidence Shortlist

| Repo | URL | Binance futures fit | Public metrics found | How it is used in `newYJT` |
| --- | --- | --- | --- | --- |
| `freqtrade` | https://github.com/freqtrade/freqtrade | Direct support for Binance isolated futures and FreqAI | No fixed universal win rate in README | Primary ML-first Binance USD-M dry-run runtime |
| `nautilus_AItrader` | https://github.com/Patrick-code-Bot/nautilus_AItrader | Direct: BTC/USDT perpetual futures on Binance | README claims `60-70%` win rate, weekly `0.5%-1.5%`, monthly `2%-6%`, best combo `68%` | Binance-futures-specific execution and risk-management reference |
| `ultimate-crypto-trading-bot` | https://github.com/dextergocode/ultimate-crypto-trading-bot | Indirect: Pine strategy source for crypto, not exchange runtime | README claims `150+` trades, `65%` win rate, `PF 1.8`, `Sharpe 1.2`, `MDD 15%` | Strategy source pool and public-metric benchmark |
| `FinRL-Trading` | https://github.com/AI4Finance-Foundation/FinRL-Trading | Indirect: paper/live framework, but Alpaca / equities centric | README paper trading `+19.76%`, `64.89%` win rate, `Sharpe 1.96` | DL / RL benchmark and research loop |
| `FenixAI_tradingBot` | https://github.com/Ganador1/FenixAI_tradingBot | Direct: Binance Futures, local LLM, paper mode default | README explicitly says `not yet profitable`; no fixed win-rate figure | Pure GitHub local-LLM Binance futures candidate |

## Reference-Only Repos

| Repo | URL | Reason kept |
| --- | --- | --- |
| `FinGPT` | https://github.com/AI4Finance-Foundation/FinGPT | Strong finance LLM baseline, but no public trading win-rate metric |
| `PromptWizard` | https://github.com/microsoft/PromptWizard | Strong prompt optimization tool, but no public trading win-rate metric |
| `binance-anthropic-trading-bot` | https://github.com/dmrrlc/binance-anthropic-trading-bot | Binance AI-decision architecture reference, but no public fixed win-rate table |
| `trading-gpt` | https://github.com/yubing744/trading-gpt | Ollama-capable trading agent framework, but no public fixed trading metric and OKX-first examples |

## Practical Conclusion

No single public GitHub repository honestly provides:

- Binance USD-M futures support,
- ML,
- DL / RL,
- LLM,
- and a universally verified highest real-world win rate.

The strongest practical combination remains:

1. `freqtrade` for Binance USD-M ML / FreqAI runtime
2. `nautilus_AItrader` for Binance-perpetual execution heuristics and claimed win-rate benchmark
3. `ultimate-crypto-trading-bot` for public-metric crypto strategy sourcing
4. `FinRL-Trading` for DL / RL paper / backtest benchmarking
5. `FenixAI_tradingBot` as the cleanest pure-GitHub local-LLM Binance futures candidate
6. `FinGPT` + `PromptWizard` as finance-LLM / prompt references
