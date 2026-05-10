"""
Patch untuk main.py di repo — menambahkan:
1. import market_calendar, monitor
2. IHSG fetch sebelum scan
3. Monitor background task
4. /performa command
5. /setmodal & /setrisk command
6. Market calendar check di job_morning_signal & job_afternoon_update
7. Safe trading time warning di cmd_signal

Cara pakai:
  Ganti seluruh main.py di repo dengan file ini.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import time

from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, Defaults, filters
)
import google.generativeai as genai

from analyzer import StockAnalyzer
from config import (
    ACCOUNT_SIZE, BUY_FEE_PCT, DATABASE_URL, DAILY_MAX_LOSS_R, DB_PATH,
    HIGH_PROB_THRESHOLD, LOT_SIZE, LQ45_SYMBOLS, MAX_OPEN_POSITIONS,
    MIN_RRR, PARTIAL_EXIT_RATIO, RISK_OFF_MODE, RISK_OFF_SIZE_MULTIPLIER,
    RISK_PER_TRADE_PCT, SELL_FEE_PCT, SLIPPAGE_PCT,
    SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN, TIMEZONE, GEMINI_API_KEY,
)
from global_macro import GlobalMacroAnalyzer
from market_calendar import is_trading_day, is_safe_trading_time
from market_session import IDXMarketSession
from monitor import SignalMonitor
from notifier import TelegramFormatter
from risk import RiskEngine
from storage import TradingStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class IDXDayTraderBot:
    def __init__(self) -> None:
        self.analyzer = StockAnalyzer()
        self.macro    = GlobalMacroAnalyzer()
        self.session  = IDXMarketSession(TIMEZONE)
        self.storage  = TradingStorage(
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
        self.tz        = self.session.tz
        self.monitor   = None  # init after app build

        # Gemini AI Assistant
        self.ai_active = False
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.ai_active = True
                logger.info("✅ Gemini AI Assistant aktif.")
            except Exception as e:
                logger.warning(f"⚠️ Gagal inisialisasi Gemini: {e}")

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
                "Senin–Kamis 09:00–12:00 & 13:30–15:49 WIB, "
                "Jumat 09:00–11:30 & 14:00–15:49 WIB."
            )
        return (
            "⏰ Bursa IDX sedang tutup.\n"
            "Senin–Kamis 09:00–12:00 & 13:30–15:49 WIB, "
            "Jumat 09:00–11:30 & 14:00–15:49 WIB."
        )

    def _analyze_one(
        self, sym: str, threshold: int,
        strict_filter: bool = True, ihsg_chg: float | None = None
    ) -> dict | None:
        try:
            res = self.analyzer.analyze(
                sym, threshold=threshold,
                strict_filter=strict_filter, ihsg_chg=ihsg_chg
            )
            if strict_filter and res and res.get("rrr", 0) < MIN_RRR:
                return None
            return res
        except Exception as exc:
            logger.warning(f"[{sym}] analyze error: {exc}")
            return None

    async def _scan_async(
        self, symbols: list[str], threshold: int,
        strict_filter: bool = True, ihsg_chg: float | None = None
    ) -> list[dict]:
        loop    = asyncio.get_event_loop()
        tasks   = [
            loop.run_in_executor(None, self._analyze_one, s, threshold, strict_filter, ihsg_chg)
            for s in symbols
        ]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r is not None]
        return sorted(signals, key=lambda x: x["score"], reverse=True)

    async def _get_macro_async(self) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.macro.get_macro_context)

    async def _get_ihsg_async(self) -> float | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.analyzer.fetch_ihsg)

    def _build_trade_plans(self, signals: list[dict], macro: dict) -> list[dict]:
        trade_date = self._trade_date()
        realized_r = self.storage.get_daily_realized_r(trade_date)
        risk_off   = macro.get("is_risk_off", False)
        finalized  = {
            t["symbol"] for t in self.storage.get_trade_plans(trade_date, include_finalized=True)
            if t.get("finalized")
        }
        plans: list[dict] = []
        for signal in signals:
            if signal["symbol"] in finalized:
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
                "trade_date":      trade_date,
                "risk_off":        risk_off,
                "qty":             plan.qty,
                "lot_count":       plan.lot_count,
                "risk_amount":     plan.risk_amount,
                "planned_notional": plan.planned_notional,
                "size_mode":       plan.size_mode,
                "size_notes":      plan.notes,
                "analyzer_snapshot": json.dumps(signal, default=str),
            })
        self.storage.replace_trade_plans(trade_date, plans)
        return plans

    def _evaluate_trades(self, trades: list[dict], finalize: bool) -> list[dict]:
        updates = []
        for trade in trades:
            df = self.analyzer.fetch_data(trade["symbol"])
            if df is None:
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
            updates.append({**trade, **result})
        return updates

    async def _send_trade_update(self, reply_fn, trade_date: str, finalize: bool, empty_msg: str):
        trades = self.storage.get_active_trade_plans(trade_date)
        if not trades:
            trades = self.storage.get_trade_plans(trade_date, include_finalized=True)
        if not trades:
            await reply_fn(empty_msg)
            return
        updates = self._evaluate_trades(trades, finalize=finalize)
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
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = self.session.now()
        if not is_trading_day(now.date()):
            logger.info("Hari libur IDX — job pagi dilewati.")
            return

        logger.info("🌅 Job pagi: mencari sinyal...")
        try:
            macro_task = self._get_macro_async()
            ihsg_task  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)

            signals = await self._scan_async(
                LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD,
                strict_filter=True, ihsg_chg=ihsg_chg,
            )

            async def send(text, **kw):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kw)

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
                logger.info(f"✅ {len(plans)} trade plan tersimpan.")
            else:
                await send("📭 Tidak ada trade plan yang lolos risk engine hari ini.")
        except Exception as exc:
            logger.error(f"job_morning_signal error: {exc}")

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = self.session.now()
        if not is_trading_day(now.date()):
            return

        logger.info("🌇 Job sore: update journal...")
        try:
            trade_date = self._trade_date()
            trades     = self.storage.get_active_trade_plans(trade_date)
            if not trades:
                return

            macro = await self._get_macro_async()

            async def send(text, **kw):
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, **kw)

            await send(self.formatter.format_macro_context(macro), parse_mode="HTML")
            await self._send_trade_update(
                reply_fn=send, trade_date=trade_date,
                finalize=True, empty_msg="📭 Belum ada trade plan aktif hari ini.",
            )
        except Exception as exc:
            logger.error(f"job_afternoon_update error: {exc}")

    # ------------------------------------------------------------------ #
    #  COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🤖 <b>IDX Day Trader Assistant</b>\n\n"
            "📋 <b>Command tersedia:</b>\n"
            "/signal     — Trade plan saham hari ini\n"
            "/update     — Status fill/P&L hari ini\n"
            "/detail &lt;KODE&gt; — Analisa mendalam satu saham\n"
            "/top        — Saham paling aktif LQ45\n"
            "/macro      — Kondisi makro global\n"
            "/performa   — Win rate & history 30 hari\n"
            "/watchlist  — Daftar pantau kamu\n"
            "/watch &lt;KODE&gt;   — Tambah ke watchlist\n"
            "/unwatch &lt;KODE&gt; — Hapus dari watchlist\n"
            "/setmodal &lt;juta&gt; — Set modal (cth: /setmodal 10)\n"
            "/setrisk &lt;pct&gt;  — Set risk/trade (cth: /setrisk 1.0)\n"
            "/help       — Menu ini\n\n"
            "⏰ <b>Scheduler Otomatis:</b>\n"
            "  09:25 WIB — Sinyal pagi + makro\n"
            "  15:25 WIB — Update P/L + makro\n"
            "  Setiap 15 menit — Monitor TP/SL\n\n"
            "<i>⚠️ Bukan ajakan/rekomendasi finansial.</i>",
            parse_mode="HTML",
        )

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🌍 Mengambil data makro global...")
        try:
            macro = await self._get_macro_async()
            await update.message.reply_text(
                self.formatter.format_macro_standalone(macro), parse_mode="HTML"
            )
        except Exception as exc:
            logger.error(f"cmd_macro: {exc}")
            await update.message.reply_text("⚠️ Gagal mengambil data makro.")

    async def cmd_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = self.session.now()
        if not is_trading_day(now.date()):
            await update.message.reply_text("📅 Hari ini bursa IDX libur.")
            return
        if not self._is_market_hours():
            await update.message.reply_text(self._market_closed_message())
            return
        if not is_safe_trading_time(now.hour, now.minute):
            await update.message.reply_text(
                "⚠️ <b>Waktu kurang ideal untuk entry:</b>\n"
                "• Pre-opening (sebelum 09:15) — harga belum stabil\n"
                "• Jeda sesi (12:00–13:45) — volume tipis\n"
                "• Pre-closing (setelah 14:55) — matching period\n\n"
                "Sinyal tetap ditampilkan untuk referensi.",
                parse_mode="HTML",
            )

        await update.message.reply_text("🔎 Menganalisa LQ45 + makro, mohon tunggu ~20 detik...")

        macro_task = self._get_macro_async()
        ihsg_task  = self._get_ihsg_async()
        macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)

        signals = await self._scan_async(
            LQ45_SYMBOLS, threshold=HIGH_PROB_THRESHOLD,
            strict_filter=True, ihsg_chg=ihsg_chg,
        )

        await update.message.reply_text(
            self.formatter.format_macro_context(macro), parse_mode="HTML"
        )

        if not signals:
            await update.message.reply_text(
                f"📭 Tidak ada setup memenuhi kriteria\n(Skor≥{HIGH_PROB_THRESHOLD} & RRR≥{MIN_RRR})."
            )
            return

        plans = self._build_trade_plans(signals, macro)
        if plans:
            await update.message.reply_text(
                self.formatter.format_morning_signal(plans), parse_mode="HTML"
            )
        else:
            await update.message.reply_text("📭 Tidak ada trade plan yang lolos risk engine.")

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("⏳ Menghitung P/L + update makro...")
        trade_date = self._trade_date()
        macro      = await self._get_macro_async()

        await update.message.reply_text(
            self.formatter.format_macro_context(macro), parse_mode="HTML"
        )
        await self._send_trade_update(
            reply_fn=update.message.reply_text,
            trade_date=trade_date,
            finalize=False,
            empty_msg="📭 Belum ada trade plan aktif hari ini. Jalankan /signal terlebih dahulu.",
        )

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("⚠️ Format salah. Contoh: /detail BBCA")
            return
        symbol = context.args[0].upper().replace(".JK", "")
        await update.message.reply_text(f"🔬 Menganalisa {symbol} + makro...")

        try:
            loop       = asyncio.get_event_loop()
            macro_task = self._get_macro_async()
            ihsg_task  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)

            res = await loop.run_in_executor(
                None, self._analyze_one, symbol, 0, False, ihsg_chg
            )

            await update.message.reply_text(
                self.formatter.format_macro_context(macro), parse_mode="HTML"
            )
            if res:
                await update.message.reply_text(
                    self.formatter.format_detail(res), parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"❌ Data {symbol} tidak ditemukan.\n"
                    "Pastikan kode saham benar (contoh: BBCA, TLKM, GOTO)."
                )
        except Exception as exc:
            logger.error(f"cmd_detail [{symbol}]: {exc}")
            await update.message.reply_text(f"⚠️ Error saat menganalisa {symbol}.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📊 Memindai LQ45 + makro, mohon tunggu ~20 detik...")
        try:
            macro_task = self._get_macro_async()
            ihsg_task  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)

            all_data = await self._scan_async(
                LQ45_SYMBOLS, threshold=0, strict_filter=True, ihsg_chg=ihsg_chg
            )

            await update.message.reply_text(
                self.formatter.format_macro_context(macro), parse_mode="HTML"
            )
            if not all_data:
                await update.message.reply_text("📭 Tidak ada data lolos filter saat ini.")
                return

            top_vol     = sorted(all_data, key=lambda x: x["volume_ratio"], reverse=True)[:3]
            top_gainers = sorted(all_data, key=lambda x: x["change_pct"],   reverse=True)[:3]
            await update.message.reply_text(
                self.formatter.format_top(top_vol, top_gainers), parse_mode="HTML"
            )
        except Exception as exc:
            logger.error(f"cmd_top: {exc}")
            await update.message.reply_text("⚠️ Error saat memindai saham.")

    async def cmd_performa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📈 Mengambil data performa 30 hari...")
        try:
            history = self.storage.get_closed_trades(days=30)
            await update.message.reply_text(
                self.formatter.format_performance(history, period_days=30),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error(f"cmd_performa: {exc}")
            await update.message.reply_text("⚠️ Gagal mengambil data performa.")

    async def cmd_setmodal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            size = self.risk.account_size
            await update.message.reply_text(
                f"💰 Modal saat ini: Rp {size/1_000_000:.0f} juta\n"
                "Ubah: /setmodal 10  (= Rp 10 juta)"
            )
            return
        try:
            juta = float(context.args[0])
            self.risk.account_size = juta * 1_000_000
            await update.message.reply_text(
                f"✅ Modal diset ke <b>Rp {juta:.0f} juta</b>", parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text("⚠️ Format salah. Contoh: /setmodal 10")

    async def cmd_setrisk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(
                f"⚡ Risk/trade saat ini: {self.risk.risk_per_trade_pct*100:.2f}%\n"
                "Ubah: /setrisk 1.0  (= 1%)"
            )
            return
        try:
            pct = float(context.args[0])
            if not 0.1 <= pct <= 5:
                await update.message.reply_text("⚠️ Risk harus antara 0.1%–5%")
                return
            self.risk.risk_per_trade_pct = pct / 100
            await update.message.reply_text(
                f"✅ Risk/trade diset ke <b>{pct}%</b>", parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text("⚠️ Format salah. Contoh: /setrisk 1.0")

    # ── Watchlist ───────────────────────────────────────────────────────
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("⚠️ Format: /watch BBCA")
            return
        symbol  = context.args[0].upper().replace(".JK", "")
        user_id = str(update.effective_user.id)
        wl      = self.storage.get_watchlist(user_id)
        if symbol in wl:
            await update.message.reply_text(f"⚠️ {symbol} sudah ada.")
            return
        if len(wl) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10). Hapus dengan /unwatch.")
            return
        self.storage.add_to_watchlist(user_id, symbol)
        await update.message.reply_text(f"✅ <b>{symbol}</b> ditambahkan.", parse_mode="HTML")

    async def cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("⚠️ Format: /unwatch BBCA")
            return
        symbol  = context.args[0].upper().replace(".JK", "")
        user_id = str(update.effective_user.id)
        self.storage.remove_from_watchlist(user_id, symbol)
        await update.message.reply_text(f"🗑️ <b>{symbol}</b> dihapus.", parse_mode="HTML")

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        symbols = self.storage.get_watchlist(user_id)
        if not symbols:
            await update.message.reply_text("📋 Watchlist kosong.\nTambahkan: /watch BBCA")
            return
        await update.message.reply_text(f"🔍 Menganalisa {len(symbols)} saham di watchlist...")
        ihsg_chg = await self._get_ihsg_async()
        results  = await self._scan_async(symbols, threshold=0, strict_filter=False, ihsg_chg=ihsg_chg)
        if not results:
            await update.message.reply_text("Gagal mengambil data. Coba lagi sesaat.")
            return
        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            rek  = "💪 BUY" if s["score"] >= 75 else "👀 WATCH" if s["score"] >= 50 else "🚫 AVOID"
            vok  = "✅" if s["price"] > s.get("vwap", 0) else "⚠️"
            mtf  = "✅" if s.get("mtf_trend") == "daily_uptrend" else "⚠️" if s.get("mtf_trend") == "daily_downtrend" else "➡️"
            rs   = "💪" if s.get("rs_stronger") else ""
            sign = "+" if s["change_pct"] > 0 else ""
            msg += (
                f"<b>{s['symbol']}</b> {rs} — Rp {s['price']:,}  ({sign}{s['change_pct']}%)\n"
                f"RSI:{s['rsi']} ADX:{s.get('adx','—')} MTF:{mtf} VWAP:{vok} OBV:{'✅' if s.get('obv_ok') else '⚠️'}\n"
                f"Entry:Rp {s.get('best_entry',s['price']):,} | Skor:{s['score']} → {rek}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle non-command messages using Gemini AI."""
        if not self.ai_active:
            # Jika AI tidak aktif, jangan respon chat biasa agar tidak spam
            return

        user_text = update.message.text
        if not user_text:
            return

        # Hanya respon di private chat atau jika bot di-mention (jika di grup)
        # Untuk kesederhanaan, kita respon semua text di chat yang terdaftar
        
        logger.info(f"AI Chat request from {update.effective_user.first_name}: {user_text[:50]}...")
        
        try:
            # Enhanced System Prompt
            system_prompt = (
                "Role & Personality:\n"
                "Anda adalah IDX Day Trader Assistant (Enhanced), seorang asisten cerdas dan analis teknikal pro "
                "untuk pasar saham Bursa Efek Indonesia (BEI). Kepribadian Anda adalah campuran antara trader senior "
                "yang bijak, santai, namun sangat presisi. Gunakan bahasa Indonesia yang modern, sering gunakan "
                "istilah trading yang umum (seperti support, resistance, breakout, cut loss), namun tetap profesional.\n\n"
                "Core Tasks:\n"
                "1. Analisa Teknikal: Membantu memetakan support/resistance, indikator (MA, RSI, MACD), & pola grafik.\n"
                "2. Edukasi & Strategi: Menjelaskan konsep day trading, swing trading, risk management, & psikologi.\n"
                "3. Navigasi Bot: Menjelaskan fitur bot ini (cek harga, alert, baca chart).\n"
                "4. Sentimen Pasar: Rangkuman sentimen harian atau berita emiten BEI.\n\n"
                "Operational Guidelines:\n"
                "- Disclaimer (Wajib): Selalu sertakan bahwa ini bukan ajakan beli/jual. Gunakan frasa: 'Ingat, ini hanya opini untuk bahan pertimbangan, keputusan ada di tanganmu (DYOR - Do Your Own Research).'\n"
                "- Manajemen Risiko: Selalu tekankan pentingnya Stop Loss.\n"
                "- Saham Gorengan: Berikan peringatan ekstra risiko volatilitas untuk saham tidak likuid.\n"
                "- Interaksi: Tetap di topik trading saham BEI.\n\n"
                "Contoh Gaya Bahasa:\n"
                "- 'Wah, $BBRI lagi ngetes resistance kuat di area 5500 nih. Kalau kuat breakout, potensinya lanjut, tapi jangan lupa jaga jempol di tombol sell kalau balik arah ya!'\n"
                "- 'Saran saya, atur money management-mu dulu sebelum entry. Lebih baik ketinggalan kereta daripada nyangkut di pucuk.'\n"
            )

            # Show typing status in Telegram
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

            # Build final prompt with context
            full_prompt = f"{system_prompt}\n\nUser bertanya: {user_text}"
            
            # Tambahkan info market jika perlu
            if any(k in user_text.lower() for k in ["market", "ihsg", "bursa"]):
                ihsg = await self._get_ihsg_async()
                if ihsg:
                    full_prompt += f"\n\nInfo tambahan: IHSG saat ini sedang {ihsg}%."

            # Call Gemini with timeout
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(self.model.generate_content, full_prompt, request_options={"timeout": 60}),
                    timeout=65.0
                )
                await update.message.reply_text(response.text)
            except asyncio.TimeoutError:
                logger.error("Gemini request timed out.")
                await update.message.reply_text(
                    "⚠️ Maaf, respon AI terlalu lama. Silakan coba tanya lagi sesaat lagi."
                )
        except Exception as exc:
            logger.error(f"Gemini error: {exc}")
            # Jangan kirim error ke user agar tidak mengganggu, cukup log saja

    # ------------------------------------------------------------------ #
    #  MAIN RUNNER
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        for cmd, fn in [
            ("start",     self.cmd_start),
            ("help",      self.cmd_start),
            ("signal",    self.cmd_signal),
            ("update",    self.cmd_update),
            ("detail",    self.cmd_detail),
            ("top",       self.cmd_top),
            ("macro",     self.cmd_macro),
            ("performa",  self.cmd_performa),
            ("setmodal",  self.cmd_setmodal),
            ("setrisk",   self.cmd_setrisk),
            ("watch",     self.cmd_watch),
            ("unwatch",   self.cmd_unwatch),
            ("watchlist", self.cmd_watchlist),
        ]:
            app.add_handler(CommandHandler(cmd, fn))

        # Generic message handler for AI Chat
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        jq = app.job_queue
        jq.run_daily(self.job_morning_signal,   time(hour=9,  minute=25), days=(0, 1, 2, 3, 4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=25), days=(0, 1, 2, 3, 4))

        # Background TP/SL monitor
        self.monitor = SignalMonitor(app, self.storage)

        async def _on_startup(application):
            asyncio.create_task(
                self.monitor.run_loop(TELEGRAM_CHAT_ID, self._trade_date)
            )

        app.post_init = _on_startup

        logger.info("🚀 Bot siap! 13 commands + scheduler + real-time monitor aktif.")
        app.run_polling()


if __name__ == "__main__":
    IDXDayTraderBot().run()
