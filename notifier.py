"""
notifier.py — Telegram message formatter untuk IDX Day Trader Bot.
Compatible dengan repo martinusiron/idx-lq45-ai-bot.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_ENTRY_LABEL = {
    "market":  "🟡 Market (agresif)",
    "vwap":    "🔵 VWAP Pullback",
    "support": "🟢 Dekat Support",
    "bb_low":  "🟢 Lower BB",
}
_MKT_EMOJI = {"trending_up": "📈", "sideways": "➡️", "trending_down": "📉"}
_MTF_EMOJI = {"daily_uptrend": "✅", "daily_downtrend": "⚠️", "daily_neutral": "➡️", "unknown": "❓"}


class TelegramFormatter:

    # ------------------------------------------------------------------ #
    #  MACRO CONTEXT
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_context(macro: dict) -> str:
        data        = macro.get("data", {})
        warnings    = macro.get("warnings", [])
        is_risk_off = macro.get("is_risk_off", False)

        type_emoji = {"index": "📊", "yield": "📈", "commodity": "⛽", "sentiment": "😨"}
        msg = "🌍 <b>Kondisi Makro Global</b>\n━━━━━━━━━━━━━━━━━━━━━\n"

        for ticker, d in data.items():
            chg   = d["change_pct"]
            sign  = "+" if chg > 0 else ""
            arrow = "🔴" if chg < -0.5 else "🟢" if chg > 0.5 else "⚪"
            msg  += f"{type_emoji.get(d['type'], '•')} {d['label']}: <b>{d['value']:,}</b>  {arrow} {sign}{chg}%\n"

        if warnings:
            msg += "\n⚠️ <b>Warning:</b>\n"
            for w in warnings:
                msg += f"  • {w}\n"

        msg += "\n🚨 <b>RISK-OFF MODE</b>\n" if is_risk_off else "\n✅ Makro kondusif\n"
        return msg

    # ------------------------------------------------------------------ #
    #  MORNING SIGNAL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_morning_signal(plans: list[dict]) -> str:
        top = sorted(plans, key=lambda x: x.get("score", 0), reverse=True)[:3]
        msg = "🔔 <b>TRADE PLAN PAGI — IDX Day Trader</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, s in enumerate(top, 1):
            entry  = s.get("best_entry", s.get("planned_entry", s.get("price", 0)))
            tp1    = s.get("tp1", 0)
            tp2    = s.get("tp2", 0)
            sl     = s.get("sl", 0)
            etype  = s.get("entry_type", "market")
            cond   = _MKT_EMOJI.get(s.get("market_cond", ""), "❓")
            mtf    = _MTF_EMOJI.get(s.get("mtf_trend", "unknown"), "❓")
            obv    = "✅" if s.get("obv_ok") else "⚠️"
            sup_ic = "🛡️" if s.get("near_support") else ""
            rs_ic  = "💪" if s.get("rs_stronger") else ""

            tp1_pct = round((tp1 - entry) / entry * 100, 1) if entry > 0 else 0
            tp2_pct = round((tp2 - entry) / entry * 100, 1) if entry > 0 and tp2 > 0 else 0
            sl_pct  = round((entry - sl) / entry * 100, 1)  if entry > 0 else 0

            lot_str = ""
            if s.get("lot_count"):
                mode = s.get("size_mode", "")
                lot_str = f"Lot : {s['lot_count']} lot ({s.get('qty',0):,} lbr)"
                if mode == "reduced":
                    lot_str += " ⚠️ diperkecil (risk-off)"

            msg += (
                f"<b>{i}. ${s['symbol']}</b>  {cond} {sup_ic} {rs_ic}\n"
                f"Harga Pasar  : Rp {s.get('price', entry):,}\n"
                f"Best Entry   : <b>Rp {entry:,}</b>  ({_ENTRY_LABEL.get(etype, etype)})\n"
                f"TP1 (parsial): Rp {tp1:,}  <i>(+{tp1_pct}%)</i>\n"
                f"TP2 (runner) : Rp {tp2:,}  <i>(+{tp2_pct}%)</i>\n"
                f"SL (swing)   : Rp {sl:,}  <i>(-{sl_pct}%)</i>\n"
                f"RRR  : <b>1 : {s.get('rrr', 'N/A')}</b>\n"
            )
            if lot_str:
                msg += f"{lot_str}\n"
            msg += (
                f"Skor : {s.get('score', 0)}/100\n"
                f"RSI {s.get('rsi','—')} | ADX {s.get('adx','—')} | MTF {mtf} | OBV {obv}\n"
                f"Vol {s.get('volume_ratio','—')}x | S/R {s.get('support','-'):,}/{s.get('resistance','-'):,}\n"
                f"<i>{s.get('alasan', '')}</i>\n"
                f"{'━'*22}\n\n"
            )

        msg += "⚠️ <i>Bukan rekomendasi finansial. Gunakan manajemen risiko.</i>"
        return msg

    # ------------------------------------------------------------------ #
    #  AFTERNOON UPDATE
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_afternoon_update(updates: list[dict], summary: dict | None = None) -> str:
        msg = "📊 <b>UPDATE SORE — Hasil Hari Ini</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"

        for u in updates:
            pnl    = float(u.get("pnl_pct", 0))
            status = u.get("status", "OPEN")
            price  = u.get("last_price") or u.get("exit_price") or u.get("current_price", 0)

            if "TP2" in status:
                emoji, label = "🚀", "TP2 HIT"
            elif "TP1" in status:
                emoji, label = "✅", "TP1 HIT"
            elif "SL" in status:
                emoji, label = "🔴", "SL HIT"
            else:
                emoji, label = "⏳", "HOLD"

            bar  = ("🟢" * min(int(pnl), 5)) if pnl >= 2 else ("🔴" * min(int(abs(pnl)), 5)) if pnl <= -1.5 else "🟡"
            sign = "+" if pnl > 0 else ""
            msg += (
                f"{emoji} <b>{u['symbol']}</b>  →  {label}\n"
                f"Harga : Rp {int(price):,}  ({sign}{pnl}%)\n"
                f"{bar}\n\n"
            )

        if summary:
            total_r  = summary.get("total_realized_r", 0)
            total_pnl= summary.get("total_pnl_pct", 0)
            wins     = summary.get("wins", 0)
            losses   = summary.get("losses", 0)
            msg += (
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Ringkasan Hari Ini:</b>\n"
                f"W/L   : {wins}W / {losses}L\n"
                f"Net P/L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}%\n"
                f"Total R: {'+' if total_r >= 0 else ''}{total_r:.2f}R\n"
            )
        return msg

    # ------------------------------------------------------------------ #
    #  DETAIL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_detail(s: dict) -> str:
        score = s.get("score", 0)
        if score >= 80:
            rek, rik = "STRONG BUY", "💪"
        elif score >= 65:
            rek, rik = "BUY",        "✅"
        elif score >= 50:
            rek, rik = "WATCH",      "👀"
        else:
            rek, rik = "AVOID",      "🚫"

        entry   = s.get("best_entry", s.get("price", 0))
        tp1     = s.get("tp1", 0)
        tp2     = s.get("tp2", 0)
        sl      = s.get("sl", 0)
        tp1_pct = round((tp1 - entry) / entry * 100, 1) if entry > 0 else 0
        tp2_pct = round((tp2 - entry) / entry * 100, 1) if entry > 0 and tp2 > 0 else 0
        sl_pct  = round((entry - sl) / entry * 100, 1)  if entry > 0 else 0
        vwap_ok = s.get("price", 0) > s.get("vwap", 0)
        etype   = s.get("entry_type", "market")
        cond_map = {"trending_up": "Uptrend 📈", "sideways": "Sideways ➡️", "trending_down": "Downtrend 📉"}
        cond    = cond_map.get(s.get("market_cond", ""), "Unknown")
        mtf     = _MTF_EMOJI.get(s.get("mtf_trend", "unknown"), "❓")
        vol_m   = f"{s.get('volume_real', 0) / 1_000_000:.1f}M"

        msg = (
            f"📊 <b>Analisa: {s.get('symbol', '')}</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Harga Pasar  : Rp {s.get('price', 0):,}\n"
            f"Volume       : {vol_m} ({s.get('volume_ratio', 0)}x rata-rata)\n"
            f"Pergerakan   : {'+' if s.get('change_pct', 0) > 0 else ''}{s.get('change_pct', 0)}%\n\n"
            f"<b>Indikator Teknikal:</b>\n"
            f"  RSI (14)   : {s.get('rsi', 'N/A')} {'🔥' if s.get('rsi', 50) < 40 else '✅' if s.get('rsi', 50) < 60 else '⚠️'}\n"
            f"  Stochastic : {s.get('stoch_k', 'N/A')}\n"
            f"  MACD Hist  : {s.get('macd_hist', 'N/A')}\n"
            f"  ADX        : {s.get('adx', 'N/A')} {'💪' if s.get('adx', 0) > 35 else '✅' if s.get('adx', 0) > 25 else '⚠️'}\n"
            f"  VWAP       : Rp {s.get('vwap', 0):,}  {'✅ Above' if vwap_ok else '⚠️ Below'}\n"
            f"  BB %B      : {s.get('bb_pct', 'N/A')} {'🔥 Oversold' if s.get('bb_pct', 0.5) < 0.2 else ''}\n"
            f"  OBV        : {'✅ Konfirmasi' if s.get('obv_ok') else '⚠️ Divergence'}\n"
            f"  Support    : Rp {s.get('support', 0):,} {'🛡️' if s.get('near_support') else ''}\n"
            f"  Resistance : Rp {s.get('resistance', 0):,}\n"
            f"  ATR        : {s.get('atr', 'N/A')}\n"
            f"  Trend 15m  : {cond}\n"
            f"  MTF Daily  : {mtf}\n"
            f"  RS vs IHSG : {'💪 Lebih kuat' if s.get('rs_stronger') else 'Normal'}\n\n"
            f"<b>🎯 Setup Trading:</b>\n"
            f"  Best Entry  : <b>Rp {entry:,}</b>  ({_ENTRY_LABEL.get(etype, etype)})\n"
            f"  TP1 (parsial): Rp {tp1:,}  (+{tp1_pct}%)\n"
            f"  TP2 (runner) : Rp {tp2:,}  (+{tp2_pct}%)\n"
            f"  SL (swing)   : Rp {sl:,}  (-{sl_pct}%)\n"
            f"  RRR          : 1 : {s.get('rrr', 'N/A')}\n\n"
            f"Sinyal  : <i>{s.get('alasan', '')}</i>\n"
            f"Skor AI : {score}/100\n\n"
            f"<b>Rekomendasi: {rik} {rek}</b>\n\n"
            f"⚠️ <i>Bukan rekomendasi finansial.</i>"
        )
        return msg

    # ------------------------------------------------------------------ #
    #  TOP STOCKS
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_top(top_vol: list[dict], top_gainers: list[dict]) -> str:
        msg = "🏆 <b>TOP SAHAM LQ45 HARI INI</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"

        msg += "🔥 <b>Volume Tertinggi:</b>\n"
        for i, s in enumerate(top_vol, 1):
            mtf = _MTF_EMOJI.get(s.get("mtf_trend", "unknown"), "❓")
            msg += f"  {i}. <b>{s['symbol']}</b> — {s.get('volume_ratio',0)}x  (RSI:{s.get('rsi','—')} ADX:{s.get('adx','—')} MTF:{mtf})\n"

        msg += "\n🚀 <b>Gainers Terkuat:</b>\n"
        for i, s in enumerate(top_gainers, 1):
            rs = "💪" if s.get("rs_stronger") else ""
            msg += f"  {i}. <b>{s['symbol']}</b> {rs} — +{s.get('change_pct',0)}%  (Skor:{s.get('score',0)})\n"

        all_s    = list({s["symbol"]: s for s in top_vol + top_gainers}.values())
        best_rrr = sorted(all_s, key=lambda x: x.get("rrr", 0), reverse=True)[:3]
        msg += "\n🎯 <b>RRR Terbaik:</b>\n"
        for i, s in enumerate(best_rrr, 1):
            vok = "✅" if s.get("price", 0) > s.get("vwap", 0) else "⚠️"
            msg += f"  {i}. <b>{s['symbol']}</b> — RRR 1:{s.get('rrr','N/A')}  VWAP:{vok}\n"

        return msg

    # ------------------------------------------------------------------ #
    #  PERFORMA
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_performance(history: list[dict], period_days: int = 30) -> str:
        if not history:
            return "📭 Belum ada data performa. Mulai trading dulu!"

        total  = len(history)
        wins   = sum(1 for h in history if "TP" in h.get("status", ""))
        losses = sum(1 for h in history if "SL" in h.get("status", ""))
        wr     = round(wins / total * 100, 1) if total > 0 else 0
        avg_r  = round(sum(h.get("realized_r", 0) for h in history) / total, 2) if total > 0 else 0
        avg_pnl= round(sum(h.get("pnl_pct", 0) for h in history) / total, 2) if total > 0 else 0

        msg = (
            f"📊 <b>Performa {period_days} Hari Terakhir</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Total Signal : {total}\n"
            f"✅ Win (TP)  : {wins}\n"
            f"🔴 Loss (SL) : {losses}\n"
            f"⏳ Open      : {total - wins - losses}\n"
            f"Win Rate     : <b>{wr}%</b>\n"
            f"Avg P/L      : <b>{'+' if avg_pnl >= 0 else ''}{avg_pnl}%</b>\n"
            f"Avg R        : <b>{'+' if avg_r >= 0 else ''}{avg_r}R</b>\n\n"
            f"<b>5 Trade Terakhir:</b>\n"
        )
        for h in history[:5]:
            sym    = h.get("symbol", "?")
            status = h.get("status", "OPEN")
            pnl    = h.get("pnl_pct", 0)
            r      = h.get("realized_r", 0)
            emoji  = "✅" if "TP" in status else "🔴" if "SL" in status else "⏳"
            sign   = "+" if pnl >= 0 else ""
            msg   += f"  {emoji} {sym} — {sign}{pnl}%  ({r:+.1f}R)  [{status}]\n"
        return msg

    # ------------------------------------------------------------------ #
    #  MACRO STANDALONE
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_standalone(macro: dict) -> str:
        msg  = TelegramFormatter.format_macro_context(macro)
        data = macro.get("data", {})
        msg += "\n📌 <b>Dampak ke Sektor IDX:</b>\n"

        mapping = {
            "BZ=F":     ("⛽ Minyak",   "BREN, MEDC, ENRG"),
            "^SPGSIK":  ("🪨 Nikel",    "INCO, MDKA, ANTM"),
            "^COAL":    ("🪵 Batubara", "ADRO, ITMG, PTBA"),
            "GC=F":     ("🥇 Emas",     "ANTM (safe haven)"),
            "DX-Y.NYB": ("💵 DXY",      "Banking, Consumer"),
        }
        for ticker, (label, sectors) in mapping.items():
            d = data.get(ticker, {})
            if not d:
                continue
            chg  = d.get("change_pct", 0)
            arah = "positif ✅" if chg > 0 else "negatif ⚠️"
            if ticker == "DX-Y.NYB":
                arah = "tekanan Rupiah ⚠️" if chg > 0.3 else "Rupiah menguat ✅" if chg < -0.3 else "stabil ⚪"
            msg += f"  • {label} ({'+' if chg >= 0 else ''}{chg}%) → {sectors}: {arah}\n"
        return msg