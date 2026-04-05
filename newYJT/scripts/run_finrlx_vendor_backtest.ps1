$ErrorActionPreference = "Stop"

Set-Location newYJT\vendor\FinRL-Trading
python src/strategies/run_adaptive_rotation_strategy.py --mode backtest --start 2023-01-01 --end 2024-12-31
