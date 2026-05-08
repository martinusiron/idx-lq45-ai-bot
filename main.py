import asyncio
import json
import logging
from datetime import time

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Defaults

from analyzer import StockAnalyzer
from config import (
    ACCOUNT_SIZE,
    BUY_FEE_PCT,
    DATABASE_URL,
    DAILY_MAX_LOSS_R,
    DB_PATH,
    HIGH_PROB_THRESHOLD,
    LOT_SIZE,
    LQ45_SYMBOLS,
    MAX_OPEN_POSITIONS,
    MIN_RRR,
    PARTIAL_EXIT_RATIO,
    RISK_OFF_MODE,
    RISK_OFF_SIZE_MULTIPLIER,
    RISK_PER_TRADE_PCT,
    SELL_FEE_PCT,
    SLIPPAGE_PCT,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    TIMEZONE,
)
from global_macro import GlobalMacroAnalyzer
from market_session import IDXMarketSession
from notifier import TelegramFormatter
from risk import RiskEngine
from storage import TradingStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class IDXDayTraderBot:
    def __init__(self):
        self.analyzer = StockAnalyzer()
        self.macro = GlobalMacroAnalyzer()
        self.session = IDXMarketSession(TIMEZONE)
        self.storage = TradingStorage(
            sqlite_path=DB_PATH,
            database_url=DATABASE_URL,
            supabase_url=SUPABASE_URL,
            supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info(f"storage backend: {self.storage.describe_backend()}")
        self.storage.healthcheck()
        self.risk = RiskEngine(
            account_size=ACCOUNT_SIZE,
            risk_per_trade_pct=RISK_PER_TRADE_PCT,
            daily_max_loss_r=DAILY_MAX_LOSS_R,
            max_open_positions=MAX_OPEN_POSITIONS,
            lot_size=LOT_SIZE,
            buy_fee_pct=BUY_FEE_PCT,
            sell_fee_pct=SELL_FEE_PCT,
            slippage_pct=SLIPPAGE_PCT,
            partial_exit_ratio=PARTIAL_EXIT_RATIO,
            risk_off_mode=RISK_OFF_MODE,
            risk_off_size_multiplier=RISK_OFF_SIZE_MULTIPLIER,
        )
        self.formatter = TelegramFormatter()
        self.tz = self.session.tz

    # ------------------------------------------------------------------ #
    #  HELPERS
    # ------------------------------------------------------------------ #
    def _trade_date(self) -> str:
        return self.session.now().date().isoformat()

    def _is_market_hours(self) -> bool:
        return self.session.is_regular_session()

    def _market_closed_message(self) -> str:
        status = self.session.get_status()
        if status == "lunch_break":
            return (
                "⏸️ Bursa IDX sedang jeda siang.\n"
                "Jam reguler BEI: Senin–Kamis 09:00–12:00 & 13:30–15:49 WIB, "
                "Jumat 09:00–11:30 & 14:00–15:49 WIB."
            )
        return (
            "⏰ Bursa IDX sedang tutup.\n"
            "Jam reguler BEI: Senin–Kamis 09:00–12:00 & 13:30–15:49 WIB, "
            "Jumat 09:00–11:30 & 14:00–15:49 WIB."
        )

    def _analyze_one(self, sym: str, threshold: int, strict_filter: bool = True) -> dict | None:
        try:
            res = self.analyzer.analyze(sym, threshold=threshold, strict_filter=strict_filter)
            if strict_filter and res and res.get("rrr", 0) < MIN_RRR:
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
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self._analyze_one, sym, threshold, strict_filter)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r is not None]
        return sorted(signals, key=lambda x: x["score"], reverse=True)

    async def _get_macro_async(self) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.macro.get_macro_context)

    def _build_trade_plans(self, signals: list[dict], macro: dict) -> list[dict]:
        trade_date = self._trade_date()
        realized_r = self.storage.get_daily_realized_r(trade_date)
        risk_off = macro.get("is_risk_off", False)
        finalized_symbols = {
            trade["symbol"]
            for trade in self.storage.get_trade_plans(trade_date, include_finalized=True)
            if trade.get("finalized")
        }
        plans: list[dict] = []

        for signal in signals:
            if signal["symbol"] in finalized_symbols:
                logger.info(f"[{signal['symbol']}] plan skipped: trade hari ini sudah finalized.")
                continue

            plan, reason = self.risk.plan_position(
                entry=signal["best_entry"],
                stop=signal["sl"],
                open_positions=len(plans),
                realized_r=realized_r,
                risk_off=risk_off,
            )
            if plan is None:
                logger.info(f"[{signal['symbol']}] plan skipped: {reason}")
                continue

            plans.append({
                **signal,
                "trade_date": trade_date,
                "risk_off": risk_off,
                "qty": plan.qty,
                "lot_count": plan.lot_count,
                "risk_amount": plan.risk_amount,
                "planned_notional": plan.planned_notional,
                "size_mode": plan.size_mode,
                "size_notes": plan.notes,
                "analyzer_snapshot": json.dumps(signal, default=str),
            })

        self.storage.replace_trade_plans(trade_date, plans)
        return plans

    def _evaluate_trades(self, trades: list[dict], finalize: bool) -> list[dict]:
        updates: list[dict] = []
        for trade in trades:
            df = self.analyzer.fetch_data(trade["symbol"])
            if df is None:
                logger.warning(f"[{trade['symbol']}] gagal fetch data evaluasi")
                continue

            result = self.risk.evaluate_trade(
                candles=df,
                signal_timestamp=trade["signal_timestamp"],
                entry=float(trade["planned_entry"]),
                stop=float(trade["sl"]),
                tp1=float(trade["tp1"]),
                tp2=float(trade["tp2"]),
                qty=int(trade["qty"]),
                finalize=finalize,
            )
            self.storage.update_trade_result(trade["trade_date"], trade["symbol"], result)
            updates.append({
                **trade,
                **result,
            })
        return updates

    async def _send_trade_update(
        self,
        reply_fn,
        trade_date: str,
        finalize: bool,
        empty_message: str,
    ):
        use_stored = False
        trades = self.storage.get_active_trade_plans(trade_date)
        if not trades:
            trades = self.storage.get_trade_plans(trade_date, include_finalized=True)
            if not trades:
                await reply_fn(empty_message)
                return
            use_stored = True

        updates = trades if use_stored else self._evaluate_trades(trades, finalize=finalize)
        if not updates:
            await reply_fn("Gagal mengambil data terkini. Coba lagi sesaat.")
            return

        summary = self.storage.get_today_summary(trade_date)
        await reply_fn(
            self.formatter.format_afternoon_update(updates, summary=summary),
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------ #
    #  SCHEDULER JOBS
    # ------------------------------------------------------------------ #
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌅 Job pagi: mencari sinyal...")
        try:
            macro_task = self._get_macro_async()
            signal_task = self._scan_async(
                LQ45_SYMBOLS,
                threshold=HIGH_PROB_THRESHOLD,
                strict_filter=True,
            )
            macro, signals = await asyncio.gather(macro_task, signal_task)

            async def send(text, **kwargs):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kwargs)

            await send(self.formatter.format_macro_context(macro), parse_mode="HTML")

            if not signals:
                await send(
                    f"📭 Tidak ada setup yang memenuhi kriteria hari ini\n"
                    f"(Skor ≥ {HIGH_PROB_THRESHOLD} & RRR ≥ {MIN_RRR})."
                )
                return

            plans = self._build_trade_plans(signals, macro)
            if plans:
                await send(self.formatter.format_morning_signal(plans), parse_mode="HTML")
                logger.info(f"✅ Trade plan tersimpan: {len(plans)} saham.")
            else:
                await send("📭 Tidak ada trade plan yang lolos risk engine hari ini.")
        except Exception as e:
            logger.error(f"job_morning_signal error: {e}")

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🌇 Job sore: update journal...")
        try:
            trade_date = self._trade_date()
            trades = self.storage.get_active_trade_plans(trade_date)
            if not trades:
                return

            macro = await self._get_macro_async()

            async def send(text, **kwargs):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kwargs)

            await send(self.formatter.format_macro_context(macro), parse_mode="HTML")
            await self._send_trade_update(
                reply_fn=send,
                trade_date=trade_date,
                finalize=True,
                empty_message="📭 Belum ada trade plan aktif hari ini.",
            )
        except Exception as e:
            logger.error(f"job_afternoon_update error: {e}")

    # ------------------------------------------------------------------ #
    #  COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        intro = (
            "🤖 <b>IDX Day Trader Assistant</b>\n\n"
            "📋 <b>Command tersedia:</b>\n"
            "/signal     — Trade plan saham hari ini\n"
            "/update     — Status fill/P&L trade plan hari ini\n"
            "/detail &lt;KODE&gt; — Analisa mendalam satu saham\n"
            "/top        — Saham paling aktif di LQ45\n"
            "/macro      — Kondisi makro global hari ini\n"
            "/watchlist  — Lihat daftar pantau kamu\n"
            "/watch &lt;KODE&gt; — Tambah saham ke watchlist\n"
            "/unwatch &lt;KODE&gt; — Hapus dari watchlist\n"
            "/help       — Menu bantuan ini\n\n"
            "⏰ <b>Jadwal Otomatis:</b>\n"
            "  09:25 WIB — Trade plan pagi + kondisi makro\n"
            "  15:50 WIB — Journal update + kondisi makro\n\n"
            "📌 <b>Risk Rules Default:</b>\n"
            f"  Modal acuan: Rp {int(ACCOUNT_SIZE):,}\n"
            f"  Risk/trade: {RISK_PER_TRADE_PCT * 100:.2f}% | Max posisi: {MAX_OPEN_POSITIONS}\n"
            f"  Daily stop: {DAILY_MAX_LOSS_R:.2f}R | Risk-off mode: {RISK_OFF_MODE}\n\n"
            "<i>⚠️ Bukan ajakan/rekomendasi finansial.</i>"
        )
        await update.message.reply_text(intro, parse_mode="HTML")

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🌍 Mengambil data makro global...")
        try:
            macro = await self._get_macro_async()
            msg = self.formatter.format_macro_standalone(macro)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"cmd_macro error: {e}")
            await update.message.reply_text("⚠️ Gagal mengambil data makro. Coba lagi sesaat.")

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_market_hours():
            await update.message.reply_text(self._market_closed_message())
            return

        await update.message.reply_text("🔎 Memindai LQ45 + menyusun trade plan, mohon tunggu ~15 detik...")

        macro_task = self._get_macro_async()
        signal_task = self._scan_async(
            LQ45_SYMBOLS,
            threshold=HIGH_PROB_THRESHOLD,
            strict_filter=True,
        )
        macro, signals = await asyncio.gather(macro_task, signal_task)

        await update.message.reply_text(
            self.formatter.format_macro_context(macro),
            parse_mode="HTML",
        )

        if not signals:
            await update.message.reply_text(
                f"📭 Tidak ada setup yang memenuhi kriteria saat ini\n"
                f"(Skor ≥ {HIGH_PROB_THRESHOLD} & RRR ≥ {MIN_RRR})."
            )
            return

        plans = self._build_trade_plans(signals, macro)
        if plans:
            await update.message.reply_text(
                self.formatter.format_morning_signal(plans),
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("📭 Tidak ada trade plan yang lolos risk engine saat ini.")

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        trade_date = self._trade_date()
        await update.message.reply_text("⏳ Mengevaluasi fill, P/L, dan journal trade...")

        macro = await self._get_macro_async()
        await update.message.reply_text(
            self.formatter.format_macro_context(macro),
            parse_mode="HTML",
        )

        await self._send_trade_update(
            reply_fn=update.message.reply_text,
            trade_date=trade_date,
            finalize=not self._is_market_hours(),
            empty_message="📭 Belum ada trade plan aktif hari ini. Jalankan /signal terlebih dahulu.",
        )

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format salah. Contoh: /detail BBCA")
            return

        symbol = context.args[0].upper().replace(".JK", "")
        await update.message.reply_text(f"🔬 Menganalisa {symbol} + kondisi makro...")

        try:
            loop = asyncio.get_event_loop()
            macro_task = self._get_macro_async()
            stock_task = loop.run_in_executor(None, self._analyze_one, symbol, 0, False)
            macro, res = await asyncio.gather(macro_task, stock_task)

            await update.message.reply_text(
                self.formatter.format_macro_context(macro),
                parse_mode="HTML",
            )

            if res:
                await update.message.reply_text(
                    self.formatter.format_detail(res),
                    parse_mode="HTML",
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
        await update.message.reply_text("📊 Memindai LQ45 + makro global, mohon tunggu ~15 detik...")
        try:
            macro_task = self._get_macro_async()
            signal_task = self._scan_async(LQ45_SYMBOLS, threshold=0, strict_filter=True)
            macro, all_data = await asyncio.gather(macro_task, signal_task)

            await update.message.reply_text(
                self.formatter.format_macro_context(macro),
                parse_mode="HTML",
            )

            if not all_data:
                await update.message.reply_text(
                    "📭 Tidak ada data yang lolos filter likuiditas saat ini."
                )
                return

            top_vol = sorted(all_data, key=lambda x: x["volume_ratio"], reverse=True)[:3]
            top_gainers = sorted(all_data, key=lambda x: x["change_pct"], reverse=True)[:3]
            await update.message.reply_text(
                self.formatter.format_top(top_vol, top_gainers),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"cmd_top error: {e}")
            await update.message.reply_text("⚠️ Terjadi error saat memindai saham.")

    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format: /watch BBCA")
            return

        symbol = context.args[0].upper().replace(".JK", "")
        user_id = str(update.effective_user.id)
        watchlist = self.storage.get_watchlist(user_id)

        if symbol in watchlist:
            await update.message.reply_text(f"⚠️ {symbol} sudah ada di watchlist.")
            return
        if len(watchlist) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10). Hapus dengan /unwatch.")
            return

        self.storage.add_watch_symbol(user_id, symbol)
        await update.message.reply_text(f"✅ <b>{symbol}</b> ditambahkan ke watchlist.", parse_mode="HTML")

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("⚠️ Format: /unwatch BBCA")
            return

        symbol = context.args[0].upper().replace(".JK", "")
        user_id = str(update.effective_user.id)
        removed = self.storage.remove_watch_symbol(user_id, symbol)

        if removed:
            await update.message.reply_text(f"🗑️ <b>{symbol}</b> dihapus dari watchlist.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ {symbol} tidak ada di watchlist.")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        user_wl = self.storage.get_watchlist(user_id)

        if not user_wl:
            await update.message.reply_text(
                "📋 Watchlist kosong.\nTambahkan saham dengan: /watch BBCA"
            )
            return

        await update.message.reply_text(f"🔍 Menganalisa {len(user_wl)} saham di watchlist...")
        results = await self._scan_async(user_wl, threshold=0, strict_filter=False)

        if not results:
            await update.message.reply_text("Gagal mengambil data. Coba lagi sesaat.")
            return

        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            if s["score"] >= 75:
                rek = "💪 BUY"
            elif s["score"] >= 50:
                rek = "👀 WATCH"
            else:
                rek = "🚫 AVOID"

            vwap_ok = s["price"] > s.get("vwap", 0)
            sign = "+" if s["change_pct"] > 0 else ""
            msg += (
                f"<b>{s['symbol']}</b> — Rp {s['price']:,}  ({sign}{s['change_pct']}%)\n"
                f"RSI: {s['rsi']} | ADX: {s.get('adx','—')} | "
                f"VWAP: {'✅' if vwap_ok else '⚠️'} | OBV: {'✅' if s.get('obv_ok') else '⚠️'}\n"
                f"Skor: {s['score']}/100 → {rek}\n\n"
            )

        await update.message.reply_text(msg, parse_mode="HTML")

    # ------------------------------------------------------------------ #
    #  MAIN RUNNER
    # ------------------------------------------------------------------ #
    def run(self):
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_start))
        app.add_handler(CommandHandler("signal", self.cmd_signal))
        app.add_handler(CommandHandler("update", self.cmd_update))
        app.add_handler(CommandHandler("detail", self.cmd_detail))
        app.add_handler(CommandHandler("top", self.cmd_top))
        app.add_handler(CommandHandler("macro", self.cmd_macro))
        app.add_handler(CommandHandler("watch", self.cmd_watch))
        app.add_handler(CommandHandler("unwatch", self.cmd_unwatch))
        app.add_handler(CommandHandler("watchlist", self.cmd_watchlist))

        jq = app.job_queue
        jq.run_daily(self.job_morning_signal, time(hour=9, minute=25), days=(0, 1, 2, 3, 4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=50), days=(0, 1, 2, 3, 4))

        logger.info("🚀 Bot siap! Command aktif + journal trading berjalan.")
        app.run_polling()


if __name__ == "__main__":
    bot = IDXDayTraderBot()
    bot.run()
