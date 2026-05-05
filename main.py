import logging
import pytz
from datetime import time
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults
from analyzer import StockAnalyzer
from notifier import TelegramFormatter
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, LQ45_SYMBOLS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IDXDayTraderBot:
    def __init__(self):
        self.analyzer = StockAnalyzer()
        self.tz = pytz.timezone('Asia/Jakarta')
        self.formatter = TelegramFormatter()

    # --- SCHEDULER JOBS ---
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Mencari sinyal pagi...")
        signals = []
        for sym in LQ45_SYMBOLS:
            res = self.analyzer.analyze(sym, threshold=75) # Filter ketat 75
            if res: signals.append(res)
        
        if signals:
            # Simpan signal pagi di bot_data untuk di-update nanti sore
            context.bot_data['morning_signals'] = signals
            msg = self.formatter.format_morning_signal(signals)
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Membuat update sore...")
        morning_signals = context.bot_data.get('morning_signals', [])
        if not morning_signals:
            return

        updates = []
        for s in morning_signals:
            # Cek harga terkini tanpa threshold
            res = self.analyzer.analyze(s['symbol'], threshold=0)
            if res:
                pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                updates.append({
                    'symbol': s['symbol'],
                    'current_price': res['price'],
                    'pnl': pnl
                })
        
        if updates:
            msg = self.formatter.format_afternoon_update(updates)
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')

    # --- COMMAND HANDLERS ---
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        intro = ("🤖 <b>IDX Day Trader Assistant</b>\n\n"
                 "Gunakan command berikut:\n"
                 "/signal - Rekomendasi pagi ini\n"
                 "/update - Status profit/loss sore\n"
                 "/detail &lt;kode&gt; - Analisa spesifik\n"
                 "/top - Saham teraktif\n"
                 "/help - Daftar bantuan\n\n"
                 "<i>Catatan: Bukan ajakan finansial.</i>")
        await update.message.reply_text(intro, parse_mode='HTML')

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔎 Menganalisa saham potensial, mohon tunggu...")
        signals = []
        for sym in LQ45_SYMBOLS:
            res = self.analyzer.analyze(sym, threshold=75)
            if res: signals.append(res)
        
        if signals:
            context.bot_data['morning_signals'] = signals
            msg = self.formatter.format_morning_signal(signals)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("Belum ada setup yang memenuhi kriteria (Skor > 75).")

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        signals = context.bot_data.get('morning_signals', [])
        if not signals:
            await update.message.reply_text("Belum ada sinyal pagi yang dikeluarkan hari ini.")
            return
            
        await update.message.reply_text("⏳ Menghitung Profit/Loss hari ini...")
        updates = []
        for s in signals:
            res = self.analyzer.analyze(s['symbol'], threshold=0)
            if res:
                pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                updates.append({'symbol': s['symbol'], 'current_price': res['price'], 'pnl': pnl})
                
        msg = self.formatter.format_afternoon_update(updates)
        await update.message.reply_text(msg, parse_mode='HTML')

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Format salah. Gunakan: /detail BBCA")
            return
            
        symbol = context.args[0].upper()
        res = self.analyzer.analyze(symbol, threshold=0)
        
        if res:
            msg = self.formatter.format_detail(res)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text(f"Data {symbol} tidak ditemukan atau kurang.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📊 Memindai seluruh LQ45...")
        all_data = []
        for sym in LQ45_SYMBOLS:
            res = self.analyzer.analyze(sym, threshold=0)
            if res: all_data.append(res)
            
        top_vol = sorted(all_data, key=lambda x: x['volume_ratio'], reverse=True)[:3]
        top_gainers = sorted(all_data, key=lambda x: x['change_pct'], reverse=True)[:3]
        
        msg = self.formatter.format_top(top_vol, top_gainers)
        await update.message.reply_text(msg, parse_mode='HTML')

    # --- MAIN RUNNER ---
    def run(self):
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        # Command Handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_start))
        app.add_handler(CommandHandler("signal", self.cmd_signal))
        app.add_handler(CommandHandler("update", self.cmd_update))
        app.add_handler(CommandHandler("detail", self.cmd_detail))
        app.add_handler(CommandHandler("top", self.cmd_top))

        # Schedulers - Senin s/d Jumat (0-4)
        jq = app.job_queue
        jq.run_daily(self.job_morning_signal, time(hour=9, minute=25), days=(0,1,2,3,4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=25), days=(0,1,2,3,4))

        logger.info("🚀 Bot siap menerima command dan menjalankan jadwal otomatis!")
        app.run_polling()

if __name__ == "__main__":
    bot = IDXDayTraderBot()
    bot.run()