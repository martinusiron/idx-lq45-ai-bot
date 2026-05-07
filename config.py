import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

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

# ── Trading Hours (WIB / UTC+7) ───────────────────────────────────────────────
MARKET_OPEN  = 9    # 09:00 WIB — Sesi 1 dibuka
MARKET_CLOSE = 15   # 15:00 WIB — Sesi 2 tutup (sebelum matching)

# ── Scoring & Filter ──────────────────────────────────────────────────────────
HIGH_PROB_THRESHOLD = 75        # Skor minimum untuk sinyal morning
DETAIL_THRESHOLD    = 0         # Tidak ada filter untuk /detail dan /top

# ── Risk Management ───────────────────────────────────────────────────────────
# Semua TP/SL sekarang berbasis ATR (di analyzer.py), parameter ini sebagai fallback
MIN_TP_PCT  = 2.0               # TP minimum 2% dari entry
MIN_SL_PCT  = 1.5               # SL minimum 1.5% dari entry
MIN_RRR     = 1.3               # Risk-Reward Ratio minimum 1:1.3

# ── Volume Filter ─────────────────────────────────────────────────────────────
MIN_VOLUME_ABS = 5_000_000      # Minimum 5 juta lembar per candle — filter saham tipis

# ── Analyzer Timeframe ────────────────────────────────────────────────────────
DATA_PERIOD   = '2mo'           # 2 bulan data untuk warm-up indikator
DATA_INTERVAL = '15m'           # Interval 15 menit (sesuai untuk day trading IDX)