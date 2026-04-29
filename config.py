import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# LQ45 High Liquidity
LQ45_SYMBOLS = [
    'ACES', 'ADRO', 'AKRA', 'AMRT', 'AMMN', 'ANTM', 'ARTO', 'ASII', 'BBCA', 'BBNI',
    'BBRI', 'BBTN', 'BMRI', 'BRIS', 'BRPT', 'CPIN', 'ESSA', 'EXCL', 'GOTO', 'HRUM',
    'ICBP', 'INCO', 'INDF', 'INKP', 'INTP', 'ISAT', 'ITMG', 'JSMR', 'KLBF', 'MAPI',
    'MBMA', 'MDKA', 'MEDC', 'MIKA', 'MTEL', 'PGAS', 'PTBA', 'PTPP', 'SIDO', 'SMGR',
    'TLKM', 'TPIA', 'UNTR', 'UNVR', 'VCOR'
]

# Trading Hours WIB
MARKET_OPEN = 9
MARKET_CLOSE = 15

HIGH_PROB_THRESHOLD = 75  # Score minimum
