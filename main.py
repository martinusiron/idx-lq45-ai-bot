import logging
import pytz
from datetime import time, datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults
from analyzer import StockAnalyzer
from notifier import TelegramFormatter
from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, LQ45_SYMBOLS,
    HIGH_PROB_THRESHOLD, MIN_RRR, MARKET_OPEN, MARKET_CLOSE
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IDXDayTraderBot:
    def __init__(self):
        self.analyzer  = StockAnalyzer()
        self.tz        = pytz.timezone('Asia/Jakarta')
        self.formatter = TelegramFormatter()

    # ------------------------------------------------------------------ #
    #  HELPER
    # ------------------------------------------------------------------ #
    def _is_market_hours(self) -> bool:
        """Cek apakah sekarang dalam jam bursa IDX (Senin–Jumat, 09:00–15:30 WIB)."""
        now = datetime.now(self.tz)
        if now.weekday() >= 5:          # Sabtu / Minggu
            return False
        return MARKET_OPEN <= now.hour < MARKET_CLOSE + 1

    def _scan_symbols(self, symbols: list[str], threshold: int) -> list[dict]:
        """
        Scan daftar simbol, kembalikan sinyal yang lolos threshold,
        diurutkan dari skor tertinggi.
        """
        results = []
        for sym in symbols:
            try:
                res = self.analyzer.analyze(sym, threshold=threshold)
                if res:
                    # Filter tambahan: buang sinyal dengan RRR di bawah minimum
                    if res.get('rrr', 0) >= MIN_RRR:
                        results.append(res)
            except Exception as e:
                logger.warning(f"[{sym}] Gagal dianalisa: {e}")
        return sorted(results, key=lambda x: x['score'], reverse=True)

    # ------------------------------------------------------------------ #
    #  SCHEDULER JOBS
    # ------------------------------------------------------------------ #
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌅 Job pagi: mencari sinyal...")
        try:
            signals = self._scan_symbols(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD)
            if signals:
                context.bot_data['morning_signals'] = signals
                msg = self.formatter.format_morning_signal(signals)
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML'
                )
                logger.info(f"Sinyal pagi dikirim: {len(signals)} saham lolos.")
            else:
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text="📭 Tidak ada setup yang memenuhi kriteria pagi ini (Skor ≥ 75 & RRR ≥ 1.3)."
                )
        except Exception as e:
            logger.error(f"job_morning_signal error: {e}")

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌇 Job sore: membuat update P/L...")
        try:
            morning_signals = context.bot_data.get('morning_signals', [])
            if not morning_signals:
                return

            updates = []
            for s in morning_signals:
                try:
                    res = self.analyzer.analyze(s['symbol'], threshold=0)
                    if res:
                        pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                        updates.append({
                            'symbol':        s['symbol'],
                            'current_price': res['price'],
                            'pnl':           pnl,
                        })
                except Exception as e:
                    logger.warning(f"[{s['symbol']}] Update sore error: {e}")

            if updates:
                msg = self.formatter.format_afternoon_update(updates)
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML'
                )
            # Reset sinyal setelah update sore
            context.bot_data['morning_signals'] = []
        except Exception as e:
            logger.error(f"job_afternoon_update error: {e}")

    # ------------------------------------------------------------------ #
    #  COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        intro = (
            "🤖 <b>IDX Day Trader Assistant</b>\n\n"
            "📋 <b>Command tersedia:</b>\n"
            "/signal     — Rekomendasi saham hari ini\n"
            "/update     — Status profit/loss sinyal hari ini\n"
            "/detail &lt;KODE&gt; — Analisa mendalam satu saham\n"
            "/top        — Saham paling aktif di LQ45\n"
            "/watchlist  — Lihat daftar pantau kamu\n"
            "/watch &lt;KODE&gt; — Tambah saham ke watchlist\n"
            "/unwatch &lt;KODE&gt; — Hapus dari watchlist\n"
            "/help       — Menu bantuan ini\n\n"
            "<i>⚠️ Bukan ajakan/rekomendasi finansial.</i>"
        )
        await update.message.reply_text(intro, parse_mode='HTML')

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_market_hours():
            await update.message.reply_text(
                "⏰ Bursa IDX sedang tutup. Sinyal hanya tersedia di hari & jam bursa (Senin–Jumat, 09:00–15:30 WIB)."
            )
            return

        await update.message.reply_text("🔎 Menganalisa saham potensial, mohon tunggu...")
        signals = self._scan_symbols(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD)

        if signals:
            context.bot_data['morning_signals'] = signals
            msg = self.formatter.format_morning_signal(signals)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text(
                "📭 Belum ada setup yang memenuhi kriteria saat ini\n"
                f"(Skor ≥ {HIGH_PROB_THRESHOLD} & RRR ≥ {MIN_RRR})."
            )

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        signals = context.bot_data.get('morning_signals', [])
        if not signals:
            await update.message.reply_text(
                "📭 Belum ada sinyal aktif hari ini. Jalankan /signal terlebih dahulu."
            )
            return

        await update.message.reply_text("⏳ Menghitung Profit/Loss hari ini...")
        updates = []
        for s in signals:
            try:
                res = self.analyzer.analyze(s['symbol'], threshold=0)
                if res:
                    pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                    updates.append({
                        'symbol':        s['symbol'],
                        'current_price': res['price'],
                        'pnl':           pnl,
                    })
            except Exception as e:
                logger.warning(f"[{s['symbol']}] cmd_update error: {e}")

        if updates:
            msg = self.formatter.format_afternoon_update(updates)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("Gagal mengambil data terkini. Coba lagi sesaat.")

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format salah. Contoh: /detail BBCA")
            return

        symbol = context.args[0].upper().replace('.JK', '')
        await update.message.reply_text(f"🔬 Menganalisa {symbol}...")

        try:
            res = self.analyzer.analyze(symbol, threshold=0)
            if res:
                msg = self.formatter.format_detail(res)
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                await update.message.reply_text(
                    f"❌ Data {symbol} tidak ditemukan atau tidak cukup untuk dianalisa.\n"
                    "Pastikan kode saham benar (contoh: BBCA, TLKM, GOTO)."
                )
        except Exception as e:
            logger.error(f"cmd_detail [{symbol}] error: {e}")
            await update.message.reply_text(f"⚠️ Terjadi error saat menganalisa {symbol}.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📊 Memindai seluruh LQ45, mohon tunggu...")
        try:
            all_data = self._scan_symbols(LQ45_SYMBOLS, threshold=0)

            if not all_data:
                await update.message.reply_text("Gagal mendapatkan data. Coba beberapa saat lagi.")
                return

            top_vol     = sorted(all_data, key=lambda x: x['volume_ratio'], reverse=True)[:3]
            top_gainers = sorted(all_data, key=lambda x: x['change_pct'],   reverse=True)[:3]

            msg = self.formatter.format_top(top_vol, top_gainers)
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            logger.error(f"cmd_top error: {e}")
            await update.message.reply_text("⚠️ Terjadi error saat memindai saham.")

    # ── Watchlist Commands ──────────────────────────────────────────────
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tambah saham ke personal watchlist user."""
        if not context.args:
            await update.message.reply_text("⚠️ Format: /watch BBCA")
            return

        symbol   = context.args[0].upper().replace('.JK', '')
        user_id  = str(update.effective_user.id)
        watchlist: dict = context.bot_data.setdefault('watchlist', {})
        user_wl: list   = watchlist.setdefault(user_id, [])

        if symbol in user_wl:
            await update.message.reply_text(f"⚠️ {symbol} sudah ada di watchlist kamu.")
        elif len(user_wl) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10 saham). Hapus salah satu dengan /unwatch.")
        else:
            user_wl.append(symbol)
            await update.message.reply_text(f"✅ <b>{symbol}</b> ditambahkan ke watchlist.", parse_mode='HTML')

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hapus saham dari watchlist."""
        if not context.args:
            await update.message.reply_text("⚠️ Format: /unwatch BBCA")
            return

        symbol  = context.args[0].upper().replace('.JK', '')
        user_id = str(update.effective_user.id)
        user_wl = context.bot_data.get('watchlist', {}).get(user_id, [])

        if symbol in user_wl:
            user_wl.remove(symbol)
            await update.message.reply_text(f"🗑️ <b>{symbol}</b> dihapus dari watchlist.", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ {symbol} tidak ada di watchlist kamu.")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan watchlist dan analisa singkat tiap saham."""
        user_id = str(update.effective_user.id)
        user_wl = context.bot_data.get('watchlist', {}).get(user_id, [])

        if not user_wl:
            await update.message.reply_text(
                "📋 Watchlist kamu kosong.\nTambahkan dengan: /watch BBCA"
            )
            return

        await update.message.reply_text(f"🔍 Menganalisa {len(user_wl)} saham di watchlist...")
        results = self._scan_symbols(user_wl, threshold=0)

        if not results:
            await update.message.reply_text("Gagal mengambil data watchlist. Coba lagi sesaat.")
            return

        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            rek = "💪 BUY" if s['score'] >= 75 else "👀 WATCH" if s['score'] >= 50 else "🚫 AVOID"
            msg += (
                f"<b>{s['symbol']}</b> — Rp {s['price']:,}  ({'+' if s['change_pct'] > 0 else ''}{s['change_pct']}%)\n"
                f"RSI: {s['rsi']} | Skor: {s['score']} | {rek}\n\n"
            )
        await update.message.reply_text(msg, parse_mode='HTML')

    # ------------------------------------------------------------------ #
    #  MAIN RUNNER
    # ------------------------------------------------------------------ #
    def run(self):
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        # Command Handlers
        app.add_handler(CommandHandler("start",     self.cmd_start))
        app.add_handler(CommandHandler("help",      self.cmd_start))
        app.add_handler(CommandHandler("signal",    self.cmd_signal))
        app.add_handler(CommandHandler("update",    self.cmd_update))
        app.add_handler(CommandHandler("detail",    self.cmd_detail))
        app.add_handler(CommandHandler("top",       self.cmd_top))
        app.add_handler(CommandHandler("watch",     self.cmd_watch))
        app.add_handler(CommandHandler("unwatch",   self.cmd_unwatch))
        app.add_handler(CommandHandler("watchlist", self.cmd_watchlist))

        # Schedulers — Senin s/d Jumat (0–4)
        jq = app.job_queue
        jq.run_daily(self.job_morning_signal,   time(hour=9,  minute=25), days=(0, 1, 2, 3, 4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=25), days=(0, 1, 2, 3, 4))

        logger.info("🚀 Bot siap! Command aktif + jadwal otomatis berjalan.")
        app.run_polling()


if __name__ == "__main__":
    bot = IDXDayTraderBot()
    bot.run()