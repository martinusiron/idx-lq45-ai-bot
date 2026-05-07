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
        """
        Fetch OHLCV data dari Yahoo Finance.
        PENTING: Yahoo Finance membatasi data 15m hanya untuk 60 hari terakhir.
        Gunakan '59d' (bukan '2mo') karena '2mo' bisa dihitung ~61 hari dan
        menyebabkan error "startTime out of range" untuk semua saham.
        """
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith('.JK') else symbol
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True)
            if df.empty:
                return None

            # Flatten MultiIndex jika ada
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename kolom lowercase supaya konsisten
            df.columns = [c.lower() for c in df.columns]

            if len(df) < self.min_data_points:
                return None

            return df

        except Exception as e:
            logger.error(f"[{symbol}] Data fetch error: {e}")
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
            return None

        # ── Indikator Teknikal ──────────────────────────────────────────
        # Trend
        df['ema20']  = ta.ema(df['close'], length=20)
        df['ema50']  = ta.ema(df['close'], length=50)

        # Momentum
        df['rsi']    = ta.rsi(df['close'], length=14)

        stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch.iloc[:, 0]
            df['stoch_d'] = stoch.iloc[:, 1]
        else:
            df['stoch_k'] = 50.0
            df['stoch_d'] = 50.0

        # MACD
        macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            df['macd']        = macd_df.iloc[:, 0]
            df['macd_signal'] = macd_df.iloc[:, 1]
            df['macd_hist']   = macd_df.iloc[:, 2]
        else:
            df['macd'] = df['macd_signal'] = df['macd_hist'] = 0.0

        # ATR untuk volatility-based TP/SL
        atr_series = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr']   = atr_series if atr_series is not None else pd.Series(0.0, index=df.index)

        # Volume
        df['vol_ma']    = ta.sma(df['volume'], length=20)   # window lebih panjang (20 vs 10)
        df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)

        df = df.dropna()
        if df.empty:
            return None

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        # ── Liquidity Gate ─────────────────────────────────────────────
        if latest['volume'] < self.min_volume_abs:
            logger.debug(f"[{symbol}] Volume terlalu tipis: {latest['volume']:.0f}")
            return None

        # ── Scoring System ──────────────────────────────────────────────
        score   = 0
        reasons = []

        # 1. TREND FILTER (EMA20 vs EMA50) — bobot tinggi
        if latest['ema20'] > latest['ema50']:
            score += 20
            reasons.append("Uptrend EMA20>50")

        # 2. HARGA DI ATAS EMA20 (konfirmasi momentum jangka pendek)
        if latest['close'] > latest['ema20']:
            score += 15
            reasons.append("Harga > EMA20")

        # 3. RSI LOGIC — lebih granular
        rsi = latest['rsi']
        if 30 <= rsi <= 45:
            score += 30         # Oversold recovery — setup terbaik
            reasons.append(f"RSI Rebound ({rsi:.0f})")
        elif 45 < rsi <= 60:
            score += 15         # Neutral bullish momentum
        elif rsi > 70:
            score -= 10         # Overbought — penalty

        # 4. STOCHASTIC DOUBLE KONFIRMASI
        sk, sd = latest['stoch_k'], latest['stoch_d']
        if sk < 25 and sk > sd:
            score += 20
            reasons.append(f"Stoch Bullish Cross ({sk:.0f})")
        elif sk < 40 and sk > sd:
            score += 10

        # 5. MACD CROSSOVER / MOMENTUM
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            score += 20
            reasons.append("MACD Golden Cross")
        elif latest['macd'] > latest['macd_signal']:
            score += 10
            reasons.append("MACD Bullish")
        if latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']:
            score += 5          # Histogram menguat

        # 6. VOLUME SPIKE
        vol_ratio = latest['vol_ratio']
        if vol_ratio > 2.0:
            score += 25
            reasons.append(f"Volume Spike {vol_ratio:.1f}x")
        elif vol_ratio > 1.5:
            score += 15
            reasons.append(f"Volume Naik {vol_ratio:.1f}x")

        # 7. CANDLESTICK PATTERN
        pattern_name, pattern_score = StockAnalyzer._detect_candle_pattern(df)
        if pattern_score > 0:
            score += pattern_score
            reasons.append(pattern_name)

        # 8. MARKET CONDITION MULTIPLIER
        market = _market_condition = StockAnalyzer._market_condition(df)
        if market == 'trending_up':
            score = int(score * 1.1)    # Bonus 10% di trending market
        elif market == 'sideways':
            score = int(score * 0.85)   # Penalty 15% di sideways (rawan false signal)
        elif market == 'trending_down':
            score = int(score * 0.70)   # Penalty besar — counter-trend trading berisiko

        # 9. PRICE ACTION vs PREVIOUS CLOSE
        change_pct = round(((latest['close'] - prev['close']) / prev['close']) * 100, 2)
        if 0.5 < change_pct < 3.0:
            score += 10         # Gerak sehat, tidak terlalu cepat
        elif change_pct > 5.0:
            score -= 5          # Sudah terlalu banyak naik, FOMO risk

        # ── Threshold Filter ────────────────────────────────────────────
        if score < threshold:
            return None

        # ── TP/SL Berbasis ATR (volatility-adjusted) ────────────────────
        price = round(float(latest['close']), 2)
        atr   = round(float(latest['atr']), 2)

        # ATR multiplier: TP = 2x ATR, SL = 1.5x ATR → RRR >= 1:1.33
        tp_distance = max(atr * 2.0, price * 0.02)   # minimum 2% TP
        sl_distance = max(atr * 1.5, price * 0.015)  # minimum 1.5% SL

        tp = int(price + tp_distance)
        sl = int(price - sl_distance)

        # RRR (Risk Reward Ratio)
        rrr = round(tp_distance / sl_distance, 2)

        alasan = " + ".join(reasons) if reasons else "Momentum Bullish"

        return {
            'symbol':       symbol.replace('.JK', ''),
            'price':        int(price),
            'tp':           tp,
            'sl':           sl,
            'rrr':          rrr,            # ← BARU: Risk-Reward Ratio
            'atr':          atr,            # ← BARU: Average True Range
            'rsi':          round(rsi, 1),
            'stoch_k':      round(sk, 1),   # ← BARU: Stochastic %K
            'macd_hist':    round(float(latest['macd_hist']), 4),  # ← BARU
            'volume_ratio': round(float(vol_ratio), 1),
            'volume_real':  int(latest['volume']),
            'score':        score,
            'change_pct':   change_pct,
            'market_cond':  market,         # ← BARU: trending_up/sideways/trending_down
            'alasan':       alasan,
        }