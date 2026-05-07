import logging

logger = logging.getLogger(__name__)


class TelegramFormatter:
    """
    Improved formatter dengan:
    - RRR (Risk-Reward Ratio) ditampilkan
    - Market condition info
    - Stochastic & MACD summary
    - Format lebih informatif untuk morning signal
    - Top saham diurutkan by score (bukan hanya volume/change)
    """

    # ------------------------------------------------------------------ #
    #  MORNING SIGNAL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_morning_signal(signals: list[dict]) -> str:
        # Sort by score descending, tampilkan max 3
        top = sorted(signals, key=lambda x: x['score'], reverse=True)[:3]

        mkt_emoji = {'trending_up': '📈', 'sideways': '➡️', 'trending_down': '📉'}

        msg = "🔔 <b>SINYAL PAGI — IDX Day Trader</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, s in enumerate(top, 1):
            tp_pct = round((s['tp'] - s['price']) / s['price'] * 100, 1)
            sl_pct = round((s['price'] - s['sl']) / s['price'] * 100, 1)
            cond   = mkt_emoji.get(s.get('market_cond', ''), '❓')

            msg += (
                f"<b>{i}. ${s['symbol']}</b>  {cond}\n"
                f"Entry  : <b>Rp {s['price']:,}</b>\n"
                f"TP     : Rp {s['tp']:,}  <i>(+{tp_pct}%)</i>\n"
                f"SL     : Rp {s['sl']:,}  <i>(-{sl_pct}%)</i>\n"
                f"RRR    : <b>1 : {s.get('rrr', 'N/A')}</b>\n"
                f"Skor   : {s['score']}/100\n"
                f"Sinyal : <i>{s['alasan']}</i>\n"
                f"RSI {s['rsi']} | Stoch {s.get('stoch_k', '—')} | Vol {s['volume_ratio']}x\n"
                f"{'━'*22}\n\n"
            )

        msg += "⚠️ <i>Bukan rekomendasi finansial. Selalu gunakan manajemen risiko.</i>"
        return msg

    # ------------------------------------------------------------------ #
    #  AFTERNOON UPDATE
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_afternoon_update(updates: list[dict]) -> str:
        msg = "📊 <b>UPDATE SORE — Hasil Hari Ini</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        total_pnl = sum(u['pnl'] for u in updates)

        for u in updates:
            pnl = u['pnl']
            if pnl >= 2.0:
                status = "✅ PROFIT"
                bar    = "🟢" * min(int(pnl), 5)
            elif pnl <= -1.5:
                status = "🔴 LOSS"
                bar    = "🔴" * min(int(abs(pnl)), 5)
            else:
                status = "⏳ HOLD"
                bar    = "🟡"

            sign = "+" if pnl > 0 else ""
            msg += (
                f"<b>{u['symbol']}</b>  →  {status}\n"
                f"Harga : Rp {u['current_price']:,}  ({sign}{pnl}%)\n"
                f"{bar}\n\n"
            )

        sign_total = "+" if total_pnl > 0 else ""
        msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>Net Portofolio Hari Ini: {sign_total}{total_pnl:.2f}%</b>\n"
        return msg

    # ------------------------------------------------------------------ #
    #  DETAIL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_detail(s: dict) -> str:
        vol_m = f"{s['volume_real'] / 1_000_000:.1f}M"
        score = s['score']

        if score >= 80:
            rek, rek_emoji = "STRONG BUY",  "💪"
        elif score >= 65:
            rek, rek_emoji = "BUY",         "✅"
        elif score >= 50:
            rek, rek_emoji = "WATCH",       "👀"
        else:
            rek, rek_emoji = "AVOID",       "🚫"

        tp_pct = round((s['tp'] - s['price']) / s['price'] * 100, 1)
        sl_pct = round((s['price'] - s['sl']) / s['price'] * 100, 1)
        cond_map = {'trending_up': 'Uptrend 📈', 'sideways': 'Sideways ➡️', 'trending_down': 'Downtrend 📉'}
        cond = cond_map.get(s.get('market_cond', ''), 'Unknown')

        msg = (
            f"📊 <b>Analisa: {s['symbol']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Harga Saat Ini : Rp {s['price']:,}\n"
            f"Volume         : {vol_m} ({s['volume_ratio']}x rata-rata)\n"
            f"Pergerakan     : {'+' if s['change_pct'] > 0 else ''}{s['change_pct']}%\n\n"
            f"<b>Indikator:</b>\n"
            f"  RSI (14)     : {s['rsi']} {'🔥' if s['rsi'] < 40 else '✅' if s['rsi'] < 60 else '⚠️'}\n"
            f"  Stochastic   : {s.get('stoch_k', 'N/A')}\n"
            f"  MACD Hist    : {s.get('macd_hist', 'N/A')}\n"
            f"  ATR          : {s.get('atr', 'N/A')}\n"
            f"  Kondisi Pasar: {cond}\n\n"
            f"<b>Setup Trading:</b>\n"
            f"  Entry : Rp {s['price']:,}\n"
            f"  TP    : Rp {s['tp']:,} (+{tp_pct}%)\n"
            f"  SL    : Rp {s['sl']:,} (-{sl_pct}%)\n"
            f"  RRR   : 1 : {s.get('rrr', 'N/A')}\n\n"
            f"Sinyal  : <i>{s['alasan']}</i>\n"
            f"Skor AI : {score}/100\n\n"
            f"<b>Rekomendasi: {rek_emoji} {rek}</b>\n\n"
            f"⚠️ <i>Bukan rekomendasi finansial.</i>"
        )
        return msg

    # ------------------------------------------------------------------ #
    #  TOP STOCKS
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_top(top_vol: list[dict], top_gainers: list[dict]) -> str:
        msg = "🏆 <b>TOP SAHAM LQ45 HARI INI</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        msg += "🔥 <b>Volume Tertinggi:</b>\n"
        for i, s in enumerate(top_vol, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — {s['volume_ratio']}x rata-rata  (RSI: {s['rsi']})\n"

        msg += "\n🚀 <b>Gainers Terkuat:</b>\n"
        for i, s in enumerate(top_gainers, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — +{s['change_pct']}%  (Skor: {s['score']})\n"

        # Tambahan: saham RRR terbaik
        all_stocks = list({s['symbol']: s for s in top_vol + top_gainers}.values())
        best_rrr = sorted(all_stocks, key=lambda x: x.get('rrr', 0), reverse=True)[:3]

        msg += "\n🎯 <b>RRR Terbaik (Risk-Reward):</b>\n"
        for i, s in enumerate(best_rrr, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — RRR 1:{s.get('rrr', 'N/A')}\n"

        return msg