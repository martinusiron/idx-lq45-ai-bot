import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL      = os.getenv('SUPABASE_URL', 'https://bdlmltxzvlxbxzyyvpuw.supabase.co')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')
SUPABASE_KEY      = os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Untuk bypass RLS

# ── LQ45 Universe ─────────────────────────────────────────────────────────────
LQ45_SYMBOLS = [
    'ACES', 'ADRO', 'AKRA', 'AMMN', 'AMRT', 'ANTM', 'ARTO', 'ASII', 'BBCA', 'BBNI',
    'BBRI', 'BBTN', 'BELI', 'BMRI', 'BREN', 'BRIS', 'BRMS', 'BRPT', 'BUMI',
    'CPIN', 'CUAN', 'DEWA', 'ENRG', 'ESSA', 'EXCL', 'GOTO', 'HRUM', 'ICBP', 'INCO',
    'INDF', 'INKP', 'INTP', 'ISAT', 'ITMG', 'JSMR', 'KLBF', 'LPKR', 'MAPI',
    'MAYA', 'MBMA', 'MDKA', 'MDIA', 'MEDC', 'MIKA', 'MPPA', 'MTEL', 'PANI', 'PGAS',
    'PTBA', 'PTPP', 'SIDO', 'SILO', 'SMGR', 'SRTG', 'TEBE', 'TLKM',
    'TOWR', 'TPIA', 'UNTR', 'UNVR', 'VIVA',
]

# ── Trading Hours (WIB) ───────────────────────────────────────────────────────
MARKET_OPEN  = 9
MARKET_CLOSE = 15

# ── Scoring & Filter ──────────────────────────────────────────────────────────
HIGH_PROB_THRESHOLD = 75
DETAIL_THRESHOLD    = 0
MIN_RRR             = 1.3

# ── Risk Management Default ───────────────────────────────────────────────────
DEFAULT_MODAL    = 10_000_000   # Rp 10 juta (bisa diubah user via /setmodal)
DEFAULT_RISK_PCT = 1.0          # Risk 1% per trade

# ── Volume & Likuiditas ───────────────────────────────────────────────────────
MIN_VOLUME_RATIO = 0.3
MIN_ADX          = 20
MAX_SPREAD_PCT   = 3.0

# ── Analyzer Timeframe ────────────────────────────────────────────────────────
DATA_PERIOD   = '59d'
DATA_INTERVAL = '15m'
