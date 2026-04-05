import json
import time
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd
import anthropic
from binance.client import Client
from binance.exceptions import BinanceAPIException
from pattern_analysis import PatternAnalyzer, Pattern

class TradingBot:
    def __init__(self, config: Dict):
        self.config = config
        self.positions: Dict[str, Dict] = {}
        self.pnl_history: List[Dict] = []
        self.pattern_analyzer = PatternAnalyzer(
            min_pattern_size=self.config.get('min_pattern_size', 5),
            confidence_threshold=self.config.get('confidence_threshold', 0.7)
        )
        
        # Initialize clients
        if not self.config['simulation_mode']:
            self.binance_client = Client(
                self.config['api_key'],
                self.config['api_secret']
            )
        else:
            # In simulation mode, still initialize client for market data
            self.binance_client = Client("", "")

        # Keep provider/model configurable so the same veto loop can use Claude or local Ollama.
        self.claude_api_key = self.config['claude_api_key']
        self.llm_provider = str(self.config.get('llm_provider') or ('anthropic' if self.claude_api_key else 'ollama')).strip().lower()
        self.llm_model = str(
            self.config.get('llm_model')
            or ('claude-3-5-sonnet-latest' if self.llm_provider == 'anthropic' else 'deepseek-r1:8b')
        ).strip()
        self.llm_fallback_model = str(self.config.get('llm_fallback_model') or '').strip()
        self.market_type = str(self.config.get('llm_market_type') or 'futures').strip().lower()
        self.llm_base_url = str(self.config.get('llm_base_url') or 'http://127.0.0.1:11434').rstrip('/')
        self.llm_timeout_seconds = int(self.config.get('llm_timeout_seconds') or 60)

    def reload_config(self):
        """Reload configuration from file."""
        with open('config.json', 'r') as f:
            new_config = json.load(f)
        self.config = new_config
        self.claude_api_key = self.config.get('claude_api_key', '')
        self.llm_provider = str(self.config.get('llm_provider') or ('anthropic' if self.claude_api_key else 'ollama')).strip().lower()
        self.llm_model = str(
            self.config.get('llm_model')
            or ('claude-3-5-sonnet-latest' if self.llm_provider == 'anthropic' else 'deepseek-r1:8b')
        ).strip()
        self.llm_fallback_model = str(self.config.get('llm_fallback_model') or '').strip()
        self.market_type = str(self.config.get('llm_market_type') or 'futures').strip().lower()
        self.llm_base_url = str(self.config.get('llm_base_url') or 'http://127.0.0.1:11434').rstrip('/')
        self.llm_timeout_seconds = int(self.config.get('llm_timeout_seconds') or 60)
        logging.info("Configuration reloaded successfully")

    def get_market_data(self, symbol: str) -> Tuple[Dict, pd.DataFrame]:
        """Get current market data and historical data for pattern analysis."""
        try:
            # Get current ticker data
            if self.market_type == 'futures':
                ticker = self.binance_client.futures_symbol_ticker(symbol=symbol)
            else:
                ticker = self.binance_client.get_symbol_ticker(symbol=symbol)
            current_data = {
                'price': float(ticker['price']),
                'timestamp': datetime.now()
            }
            
            # Get historical data for pattern analysis
            historical_data = self.pattern_analyzer.get_market_data(
                self.binance_client,
                symbol,
                interval=self.config.get('analysis_interval', '1h'),
                limit=self.config.get('analysis_lookback', 100),
                market_type=self.market_type,
            )
            
            return current_data, historical_data
            
        except BinanceAPIException as e:
            logging.error(f"Error fetching market data: {e}")
            return None, None

    def _build_prompt(self, symbol: str, market_data: Dict, patterns: List[Pattern]) -> str:
        pattern_info = "\n".join([
            f"Pattern: {p.name}, Direction: {p.direction}, Confidence: {p.confidence:.2f}"
            for p in patterns
        ]) if patterns else "No significant patterns detected"

        return f"""Based on the following market data for {symbol}:
        Current price: {market_data['price']}
        Position status: {'In position' if symbol in self.positions else 'No position'}
        
        Technical Analysis:
        {pattern_info}
        
        Decision rules:
        - Prefer HOLD when the signal is mixed or confidence is weak.
        - Use BUY only when upside evidence is clearly stronger than downside evidence.
        - Use SELL only when downside evidence is clearly stronger than upside evidence.
        - Respond with exactly one word and nothing else: BUY, SELL, or HOLD"""

    def _normalize_signal(self, response_text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", " ", response_text, flags=re.IGNORECASE | re.DOTALL)
        matches = re.findall(r"\b(BUY|SELL|HOLD)\b", cleaned.upper())
        if matches:
            return matches[-1]
        return "HOLD"

    def _ask_anthropic(self, prompt: str) -> str:
        if not self.claude_api_key:
            logging.info("Anthropic API key not configured, defaulting to HOLD")
            return "HOLD"

        try:
            client = anthropic.Anthropic(api_key=self.config['claude_api_key'])
            completion = client.completions.create(
                model=self.llm_model or "claude-2.1",
                max_tokens_to_sample=10,
                temperature=0,
                prompt=f"\n\nHuman: {prompt}\n\nAssistant: Let me analyze this and provide a clear recommendation. Based on the data provided, my recommendation is: ",
            )
            return self._normalize_signal(completion.completion.strip())
        except Exception as e:
            logging.error(f"Error getting Anthropic advice: {e}")
            return "HOLD"

    def _ask_ollama_model(self, model_name: str, prompt: str) -> str:
        payload = json.dumps({
            "model": model_name,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a conservative crypto trading veto model. Reply with exactly one word: BUY, SELL, or HOLD.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "options": {
                "temperature": 0,
            },
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.llm_base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.llm_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            message = body.get("message", {}) if isinstance(body, dict) else {}
            content = message.get("content", "") if isinstance(message, dict) else ""
            return self._normalize_signal(str(content))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            raise RuntimeError(str(e)) from e

    def _ask_ollama(self, prompt: str) -> str:
        try:
            return self._ask_ollama_model(self.llm_model, prompt)
        except Exception as primary_error:
            if self.llm_fallback_model and self.llm_fallback_model != self.llm_model:
                logging.warning(
                    "Primary Ollama model %s failed (%s). Retrying with fallback %s",
                    self.llm_model,
                    primary_error,
                    self.llm_fallback_model,
                )
                try:
                    return self._ask_ollama_model(self.llm_fallback_model, prompt)
                except Exception as fallback_error:
                    logging.error(
                        "Fallback Ollama model %s also failed: %s",
                        self.llm_fallback_model,
                        fallback_error,
                    )
                    return "HOLD"
            logging.error(f"Error getting Ollama advice: {primary_error}")
            return "HOLD"

    def ask_llm(self, symbol: str, market_data: Dict, patterns: List[Pattern]) -> str:
        """Ask the configured LLM provider for trading advice including pattern analysis."""
        prompt = self._build_prompt(symbol, market_data, patterns)
        if self.llm_provider == "anthropic":
            return self._ask_anthropic(prompt)
        if self.llm_provider == "ollama":
            return self._ask_ollama(prompt)
        logging.warning("Unsupported llm_provider=%s, defaulting to HOLD", self.llm_provider)
        return "HOLD"

    def _combine_signals(self, pattern_signal: str, llm_signal: str) -> str:
        """Combine pattern analysis signal with the configured LLM advice for final decision."""
        # If we get conflicting signals (BUY vs SELL)
        if (pattern_signal in ["BUY", "SELL"] and 
            llm_signal in ["BUY", "SELL"] and 
            pattern_signal != llm_signal):
            
            logging.warning(f"Conflicting signals detected: Pattern={pattern_signal}, LLM={llm_signal}")
            return "HOLD"  # Conservative approach to conflicting signals
            
        # If both signals agree, follow the agreed direction
        if pattern_signal == llm_signal:
            return pattern_signal
            
        # If one signal is HOLD, use the other signal
        if pattern_signal == "HOLD":
            return llm_signal
        if llm_signal == "HOLD":
            return pattern_signal
            
        return "HOLD"  # Default safe behavior

    def execute_trade(self, symbol: str, signal: str, market_data: Dict):
        """Execute or simulate a trade with risk management."""
        # Check daily loss limit
        if self._check_daily_loss_limit():
            logging.warning("Daily loss limit reached. No new trades allowed.")
            return
            
        # Calculate position size based on risk
        position_size = self._calculate_position_size(symbol, market_data)
        
        if signal == "BUY" and symbol not in self.positions:
            # Calculate stop loss and take profit levels
            stop_loss = market_data['price'] * (1 - self.config['stop_loss_percentage'] / 100)
            take_profit = market_data['price'] * (1 + self.config['take_profit_percentage'] / 100)
            
            if self.config['simulation_mode']:
                self._simulate_trade("BUY", symbol, market_data, position_size, stop_loss, take_profit)
            else:
                self._execute_live_trade("BUY", symbol, position_size, stop_loss, take_profit)
                
        elif signal == "SELL" and symbol in self.positions:
            if self.config['simulation_mode']:
                self._simulate_trade("SELL", symbol, market_data, position_size)
            else:
                self._execute_live_trade("SELL", symbol, position_size)

    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached."""
        today = datetime.now().date()
        daily_pnl = sum(
            trade['pnl'] for trade in self.pnl_history 
            if trade['timestamp'].date() == today
        )
        
        max_daily_loss = self.config.get('max_daily_loss_usdt', 100)
        return daily_pnl < -max_daily_loss

    def _calculate_position_size(self, symbol: str, market_data: Dict) -> float:
        """Calculate position size based on risk management rules."""
        account_balance = self.config['trade_amount_usdt']
        risk_per_trade = self.config.get('risk_per_trade_percentage', 1) / 100
        stop_loss_percentage = self.config['stop_loss_percentage'] / 100
        
        # Calculate maximum loss allowed for this trade
        max_loss_amount = account_balance * risk_per_trade
        
        # Calculate position size based on stop loss
        position_size = max_loss_amount / stop_loss_percentage
        
        # Ensure position size doesn't exceed maximum allowed
        max_position_size = self.config.get('max_position_size_usdt', account_balance * 0.1)
        return min(position_size, max_position_size)

    def _simulate_trade(self, action: str, symbol: str, market_data: Dict, 
                       position_size: float, stop_loss: float = None, 
                       take_profit: float = None):
        """Simulate a trade with risk management parameters."""
        if action == "BUY":
            self.positions[symbol] = {
                'entry_price': market_data['price'],
                'amount': position_size / market_data['price'],
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': market_data['timestamp']
            }
            logging.info(f"Simulated BUY: {symbol} at {market_data['price']}, "
                        f"Stop Loss: {stop_loss}, Take Profit: {take_profit}")
            
        elif action == "SELL":
            if symbol in self.positions:
                entry = self.positions[symbol]
                pnl = (market_data['price'] - entry['entry_price']) * entry['amount']
                
                self.pnl_history.append({
                    'symbol': symbol,
                    'entry_price': entry['entry_price'],
                    'exit_price': market_data['price'],
                    'pnl': pnl,
                    'timestamp': market_data['timestamp'],
                    'position_size': position_size,
                    'trade_duration': (market_data['timestamp'] - entry['timestamp']).total_seconds() / 3600  # hours
                })
                
                logging.info(f"Simulated SELL: {symbol} at {market_data['price']}, PNL: {pnl:.2f} USDT")
                del self.positions[symbol]

    def _execute_live_trade(self, action: str, symbol: str, position_size: float,
                          stop_loss: float = None, take_profit: float = None):
        """Execute a live trade on Binance."""
        try:
            if action == "BUY":
                if self.market_type == 'futures':
                    mark_price = float(self.binance_client.futures_symbol_ticker(symbol=symbol)['price'])
                    quantity = max(position_size / mark_price, 0)
                    order = self.binance_client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quantity=quantity
                    )
                else:
                    order = self.binance_client.create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quoteOrderQty=position_size
                    )
                logging.info(f"Executed BUY: {symbol} - {order}")
                
            elif action == "SELL":
                if self.market_type == 'futures':
                    positions = self.binance_client.futures_position_information(symbol=symbol)
                    quantity = 0.0
                    for position in positions:
                        quantity = max(quantity, abs(float(position.get('positionAmt') or 0.0)))
                    if quantity <= 0:
                        logging.warning("No futures position amount found for %s", symbol)
                        return
                    order = self.binance_client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=quantity
                    )
                else:
                    position = self.binance_client.get_asset_balance(asset=symbol.split('/')[0])
                    order = self.binance_client.create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=position['free']
                    )
                logging.info(f"Executed SELL: {symbol} - {order}")
                
        except BinanceAPIException as e:
            logging.error(f"Trade execution error: {e}")

    def evaluate_positions(self):
        """Evaluate all trading pairs and execute trades based on pattern analysis and Claude's advice."""
        for symbol in self.config['trading_pairs']:
            market_data, historical_data = self.get_market_data(symbol)
            if not market_data or historical_data is None:
                continue
            
            # Analyze patterns
            patterns = self.pattern_analyzer.analyze_patterns(historical_data)
            
            # Log detected patterns
            if patterns:
                for pattern in patterns:
                    logging.info(f"Detected {pattern.name} pattern for {symbol}: {pattern.direction} "
                               f"(confidence: {pattern.confidence:.2f})")
            
            # Get pattern-based signal
            pattern_signal = self.pattern_analyzer.get_trading_signal(
                patterns,
                current_position=(symbol in self.positions)
            )
            
            # Get LLM advice incorporating pattern analysis
            llm_advice = self.ask_llm(symbol, market_data, patterns)
            logging.info(f"Pattern analysis signal for {symbol}: {pattern_signal}")
            logging.info(
                "LLM advice for %s via %s/%s: %s",
                symbol,
                self.llm_provider,
                self.llm_model,
                llm_advice,
            )
            
            # Combine signals for final decision
            final_signal = self._combine_signals(pattern_signal, llm_advice)
            logging.info(f"Final trading decision for {symbol}: {final_signal}")
            
            # Execute trades based on final decision
            self.execute_trade(symbol, final_signal, market_data)
            
            # Calculate and log daily PNL
            self._log_daily_pnl()

    def _log_daily_pnl(self):
        """Calculate and log detailed daily PNL metrics."""
        today = datetime.now().date()
        daily_trades = [
            trade for trade in self.pnl_history 
            if trade['timestamp'].date() == today
        ]
        
        if not daily_trades:
            return
            
        # Calculate daily metrics
        daily_pnl = sum(trade['pnl'] for trade in daily_trades)
        winning_trades = [trade for trade in daily_trades if trade['pnl'] > 0]
        losing_trades = [trade for trade in daily_trades if trade['pnl'] < 0]
        
        win_rate = len(winning_trades) / len(daily_trades) if daily_trades else 0
        average_win = sum(trade['pnl'] for trade in winning_trades) / len(winning_trades) if winning_trades else 0
        average_loss = sum(trade['pnl'] for trade in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # Log detailed metrics
        logging.info(f"""
Daily Trading Summary:
- Total PNL: {daily_pnl:.2f} USDT
- Number of Trades: {len(daily_trades)}
- Win Rate: {win_rate:.2%}
- Average Win: {average_win:.2f} USDT
- Average Loss: {average_loss:.2f} USDT
- Profit Factor: {abs(average_win / average_loss) if average_loss != 0 else float('inf'):.2f}
""".strip())

    def cleanup(self):
        """Cleanup resources and save final statistics."""
        logging.info("Bot shutting down...")
        if not self.config['simulation_mode']:
            # Close any open positions if needed
            pass
        
        # Save trading history and statistics
        with open('trading_history.json', 'w') as f:
            json.dump({
                'pnl_history': self.pnl_history,
                'final_positions': self.positions
            }, f, default=str)
