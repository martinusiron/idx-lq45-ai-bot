import yfinance as yf
import ta
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class StockAnalyzer:
    """
    IDX Day Trader Analyzer
    Menggunakan library 'ta' (pip install ta) — kompatibel Python 3.11+
 
    Kriteria Day Trading Profesional IDX:
    1. Trend Filter      - EMA20 vs EMA50 konfirmasi arah trend
    2. Momentum          - RSI(14) + Stochastic(14,3,3) double konfirmasi
    3. Trend Strength    - MACD untuk momentum divergence/crossover
    4. Volume Quality    - Volume spike relatif dengan lookback 20 bar
    5. Volatility-Based  - ATR untuk TP/SL yang realistis (bukan % flat)
    6. Candlestick       - Deteksi pola reversal (Hammer, Engulfing, Morning Star)
    7. Market Condition  - Trending vs Sideways multiplier
    8. Liquidity Gate    - Filter saham volume tipis (rawan manipulasi)
    """
 
    def __init__(self):
        self.min_data_points = 60
        self.min_volume_abs  = 5_000_000  # 5 juta lembar per candle
 
    # ------------------------------------------------------------------ #
    #  DATA FETCHING
    # ------------------------------------------------------------------ #
    def fetch_data(self, symbol: str, period: str = '59d', interval: str = '15m') -> pd.DataFrame | None:
        """
        Fetch OHLCV dari Yahoo Finance.
        PENTING: Gunakan '59d' bukan '2mo' — Yahoo Finance batasi 15m data
        hanya 60 hari terakhir. '2mo' bisa dihitung ~61 hari dan error.
        """
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith('.JK') else symbol
            df = yf.download(
                ticker, period=period, interval=interval,
                progress=False, auto_adjust=True
            )
 
            logger.info(f"[{symbol}] df.empty={df.empty}, len={len(df)}")
 
            if df.empty:
                return None
 
            # Flatten MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
 
            df.columns = [c.lower() for c in df.columns]
 
            logger.info(f"[{symbol}] columns={list(df.columns)}, rows={len(df)}, min_required={self.min_data_points}")
 
            if len(df) < self.min_data_points:
                return None
 
            return df
 
        except Exception as e:
            logger.error(f"[{symbol}] fetch_data error: {e}")
            return None
 
    # ------------------------------------------------------------------ #
    #  CANDLESTICK PATTERN DETECTION
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_candle_pattern(df: pd.DataFrame) -> tuple[str, int]:
        c = df.iloc[-1]
        p = df.iloc[-2]
 
        body         = abs(c['close'] - c['open'])
        candle_range = c['high'] - c['low']
        lower_wick   = min(c['close'], c['open']) - c['low']
 
        if candle_range == 0:
            return ("", 0)
 
        body_ratio       = body / candle_range
        lower_wick_ratio = lower_wick / candle_range
 
        # Bullish Hammer
        if lower_wick_ratio > 0.55 and body_ratio < 0.35 and c['close'] >= c['open']:
            return ("Bullish Hammer 🔨", 15)
 
        # Bullish Engulfing
        if (c['close'] > c['open'] and p['close'] < p['open']
                and c['open'] <= p['close'] and c['close'] >= p['open']):
            return ("Bullish Engulfing 🕯️", 20)
 
        # Morning Star
        if len(df) >= 3:
            pp = df.iloc[-3]
            if (pp['close'] < pp['open']
                    and body_ratio < 0.3
                    and c['close'] > c['open']
                    and c['close'] > (pp['open'] + pp['close']) / 2):
                return ("Morning Star ⭐", 20)
 
        # Marubozu Bullish
        if body_ratio > 0.85 and c['close'] > c['open']:
            return ("Marubozu Bullish 💹", 10)
 
        return ("", 0)
 
    # ------------------------------------------------------------------ #
    #  MARKET CONDITION
    # ------------------------------------------------------------------ #
    @staticmethod
    def _market_condition(df: pd.DataFrame) -> str:
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
 
        # ── Indikator — pakai library 'ta' ─────────────────────────────
        # Trend
        df['ema20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
 
        # RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
 
        # Stochastic
        stoch_ind     = ta.momentum.StochasticOscillator(
            df['high'], df['low'], df['close'], window=14, smooth_window=3
        )
        df['stoch_k'] = stoch_ind.stoch()
        df['stoch_d'] = stoch_ind.stoch_signal()
 
        # MACD
        macd_ind          = ta.trend.MACD(df['close'], window_fast=12, window_slow=26, window_sign=9)
        df['macd']        = macd_ind.macd()
        df['macd_signal'] = macd_ind.macd_signal()
        df['macd_hist']   = macd_ind.macd_diff()
 
        # ATR
        df['atr'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], window=14
        )
 
        # Volume MA & ratio
        df['vol_ma']    = df['volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)
 
        logger.info(f"[{symbol}] sebelum dropna: {len(df)} rows")
        df = df.dropna()
        logger.info(f"[{symbol}] setelah dropna: {len(df)} rows")
 
        if df.empty:
            logger.info(f"[{symbol}] df kosong setelah dropna")
            return None
 
        latest = df.iloc[-1]
        prev   = df.iloc[-2]
 
        # ── Liquidity Gate ─────────────────────────────────────────────
        if latest['volume'] < self.min_volume_abs:
            logger.info(f"[{symbol}] TIDAK LOLOS liquidity gate: volume={latest['volume']:.0f}")
            return None
 
        # ── Scoring ────────────────────────────────────────────────────
        score   = 0
        reasons = []
 
        # 1. Trend Filter
        if latest['ema20'] > latest['ema50']:
            score += 20
            reasons.append("Uptrend EMA20>50")
 
        # 2. Harga di atas EMA20
        if latest['close'] > latest['ema20']:
            score += 15
            reasons.append("Harga > EMA20")
 
        # 3. RSI
        rsi = latest['rsi']
        if 30 <= rsi <= 45:
            score += 30
            reasons.append(f"RSI Rebound ({rsi:.0f})")
        elif 45 < rsi <= 60:
            score += 15
        elif rsi > 70:
            score -= 10  # overbought penalty
 
        # 4. Stochastic
        sk = latest['stoch_k']
        sd = latest['stoch_d']
        if sk < 25 and sk > sd:
            score += 20
            reasons.append(f"Stoch Bullish Cross ({sk:.0f})")
        elif sk < 40 and sk > sd:
            score += 10
 
        # 5. MACD
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            score += 20
            reasons.append("MACD Golden Cross")
        elif latest['macd'] > latest['macd_signal']:
            score += 10
            reasons.append("MACD Bullish")
        if latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']:
            score += 5
 
        # 6. Volume Spike
        vol_ratio = latest['vol_ratio']
        if vol_ratio > 2.0:
            score += 25
            reasons.append(f"Volume Spike {vol_ratio:.1f}x")
        elif vol_ratio > 1.5:
            score += 15
            reasons.append(f"Volume Naik {vol_ratio:.1f}x")
 
        # 7. Candlestick Pattern
        pattern_name, pattern_score = StockAnalyzer._detect_candle_pattern(df)
        if pattern_score > 0:
            score += pattern_score
            reasons.append(pattern_name)
 
        # 8. Market Condition Multiplier
        market = StockAnalyzer._market_condition(df)
        if market == 'trending_up':
            score = int(score * 1.1)
        elif market == 'sideways':
            score = int(score * 0.85)
        elif market == 'trending_down':
            score = int(score * 0.70)
 
        # 9. Price Action vs previous close
        change_pct = round(((latest['close'] - prev['close']) / prev['close']) * 100, 2)
        if 0.5 < change_pct < 3.0:
            score += 10
        elif change_pct > 5.0:
            score -= 5
 
        logger.info(f"[{symbol}] score={score}, threshold={threshold}, market={market}")
 
        # ── Threshold ──────────────────────────────────────────────────
        if score < threshold:
            logger.info(f"[{symbol}] TIDAK LOLOS threshold ({score} < {threshold})")
            return None
 
        # ── TP/SL berbasis ATR ─────────────────────────────────────────
        price = round(float(latest['close']), 2)
        atr   = round(float(latest['atr']), 2)
 
        tp_distance = max(atr * 2.0, price * 0.02)
        sl_distance = max(atr * 1.5, price * 0.015)
 
        tp  = int(price + tp_distance)
        sl  = int(price - sl_distance)
        rrr = round(tp_distance / sl_distance, 2)
 
        alasan = " + ".join(reasons) if reasons else "Momentum Bullish"
 
        return {
            'symbol':       symbol.replace('.JK', ''),
            'price':        int(price),
            'tp':           tp,
            'sl':           sl,
            'rrr':          rrr,
            'atr':          atr,
            'rsi':          round(float(rsi), 1),
            'stoch_k':      round(float(sk), 1),
            'macd_hist':    round(float(latest['macd_hist']), 4),
            'volume_ratio': round(float(vol_ratio), 1),
            'volume_real':  int(latest['volume']),
            'score':        score,
            'change_pct':   change_pct,
            'market_cond':  market,
            'alasan':       alasan,
        }
 