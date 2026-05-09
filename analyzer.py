"""
analyzer.py — IDX Day Trader Signal Engine v4

20 indikator teknikal + MTF + anti-chasing + IHSG correlation.
Compatible dengan repo martinusiron/idx-lq45-ai-bot.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import ta
import yfinance as yf

from config import DATA_INTERVAL, DATA_PERIOD, MIN_VOLUME_ABS

logger = logging.getLogger(__name__)


class StockAnalyzer:
    """
    IDX Day Trader Analyzer — v4

    Indikator:
     1. EMA20 vs EMA50          — Trend filter
     2. RSI (14)                — Momentum
     3. Stochastic (14,3,3)     — Double konfirmasi
     4. MACD (12,26,9)          — Crossover & histogram
     5. ATR (14)                — Volatility-based TP/SL
     6. Volume Ratio            — Spike detection
     7. Candlestick Pattern     — Hammer, Engulfing, Morning Star, Marubozu
     8. Market Condition        — Trending vs Sideways multiplier
     9. VWAP                    — Institutional intraday benchmark
    10. Bollinger Bands         — Squeeze & oversold detection
    11. ADX (14)                — Trend strength filter
    12. OBV Divergence          — Volume/price confirmation
    13. Support/Resistance      — Multi-level pivot detection
    14. Gap Detection           — Gap up/down scoring
    15. RSI Divergence          — Bullish divergence
    16. Anti-Chasing            — Block FOMO entry (>3% dari open)
    17. Bid-Ask Spread Proxy    — Filter likuiditas buruk
    18. MTF Daily Confirmation  — Konfirmasi trend harian
    19. Relative Strength IHSG  — Saham lebih kuat dari indeks
    20. IHSG Correlation        — Penalty saat market merah
    """

    def __init__(self) -> None:
        self.min_data_points  = 60
        self.min_volume_ratio = 0.3
        self.min_adx          = 20
        self.max_spread_pct   = 3.0

    # ------------------------------------------------------------------ #
    #  DATA FETCHING
    # ------------------------------------------------------------------ #
    def fetch_data(
        self,
        symbol: str,
        period: str = DATA_PERIOD,
        interval: str = DATA_INTERVAL,
    ) -> pd.DataFrame | None:
        """Fetch OHLCV 15m. Pakai '59d' bukan '2mo' — Yahoo batas 60 hari."""
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith(".JK") else symbol
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True)

            logger.info(f"[{symbol}] df.empty={df.empty}, len={len(df)}")
            if df.empty:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]

            if len(df) < self.min_data_points:
                return None
            return df
        except Exception as exc:
            logger.error(f"[{symbol}] fetch_data error: {exc}")
            return None

    def fetch_daily(self, symbol: str) -> pd.DataFrame | None:
        """Fetch data daily untuk MTF confirmation."""
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith(".JK") else symbol
            df = yf.download(ticker, period="6mo", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 20:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as exc:
            logger.warning(f"[{symbol}] fetch_daily error: {exc}")
            return None

    def fetch_ihsg(self) -> float | None:
        """Fetch % perubahan IHSG hari ini."""
        try:
            df = yf.download("^JKSE", period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            return round(
                (float(df["close"].iloc[-1]) - float(df["close"].iloc[-2]))
                / float(df["close"].iloc[-2]) * 100, 2
            )
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  STATIC HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _calc_vwap(df: pd.DataFrame) -> pd.Series:
        """VWAP harian — reset setiap hari."""
        d = df.copy()
        d["tp"]    = (d["high"] + d["low"] + d["close"]) / 3
        d["tp_vol"] = d["tp"] * d["volume"]
        d["date"]  = d.index.date
        return (
            d.groupby("date")
            .apply(lambda g: g["tp_vol"].cumsum() / g["volume"].cumsum())
            .reset_index(level=0, drop=True)
        )

    @staticmethod
    def _find_sr_levels(
        df: pd.DataFrame, lookback: int = 20
    ) -> tuple[float, float, list, list]:
        """Pivot-based S/R dengan 2-bar confirmation."""
        recent = df.iloc[-lookback - 4:]
        price  = float(df["close"].iloc[-1])
        sup, res = [], []

        for i in range(2, len(recent) - 2):
            lo = recent["low"].iloc[i]
            hi = recent["high"].iloc[i]
            if (lo < recent["low"].iloc[i-1] and lo < recent["low"].iloc[i-2]
                    and lo < recent["low"].iloc[i+1] and lo < recent["low"].iloc[i+2]):
                sup.append(round(float(lo), 0))
            if (hi > recent["high"].iloc[i-1] and hi > recent["high"].iloc[i-2]
                    and hi > recent["high"].iloc[i+1] and hi > recent["high"].iloc[i+2]):
                res.append(round(float(hi), 0))

        if not sup:
            sup = [round(float(recent["low"].min()), 0)]
        if not res:
            res = [round(float(recent["high"].max()), 0)]

        below = [s for s in sup if s < price]
        above = [r for r in res if r > price]
        return (
            max(below) if below else min(sup),
            min(above) if above else max(res),
            sorted(sup), sorted(res),
        )

    @staticmethod
    def _calc_best_entry(
        price: float, support: float, vwap: float, bb_lower: float
    ) -> dict:
        """Zona entry ideal: VWAP pullback / dekat support / lower BB."""
        candidates = {
            "market":  round(price, 0),
            "vwap":    round(vwap * 1.001, 0),
            "support": round(support * 1.005, 0),
            "bb_low":  round(bb_lower * 1.002, 0),
        }
        valid = {k: v for k, v in candidates.items() if price * 0.97 <= v <= price}
        if not valid:
            valid = {"market": round(price, 0)}
        best_key = max(valid, key=lambda k: valid[k])
        return {
            "best_entry":       int(valid[best_key]),
            "entry_type":       best_key,
            "entry_candidates": {k: int(v) for k, v in candidates.items()},
        }

    @staticmethod
    def _detect_candle_pattern(df: pd.DataFrame) -> tuple[str, int]:
        c = df.iloc[-1]
        p = df.iloc[-2]
        body        = abs(c["close"] - c["open"])
        rng         = c["high"] - c["low"]
        lower_wick  = min(c["close"], c["open"]) - c["low"]
        if rng == 0:
            return "", 0
        br = body / rng
        lwr = lower_wick / rng
        if lwr > 0.55 and br < 0.35 and c["close"] >= c["open"]:
            return "Bullish Hammer 🔨", 15
        if (c["close"] > c["open"] and p["close"] < p["open"]
                and c["open"] <= p["close"] and c["close"] >= p["open"]):
            return "Bullish Engulfing 🕯️", 20
        if len(df) >= 3:
            pp = df.iloc[-3]
            if (pp["close"] < pp["open"] and br < 0.3 and c["close"] > c["open"]
                    and c["close"] > (pp["open"] + pp["close"]) / 2):
                return "Morning Star ⭐", 20
        if br > 0.85 and c["close"] > c["open"]:
            return "Marubozu Bullish 💹", 10
        return "", 0

    @staticmethod
    def _detect_bb_squeeze(df: pd.DataFrame) -> tuple[bool, bool]:
        bw = df["bb_bandwidth"].dropna()
        if len(bw) < 10:
            return False, False
        squeeze     = bw.iloc[-1] < bw.iloc[-20:].mean() * 0.5
        touch_lower = df["close"].iloc[-1] <= df["bb_lower"].iloc[-1] * 1.005
        return bool(squeeze), bool(touch_lower)

    @staticmethod
    def _detect_rsi_divergence(df: pd.DataFrame, lookback: int = 10) -> bool:
        try:
            rec = df.iloc[-lookback:]
            idx = rec["close"].idxmin()
            if df["close"].iloc[-1] <= float(rec["close"].min()) * 1.01:
                return float(df["rsi"].iloc[-1]) > float(rec.loc[idx, "rsi"]) * 1.05
        except Exception:
            pass
        return False

    @staticmethod
    def _market_condition(df: pd.DataFrame) -> str:
        ema20 = df["ema20"].dropna()
        if len(ema20) < 10:
            return "sideways"
        slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100
        if slope > 0.5:
            return "trending_up"
        if slope < -0.5:
            return "trending_down"
        return "sideways"

    @staticmethod
    def _mtf_confirmation(df_daily: pd.DataFrame | None) -> tuple[str, int]:
        """Konfirmasi trend dari timeframe harian."""
        if df_daily is None or len(df_daily) < 20:
            return "unknown", 0
        ema20d = df_daily["close"].ewm(span=20).mean()
        ema50d = df_daily["close"].ewm(span=50).mean()
        price  = float(df_daily["close"].iloc[-1])
        if ema20d.iloc[-1] > ema50d.iloc[-1] and price > ema20d.iloc[-1]:
            return "daily_uptrend", 20
        if ema20d.iloc[-1] < ema50d.iloc[-1]:
            return "daily_downtrend", -20
        return "daily_neutral", 0

    @staticmethod
    def _relative_strength(df: pd.DataFrame, ihsg_chg: float | None) -> tuple[bool, int]:
        if ihsg_chg is None:
            return False, 0
        stk_chg = (
            (float(df["close"].iloc[-1]) - float(df["close"].iloc[-2]))
            / float(df["close"].iloc[-2]) * 100
        )
        if stk_chg > ihsg_chg + 0.5:
            return True, 15
        if stk_chg < ihsg_chg - 0.5:
            return False, -10
        return False, 0

    @staticmethod
    def _is_chasing(df: pd.DataFrame) -> bool:
        """Return True jika harga sudah naik >3% dari open hari ini."""
        try:
            today_open = float(df["open"].iloc[0])
            current    = float(df["close"].iloc[-1])
            return (current - today_open) / today_open * 100 > 3.0
        except Exception:
            return False

    @staticmethod
    def _spread_proxy(df: pd.DataFrame) -> float:
        latest = df.iloc[-1]
        if float(latest["close"]) == 0:
            return 0.0
        return (float(latest["high"]) - float(latest["low"])) / float(latest["close"]) * 100

    # ------------------------------------------------------------------ #
    #  MAIN ANALYZE
    # ------------------------------------------------------------------ #
    def analyze(
        self,
        symbol: str,
        threshold: int = 75,
        strict_filter: bool = True,
        ihsg_chg: float | None = None,
    ) -> dict | None:
        df = self.fetch_data(symbol)
        if df is None:
            logger.info(f"[{symbol}] fetch_data return None")
            return None

        # ── Indikator ──────────────────────────────────────────────────
        df["ema20"] = ta.trend.ema_indicator(df["close"], window=20)
        df["ema50"] = ta.trend.ema_indicator(df["close"], window=50)
        df["rsi"]   = ta.momentum.rsi(df["close"], window=14)

        stoch = ta.momentum.StochasticOscillator(
            df["high"], df["low"], df["close"], window=14, smooth_window=3)
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

        macd = ta.trend.MACD(df["close"], window_fast=12, window_slow=26, window_sign=9)
        df["macd"]        = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"]   = macd.macd_diff()

        df["atr"] = ta.volatility.average_true_range(
            df["high"], df["low"], df["close"], window=14)

        df["vol_ma"]    = df["volume"].rolling(window=20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_ma"].replace(0, np.nan)

        try:
            df["vwap"] = self._calc_vwap(df)
        except Exception:
            df["vwap"] = df["close"]

        bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_upper"]     = bb.bollinger_hband()
        df["bb_lower"]     = bb.bollinger_lband()
        df["bb_mid"]       = bb.bollinger_mavg()
        df["bb_bandwidth"] = bb.bollinger_wband()
        df["bb_pct"]       = bb.bollinger_pband()

        adx_ind    = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"]     = adx_ind.adx()
        df["adx_pos"] = adx_ind.adx_pos()
        df["adx_neg"] = adx_ind.adx_neg()

        df["obv"]    = ta.volume.on_balance_volume(df["close"], df["volume"])
        df["obv_ma"] = df["obv"].rolling(window=20).mean()

        logger.info(f"[{symbol}] sebelum dropna: {len(df)} rows")
        df = df.dropna()
        logger.info(f"[{symbol}] setelah dropna: {len(df)} rows")

        if df.empty:
            return None

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        # ── Pre-filter Gates ───────────────────────────────────────────
        vol_ratio = float(latest["vol_ratio"])
        adx       = float(latest["adx"])
        spread    = self._spread_proxy(df)

        if strict_filter:
            if vol_ratio < self.min_volume_ratio:
                logger.info(f"[{symbol}] GATE vol_ratio={vol_ratio:.2f}")
                return None
            if float(latest["volume"]) < MIN_VOLUME_ABS:
                logger.info(f"[{symbol}] GATE abs_volume={float(latest['volume']):.0f}")
                return None
            if threshold > 0 and adx < self.min_adx:
                logger.info(f"[{symbol}] GATE adx={adx:.1f}")
                return None
            if spread > self.max_spread_pct:
                logger.info(f"[{symbol}] GATE spread={spread:.1f}%")
                return None
            if self._is_chasing(df):
                logger.info(f"[{symbol}] GATE anti-chasing")
                return None

        # ── Scoring ────────────────────────────────────────────────────
        score, reasons = 0, []

        # 1. EMA Trend
        if latest["ema20"] > latest["ema50"]:
            score += 20; reasons.append("Uptrend EMA20>50")

        # 2. Price vs EMA20
        if latest["close"] > latest["ema20"]:
            score += 15; reasons.append("Harga > EMA20")

        # 3. RSI
        rsi = float(latest["rsi"])
        if 30 <= rsi <= 45:
            score += 30; reasons.append(f"RSI Rebound ({rsi:.0f})")
        elif 45 < rsi <= 60:
            score += 15
        elif rsi > 70:
            score -= 10

        # 4. Stochastic
        sk = float(latest["stoch_k"])
        sd = float(latest["stoch_d"])
        if sk < 25 and sk > sd:
            score += 20; reasons.append(f"Stoch Bullish Cross ({sk:.0f})")
        elif sk < 40 and sk > sd:
            score += 10

        # 5. MACD
        if float(latest["macd"]) > float(latest["macd_signal"]) and float(prev["macd"]) <= float(prev["macd_signal"]):
            score += 20; reasons.append("MACD Golden Cross")
        elif float(latest["macd"]) > float(latest["macd_signal"]):
            score += 10; reasons.append("MACD Bullish")
        if float(latest["macd_hist"]) > 0 and float(latest["macd_hist"]) > float(prev["macd_hist"]):
            score += 5

        # 6. Volume
        if vol_ratio > 2.0:
            score += 25; reasons.append(f"Volume Spike {vol_ratio:.1f}x")
        elif vol_ratio > 1.5:
            score += 15; reasons.append(f"Volume Naik {vol_ratio:.1f}x")

        # 7. Candlestick
        pname, pscore = self._detect_candle_pattern(df)
        if pscore > 0:
            score += pscore; reasons.append(pname)

        # 8. Market Condition Multiplier
        market = self._market_condition(df)
        if market == "trending_up":
            score = int(score * 1.1)
        elif market == "sideways":
            score = int(score * 0.85)
        elif market == "trending_down":
            score = int(score * 0.70)

        # 9. VWAP
        if float(latest["close"]) > float(latest["vwap"]):
            score += 20; reasons.append("Harga > VWAP 📊")
        elif float(latest["close"]) < float(latest["vwap"]) * 0.99:
            score -= 10

        # 10. Bollinger Bands
        is_squeeze, touch_lower = self._detect_bb_squeeze(df)
        if is_squeeze:
            score += 15; reasons.append("BB Squeeze 🔥")
        if touch_lower:
            score += 15; reasons.append("BB Lower Touch")

        # 11. ADX
        if adx > 35:
            score += 15; reasons.append(f"Trend Kuat ADX {adx:.0f}")
        elif adx > 25:
            score += 8
        if float(latest["adx_pos"]) > float(latest["adx_neg"]):
            score += 10; reasons.append("+DI > -DI Bullish")

        # 12. OBV
        obv_rising = float(latest["obv"]) > float(latest["obv_ma"])
        if obv_rising and float(latest["close"]) > float(prev["close"]):
            score += 15; reasons.append("OBV Konfirmasi ✅")
        elif not obv_rising and float(latest["close"]) > float(prev["close"]):
            score -= 10

        # 13. Support & Resistance
        support, resistance, _, _ = self._find_sr_levels(df)
        price_now     = float(latest["close"])
        near_support  = price_now <= support * 1.02
        near_resist   = price_now >= resistance * 0.98
        if near_support:
            score += 15; reasons.append("Dekat Support 🛡️")
        if near_resist:
            score -= 10

        # 14. Gap Detection
        change_pct = round(
            (float(latest["close"]) - float(prev["close"])) / float(prev["close"]) * 100, 2)
        if change_pct > 1.5:
            score += 10; reasons.append(f"Gap Up {change_pct}%")
        elif 0.5 < change_pct < 1.5:
            score += 5
        elif change_pct < -2.0:
            score -= 15

        # 15. RSI Divergence
        if self._detect_rsi_divergence(df):
            score += 20; reasons.append("RSI Divergence Bullish 🔄")

        # 16-17 sudah handle di pre-filter gates (anti-chasing, spread)

        # 18. MTF Daily Confirmation
        df_daily = self.fetch_daily(symbol)
        mtf_trend, mtf_score = self._mtf_confirmation(df_daily)
        score += mtf_score
        if mtf_trend == "daily_uptrend":
            reasons.append("MTF Uptrend ✅")
        elif mtf_trend == "daily_downtrend":
            reasons.append("MTF Downtrend ⚠️")

        # 19. Relative Strength vs IHSG
        rs_stronger, rs_score = self._relative_strength(df, ihsg_chg)
        score += rs_score
        if rs_stronger:
            reasons.append("RS > IHSG 💪")

        # 20. IHSG Correlation penalty
        if ihsg_chg is not None and ihsg_chg < -1.5:
            score = int(score * 0.75)
            logger.info(f"[{symbol}] IHSG penalty applied: {ihsg_chg}%")

        logger.info(
            f"[{symbol}] score={score}, threshold={threshold}, "
            f"market={market}, adx={adx:.1f}, mtf={mtf_trend}"
        )

        if score < threshold:
            logger.info(f"[{symbol}] TIDAK LOLOS threshold ({score} < {threshold})")
            return None

        # ── Entry / TP / SL Professional Grade ────────────────────────
        price    = round(float(latest["close"]), 2)
        atr      = round(float(latest["atr"]), 2)
        vwap_val = round(float(latest["vwap"]), 0)
        bb_lower = round(float(latest["bb_lower"]), 0)

        entry_data = self._calc_best_entry(price, support, vwap_val, bb_lower)
        best_entry = entry_data["best_entry"]
        entry_type = entry_data["entry_type"]

        # SL — swing low - 0.5% buffer vs ATR; ambil yang lebih ketat (lebih tinggi)
        sl = int(max(round(support * 0.995, 0), round(price - atr * 1.5, 0)))
        sl_distance = price - sl if price - sl > 0 else price * 0.015

        # TP1 — resistance terdekat (konservatif)
        tp1 = int(max(round(resistance * 0.995, 0), round(price + atr * 1.5, 0)))

        # TP2 — Fibonacci 1.618 extension
        rec20     = df.iloc[-20:]
        fib_tp2   = round(float(rec20["low"].min()) + (float(rec20["high"].max()) - float(rec20["low"].min())) * 1.618, 0)
        tp2       = int(fib_tp2) if fib_tp2 > tp1 else int(tp1 * 1.03)

        e2sl = best_entry - sl
        rrr  = round((tp1 - best_entry) / e2sl, 2) if e2sl > 0 else 0

        alasan = " + ".join(reasons) if reasons else "Momentum Bullish"

        return {
            "symbol":            symbol.replace(".JK", ""),
            "signal_timestamp":  latest.name.isoformat(),
            "price":             int(price),
            "best_entry":        best_entry,
            "entry_type":        entry_type,
            "tp1":               tp1,
            "tp2":               tp2,
            "sl":                sl,
            "rrr":               rrr,
            "atr":               atr,
            "support":           int(support),
            "resistance":        int(resistance),
            "adx":               round(adx, 1),
            "vwap":              int(vwap_val),
            "bb_pct":            round(float(latest["bb_pct"]), 2),
            "bb_lower":          int(bb_lower),
            "rsi":               round(rsi, 1),
            "stoch_k":           round(sk, 1),
            "macd_hist":         round(float(latest["macd_hist"]), 4),
            "obv_ok":            obv_rising,
            "near_support":      near_support,
            "volume_ratio":      round(vol_ratio, 1),
            "volume_real":       int(latest["volume"]),
            "score":             score,
            "change_pct":        change_pct,
            "market_cond":       market,
            "mtf_trend":         mtf_trend,
            "rs_stronger":       rs_stronger,
            "spread_pct":        round(spread, 2),
            "alasan":            alasan,
        }
