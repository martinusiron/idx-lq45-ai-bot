import asyncio
import logging
from datetime import datetime

import pytz
import time
from analyzer import StockAnalyzer
from notifier import TelegramNotifier
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, LQ45_SYMBOLS, HIGH_PROB_THRESHOLD, MARKET_OPEN, MARKET_CLOSE

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LQ45SignalBot:
    def __init__(self):
        self.analyzer = StockAnalyzer()
        self.notifier = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        self.symbols = LQ45_SYMBOLS
        logger.info("🚀 LQ45 Signal Bot initialized")

    def is_market_open(self):
        # Change: Force Jakarta timezone
        tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz)
        return MARKET_OPEN <= now.hour < MARKET_CLOSE and now.weekday() < 5

    async def scan_market(self):
        """Main scanning logic"""
        if not self.is_market_open():
            logger.info("Outside trading hours")
            return

        logger.info("🔍 Scanning LQ45 symbols...")
        high_prob_signals = []

        for symbol in self.symbols:
            signal = self.analyzer.analyze(symbol)
            if signal:
                high_prob_signals.append(signal)
                logger.info(f"High prob: {signal['symbol']} ({signal['score']})")

        if high_prob_signals:
            await self.notifier.send_signals(high_prob_signals)
        else:
            logger.info("No high probability signals")

    async def startup(self):
        """Send startup message"""
        await self.notifier.startup_message()

    def run_scheduler(self):
        """Schedule scanning"""
        schedule.every(15).minutes.do(lambda: asyncio.create_task(self.scan_market()))
        logger.info("Scheduler started - scanning every 15 minutes")

        while True:
            schedule.run_pending()
            time.sleep(1)

    async def run(self):
        """Main entry point"""
        try:
            await self.startup()
            logger.info("Bot running...")

            while True:
                try:
                    if self.is_market_open():
                        await self.scan_market()
                    else:
                        logger.info("Market closed. Sleeping...")

                    # Sleep for 15 minutes (900 seconds)
                    await asyncio.sleep(900)
                except Exception as e:
                    logger.error(f"Loop error: {e}")
                    await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")

if __name__ == "__main__":
    bot = LQ45SignalBot()
    asyncio.run(bot.run())
