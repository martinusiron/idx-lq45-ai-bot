"""
main.py — IDX Day Trader Bot v5
Sprint 1: Multi-turn memory + Chart Vision + Price Alert
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import time

import google.generativeai as genai
from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    Defaults, MessageHandler, filters,
)

from analyzer import StockAnalyzer
from chart_vision import analyze_chart_image
from config import (
    ACCOUNT_SIZE, BUY_FEE_PCT, DATABASE_URL, DAILY_MAX_LOSS_R, DB_PATH,
    GEMINI_API_KEY, HIGH_PROB_THRESHOLD, LOT_SIZE, LQ45_SYMBOLS,
    MAX_OPEN_POSITIONS, MIN_RRR, PARTIAL_EXIT_RATIO, RISK_OFF_MODE,
    RISK_OFF_SIZE_MULTIPLIER, RISK_PER_TRADE_PCT, SELL_FEE_PCT, SLIPPAGE_PCT,
    SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN, TIMEZONE,
)
from conversation_store import ConversationStore
from global_macro import GlobalMacroAnalyzer
from market_calendar import is_trading_day, is_safe_trading_time
from market_session import IDXMarketSession
from monitor import SignalMonitor
from notifier import TelegramFormatter
from price_alert import PriceAlertManager
from risk import RiskEngine
from storage import TradingStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class IDXDayTraderBot:
    def __init__(self) -> None:
        self.analyzer  = StockAnalyzer()
        self.macro     = GlobalMacroAnalyzer()
        self.session   = IDXMarketSession(TIMEZONE)
        self.storage   = TradingStorage(
            sqlite_path=DB_PATH, database_url=DATABASE_URL,
            supabase_url=SUPABASE_URL,
            supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info(f"storage backend: {self.storage.describe_backend()}")
        self.storage.healthcheck()

        self.risk = RiskEngine(
            account_size=ACCOUNT_SIZE, risk_per_trade_pct=RISK_PER_TRADE_PCT,
            daily_max_loss_r=DAILY_MAX_LOSS_R, max_open_positions=MAX_OPEN_POSITIONS,
            lot_size=LOT_SIZE, buy_fee_pct=BUY_FEE_PCT, sell_fee_pct=SELL_FEE_PCT,
            slippage_pct=SLIPPAGE_PCT, partial_exit_ratio=PARTIAL_EXIT_RATIO,
            risk_off_mode=RISK_OFF_MODE, risk_off_size_multiplier=RISK_OFF_SIZE_MULTIPLIER,
        )
        self.formatter   = TelegramFormatter()
        self.tz          = self.session.tz
        self.conv_store  = ConversationStore()         # ← Sprint 1: memory
        self.alert_mgr   = None                        # ← Sprint 1: price alert (init after app)
        self.monitor     = None
        self.ai_active   = False
        self.model       = None

        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model     = genai.GenerativeModel("gemini-2.5-flash-lite")
                self.ai_active = True
                logger.info("✅ Gemini AI aktif (gemini-2.5-flash-lite)")
            except Exception as exc:
                logger.warning(f"⚠️ Gemini init gagal: {exc}")

    # ------------------------------------------------------------------ #
    #  HELPERS
    # ------------------------------------------------------------------ #
    def _trade_date(self) -> str:
        return self.session.now().date().isoformat()

    def _is_market_hours(self) -> bool:
        return self.session.is_regular_session()

    def _market_closed_message(self) -> str:
        if self.session.get_status() == "lunch_break":
            return "⏸️ Bursa IDX sedang jeda siang."
        return "⏰ Bursa IDX sedang tutup."

    def _analyze_one(self, sym: str, threshold: int,
                     strict_filter: bool = True,
                     ihsg_chg: float | None = None) -> dict | None:
        try:
            res = self.analyzer.analyze(sym, threshold=threshold,
                                        strict_filter=strict_filter, ihsg_chg=ihsg_chg)
            if strict_filter and res and res.get("rrr", 0) < MIN_RRR:
                return None
            return res
        except Exception as exc:
            logger.warning(f"[{sym}] analyze error: {exc}")
            return None

    async def _scan_async(self, symbols: list[str], threshold: int,
                          strict_filter: bool = True,
                          ihsg_chg: float | None = None) -> list[dict]:
        loop    = asyncio.get_event_loop()
        tasks   = [loop.run_in_executor(None, self._analyze_one, s, threshold, strict_filter, ihsg_chg) for s in symbols]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r is not None]
        return sorted(signals, key=lambda x: x["score"], reverse=True)

    async def _get_macro_async(self) -> dict:
        return await asyncio.get_event_loop().run_in_executor(None, self.macro.get_macro_context)

    async def _get_ihsg_async(self) -> float | None:
        return await asyncio.get_event_loop().run_in_executor(None, self.analyzer.fetch_ihsg)

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
                entry=signal["best_entry"], stop=signal["sl"],
                open_positions=len(plans), realized_r=realized_r, risk_off=risk_off,
            )
            if plan is None:
                logger.info(f"[{signal['symbol']}] plan skipped: {reason}")
                continue
            plans.append({
                **signal,
                "trade_date": trade_date, "risk_off": risk_off,
                "qty": plan.qty, "lot_count": plan.lot_count,
                "risk_amount": plan.risk_amount, "planned_notional": plan.planned_notional,
                "size_mode": plan.size_mode, "size_notes": plan.notes,
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
                candles=df, signal_timestamp=trade["signal_timestamp"],
                entry=float(trade["planned_entry"]), stop=float(trade["sl"]),
                tp1=float(trade["tp1"]), tp2=float(trade["tp2"]),
                qty=int(trade["qty"]), finalize=finalize,
            )
            self.storage.update_trade_result(trade["trade_date"], trade["symbol"], result)
            updates.append({**trade, **result})
        return updates

    async def _send_trade_update(self, reply_fn, trade_date: str, finalize: bool, empty_msg: str):
        trades = self.storage.get_active_trade_plans(trade_date) or \
                 self.storage.get_trade_plans(trade_date, include_finalized=True)
        if not trades:
            await reply_fn(empty_msg)
            return
        updates = self._evaluate_trades(trades, finalize=finalize)
        if not updates:
            await reply_fn("Gagal mengambil data terkini.")
            return
        summary = self.storage.get_today_summary(trade_date)
        await reply_fn(self.formatter.format_afternoon_update(updates, summary=summary), parse_mode="HTML")

    # ------------------------------------------------------------------ #
    #  SCHEDULER JOBS
    # ------------------------------------------------------------------ #
    async def job_morning_signal(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = self.session.now()
        if not is_trading_day(now.date()):
            return
        logger.info("🌅 Job pagi...")
        try:
            macro_task = self._get_macro_async()
            ihsg_task  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)
            signals = await self._scan_async(LQ45_SYMBOLS, HIGH_PROB_THRESHOLD, True, ihsg_chg)

            async def send(t, **kw): await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=t, **kw)
            await send(self.formatter.format_macro_context(macro), parse_mode="HTML")
            if not signals:
                await send(f"📭 Tidak ada setup hari ini (Skor≥{HIGH_PROB_THRESHOLD} & RRR≥{MIN_RRR}).")
                return
            plans = self._build_trade_plans(signals, macro)
            if plans:
                await send(self.formatter.format_morning_signal(plans), parse_mode="HTML")
        except Exception as exc:
            logger.error(f"job_morning_signal: {exc}")

    async def job_afternoon_update(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = self.session.now()
        if not is_trading_day(now.date()):
            return
        logger.info("🌇 Job sore...")
        try:
            trade_date = self._trade_date()
            if not self.storage.get_active_trade_plans(trade_date):
                return
            macro = await self._get_macro_async()
            async def send(t, **kw): await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=t, **kw)
            await send(self.formatter.format_macro_context(macro), parse_mode="HTML")
            await self._send_trade_update(send, trade_date, finalize=True,
                                          empty_msg="📭 Tidak ada trade plan aktif.")
        except Exception as exc:
            logger.error(f"job_afternoon_update: {exc}")

    # ------------------------------------------------------------------ #
    #  COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🤖 <b>IDX Day Trader Assistant — DUKUN KEUANGAN</b>\n\n"
            "📋 <b>Command Trading:</b>\n"
            "/signal     — Trade plan LQ45 hari ini\n"
            "/update     — Status P&L trade aktif\n"
            "/detail &lt;KODE&gt; — Analisa mendalam saham\n"
            "/top        — Top volume & gainers LQ45\n"
            "/macro      — Kondisi makro global\n"
            "/performa   — Win rate & history 30 hari\n\n"
            "🔔 <b>Price Alert:</b>\n"
            "/alert &lt;KODE&gt; &lt;HARGA&gt; [atas/bawah] — Set alert\n"
            "/alerts     — Lihat semua alert aktif\n"
            "/delalert &lt;KODE&gt; — Hapus alert saham\n\n"
            "📋 <b>Watchlist:</b>\n"
            "/watchlist  — Daftar pantau\n"
            "/watch &lt;KODE&gt; — Tambah ke watchlist\n"
            "/unwatch &lt;KODE&gt; — Hapus dari watchlist\n\n"
            "⚙️ <b>Pengaturan:</b>\n"
            "/setmodal &lt;juta&gt; — Set modal trading\n"
            "/setrisk &lt;pct&gt;  — Set risk per trade\n"
            "/reset      — Reset memory percakapan AI\n\n"
            "🤖 <b>AI Chat:</b>\n"
            "Kirim pesan atau pertanyaan trading langsung!\n"
            "📸 Kirim screenshot chart untuk analisa visual!\n\n"
            "⏰ <b>Scheduler:</b> 09:25 & 15:25 WIB (auto)\n"
            "<i>⚠️ Bukan rekomendasi finansial.</i>",
            parse_mode="HTML",
        )

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reset conversation memory user."""
        user_id = str(update.effective_user.id)
        self.conv_store.clear(user_id)
        await update.message.reply_text("🔄 Memory percakapan direset. Mulai sesi baru!")

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🌍 Mengambil data makro...")
        try:
            macro = await self._get_macro_async()
            await update.message.reply_text(self.formatter.format_macro_standalone(macro), parse_mode="HTML")
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
                "⚠️ <b>Waktu kurang ideal untuk entry.</b>\n"
                "Sinyal tetap ditampilkan untuk referensi.",
                parse_mode="HTML",
            )
        await update.message.reply_text("🔎 Menganalisa LQ45 + makro, tunggu ~20 detik...")
        macro_task = self._get_macro_async()
        ihsg_task  = self._get_ihsg_async()
        macro, ihsg_chg = await asyncio.gather(macro_task, ihsg_task)
        signals = await self._scan_async(LQ45_SYMBOLS, HIGH_PROB_THRESHOLD, True, ihsg_chg)
        await update.message.reply_text(self.formatter.format_macro_context(macro), parse_mode="HTML")
        if not signals:
            await update.message.reply_text(f"📭 Tidak ada setup (Skor≥{HIGH_PROB_THRESHOLD} & RRR≥{MIN_RRR}).")
            return
        plans = self._build_trade_plans(signals, macro)
        if plans:
            await update.message.reply_text(self.formatter.format_morning_signal(plans), parse_mode="HTML")
        else:
            await update.message.reply_text("📭 Tidak ada trade plan lolos risk engine.")

    async def cmd_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("⏳ Menghitung P/L...")
        trade_date = self._trade_date()
        macro      = await self._get_macro_async()
        await update.message.reply_text(self.formatter.format_macro_context(macro), parse_mode="HTML")
        await self._send_trade_update(
            update.message.reply_text, trade_date, finalize=False,
            empty_msg="📭 Belum ada trade plan. Jalankan /signal dulu.",
        )

    async def cmd_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("⚠️ Contoh: /detail BBCA")
            return
        symbol = context.args[0].upper().replace(".JK", "")
        await update.message.reply_text(f"🔬 Menganalisa {symbol}...")
        try:
            loop    = asyncio.get_event_loop()
            macro_t = self._get_macro_async()
            ihsg_t  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_t, ihsg_t)
            res = await loop.run_in_executor(None, self._analyze_one, symbol, 0, False, ihsg_chg)
            await update.message.reply_text(self.formatter.format_macro_context(macro), parse_mode="HTML")
            if res:
                await update.message.reply_text(self.formatter.format_detail(res), parse_mode="HTML")
            else:
                await update.message.reply_text(f"❌ Data {symbol} tidak ditemukan.")
        except Exception as exc:
            logger.error(f"cmd_detail [{symbol}]: {exc}")
            await update.message.reply_text(f"⚠️ Error saat menganalisa {symbol}.")

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📊 Memindai LQ45, tunggu ~20 detik...")
        try:
            macro_t = self._get_macro_async()
            ihsg_t  = self._get_ihsg_async()
            macro, ihsg_chg = await asyncio.gather(macro_t, ihsg_t)
            all_data = await self._scan_async(LQ45_SYMBOLS, 0, True, ihsg_chg)
            await update.message.reply_text(self.formatter.format_macro_context(macro), parse_mode="HTML")
            if not all_data:
                await update.message.reply_text("📭 Tidak ada data lolos filter.")
                return
            top_vol     = sorted(all_data, key=lambda x: x["volume_ratio"], reverse=True)[:3]
            top_gainers = sorted(all_data, key=lambda x: x["change_pct"],   reverse=True)[:3]
            await update.message.reply_text(self.formatter.format_top(top_vol, top_gainers), parse_mode="HTML")
        except Exception as exc:
            logger.error(f"cmd_top: {exc}")
            await update.message.reply_text("⚠️ Error saat memindai.")

    async def cmd_performa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📈 Mengambil data performa...")
        try:
            history = self.storage.get_closed_trades(days=30)
            await update.message.reply_text(
                self.formatter.format_performance(history, period_days=30), parse_mode="HTML"
            )
        except Exception as exc:
            logger.error(f"cmd_performa: {exc}")
            await update.message.reply_text("⚠️ Gagal mengambil data performa.")

    async def cmd_setmodal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(f"💰 Modal: Rp {self.risk.account_size/1e6:.0f}jt\nUbah: /setmodal 10")
            return
        try:
            self.risk.account_size = float(context.args[0]) * 1_000_000
            await update.message.reply_text(f"✅ Modal: <b>Rp {context.args[0]} juta</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("⚠️ Format: /setmodal 10")

    async def cmd_setrisk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(f"⚡ Risk: {self.risk.risk_per_trade_pct*100:.2f}%\nUbah: /setrisk 1.0")
            return
        try:
            pct = float(context.args[0])
            if not 0.1 <= pct <= 5:
                await update.message.reply_text("⚠️ Risk harus 0.1%–5%")
                return
            self.risk.risk_per_trade_pct = pct / 100
            await update.message.reply_text(f"✅ Risk: <b>{pct}%</b>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("⚠️ Format: /setrisk 1.0")

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
        elif len(wl) >= 10:
            await update.message.reply_text("Watchlist penuh (maks 10).")
        else:
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
        await update.message.reply_text(f"🔍 Menganalisa {len(symbols)} saham...")
        ihsg_chg = await self._get_ihsg_async()
        results  = await self._scan_async(symbols, 0, False, ihsg_chg)
        if not results:
            await update.message.reply_text("Gagal mengambil data.")
            return
        msg = "📋 <b>Watchlist Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in results:
            rek  = "💪 BUY" if s["score"] >= 75 else "👀 WATCH" if s["score"] >= 50 else "🚫 AVOID"
            vok  = "✅" if s["price"] > s.get("vwap", 0) else "⚠️"
            mtf  = "✅" if s.get("mtf_trend") == "daily_uptrend" else "⚠️" if s.get("mtf_trend") == "daily_downtrend" else "➡️"
            sign = "+" if s["change_pct"] > 0 else ""
            msg += (
                f"<b>{s['symbol']}</b> {'💪' if s.get('rs_stronger') else ''} — "
                f"Rp {s['price']:,} ({sign}{s['change_pct']}%)\n"
                f"RSI:{s['rsi']} ADX:{s.get('adx','—')} MTF:{mtf} VWAP:{vok}\n"
                f"Entry:Rp {s.get('best_entry',s['price']):,} | Skor:{s['score']} → {rek}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML")

    # ── Price Alert ─────────────────────────────────────────────────────
    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) < 2:
            await update.message.reply_text("⚠️ Format: /alert BBCA 9200 [atas/bawah]")
            return
        
        symbol = context.args[0].upper().replace(".JK", "")
        try:
            target = float(context.args[1])
        except ValueError:
            await update.message.reply_text("⚠️ Harga harus angka.")
            return
            
        direction = "atas"
        if len(context.args) >= 3:
            d_arg = context.args[2].lower()
            if d_arg in ["bawah", "down", "below"]:
                direction = "bawah"
        
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        
        success = self.alert_mgr.add_alert(user_id, chat_id, symbol, target, direction)
        if success:
            await update.message.reply_text(
                f"🔔 Alert dipasang: <b>{symbol}</b> saat harga {'≥' if direction == 'atas' else '≤'} Rp {int(target):,}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("⚠️ Gagal: Maksimum 5 alert aktif per user.")

    async def cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        alerts = self.alert_mgr.get_alerts(user_id)
        if not alerts:
            await update.message.reply_text("📭 Kamu tidak memiliki alert aktif.")
            return
            
        msg = "🔔 <b>Alert Aktif Kamu</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for a in alerts:
            msg += (
                f"• <b>{a['symbol']}</b>: {'≥' if a['direction'] == 'atas' else '≤'} "
                f"Rp {int(a['target']):,}\n"
            )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_delalert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("⚠️ Format: /delalert BBCA")
            return
        
        symbol = context.args[0].upper().replace(".JK", "")
        user_id = str(update.effective_user.id)
        count = self.alert_mgr.remove_alert(user_id, symbol)
        
        if count > 0:
            await update.message.reply_text(f"🗑️ {count} alert <b>{symbol}</b> dihapus.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ Tidak ada alert untuk {symbol}.")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming chart screenshots."""
        if not self.ai_active:
            await update.message.reply_text("⚠️ AI sedang tidak aktif.")
            return

        await update.message.reply_text("🔬 Menganalisa chart, tunggu sebentar...")
        try:
            photo_file = await update.message.photo[-1].get_file()
            img_bytes  = await photo_file.download_as_bytearray()
            
            # Additional context from caption if any
            caption = update.message.caption or ""
            
            analysis = await analyze_chart_image(self.model, bytes(img_bytes), caption)
            await update.message.reply_text(analysis, parse_mode="Markdown")
        except Exception as exc:
            logger.error(f"handle_photo error: {exc}")
            await update.message.reply_text("⚠️ Gagal menganalisa gambar. Pastikan formatnya benar.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle non-command messages using Gemini AI — Pro Trader Edition."""
        if not self.ai_active:
            return

        user_text = update.message.text
        if not user_text:
            return

        logger.info(f"AI Chat from {update.effective_user.first_name}: {user_text[:60]}...")

        try:
            # ── Kumpulkan konteks market real-time ─────────────────────
            market_context = ""
            text_lower     = user_text.lower()

            # Selalu fetch IHSG untuk context
            ihsg_chg = await self._get_ihsg_async()
            if ihsg_chg is not None:
                arah  = "menguat" if ihsg_chg > 0 else "melemah"
                market_context += f"- IHSG hari ini {arah} {ihsg_chg:+.2f}%\n"

            # Fetch makro jika relevan
            if any(k in text_lower for k in [
                "makro", "macro", "global", "dolar", "dxy", "fed", "oil", "minyak",
                "ihsg", "market", "bursa", "sentimen", "vix", "nikel", "batubara", "emas"
            ]):
                try:
                    macro = await self._get_macro_async()
                    data  = macro.get("data", {})
                    for ticker, d in data.items():
                        market_context += f"- {d['label']}: {d['value']:,} ({d['change_pct']:+.2f}%)\n"
                    if macro.get("is_risk_off"):
                        market_context += "- ⚠️ KONDISI RISK-OFF AKTIF\n"
                except Exception:
                    pass

            # Fetch analisa saham jika ada kode saham disebutkan
            import re
            saham_mentioned = re.findall(r'\b([A-Z]{4})\b', user_text.upper())
            saham_context   = ""
            lq45_set        = set(LQ45_SYMBOLS)
            for kode in saham_mentioned[:2]:   # max 2 saham per query
                if kode in lq45_set:
                    try:
                        loop = asyncio.get_event_loop()
                        res  = await loop.run_in_executor(
                            None, self._analyze_one, kode, 0, False, ihsg_chg
                        )
                        if res:
                            saham_context += (
                                f"\nData teknikal ${kode} saat ini:\n"
                                f"- Harga: Rp {res['price']:,}\n"
                                f"- Best Entry: Rp {res['best_entry']:,} ({res['entry_type']})\n"
                                f"- TP1: Rp {res['tp1']:,} | TP2: Rp {res['tp2']:,}\n"
                                f"- SL: Rp {res['sl']:,}\n"
                                f"- RSI: {res['rsi']} | ADX: {res['adx']} | Skor: {res['score']}/100\n"
                                f"- Trend 15m: {res['market_cond']} | MTF Daily: {res['mtf_trend']}\n"
                                f"- VWAP: {'Above ✅' if res['price'] > res['vwap'] else 'Below ⚠️'} | "
                                f"OBV: {'Konfirmasi ✅' if res['obv_ok'] else 'Divergence ⚠️'}\n"
                                f"- Sinyal: {res['alasan']}\n"
                            )
                    except Exception:
                        pass

            # ── System Prompt — Pro Trader IDX ─────────────────────────
            system_prompt = """Kamu adalah DUKUN KEUANGAN — AI trading assistant untuk pasar saham IDX (BEI) yang dibangun khusus untuk day trader profesional Indonesia.

                IDENTITAS & KARAKTER:
                - Seorang veteran trader IDX dengan pengalaman 15+ tahun
                - Menguasai analisa teknikal (Elliot Wave, Wyckoff Method, ICT Concepts, Smart Money Concept)
                - Bicara seperti mentor trading senior: tegas, lugas, jujur, terkadang blak-blakan tapi selalu berbasis data
                - Pakai bahasa Indonesia yang natural + istilah trading IDX yang umum
                - Tidak menggurui, tapi mengedukasi dengan contoh nyata

                KEAHLIAN UTAMA:
                1. ANALISA TEKNIKAL MENDALAM
                - Support/Resistance multi-timeframe (1m, 5m, 15m, 1H, Daily)
                - Indikator: EMA, VWAP, RSI, Stochastic, MACD, ADX, Bollinger Bands, OBV
                - Pattern: Hammer, Engulfing, Doji, Head & Shoulders, Cup & Handle, Bull/Bear Flag
                - Smart Money Concept: liquidity sweep, order block, FVG (Fair Value Gap)
                - Volume Analysis: volume spike, accumulation/distribution, climax volume

                2. TRADE MANAGEMENT PROFESIONAL
                - Entry: market order vs limit order, best entry zone (pullback ke VWAP/Support/EMA)
                - TP bertingkat: TP1 parsial (50-70%) di resistance terdekat, TP2 runner di Fibonacci 1.618
                - SL wajib: selalu di bawah swing low terdekat, bukan flat persentase
                - Trailing stop setelah TP1 tercapai: geser SL ke breakeven
                - Position sizing: risk 1-2% per trade, max 3 posisi bersamaan
                - RRR minimum 1:1.3 sebelum entry

                3. PSIKOLOGI TRADING
                - FOMO awareness: jangan kejar saham yang sudah lari >3% dari open
                - Revenge trading: istirahat setelah 2x loss berturut-turut
                - Overtrading: max 3 trade per hari untuk day trading
                - Cut loss tanpa rasa sakit: SL adalah biaya berbisnis, bukan kekalahan

                4. KONTEKS IDX SPESIFIK
                - Jam aman entry: 09:15-11:45 dan 13:45-14:55 WIB
                - Hindari: pre-opening (sebelum 09:15), jeda siang, pre-closing (setelah 14:55)
                - LQ45 focus: pilih saham dengan volume >5jt lembar/hari untuk likuiditas
                - Biaya trading IDX: buy 0.15% + sell 0.25% + estimasi slippage 0.05%
                - Auto rejection IDX: +25%/-25% dari harga acuan (ARA/ARB)

                5. RISK-OFF AWARENESS
                - Saat IHSG turun >1.5%: kurangi ukuran posisi 50%, prioritas cut loss
                - Saat VIX tinggi (>25): hindari saham volatile, fokus defensif (BBCA, TLKM, UNTR)
                - Saat DXY naik tajam: tekanan pada Rupiah, hati-hati sektor konsumer & perbankan

                CARA MENJAWAB:
                - Langsung ke inti, tidak bertele-tele
                - Selalu sertakan level harga spesifik saat bicara support/resistance
                - Format jawaban: singkat tapi padat, gunakan emoji secukupnya
                - Untuk analisa saham: selalu sebut entry zone, TP, SL, dan RRR
                - Untuk edukasi: gunakan analogi yang mudah dipahami trader Indonesia

                BATASAN:
                - Tidak memberikan rekomendasi beli/jual yang bersifat absolut
                - Selalu akhiri dengan: "DYOR — keputusan ada di tanganmu."
                - Tidak membahas topik di luar trading/investasi saham
                - Tidak membahas saham gorengan tanpa disclaimer risiko tinggi"""

            # ── Bangun full prompt ──────────────────────────────────────
            context_block = ""
            if market_context:
                context_block += f"\n📊 DATA PASAR REAL-TIME:\n{market_context}"
            if saham_context:
                context_block += f"\n📈 ANALISA TEKNIKAL BOT:{saham_context}"

            full_prompt = (
                f"{system_prompt}"
                f"{context_block}"
                f"\n\n{'─'*40}"
                f"\nUser: {user_text}"
                f"\n\nDukun Keuangan:"
            )

            # ── Kirim ke Gemini ─────────────────────────────────────────
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.model.generate_content,
                        full_prompt,
                        request_options={"timeout": 60}
                    ),
                    timeout=65.0
                )

                reply = response.text.strip()

                # Pastikan disclaimer selalu ada jika bicara saham
                if saham_mentioned and "DYOR" not in reply:
                    reply += "\n\n_DYOR — keputusan ada di tanganmu._"

                # Telegram max 4096 chars — potong kalau terlalu panjang
                if len(reply) > 4000:
                    reply = reply[:3950] + "\n\n_...(terpotong, tanya lebih spesifik)_"

                await update.message.reply_text(reply, parse_mode="Markdown")

            except asyncio.TimeoutError:
                logger.error("Gemini request timed out.")
                await update.message.reply_text(
                    "⚠️ AI-nya lagi mikir keras, timeout. Coba tanya lagi dengan pertanyaan yang lebih spesifik."
                )

        except Exception as exc:
            logger.error(f"Gemini error: {exc}")
            await update.message.reply_text(
                "⚠️ Ada gangguan teknis pada AI. Coba lagi sesaat."
            )

    # ------------------------------------------------------------------ #
    #  MAIN RUNNER
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        defaults = Defaults(tzinfo=self.tz)
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).defaults(defaults).build()

        # Commands
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
            ("reset",     self.cmd_reset),
            ("alert",     self.cmd_alert),
            ("alerts",    self.cmd_alerts),
            ("delalert",  self.cmd_delalert),
        ]:
            app.add_handler(CommandHandler(cmd, fn))

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        # Schedulers
        jq = app.job_queue
        jq.run_daily(self.job_morning_signal,   time(hour=9,  minute=25), days=(0,1,2,3,4))
        jq.run_daily(self.job_afternoon_update, time(hour=15, minute=25), days=(0,1,2,3,4))

        # Background tasks
        self.monitor   = SignalMonitor(app, self.storage)
        self.alert_mgr = PriceAlertManager(app)

        async def _on_startup(application):
            asyncio.create_task(self.monitor.run_loop(TELEGRAM_CHAT_ID, self._trade_date))
            asyncio.create_task(self.alert_mgr.run_loop())
            logger.info("✅ Monitor TP/SL + Price Alert aktif.")

        app.post_init = _on_startup

        logger.info("🚀 Bot v5 siap! 17 commands + AI chat + chart vision + price alert.")
        app.run_polling()


if __name__ == "__main__":
    IDXDayTraderBot().run()
