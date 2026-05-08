import logging
import asyncio
import pytz
from datetime import time, datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults
from analyzer import StockAnalyzer
from notifier import TelegramFormatter
from global_macro import GlobalMacroAnalyzer
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
        self.macro     = GlobalMacroAnalyzer()
        self.tz        = pytz.timezone('Asia/Jakarta')
        self.formatter = TelegramFormatter()

    # ------------------------------------------------------------------ #
    #  HELPERS
    # ------------------------------------------------------------------ #
    def _is_market_hours(self) -> bool:
        now = datetime.now(self.tz)
        if now.weekday() >= 5:
            return False
        return MARKET_OPEN <= now.hour < MARKET_CLOSE + 1

    def _analyze_one(self, sym: str, threshold: int, strict_filter: bool = True) -> dict | None:
        """
        Wrapper sync untuk dijalankan di thread pool.
        strict_filter=True  → aktifkan liquidity gate + ADX filter (untuk /signal, /top)
        strict_filter=False → matikan semua filter (untuk /detail, /watchlist, /update)
        """
        try:
            res = self.analyzer.analyze(sym, threshold=threshold, strict_filter=strict_filter)
            # RRR minimum hanya berlaku saat strict mode
            if strict_filter and res and res.get('rrr', 0) < MIN_RRR:
                return None
            return res
        except Exception as e:
            logger.warning(f"[{sym}] analyze error: {e}")
        return None

    async def _scan_async(
        self,
        symbols: list[str],
        threshold: int,
        strict_filter: bool = True
    ) -> list[dict]:
        """
        Scan semua simbol secara concurrent (thread pool).
        Hasil diurutkan by score descending.
        """
        loop  = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self._analyze_one, sym, threshold, strict_filter)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r is not None]
        return sorted(signals, key=lambda x: x['score'], reverse=True)

    async def _get_macro_async(self) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.macro.get_macro_context)

    # ------------------------------------------------------------------ #
    #  SCHEDULER JOBS
    # ------------------------------------------------------------------ #
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌅 Job pagi: mencari sinyal...")
        try:
            macro_task  = self._get_macro_async()
            # strict_filter=True — filter ketat untuk sinyal pagi
            signal_task = self._scan_async(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD, strict_filter=True)
            macro, signals = await asyncio.gather(macro_task, signal_task)

            is_risk_off, risk_reasons = self.macro.check_risk_off()
            if is_risk_off:
                logger.warning(f"⚠️ RISK-OFF: {risk_reasons}")

            async def send(text, **kwargs):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kwargs)

            # Pesan 1: makro
            await send(self.formatter.format_macro_context(macro), parse_mode='HTML')

            # Pesan 2: sinyal atau info kosong
            if signals:
                context.bot_data['morning_signals'] = signals
                await send(self.formatter.format_morning_signal(signals), parse_mode='HTML')
                logger.info(f"✅ Sinyal pagi dikirim: {len(signals)} saham lolos.")
            else:
                await send(
                    f"📭 Tidak ada setup yang memenuhi kriteria hari ini\n"
                    f"(Skor ≥ {HIGH_PROB_THRESHOLD} & RRR ≥ {MIN_RRR})."
                )
        except Exception as e:
            logger.error(f"job_morning_signal error: {e}")

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌇 Job sore: update P/L...")
        try:
            morning_signals = context.bot_data.get('morning_signals', [])
            if not morning_signals:
                return

            macro_task = self._get_macro_async()
            updates    = []

            # strict_filter=False — cek harga terkini tanpa filter
            for s in morning_signals:
                try:
                    res = self._analyze_one(s['symbol'], threshold=0, strict_filter=False)
                    if res:
                        pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                        updates.append({
                            'symbol':        s['symbol'],
                            'current_price': res['price'],
                            'pnl':           pnl,
                        })
                except Exception as e:
                    logger.warning(f"[{s['symbol']}] update sore error: {e}")

            macro = await macro_task

            async def send(text, **kwargs):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kwargs)

            # Pesan 1: makro
            await send(self.formatter.format_macro_context(macro), parse_mode='HTML')

            # Pesan 2: P/L
            if updates:
                await send(self.formatter.format_afternoon_update(updates), parse_mode='HTML')

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
            "/macro      — Kondisi makro global hari ini\n"
            "/watchlist  — Lihat daftar pantau kamu\n"
            "/watch &lt;KODE&gt; — Tambah saham ke watchlist\n"
            "/unwatch &lt;KODE&gt; — Hapus dari watchlist\n"
            "/help       — Menu bantuan ini\n\n"
            "⏰ <b>Jadwal Otomatis:</b>\n"
            "  09:25 WIB — Sinyal pagi + kondisi makro\n"
            "  15:25 WIB — Update P/L + kondisi makro\n\n"
            "<i>⚠️ Bukan ajakan/rekomendasi finansial.</i>"
        )
        await update.message.reply_text(intro, parse_mode='HTML')

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan kondisi makro global + dampak ke sektor IDX."""
        await update.message.reply_text("🌍 Mengambil data makro global...")
        try:
            macro = await self._get_macro_async()
            msg   = self.formatter.format_macro_standalone(macro)
            await update.message.reply_text(msg, parse_mode='HTML')
        except Exception as e:
            logger.error(f"cmd_macro error: {e}")
            await update.message.reply_text("⚠️ Gagal mengambil data makro. Coba lagi sesaat.")

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Scan LQ45 dengan filter ketat, tampilkan max 3 sinyal terbaik."""
        if not self._is_market_hours():
            await update.message.reply_text(
                "⏰ Bursa IDX sedang tutup.\n"
                "Sinyal tersedia Senin–Jumat, 09:00–15:30 WIB."
            )
            return

        await update.message.reply_text("🔎 Menganalisa LQ45 + makro global, mohon tunggu ~15 detik...")

        macro_task  = self._get_macro_async()
        # strict_filter=True — filter ketat: liquidity gate + ADX + RRR minimum
        signal_task = self._scan_async(LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD, strict_filter=True)
        macro, signals = await asyncio.gather(macro_task, signal_task)

        # Pesan 1: makro
        await update.message.reply_text(
            self.formatter.format_macro_context(macro), parse_mode='HTML'
        )

        # Pesan 2: sinyal
        if signals:
            context.bot_data['morning_signals'] = signals
            await update.message.reply_text(
                self.formatter.format_morning_signal(signals), parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                f"📭 Tidak ada setup yang memenuhi kriteria saat ini\n"
                f"(Skor ≥ {HIGH_PROB_THRESHOLD} & RRR ≥ {MIN_RRR})."
            )

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cek harga terkini dari sinyal pagi, hitung P/L."""
        signals = context.bot_data.get('morning_signals', [])
        if not signals:
            await update.message.reply_text(
                "📭 Belum ada sinyal aktif hari ini. Jalankan /signal terlebih dahulu."
            )
            return

        await update.message.reply_text("⏳ Menghitung P/L + update makro...")

        macro_task = self._get_macro_async()
        updates    = []

        # strict_filter=False — cek harga terkini tanpa filter apapun
        for s in signals:
            try:
                res = self._analyze_one(s['symbol'], threshold=0, strict_filter=False)
                if res:
                    pnl = round(((res['price'] - s['price']) / s['price']) * 100, 2)
                    updates.append({
                        'symbol':        s['symbol'],
                        'current_price': res['price'],
                        'pnl':           pnl,
                    })
            except Exception as e:
                logger.warning(f"[{s['symbol']}] cmd_update error: {e}")

        macro = await macro_task

        # Pesan 1: makro
        await update.message.reply_text(
            self.formatter.format_macro_context(macro), parse_mode='HTML'
        )

        # Pesan 2: P/L
        if updates:
            await update.message.reply_text(
                self.formatter.format_afternoon_update(updates), parse_mode='HTML'
            )
        else:
            await update.message.reply_text("Gagal mengambil data terkini. Coba lagi sesaat.")

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Analisa mendalam satu saham, tanpa filter (tampilkan apapun kondisinya)."""
        if not context.args:
            await update.message.reply_text("⚠️ Format salah. Contoh: /detail BBCA")
            return

        symbol = context.args[0].upper().replace('.JK', '')
        await update.message.reply_text(f"🔬 Menganalisa {symbol} + kondisi makro...")

        try:
            loop       = asyncio.get_event_loop()
            macro_task = self._get_macro_async()
            # strict_filter=False — user minta detail, tampilkan apapun
            stock_task = loop.run_in_executor(
                None, self._analyze_one, symbol, 0, False
            )
            macro, res = await asyncio.gather(macro_task, stock_task)

            # Pesan 1: makro
            await update.message.reply_text(
                self.formatter.format_macro_context(macro), parse_mode='HTML'
            )

            # Pesan 2: detail saham
            if res:
                await update.message.reply_text(
                    self.formatter.format_detail(res), parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    f"❌ Data {symbol} tidak ditemukan.\n"
                    "Pastikan kode saham benar (contoh: BBCA, TLKM, GOTO)."
                )
        except Exception as e:
            logger.error(f"cmd_detail [{symbol}] error: {e}")
            await update.message.reply_text(f"⚠️ Terjadi error saat menganalisa {symbol}.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan top volume, top gainers, dan RRR terbaik dari LQ45."""
        await update.message.reply_text("📊 Memindai LQ45 + makro global, mohon tunggu ~15 detik...")
        try:
            macro_task  = self._get_macro_async()
            # strict_filter=True — top hanya tampilkan saham yang likuid
            signal_task = self._scan_async(LQ45_SYMBOLS, threshold=0, strict_filter=True)
            macro, all_data = await asyncio.gather(macro_task, signal_task)

            # Pesan 1: makro
            await update.message.reply_text(
                self.formatter.format_macro_context(macro), parse_mode='HTML'
            )

            # Pesan 2: top saham
            if not all_data:
                await update.message.reply_text(
                    "📭 Tidak ada data yang lolos filter likuiditas saat ini."
                )
                return

            top_vol     = sorted(all_data, key=lambda x: x['volume_ratio'], reverse=True)[:3]
            top_gainers = sorted(all_data, key=lambda x: x['change_pct'],   reverse=True)[:3]
            await update.message.reply_text(
                self.formatter.format_top(top_vol, top_gainers), parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"cmd_top error: {e}")
            await update.message.reply_text("⚠️ Terjadi error saat memindai saham.")

    # ── Watchlist ───────────────────────────────────────────────────────
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tambah saham ke personal watchlist (maks 10)."""
        if not context.args:
            await update.message.reply_text("⚠️ Format: /watch BBCA")
            return
        symbol    = context.args[0].upper().replace('.JK', '')
        user_id   = str(update.effective_user.id)
        watchlist = context.bot_data.setdefault('watchlist', {})
        user_wl   = watchlist.setdefault(user_id, [])

        if symbol in user_wl:
            await update.message.reply_text(f"⚠️ {symbol} sudah ada di watchlist.")
        elif len(user_wl) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10). Hapus dengan /unwatch.")
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
            await update.message.reply_text(f"⚠️ {symbol} tidak ada di watchlist.")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan semua saham di watchlist beserta analisa singkat."""
        user_id = str(update.effective_user.id)
        user_wl = context.bot_data.get('watchlist', {}).get(user_id, [])

        if not user_wl:
            await update.message.reply_text(
                "📋 Watchlist kosong.\nTambahkan saham dengan: /watch BBCA"
            )
            return

        await update.message.reply_text(f"🔍 Menganalisa {len(user_wl)} saham di watchlist...")

        # strict_filter=False — watchlist tampilkan semua apapun kondisi volume/ADX
        results = await self._scan_async(user_wl, threshold=0, strict_filter=False)

        if not results:
            await update.message.reply_text("Gagal mengambil data. Coba lagi sesaat.")
            return

        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            if s['score'] >= 75:
                rek = "💪 BUY"
            elif s['score'] >= 50:
                rek = "👀 WATCH"
            else:
                rek = "🚫 AVOID"

            vwap_ok = s['price'] > s.get('vwap', 0)
            sign    = "+" if s['change_pct'] > 0 else ""

            msg += (
                f"<b>{s['symbol']}</b> — Rp {s['price']:,}  ({sign}{s['change_pct']}%)\n"
                f"RSI: {s['rsi']} | ADX: {s.get('adx','—')} | "
                f"VWAP: {'✅' if vwap_ok else '⚠️'} | OBV: {'✅' if s.get('obv_ok') else '⚠️'}\n"
                f"Skor: {s['score']}/100 → {rek}\n\n"
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
        app.add_handler(CommandHandler("macro",     self.cmd_macro))
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