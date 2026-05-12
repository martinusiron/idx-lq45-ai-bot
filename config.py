"""
config.py — Central configuration untuk IDX Day Trader Bot.
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
HIGH_PROB_THRESHOLD = int(os.getenv("HIGH_PROB_THRESHOLD", "75"))
MIN_RRR             = float(os.getenv("MIN_RRR", "1.3"))

# ── Analyzer Timeframe ────────────────────────────────────────────────────────
DATA_PERIOD   = os.getenv("DATA_PERIOD",   "59d")   # WAJIB <=59d untuk Yahoo 15m
DATA_INTERVAL = os.getenv("DATA_INTERVAL", "15m")

# ── Volume & Liquidity Filters ────────────────────────────────────────────────
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "0.3"))
MIN_VOLUME_ABS   = int(os.getenv("MIN_VOLUME_ABS",   "500000"))   # 500rb lembar/candle
MIN_ADX          = int(os.getenv("MIN_ADX",          "20"))
MAX_SPREAD_PCT   = float(os.getenv("MAX_SPREAD_PCT", "3.0"))

# ── Risk Management ───────────────────────────────────────────────────────────
ACCOUNT_SIZE             = float(os.getenv("ACCOUNT_SIZE",             "100000000"))  # Rp 100 juta default
RISK_PER_TRADE_PCT       = float(os.getenv("RISK_PER_TRADE_PCT",       "0.005"))      # 0.5% per trade
DAILY_MAX_LOSS_R         = float(os.getenv("DAILY_MAX_LOSS_R",         "1.5"))        # Stop trading di -1.5R/hari
MAX_OPEN_POSITIONS       = int(os.getenv("MAX_OPEN_POSITIONS",         "3"))          # Maks 3 posisi bersamaan
LOT_SIZE                 = int(os.getenv("LOT_SIZE",                   "100"))        # IDX: 1 lot = 100 lembar
BUY_FEE_PCT              = float(os.getenv("BUY_FEE_PCT",              "0.0015"))     # 0.15% broker buy
SELL_FEE_PCT             = float(os.getenv("SELL_FEE_PCT",             "0.0025"))     # 0.25% broker sell
SLIPPAGE_PCT             = float(os.getenv("SLIPPAGE_PCT",             "0.0005"))     # 0.05% slippage estimasi
PARTIAL_EXIT_RATIO       = float(os.getenv("PARTIAL_EXIT_RATIO",       "0.5"))        # Tutup 50% di TP1
RISK_OFF_MODE            = os.getenv("RISK_OFF_MODE",                  "reduce")      # reduce | block
RISK_OFF_SIZE_MULTIPLIER = float(os.getenv("RISK_OFF_SIZE_MULTIPLIER", "0.5"))        # Ukuran 50% saat risk-off
