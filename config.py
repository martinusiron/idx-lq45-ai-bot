import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TIMEZONE         = os.getenv('TIMEZONE', 'Asia/Jakarta')

# ── LQ45 Universe ─────────────────────────────────────────────────────────────
# Update: hapus simbol yang tidak lagi di LQ45 aktif (BNBR, PGUN, SRAJ, VKTR, JARR)
# dan pastikan sesuai dengan komposisi LQ45 terbaru BEI
LQ45_SYMBOLS = [
    'ACES', 'ADRO', 'AKRA', 'AMMN', 'AMRT', 'ANTM', 'ARTO', 'ASII', 'BBCA', 'BBNI',
    'BBRI', 'BBTN', 'BELI', 'BMRI', 'BREN', 'BRIS', 'BRMS', 'BRPT', 'BUMI',
    'CPIN', 'CUAN', 'DEWA', 'ENRG', 'ESSA', 'EXCL', 'GOTO', 'HRUM', 'ICBP', 'INCO',
    'INDF', 'INKP', 'INTP', 'ISAT', 'ITMG', 'JSMR', 'KLBF', 'LPKR', 'MAPI',
    'MAYA', 'MBMA', 'MDKA', 'MDIA', 'MEDC', 'MIKA', 'MPPA', 'MTEL', 'PANI', 'PGAS',
    'PTBA', 'PTPP', 'SIDO', 'SILO', 'SMGR', 'SRTG', 'TEBE', 'TLKM',
    'TOWR', 'TPIA', 'UNTR', 'UNVR', 'VCOR', 'VIVA',
]

# ── Scoring & Filter ──────────────────────────────────────────────────────────
HIGH_PROB_THRESHOLD = 75        # Skor minimum untuk sinyal morning
DETAIL_THRESHOLD    = 0         # Tidak ada filter untuk /detail dan /top

# ── Risk Management ───────────────────────────────────────────────────────────
# Semua TP/SL sekarang berbasis ATR (di analyzer.py), parameter ini sebagai fallback
MIN_TP_PCT  = 2.0               # TP minimum 2% dari entry
MIN_SL_PCT  = 1.5               # SL minimum 1.5% dari entry
MIN_RRR     = 1.3               # Risk-Reward Ratio minimum 1:1.3
ACCOUNT_SIZE = float(os.getenv('ACCOUNT_SIZE', 100_000_000))
RISK_PER_TRADE_PCT = float(os.getenv('RISK_PER_TRADE_PCT', 0.005))
DAILY_MAX_LOSS_R = float(os.getenv('DAILY_MAX_LOSS_R', 1.5))
MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', 3))
LOT_SIZE = int(os.getenv('LOT_SIZE', 100))
BUY_FEE_PCT = float(os.getenv('BUY_FEE_PCT', 0.0015))
SELL_FEE_PCT = float(os.getenv('SELL_FEE_PCT', 0.0025))
SLIPPAGE_PCT = float(os.getenv('SLIPPAGE_PCT', 0.0005))
PARTIAL_EXIT_RATIO = float(os.getenv('PARTIAL_EXIT_RATIO', 0.5))
RISK_OFF_MODE = os.getenv('RISK_OFF_MODE', 'reduce').lower()
RISK_OFF_SIZE_MULTIPLIER = float(os.getenv('RISK_OFF_SIZE_MULTIPLIER', 0.5))

# ── Volume Filter ─────────────────────────────────────────────────────────────
MIN_VOLUME_ABS = 5_000_000      # Minimum 5 juta lembar per candle — filter saham tipis

# ── Analyzer Timeframe ────────────────────────────────────────────────────────
DATA_PERIOD   = '59d'           # MAKS 59 hari — Yahoo Finance batasi 15m data hanya 60 hari terakhir
DATA_INTERVAL = '15m'           # Interval 15 menit (sesuai untuk day trading IDX)

# ── Persistence ───────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv('SUPABASE_URL') or os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
DATABASE_URL = os.getenv('SUPABASE_DB_URL') or os.getenv('DATABASE_URL')
DB_PATH = os.getenv('DB_PATH', 'data/trading_journal.db')
