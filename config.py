import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# LQ45 High Liquidity
LQ45_SYMBOLS = [
    'ACES', 'ADRO', 'AKRA', 'AMMN', 'AMRT', 'ANTM', 'ARTO', 'ASII', 'BBCA', 'BBNI',
    'BBRI', 'BBTN', 'BELI', 'BMRI', 'BNBR', 'BREN', 'BRIS', 'BRMS', 'BRPT', 'BUMI',
    'CPIN', 'CUAN', 'DEWA', 'ENRG', 'ESSA', 'EXCL', 'GOTO', 'HRUM', 'ICBP', 'INCO',
    'INDF', 'INKP', 'INTP', 'ISAT', 'ITMG', 'JARR', 'JSMR', 'KLBF', 'LPKR', 'MAPI',
    'MAYA', 'MBMA', 'MDKA', 'MDIA', 'MEDC', 'MIKA', 'MPPA', 'MTEL', 'PANI', 'PGAS',
    'PGUN', 'PTBA', 'PTPP', 'SIDO', 'SILO', 'SMGR', 'SRAJ', 'SRTG', 'TEBE', 'TLKM',
    'TOWR', 'TPIA', 'UNTR', 'UNVR', 'VCOR', 'VIVA', 'VKTR'
]

# Trading Hours WIB
MARKET_OPEN = 9
MARKET_CLOSE = 15

HIGH_PROB_THRESHOLD = 75  # Score minimum
