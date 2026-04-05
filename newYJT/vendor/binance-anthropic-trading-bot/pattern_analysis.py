import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class Pattern:
    name: str
    confidence: float
    direction: str  # 'bullish' or 'bearish'
    start_idx: int
    end_idx: int

class PatternAnalyzer:
    def __init__(self, min_pattern_size: int = 5, confidence_threshold: float = 0.7):
        self.min_pattern_size = min_pattern_size
        self.confidence_threshold = confidence_threshold

    def get_market_data(
        self,
        client,
        symbol: str,
        interval: str = '1h',
        limit: int = 100,
        market_type: str = 'spot',
    ) -> pd.DataFrame:
        """Fetch market data from Binance and convert to DataFrame."""
        if market_type == 'futures':
            klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        else:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignored'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def detect_flag_pattern(self, df: pd.DataFrame) -> Optional[Pattern]:
        """Detect bull/bear flag patterns."""
        price_changes = df['close'].pct_change()
        volatility = df['high'] - df['low']
        
        for i in range(self.min_pattern_size, len(df) - self.min_pattern_size):
            pole = price_changes[i-self.min_pattern_size:i].sum()
            flag_volatility = volatility[i:i+self.min_pattern_size].mean()
            pre_flag_volatility = volatility[i-self.min_pattern_size:i].mean()
            
            if abs(pole) > 0.05 and flag_volatility < pre_flag_volatility * 0.5:
                direction = 'bullish' if pole > 0 else 'bearish'
                return Pattern(
                    name='flag',
                    confidence=min(abs(pole) * 10, 1.0),
                    direction=direction,
                    start_idx=i-self.min_pattern_size,
                    end_idx=i+self.min_pattern_size
                )
        return None

    def detect_triangle_pattern(self, df: pd.DataFrame) -> Optional[Pattern]:
        """Detect symmetrical triangle pattern."""
        for i in range(self.min_pattern_size * 2, len(df) - self.min_pattern_size):
            window = df[i-self.min_pattern_size*2:i]
            
            highs = window['high'].values
            lows = window['low'].values
            x = np.arange(len(window))
            
            high_fit = np.polyfit(x, highs, 1)
            low_fit = np.polyfit(x, lows, 1)
            
            high_slope = high_fit[0]
            low_slope = low_fit[0]
            
            if -0.001 < high_slope < 0 and 0 < low_slope < 0.001:
                x_intersect = (low_fit[1] - high_fit[1]) / (high_fit[0] - low_fit[0])
                
                if x_intersect > len(window) and x_intersect < len(window) * 2:
                    return Pattern(
                        name='triangle',
                        confidence=0.8,
                        direction='bullish' if window['close'].iloc[-1] > window['close'].iloc[0] else 'bearish',
                        start_idx=i-self.min_pattern_size*2,
                        end_idx=i
                    )
        return None

    def detect_pennant_pattern(self, df: pd.DataFrame) -> Optional[Pattern]:
        """Detect pennant pattern."""
        for i in range(self.min_pattern_size * 3, len(df) - self.min_pattern_size):
            mast_window = df[i-self.min_pattern_size*3:i-self.min_pattern_size*2]
            mast_move = (mast_window['close'].iloc[-1] - mast_window['close'].iloc[0]) / mast_window['close'].iloc[0]
            
            if abs(mast_move) > 0.05:
                pennant_window = df[i-self.min_pattern_size*2:i]
                highs = pennant_window['high'].values
                lows = pennant_window['low'].values
                x = np.arange(len(pennant_window))
                
                high_fit = np.polyfit(x, highs, 1)
                low_fit = np.polyfit(x, lows, 1)
                
                high_slope = high_fit[0]
                low_slope = low_fit[0]
                
                if high_slope < -0.001 and low_slope > 0.001:
                    return Pattern(
                        name='pennant',
                        confidence=min(abs(mast_move) * 10, 1.0),
                        direction='bullish' if mast_move > 0 else 'bearish',
                        start_idx=i-self.min_pattern_size*3,
                        end_idx=i
                    )
        return None

    def analyze_patterns(self, df: pd.DataFrame) -> List[Pattern]:
        """Analyze all continuation patterns."""
        patterns = []
        
        for pattern in [self.detect_flag_pattern(df), 
                       self.detect_triangle_pattern(df), 
                       self.detect_pennant_pattern(df)]:
            if pattern and pattern.confidence >= self.confidence_threshold:
                patterns.append(pattern)
        
        return patterns

    def get_trading_signal(self, patterns: List[Pattern], current_position: bool) -> str:
        """Generate trading signal based on detected patterns."""
        if not patterns:
            return "HOLD"
            
        patterns.sort(key=lambda x: x.confidence, reverse=True)
        top_pattern = patterns[0]
        
        if top_pattern.direction == 'bullish':
            return "HOLD" if current_position else "BUY"
        else:
            return "SELL" if current_position else "HOLD"

    def validate_breakout(self, df: pd.DataFrame, pattern: Pattern) -> bool:
        """Validate if price has broken out of the pattern."""
        pattern_data = df.iloc[pattern.start_idx:pattern.end_idx]
        latest_close = df['close'].iloc[-1]
        
        if pattern.direction == 'bullish':
            resistance = pattern_data['high'].max()
            return latest_close > resistance
        else:
            support = pattern_data['low'].min()
            return latest_close < support
