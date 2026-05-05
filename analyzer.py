import yfinance as yf
import pandas_ta_classic as ta
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class StockAnalyzer:
    def __init__(self):
        self.min_data_points = 30

    def fetch_data(self, symbol, period='1mo', interval='15m'):
        try:
            # Peringatan: yfinance gratis mungkin delay 15 menit
            df = yf.download(f"{symbol}.JK", period=period, interval=interval, progress=False, auto_adjust=True)
            if df.empty: return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            return df if len(df) >= self.min_data_points else None
        except Exception as e:
            logger.error(f"Data fetch error {symbol}: {e}")
            return None

    def analyze(self, symbol, threshold=75):
        df = self.fetch_data(symbol)
        if df is None: return None

        # Indikator Teknikal
        df['rsi'] = ta.rsi(df['Close'], length=14)
        df['ema20'] = ta.ema(df['Close'], length=20)
        df['vol_ma'] = ta.sma(df['Volume'], length=10)
        df['vol_ratio'] = df['Volume'] / df['vol_ma']
        
        df = df.dropna()
        if df.empty: return None

        latest = df.iloc[-1]
        score = 0
        reasons = []

        # RSI Logic
        if latest['rsi'] < 40: 
            score += 30
            reasons.append("RSI Rebound")
        elif latest['rsi'] < 55: 
            score += 15

        # Trend Logic
        if latest['Close'] > latest['ema20']: 
            score += 25
            reasons.append("Breakout EMA20")

        # Volume Logic
        if latest['vol_ratio'] > 1.5: 
            score += 30
            reasons.append("Volume Spike")

        # Price Action
        change_pct = ((latest['Close'] - latest['Open']) / latest['Open']) * 100
        if change_pct > 1: score += 15

        if score >= threshold:
            price = int(latest['Close'])
            # Tentukan TP (4%) dan SL (3%) untuk Day Trading
            tp = int(price * 1.04)
            sl = int(price * 0.97)
            alasan = " + ".join(reasons) if reasons else "Momentum Bullish"

            return {
                'symbol': symbol.replace('.JK', ''),
                'price': price,
                'tp': tp,
                'sl': sl,
                'rsi': round(latest['rsi'], 1),
                'volume_ratio': round(latest['vol_ratio'], 1),
                'volume_real': int(latest['Volume']),
                'score': score,
                'change_pct': round(change_pct, 2),
                'alasan': alasan
            }
        return None