import requests
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import schedule
import os
from config import *
from strategies import ensemble_signal
from risk_manager import ConservativeRiskManager
from notifier import TelegramNotifier
from ml_predictor import SimpleMLPredictor

class LQ45AIBot:
    def __init__(self):
        self.notifier = TelegramNotifier()
        self.risk_mgr = ConservativeRiskManager(INITIAL_BALANCE)
        self.ml = SimpleMLPredictor()
        self.positions = {}
        self.trades_today = []

        print("🤖 Rp4 Juta LQ45 AI Bot Starting...")
        self.notifier.send_message("🚀 <b>Rp4 Juta Bot LIVE!</b>")

    def is_market_open(self):
        now = datetime.now()
        return 9 <= now.hour < 15 and now.weekday() < 5

    def get_quote(self, symbol):
        url = f"https://api.ipot.or.id/marketdata/quote/{symbol}"
        headers = {'X-API-KEY': IPOT_API_KEY, 'APP-ID': IPOT_APP_ID}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            return {'last_price': data.get('last_price', 0), 'volume': data.get('volume', 0)}
        except:
            return None

    def get_data(self, symbol, period='1mo'):
        import yfinance as yf
        try:
            df = yf.download(f"{symbol}.JK", period=period, progress=False)
            return df if not df.empty else None
        except:
            return None

    def scan_stocks(self):
        if not self.is_market_open():
            return

        print("🔍 Scanning LQ45...")
        for symbol in LQ45_SYMBOLS:
            df = self.get_data(symbol)
            if df is None or len(df) < 30:
                continue

            # ML Prediction
            ml_prob = self.ml.predict(df)

            # Technical Signal
            signal = ensemble_signal(df)

            # High confidence only
            if signal == 'BUY' and ml_prob > 0.65:
                self.execute_trade(symbol, df, ml_prob)

        self.notifier.status_alert(self.risk_mgr.balance, self.positions)

    def execute_trade(self, symbol, df, ml_prob):
        if not self.risk_mgr.can_trade():
            return

        quote = self.get_quote(symbol)
        if not quote:
            return

        price = quote['last_price']
        qty = self.risk_mgr.safe_position_size(price)

        # SIMULATION MODE (ganti ke real order nanti)
        print(f"📈 SIM: BUY {symbol} {qty} @ Rp{price:,} (ML: {ml_prob:.0%})")
        self.notifier.trade_alert(symbol, 'BUY', qty, price, ml_prob)

        # Update portfolio
        self.risk_mgr.positions[symbol] = {'qty': qty, 'price': price}
        self.trades_today.append({'symbol': symbol, 'qty': qty, 'price': price})

    def run(self):
        # Train ML
        for symbol in LQ45_SYMBOLS[:3]:
            df = self.get_data(symbol, '2y')
            if df is not None:
                self.ml.train(symbol)

        # Schedule
        schedule.every(15).minutes.do(self.scan_stocks)
        schedule.every().day.at("15:05").do(self.daily_report)

        while True:
            schedule.run_pending()
            time.sleep(30)

    def daily_report(self):
        total_trades = len(self.trades_today)
        self.notifier.send_message(f"📊 <b>Daily Report</b>\nTrades: {total_trades}")

if __name__ == "__main__":
    bot = LQ45AIBot()
    bot.run()
