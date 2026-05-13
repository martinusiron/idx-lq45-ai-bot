"""
config.py — Central configuration untuk IDX Swing Trader Bot.
Semua parameter diambil dari environment variables (.env).
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
GOAPI_API_KEY    = os.getenv("GOAPI_API_KEY")

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL              = os.getenv("SUPABASE_URL", "https://bdlmltxzvlxbxzyyvpuw.supabase.co")
SUPABASE_ANON_KEY         = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ── Database (Postgres DSN — opsional, fallback ke Supabase lalu SQLite) ──────
DATABASE_URL = os.getenv("DATABASE_URL")          # postgresql://user:pass@host/db
DB_PATH      = os.getenv("DB_PATH", "data/trading.db")  # SQLite fallback path

# ── LQ45 Universe ─────────────────────────────────────────────────────────────
LQ45_SYMBOLS = [
    "ACES", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BELI", "BMRI", "BREN", "BRIS", "BRMS", "BRPT", "BUMI",
    "CPIN", "CUAN", "DEWA", "ENRG", "ESSA", "EXCL", "GOTO", "HRUM", "ICBP", "INCO",
    "INDF", "INKP", "INTP", "ISAT", "ITMG", "JSMR", "KLBF", "LPKR", "MAPI",
    "MAYA", "MBMA", "MDKA", "MDIA", "MEDC", "MIKA", "MPPA", "MTEL", "PANI", "PGAS",
    "PTBA", "PTPP", "SIDO", "SILO", "SMGR", "SRTG", "TEBE", "TLKM",
    "TOWR", "TPIA", "UNTR", "UNVR", "VIVA",
]

# ── Timezone ──────────────────────────────────────────────────────────────────
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jakarta")

# ── Signal Scoring ────────────────────────────────────────────────────────────
# Swing Trading v5: 24 indikator, max score ~300+
# Threshold 120 (sebelumnya 75 untuk day trading 20 ind.)
HIGH_PROB_THRESHOLD       = int(os.getenv("HIGH_PROB_THRESHOLD",       "120")) # Main signal
WATCHLIST_ALERT_THRESHOLD = int(os.getenv("WATCHLIST_ALERT_THRESHOLD", "100")) # Watchlist notif
MIN_RRR                   = float(os.getenv("MIN_RRR",                  "1.5")) # Swing RRR


# ── Analyzer Timeframe ────────────────────────────────────────────────────────
# Swing Trading: gunakan data harian (1D) dari GoAPI
# 15m tidak cocok untuk swing karena yfinance delay ~15 menit
DATA_PERIOD   = os.getenv("DATA_PERIOD",   "2y")   # 2 tahun data harian
DATA_INTERVAL = os.getenv("DATA_INTERVAL", "1d")   # Daily candle

# ── Swing Trading Parameters ──────────────────────────────────────────────────
SWING_HOLD_DAYS          = int(os.getenv("SWING_HOLD_DAYS",     "5"))    # Target hold 5 hari
SWING_ATR_SL_MULTIPLIER  = float(os.getenv("SWING_ATR_SL",      "2.0")) # SL = 2x ATR
SWING_ATR_TP1_MULTIPLIER = float(os.getenv("SWING_ATR_TP1",     "2.5")) # TP1 = 2.5x ATR
SWING_ATR_TP2_MULTIPLIER = float(os.getenv("SWING_ATR_TP2",     "4.0")) # TP2 = 4x ATR
SWING_ANTI_CHASE_PCT     = float(os.getenv("SWING_ANTI_CHASE",  "7.0")) # Jangan kejar jika naik >7% dari low recent

# ── Volume & Liquidity Filters ────────────────────────────────────────────────
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "0.8"))     # Swing: volume minimal 80% rata-rata
MIN_VOLUME_ABS   = int(os.getenv("MIN_VOLUME_ABS",   "5000000"))   # 5 juta lembar/hari (swing)
MIN_ADX          = int(os.getenv("MIN_ADX",          "20"))
MAX_SPREAD_PCT   = float(os.getenv("MAX_SPREAD_PCT", "3.0"))

# ── Risk Management ───────────────────────────────────────────────────────────
ACCOUNT_SIZE             = float(os.getenv("ACCOUNT_SIZE",             "100000000"))  # Rp 100 juta default
RISK_PER_TRADE_PCT       = float(os.getenv("RISK_PER_TRADE_PCT",       "0.005"))      # 0.5% per trade
DAILY_MAX_LOSS_R         = float(os.getenv("DAILY_MAX_LOSS_R",         "1.5"))        # Stop trading di -1.5R/hari
MAX_OPEN_POSITIONS       = int(os.getenv("MAX_OPEN_POSITIONS",         "5"))          # Swing: maks 5 posisi
LOT_SIZE                 = int(os.getenv("LOT_SIZE",                   "100"))        # IDX: 1 lot = 100 lembar
BUY_FEE_PCT              = float(os.getenv("BUY_FEE_PCT",              "0.0015"))     # 0.15% broker buy
SELL_FEE_PCT             = float(os.getenv("SELL_FEE_PCT",             "0.0025"))     # 0.25% broker sell
SLIPPAGE_PCT             = float(os.getenv("SLIPPAGE_PCT",             "0.0005"))     # 0.05% slippage estimasi
PARTIAL_EXIT_RATIO       = float(os.getenv("PARTIAL_EXIT_RATIO",       "0.5"))        # Tutup 50% di TP1
RISK_OFF_MODE            = os.getenv("RISK_OFF_MODE",                  "reduce")      # reduce | block
RISK_OFF_SIZE_MULTIPLIER = float(os.getenv("RISK_OFF_SIZE_MULTIPLIER", "0.5"))        # Ukuran 50% saat risk-off
