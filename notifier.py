import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

class TelegramNotifier:
    def send_message(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data)
        except:
            pass

    def trade_alert(self, symbol, action, qty, price, confidence):
        message = f"""
🚨 <b>Rp4 Juta Bot TRADE</b>

📈 <b>{symbol}</b>
🎯 <b>{action} {qty:,} @ Rp{price:,.0f}</b>
🎯 Confidence: <b>{confidence:.0%}</b>
💰 Used: Rp{qty*price:,.0f} ({qty*price/4000000*100:.0f}%)
⏰ {pd.Timestamp.now().strftime('%H:%M WIB')}
        """
        self.send_message(message)

    def status_alert(self, balance, positions):
        message = f"""
📊 <b>DAILY STATUS</b>
💰 Balance: <b>Rp{balance:,.0f}</b>
📈 Positions: {len(positions)}
📉 Today P&L: <b>Rp{self.daily_pnl:,.0f}</b>
        """
        self.send_message(message)
