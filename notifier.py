from telegram import Bot
import asyncio
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def startup_message(self):
        message = """
🚀 <b>LQ45 AI Signal Bot LIVE!</b>

⏰ Trading Hours: 09:00-15:00 WIB
📡 Scan Frequency: Every 15 minutes
🎯 High Prob Threshold: 75+
📱 Manual trades via Stockbit app

💰 Rp4 Juta Strategy Ready!
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info("Startup message sent")
        except Exception as e:
            logger.error(f"Startup message failed: {e}")

    async def send_signals(self, signals):
        if not signals:
            return

        message = f"🚨 <b>HIGH PROBABILITY ({len(signals)})</b>\n\n"

        for signal in signals:
            message += f"📈 <b>{signal['symbol']}</b>\n"
            message += f"💰 Rp{signal['price']:,} | <b>Score: {signal['score']}</b>\n"
            message += f"📊 RSI: {signal['rsi']} | Vol: {signal['volume_ratio']}x | Δ{signal['change_pct']:.1f}%\n"
            message += f"⏰ {pd.Timestamp.now().strftime('%H:%M WIB')}\n\n"

        message += "💡 <b>ACTION: Manual BUY di Stockbit!</b>"

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info(f"Signals alert sent: {len(signals)}")
        except Exception as e:
            logger.error(f"Alert failed: {e}")
