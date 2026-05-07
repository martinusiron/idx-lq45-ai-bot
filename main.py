import logging
import asyncio
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
        now = datetime.now(self.tz)
        if now.weekday() >= 5:
            return False
        return MARKET_OPEN <= now.hour < MARKET_CLOSE + 1

    def _analyze_one(self, sym: str, threshold: int) -> dict | None:
        """Wrapper sync untuk dijalankan di thread pool."""
        try:
            res = self.analyzer.analyze(sym, threshold=threshold)
            if res and res.get('rrr', 0) >= MIN_RRR:
                return res
        except Exception as e:
            logger.warning(f"[{sym}] error: {e}")
        return None

    async def _scan_symbols_async(self, symbols: list[str], threshold: int) -> list[dict]:
        """
        Scan semua simbol secara concurrent menggunakan thread pool.
        Jauh lebih cepat dari sequential — 65 saham ~10-15 detik vs ~60 detik.
        """
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self._analyze_one, sym, threshold)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r is not None]
        return sorted(signals, key=lambda x: x['score'], reverse=True)

    # ------------------------------------------------------------------ #
    #  SCHEDULER JOBS
    # ------------------------------------------------------------------ #
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌅 Job pagi: mencari sinyal...")
        try:
            signals = await self._scan_symbols_async(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD)
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
                    logger.warning(f"[{s['symbol']}] update sore error: {e}")

            if updates:
                msg = self.formatter.format_afternoon_update(updates)
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML'
                )
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
                "⏰ Bursa IDX sedang tutup.\n"
                "Sinyal tersedia Senin–Jumat, 09:00–15:30 WIB."
            )
            return

        await update.message.reply_text("🔎 Menganalisa LQ45 secara paralel, mohon tunggu ~15 detik...")
        signals = await self._scan_symbols_async(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD)

        if signals:
            context.bot_data['morning_signals'] = signals
            msg = self.formatter.format_morning_signal(signals)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text(
                f"📭 Belum ada setup yang memenuhi kriteria saat ini\n"
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
            loop = asyncio.get_event_loop()
            res  = await loop.run_in_executor(None, self.analyzer.analyze, symbol, 0)
            if res:
                msg = self.formatter.format_detail(res)
                await update.message.reply_text(msg, parse_mode='HTML')
            else:
                await update.message.reply_text(
                    f"❌ Data {symbol} tidak ditemukan atau tidak cukup.\n"
                    "Pastikan kode saham benar (contoh: BBCA, TLKM, GOTO)."
                )
        except Exception as e:
            logger.error(f"cmd_detail [{symbol}] error: {e}")
            await update.message.reply_text(f"⚠️ Terjadi error saat menganalisa {symbol}.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📊 Memindai LQ45 secara paralel, mohon tunggu ~15 detik...")
        try:
            all_data = await self._scan_symbols_async(LQ45_SYMBOLS, threshold=0)
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

    # ── Watchlist ───────────────────────────────────────────────────────
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format: /watch BBCA")
            return
        symbol   = context.args[0].upper().replace('.JK', '')
        user_id  = str(update.effective_user.id)
        watchlist = context.bot_data.setdefault('watchlist', {})
        user_wl   = watchlist.setdefault(user_id, [])

        if symbol in user_wl:
            await update.message.reply_text(f"⚠️ {symbol} sudah ada di watchlist.")
        elif len(user_wl) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10). Hapus dengan /unwatch.")
        else:
            user_wl.append(symbol)
            await update.message.reply_text(f"✅ <b>{symbol}</b> ditambahkan.", parse_mode='HTML')

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format: /unwatch BBCA")
            return
        symbol  = context.args[0].upper().replace('.JK', '')
        user_id = str(update.effective_user.id)
        user_wl = context.bot_data.get('watchlist', {}).get(user_id, [])

        if symbol in user_wl:
            user_wl.remove(symbol)
            await update.message.reply_text(f"🗑️ <b>{symbol}</b> dihapus.", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ {symbol} tidak ada di watchlist.")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        user_wl = context.bot_data.get('watchlist', {}).get(user_id, [])

        if not user_wl:
            await update.message.reply_text("📋 Watchlist kosong.\nTambahkan: /watch BBCA")
            return

        await update.message.reply_text(f"🔍 Menganalisa {len(user_wl)} saham di watchlist...")
        results = await self._scan_symbols_async(user_wl, threshold=0)

        if not results:
            await update.message.reply_text("Gagal mengambil data. Coba lagi sesaat.")
            return

        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            rek = "💪 BUY" if s['score'] >= 75 else "👀 WATCH" if s['score'] >= 50 else "🚫 AVOID"
            msg += (
                f"<b>{s['symbol']}</b> — Rp {s['price']:,}  "
                f"({'+' if s['change_pct'] > 0 else ''}{s['change_pct']}%)\n"
                f"RSI: {s['rsi']} | Skor: {s['score']} | {rek}\n\n"
            )
        await update.message.reply_text(msg, parse_mode='HTML')

    # ------------------------------------------------------------------ #
    #  MAIN RUNNER
    # ------------------------------------------------------------------ #
    def run(self):
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        app.add_handler(CommandHandler("start",     self.cmd_start))
        app.add_handler(CommandHandler("help",      self.cmd_start))
        app.add_handler(CommandHandler("signal",    self.cmd_signal))
        app.add_handler(CommandHandler("update",    self.cmd_update))
        app.add_handler(CommandHandler("detail",    self.cmd_detail))
        app.add_handler(CommandHandler("top",       self.cmd_top))
        app.add_handler(CommandHandler("watch",     self.cmd_watch))
        app.add_handler(CommandHandler("unwatch",   self.cmd_unwatch))
        app.add_handler(CommandHandler("watchlist", self.cmd_watchlist))

        jq = app.job_queue
        jq.run_daily(self.job_morning_signal,   time(hour=9,  minute=25), days=(0, 1, 2, 3, 4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=25), days=(0, 1, 2, 3, 4))

        logger.info("🚀 Bot siap! Command aktif + jadwal otomatis berjalan.")
        app.run_polling()


if __name__ == "__main__":
    bot = IDXDayTraderBot()
    bot.run()