import yfinance as yf
import ta
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class StockAnalyzer:
    """
    IDX Day Trader Analyzer — Enhanced v3
    Indikator lengkap:
    1.  EMA20 vs EMA50      — Trend filter
    2.  RSI (14)            — Momentum oversold/overbought
    3.  Stochastic (14,3,3) — Double konfirmasi momentum
    4.  MACD (12,26,9)      — Crossover & histogram
    5.  ATR (14)            — Volatility-based TP/SL
    6.  Volume Ratio        — Spike detection
    7.  Candlestick Pattern — Hammer, Engulfing, Morning Star
    8.  Market Condition    — Trending vs Sideways multiplier
    -- BARU --
    9.  VWAP                — Institutional benchmark intraday
    10. Bollinger Bands     — Squeeze & lower band touch
    11. ADX (14)            — Trend strength filter (ADX < 20 = skip)
    12. OBV Divergence      — Volume/price confirmation
    13. Support/Resistance  — Pivot-based S/R proximity
    14. Gap Detection       — Gap up/down dari close kemarin
    15. RSI Divergence      — Bullish divergence detection
    16. Fibonacci TP        — Level 61.8% sebagai TP alternatif
    """

    def __init__(self):
        self.min_data_points  = 60
        self.min_volume_ratio = 0.3   # Min 30% dari rata-rata volume
        self.min_adx          = 20    # ADX < 20 = sideways, skip

    # ------------------------------------------------------------------ #
    #  DATA FETCHING
    # ------------------------------------------------------------------ #
    def fetch_data(self, symbol: str, period: str = '59d', interval: str = '15m') -> pd.DataFrame | None:
        """
        Fetch OHLCV dari Yahoo Finance.
        PENTING: '59d' bukan '2mo' — Yahoo Finance batasi 15m hanya 60 hari.
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
    #  VWAP (manual — library ta tidak punya VWAP yang proper)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _calc_vwap(df: pd.DataFrame) -> pd.Series:
        """
        VWAP = cumulative(typical_price * volume) / cumulative(volume)
        Reset setiap hari (group by date).
        """
        df = df.copy()
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['tp_vol']        = df['typical_price'] * df['volume']
        df['date']          = df.index.date

        vwap = df.groupby('date').apply(
            lambda g: (g['tp_vol'].cumsum() / g['volume'].cumsum())
        ).reset_index(level=0, drop=True)

        return vwap

    # ------------------------------------------------------------------ #
    #  SUPPORT & RESISTANCE (Pivot-based)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_sr_levels(df: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
        """
        Cari support (pivot low) dan resistance (pivot high) dari lookback bar.
        Return: (support, resistance)
        """
        recent = df.iloc[-lookback:]
        support    = float(recent['low'].min())
        resistance = float(recent['high'].max())
        return support, resistance

    # ------------------------------------------------------------------ #
    #  RSI DIVERGENCE
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_rsi_divergence(df: pd.DataFrame, lookback: int = 10) -> bool:
        """
        Bullish divergence: harga buat lower low tapi RSI buat higher low.
        """
        try:
            recent = df.iloc[-lookback:]
            price_min_idx = recent['close'].idxmin()
            rsi_at_price_min = recent.loc[price_min_idx, 'rsi']

            # Bandingkan dengan RSI sekarang
            current_rsi   = df['rsi'].iloc[-1]
            current_price = df['close'].iloc[-1]
            prev_low      = float(recent['close'].min())

            if current_price <= prev_low * 1.01 and current_rsi > rsi_at_price_min * 1.05:
                return True  # Harga flat/turun tapi RSI naik = bullish divergence
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ #
    #  BOLLINGER BAND SQUEEZE DETECTION
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_bb_squeeze(df: pd.DataFrame) -> tuple[bool, bool]:
        """
        Return: (is_squeeze, touch_lower_band)
        Squeeze = bandwidth sangat sempit (volatilitas rendah sebelum breakout)
        """
        bw = df['bb_bandwidth'].dropna()
        if len(bw) < 10:
            return False, False

        current_bw   = bw.iloc[-1]
        avg_bw       = bw.iloc[-20:].mean()
        is_squeeze   = current_bw < avg_bw * 0.5   # bandwidth < 50% rata-rata = squeeze

        # Touch lower band: harga menyentuh atau di bawah lower band
        touch_lower  = df['close'].iloc[-1] <= df['bb_lower'].iloc[-1] * 1.005

        return bool(is_squeeze), bool(touch_lower)

    # ------------------------------------------------------------------ #
    #  FIBONACCI TP
    # ------------------------------------------------------------------ #
    @staticmethod
    def _calc_fib_tp(df: pd.DataFrame, price: float) -> float:
        """
        Hitung TP berdasarkan Fibonacci 61.8% dari swing low ke swing high (20 bar).
        """
        try:
            recent     = df.iloc[-20:]
            swing_low  = float(recent['low'].min())
            swing_high = float(recent['high'].max())
            fib_618    = swing_low + (swing_high - swing_low) * 1.618
            # Pakai fib 61.8% extension dari swing sebagai TP kalau lebih tinggi dari ATR TP
            return fib_618
        except Exception:
            return price * 1.03

    # ------------------------------------------------------------------ #
    #  CANDLESTICK PATTERN
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

        if lower_wick_ratio > 0.55 and body_ratio < 0.35 and c['close'] >= c['open']:
            return ("Bullish Hammer 🔨", 15)

        if (c['close'] > c['open'] and p['close'] < p['open']
                and c['open'] <= p['close'] and c['close'] >= p['open']):
            return ("Bullish Engulfing 🕯️", 20)

        if len(df) >= 3:
            pp = df.iloc[-3]
            if (pp['close'] < pp['open']
                    and body_ratio < 0.3
                    and c['close'] > c['open']
                    and c['close'] > (pp['open'] + pp['close']) / 2):
                return ("Morning Star ⭐", 20)

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
    def analyze(self, symbol: str, threshold: int = 75, strict_filter: bool = True) -> dict | None:
        df = self.fetch_data(symbol)
        if df is None:
            logger.info(f"[{symbol}] fetch_data return None")
            return None

        # ── Indikator Lama ─────────────────────────────────────────────
        df['ema20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['rsi']   = ta.momentum.rsi(df['close'], window=14)

        stoch_ind     = ta.momentum.StochasticOscillator(
            df['high'], df['low'], df['close'], window=14, smooth_window=3
        )
        df['stoch_k'] = stoch_ind.stoch()
        df['stoch_d'] = stoch_ind.stoch_signal()

        macd_ind          = ta.trend.MACD(df['close'], window_fast=12, window_slow=26, window_sign=9)
        df['macd']        = macd_ind.macd()
        df['macd_signal'] = macd_ind.macd_signal()
        df['macd_hist']   = macd_ind.macd_diff()

        df['atr'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], window=14
        )

        df['vol_ma']    = df['volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)

        # ── Indikator Baru ─────────────────────────────────────────────

        # 9. VWAP
        try:
            df['vwap'] = StockAnalyzer._calc_vwap(df)
        except Exception:
            df['vwap'] = df['close']  # fallback

        # 10. Bollinger Bands (20, 2)
        bb_ind             = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper']     = bb_ind.bollinger_hband()
        df['bb_lower']     = bb_ind.bollinger_lband()
        df['bb_mid']       = bb_ind.bollinger_mavg()
        df['bb_bandwidth'] = bb_ind.bollinger_wband()
        df['bb_pct']       = bb_ind.bollinger_pband()   # %B: 0=lower, 1=upper

        # 11. ADX (14) — trend strength
        adx_ind    = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx']  = adx_ind.adx()
        df['adx_pos'] = adx_ind.adx_pos()   # +DI
        df['adx_neg'] = adx_ind.adx_neg()   # -DI

        # 12. OBV
        df['obv']    = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_ma'] = df['obv'].rolling(window=20).mean()

        # ── Drop NaN ───────────────────────────────────────────────────
        logger.info(f"[{symbol}] sebelum dropna: {len(df)} rows")
        df = df.dropna()
        logger.info(f"[{symbol}] setelah dropna: {len(df)} rows")

        if df.empty:
            logger.info(f"[{symbol}] df kosong setelah dropna")
            return None

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        # ── Liquidity Gate ─────────────────────────────────────────────
        vol_ratio = latest['vol_ratio']
        if strict_filter and vol_ratio < self.min_volume_ratio:
            logger.info(f"[{symbol}] TIDAK LOLOS liquidity gate: vol_ratio={vol_ratio:.2f}")
            return None

        # ── ADX Filter — skip jika market terlalu sideways ─────────────
        adx = latest['adx']
        if strict_filter and threshold > 0 and adx < self.min_adx:
            logger.info(f"[{symbol}] TIDAK LOLOS ADX filter: adx={adx:.1f} < {self.min_adx}")
            return None

        # ── Scoring ────────────────────────────────────────────────────
        score   = 0
        reasons = []

        # 1. Trend Filter EMA
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
            score -= 10

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

        # 9. VWAP — indikator institusional
        if latest['close'] > latest['vwap']:
            score += 20
            reasons.append("Harga > VWAP 📊")
        elif latest['close'] < latest['vwap'] * 0.99:
            score -= 10  # Harga jauh di bawah VWAP = bearish intraday

        # 10. Bollinger Bands
        is_squeeze, touch_lower = StockAnalyzer._detect_bb_squeeze(df)
        if is_squeeze:
            score += 15
            reasons.append("BB Squeeze 🔥")   # Volatilitas rendah = potensi breakout
        if touch_lower:
            score += 15
            reasons.append("BB Lower Touch")  # Oversold di lower band

        # 11. ADX — tambah bonus kalau trend sangat kuat
        if adx > 35:
            score += 15
            reasons.append(f"Trend Kuat ADX {adx:.0f}")
        elif adx > 25:
            score += 8
        # +DI > -DI = arah bullish dikonfirmasi ADX
        if latest['adx_pos'] > latest['adx_neg']:
            score += 10
            reasons.append("+DI > -DI Bullish")

        # 12. OBV Confirmation
        obv_rising = latest['obv'] > latest['obv_ma']
        if obv_rising and latest['close'] > prev['close']:
            score += 15
            reasons.append("OBV Konfirmasi ✅")
        elif not obv_rising and latest['close'] > prev['close']:
            score -= 10  # Harga naik tapi OBV turun = divergence negatif

        # 13. Support & Resistance
        support, resistance = StockAnalyzer._find_sr_levels(df)
        price_now = float(latest['close'])
        near_support    = price_now <= support * 1.02      # Dalam 2% dari support
        near_resistance = price_now >= resistance * 0.98   # Dalam 2% dari resistance
        if near_support:
            score += 15
            reasons.append("Dekat Support 🛡️")
        if near_resistance:
            score -= 10  # Dekat resistance = potensi terbentur

        # 14. Gap Detection
        change_pct = round(((latest['close'] - prev['close']) / prev['close']) * 100, 2)
        if change_pct > 1.5:
            score += 10
            reasons.append(f"Gap Up {change_pct}%")
        elif 0.5 < change_pct < 1.5:
            score += 5
        elif change_pct < -2.0:
            score -= 15  # Gap down besar = hindari

        # 15. RSI Divergence (bullish)
        if StockAnalyzer._detect_rsi_divergence(df):
            score += 20
            reasons.append("RSI Divergence Bullish 🔄")

        logger.info(
            f"[{symbol}] score={score}, threshold={threshold}, "
            f"market={market}, adx={adx:.1f}, vwap_ok={latest['close'] > latest['vwap']}"
        )

        # ── Threshold ──────────────────────────────────────────────────
        if score < threshold:
            logger.info(f"[{symbol}] TIDAK LOLOS threshold ({score} < {threshold})")
            return None

        # ── TP/SL: gabungan ATR + Fibonacci ───────────────────────────
        price = round(float(latest['close']), 2)
        atr   = round(float(latest['atr']), 2)

        atr_tp      = price + max(atr * 2.0, price * 0.02)
        fib_tp      = StockAnalyzer._calc_fib_tp(df, price)
        # Pakai yang lebih konservatif (lebih rendah) untuk safety
        tp_price    = min(atr_tp, fib_tp) if fib_tp > price else atr_tp

        sl_distance = max(atr * 1.5, price * 0.015)
        tp          = int(tp_price)
        sl          = int(price - sl_distance)
        rrr         = round((tp - price) / sl_distance, 2)

        alasan = " + ".join(reasons) if reasons else "Momentum Bullish"

        return {
            'symbol':       symbol.replace('.JK', ''),
            'price':        int(price),
            'tp':           tp,
            'sl':           sl,
            'rrr':          rrr,
            'atr':          atr,
            'adx':          round(float(adx), 1),
            'vwap':         round(float(latest['vwap']), 0),
            'bb_pct':       round(float(latest['bb_pct']), 2),
            'rsi':          round(float(rsi), 1),
            'stoch_k':      round(float(sk), 1),
            'macd_hist':    round(float(latest['macd_hist']), 4),
            'obv_ok':       bool(obv_rising),
            'near_support': bool(near_support),
            'volume_ratio': round(float(vol_ratio), 1),
            'volume_real':  int(latest['volume']),
            'score':        score,
            'change_pct':   change_pct,
            'market_cond':  market,
            'alasan':       alasan,
        }