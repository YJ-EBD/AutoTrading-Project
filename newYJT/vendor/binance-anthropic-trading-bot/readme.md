# Binance Trading Bot with Claude Integration

A Python-based cryptocurrency trading bot that combines technical analysis with Claude AI for trading decisions. The bot supports both live trading and simulation modes, with configurable parameters that can be modified during runtime.

## Features

### Core Trading Features
- Real-time trading execution
- Simulation mode for testing
- Configurable trading pairs
- Risk management with stop-loss and take-profit
- Position sizing based on risk parameters
- Daily loss limits

### Technical Analysis
- Continuation pattern recognition:
  - Flag patterns
  - Triangle patterns
  - Pennant patterns
- Pattern confidence scoring
- Breakout validation

### AI Integration
- Claude AI integration for trade decisions
- Pattern analysis combination with AI signals
- Configurable decision parameters

### Monitoring & Logging
- Real-time configuration updates
- Comprehensive logging system
- Performance metrics tracking
- Trade history export

## Project Structure
```
binance-anthropic-trading-bot/
├── main.py              # Main entry point
├── trading_bot.py       # Core trading logic
├── pattern_analysis.py  # Technical analysis
├── config.json         # Configuration file
├── requirements.txt    # Dependencies
└── __init__.py         # Python package file
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd binance-anthropic-trading-bot
```

2. Create virtual environment (recommended):
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your API keys:
Edit `config.json` and add your API keys:
```json
{
    "api_key": "your_binance_api_key",
    "api_secret": "your_binance_api_secret",
    "claude_api_key": "your_claude_api_key",
    ...
}
```

## Configuration

The `config.json` file contains all trading parameters:

### Essential Parameters
- `simulation_mode`: Enable/disable simulation mode (boolean)
- `trading_pairs`: List of trading pairs (e.g., ["BTCUSDT", "ETHUSDT"])
- `trade_amount_usdt`: Base trade amount in USDT
- `evaluation_interval`: Time between evaluations (seconds)

### Risk Management
- `stop_loss_percentage`: Stop loss level (%)
- `take_profit_percentage`: Take profit level (%)
- `risk_per_trade_percentage`: Risk per trade (%)
- `max_daily_loss_usdt`: Maximum daily loss limit

### Technical Analysis
- `analysis_interval`: Timeframe for analysis ("1h", "4h", etc.)
- `analysis_lookback`: Number of candles to analyze
- `min_pattern_size`: Minimum size for pattern detection
- `confidence_threshold`: Minimum pattern confidence

## Usage

1. Start the bot:
```bash
python main.py
```

2. Monitor the output:
- Check terminal for real-time logs
- Review `trading_bot.log` for detailed history
- Analyze `trading_history.json` for performance metrics

3. Modify settings:
- Edit `config.json` while bot is running
- Changes are automatically detected and applied

## Logging System

The bot maintains several log files:

### trading_bot.log
- Trading signals and decisions
- Pattern detection results
- Position updates
- Performance metrics

### trading_history.json
- Complete trade history
- PNL calculations
- Position details
- Performance analytics

## Safety Features

- Simulation mode for testing
- Configurable risk limits
- Position size management
- Stop-loss protection
- Daily loss limits
- Error handling and logging

## Performance Metrics

The bot tracks various performance metrics:
- Daily PNL
- Win rate
- Average win/loss
- Profit factor
- Trade duration
- Pattern success rate

## Troubleshooting

Common issues and solutions:

1. Module not found errors:
```bash
# Ensure all files are in the correct directory
# Verify __init__.py exists
# Check Python path:
python -c "import sys; print(sys.path)"
```

2. API connection issues:
```bash
# Verify API keys in config.json
# Check internet connection
# Ensure Binance API access from your location
```

## Disclaimer

This trading bot is for educational and experimental purposes only. Cryptocurrency trading carries significant risks. Never trade with funds you cannot afford to lose. The bot's performance depends on market conditions and multiple factors. Neither this bot nor its creators are responsible for any financial losses.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support:
1. Check the troubleshooting section
2. Review the logs for specific errors
3. Open an issue in the repository