import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
IPOT_API_KEY = os.getenv('IPOT_API_KEY')
IPOT_APP_ID = os.getenv('IPOT_APP_ID')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Rp4 Juta Settings
INITIAL_BALANCE = int(os.getenv('INITIAL_BALANCE', '4000000'))
RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE', '0.01'))

# LQ45 Focus (High liquidity, low price)
LQ45_SYMBOLS = ['BBRI', 'BRIS', 'BBNI', 'BMRI', 'BBCA', 'TLKM']

MARKET_HOURS = {'open': 9, 'close': 15}
