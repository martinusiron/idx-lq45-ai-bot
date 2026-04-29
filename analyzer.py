import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class StockAnalyzer:
    def __init__(self):
        self.min_data_points = 30

    def fetch_data(self, symbol, period='3mo'):
        """Download OHLCV data"""
        try:
            df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
            return df if len(df) >= self.min_data_points else None
        except Exception as e:
            logger.error(f"Data fetch error {symbol}: {e}")
            return None

    def calculate_score(self, df):
        """AI Scoring 0-100"""
        if len(df) < self.min_data_points:
            return 0

        # Technical indicators
        df['rsi'] = ta.rsi(df['Close'], length=14)
        df['ema20'] = ta.ema(df['Close'], length=20)
        df['sma50'] = ta.sma(df['Close'], length=50)
        df['bb'] = ta.bbands(df['Close'], length=20)
        df['bb_upper'] = df['bb']['BBU_20_2.0']
        df['bb_lower'] = df['bb']['BBL_20_2.0']

        # Volume analysis
        df['vol_ma'] = ta.sma(df['Volume'], length=10)
        df['vol_ratio'] = df['Volume'] / df['vol_ma']

        # Support/Resistance
        df['support'] = ta.lowest(df['Low'], length=20)
        df['resistance'] = ta.highest(df['High'], length=20)

        latest = df.iloc[-1]

        score = 0

        # RSI Oversold (30 pts max)
        if pd.notna(latest['rsi']):
            if latest['rsi'] < 30: score += 30
            elif latest['rsi'] < 40: score += 20
            elif latest['rsi'] < 50: score += 10

        # Trend Strength (25 pts)
        if latest['Close'] > latest['ema20']:
            score += 15
        if latest['ema20'] > latest['sma50']:
            score += 10

        # Volume Confirmation (20 pts)
        if latest['vol_ratio'] > 1.8:
            score += 20
        elif latest['vol_ratio'] > 1.3:
            score += 12

        # Price Action (15 pts)
        support_dist = (latest['Close'] - latest['support']) / latest['Close']
        if support_dist < 0.025:  # Within 2.5%
            score += 15

        # Bollinger Bands (10 pts)
        bb_position = (latest['Close'] - latest['bb_lower']) / (latest['bb_upper'] - latest['bb_lower'])
        if bb_position < 0.25:
            score += 10

        return min(round(score, 1), 100)

    def analyze(self, symbol):
        """Full analysis"""
        df = self.fetch_data(symbol)
        if df is None:
            return None

        score = self.calculate_score(df)
        latest = df.iloc[-1]

        if score >= 75:
            return {
                'symbol': symbol.replace('.JK', ''),
                'price': round(latest['Close'], -2),  # Round to nearest 100
                'rsi': round(latest['rsi'], 1),
                'volume_ratio': round(latest['vol_ratio'], 1),
                'score': score,
                'change_pct': round((latest['Close'] / latest['Open'] - 1) * 100, 1)
            }
        return None
