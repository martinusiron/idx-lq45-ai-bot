import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class StockAnalyzer:
    """
    Improved IDX Day Trader Analyzer
    
    Kriteria Day Trading Profesional IDX:
    1. Trend Filter      - EMA20 vs EMA50 untuk konfirmasi arah trend
    2. Momentum          - RSI(14) + Stochastic(14,3,3) double konfirmasi
    3. Trend Strength    - MACD untuk momentum divergence/crossover
    4. Volume Quality    - Volume spike RELATIF dengan lookback adaptif
    5. Volatility-Based  - ATR untuk set TP/SL yang realistis (bukan % flat)
    6. Candlestick       - Deteksi pola reversal/continuation (Hammer, Engulfing, Doji)
    7. Market Breadth    - Cek apakah setup ini strong atau lemah vs hari kemarin
    8. Liquidity Gate    - Filter saham yang volume terlalu tipis (rawan bandar)
    """

    def __init__(self):
        self.min_data_points = 60   # Naik dari 30 → butuh cukup data untuk MACD & EMA50
        self.min_volume_abs  = 5_000_000   # Minimum 5 juta lembar/hari (gate likuiditas)

    # ------------------------------------------------------------------ #
    #  DATA FETCHING
    # ------------------------------------------------------------------ #
    def fetch_data(self, symbol: str, period: str = '59d', interval: str = '15m') -> pd.DataFrame | None:
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith('.JK') else symbol
            df = yf.download(ticker, period=period, interval=interval,
                            progress=False, auto_adjust=True)
            
            logger.info(f"[{symbol}] df.empty={df.empty}, len={len(df)}")  # ← TAMBAH INI
            
            if df.empty:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.columns = [c.lower() for c in df.columns]

            logger.info(f"[{symbol}] columns={list(df.columns)}, rows={len(df)}, min_required={self.min_data_points}")  # ← TAMBAH INI

            if len(df) < self.min_data_points:
                return None

            return df
        except Exception as e:
            logger.error(f"Data fetch error {symbol}: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  CANDLESTICK PATTERN DETECTION (manual — lightweight)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_candle_pattern(df: pd.DataFrame) -> tuple[str, int]:
        """
        Deteksi pola candlestick pada 2 candle terakhir.
        Return: (nama_pola, skor_bonus)
        """
        c = df.iloc[-1]
        p = df.iloc[-2]

        body     = abs(c['close'] - c['open'])
        candle_range = c['high'] - c['low']
        lower_wick   = min(c['close'], c['open']) - c['low']
        upper_wick   = c['high'] - max(c['close'], c['open'])

        if candle_range == 0:
            return ("", 0)

        body_ratio        = body / candle_range
        lower_wick_ratio  = lower_wick / candle_range

        # Bullish Hammer / Dragonfly Doji (reversal bawah)
        if lower_wick_ratio > 0.55 and body_ratio < 0.35 and c['close'] >= c['open']:
            return ("Bullish Hammer 🔨", 15)

        # Bullish Engulfing
        if (c['close'] > c['open'] and p['close'] < p['open']
                and c['open'] <= p['close'] and c['close'] >= p['open']):
            return ("Bullish Engulfing 🕯️", 20)

        # Morning Star (simplified: red → small body → big green)
        if len(df) >= 3:
            pp = df.iloc[-3]
            if (pp['close'] < pp['open']                       # candle pertama merah
                    and body_ratio < 0.3                       # candle tengah kecil
                    and c['close'] > c['open']                 # candle ketiga hijau
                    and c['close'] > (pp['open'] + pp['close']) / 2):
                return ("Morning Star ⭐", 20)

        # Bullish Marubozu (full body, sedikit wick)
        if body_ratio > 0.85 and c['close'] > c['open']:
            return ("Marubozu Bullish 💹", 10)

        return ("", 0)

    # ------------------------------------------------------------------ #
    #  MARKET CONDITION (Trending vs Sideways)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _market_condition(df: pd.DataFrame) -> str:
        """
        Sederhana: bandingkan slope EMA20 dan rentang harga 20 bar terakhir.
        Return: 'trending_up' | 'trending_down' | 'sideways'
        """
        ema20 = df['ema20'].dropna()
        if len(ema20) < 10:
            return 'sideways'

        slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100
        if slope > 0.5:
            return 'trending_up'
        elif slope < -0.5:
            return 'trending_down'
        return 'sideways'

    # ------------------------------------------------------------------ #
    #  MAIN ANALYZE
    # ------------------------------------------------------------------ #
    def analyze(self, symbol: str, threshold: int = 75) -> dict | None:
        df = self.fetch_data(symbol)
        if df is None:
            logger.info(f"[{symbol}] fetch_data return None")
            return None

        # Indikator
        df['ema20']  = ta.trend.ema_indicator(df['close'], window=20)
        df['ema50']  = ta.trend.ema_indicator(df['close'], window=50)
        df['rsi']    = ta.momentum.rsi(df['close'], window=14)
        # ... dst

        logger.info(f"[{symbol}] sebelum dropna: {len(df)} rows")
        df = df.dropna()
        logger.info(f"[{symbol}] setelah dropna: {len(df)} rows")  # ← cek ini hilang berapa

        if df.empty:
            logger.info(f"[{symbol}] df kosong setelah dropna")
            return None

        latest = df.iloc[-1]
        logger.info(f"[{symbol}] score sebelum threshold: {score}, threshold: {threshold}")  # ← taruh di akhir scoring

        if score < threshold:
            logger.info(f"[{symbol}] TIDAK LOLOS threshold ({score} < {threshold})")
            return None

        # Liquidity gate
        if latest['volume'] < self.min_volume_abs:
            logger.info(f"[{symbol}] TIDAK LOLOS liquidity gate: volume={latest['volume']}")
            return None