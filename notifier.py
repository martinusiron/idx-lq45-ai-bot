import logging

logger = logging.getLogger(__name__)


class TelegramFormatter:

    # ------------------------------------------------------------------ #
    #  MACRO CONTEXT BLOCK (dipakai di morning signal & standalone)
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_context(macro: dict) -> str:
        """Render blok kondisi makro global."""
        data     = macro.get('data', {})
        warnings = macro.get('warnings', [])
        is_risk_off = macro.get('is_risk_off', False)

        # Emoji per tipe
        type_emoji = {
            'index':     '📊',
            'yield':     '📈',
            'commodity': '⛽',
            'sentiment': '😨',
        }

        msg = "🌍 <b>Kondisi Makro Global</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"

        for ticker, d in data.items():
            emoji  = type_emoji.get(d['type'], '•')
            chg    = d['change_pct']
            sign   = "+" if chg > 0 else ""
            arrow  = "🔴" if chg < -0.5 else "🟢" if chg > 0.5 else "⚪"
            msg += f"{emoji} {d['label']}: <b>{d['value']:,}</b>  {arrow} {sign}{chg}%\n"

        if warnings:
            msg += "\n⚠️ <b>Warning Aktif:</b>\n"
            for w in warnings:
                msg += f"  • {w}\n"

        if is_risk_off:
            msg += "\n🚨 <b>KONDISI RISK-OFF</b> — pertimbangkan ukuran posisi lebih kecil\n"
        else:
            msg += "\n✅ Kondisi makro relatif kondusif\n"

        return msg

    # ------------------------------------------------------------------ #
    #  MORNING SIGNAL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_morning_signal(signals: list[dict], macro: dict | None = None) -> str:
        top = sorted(signals, key=lambda x: x['score'], reverse=True)[:3]
        mkt_emoji = {'trending_up': '📈', 'sideways': '➡️', 'trending_down': '📉'}

        msg = "🔔 <b>SINYAL PAGI — IDX Day Trader</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        # Blok makro di atas sinyal
        if macro:
            msg += TelegramFormatter.format_macro_context(macro)
            msg += "\n"

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
    def format_afternoon_update(updates: list[dict], macro: dict | None = None) -> str:
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
        msg += f"<b>Net Hari Ini: {sign_total}{total_pnl:.2f}%</b>\n\n"

        # Macro summary singkat di update sore
        if macro:
            data = macro.get('data', {})
            ihsg = data.get('^JKSE', {})
            dxy  = data.get('DX-Y.NYB', {})
            if ihsg:
                sign_i = "+" if ihsg['change_pct'] > 0 else ""
                msg += f"📊 IHSG: {ihsg['value']:,}  ({sign_i}{ihsg['change_pct']}%)\n"
            if dxy:
                sign_d = "+" if dxy['change_pct'] > 0 else ""
                msg += f"💵 DXY: {dxy['value']}  ({sign_d}{dxy['change_pct']}%)\n"

        return msg

    # ------------------------------------------------------------------ #
    #  DETAIL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_detail(s: dict, macro: dict | None = None) -> str:
        vol_m = f"{s['volume_real'] / 1_000_000:.1f}M"
        score = s['score']

        if score >= 80:
            rek, rek_emoji = "STRONG BUY", "💪"
        elif score >= 65:
            rek, rek_emoji = "BUY",        "✅"
        elif score >= 50:
            rek, rek_emoji = "WATCH",      "👀"
        else:
            rek, rek_emoji = "AVOID",      "🚫"

        tp_pct = round((s['tp'] - s['price']) / s['price'] * 100, 1)
        sl_pct = round((s['price'] - s['sl']) / s['price'] * 100, 1)
        cond_map = {
            'trending_up':   'Uptrend 📈',
            'sideways':      'Sideways ➡️',
            'trending_down': 'Downtrend 📉'
        }
        cond = cond_map.get(s.get('market_cond', ''), 'Unknown')

        msg = (
            f"📊 <b>Analisa: {s['symbol']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Harga      : Rp {s['price']:,}\n"
            f"Volume     : {vol_m} ({s['volume_ratio']}x rata-rata)\n"
            f"Pergerakan : {'+' if s['change_pct'] > 0 else ''}{s['change_pct']}%\n\n"
            f"<b>Indikator Teknikal:</b>\n"
            f"  RSI (14)   : {s['rsi']} {'🔥' if s['rsi'] < 40 else '✅' if s['rsi'] < 60 else '⚠️'}\n"
            f"  Stochastic : {s.get('stoch_k', 'N/A')}\n"
            f"  MACD Hist  : {s.get('macd_hist', 'N/A')}\n"
            f"  ATR        : {s.get('atr', 'N/A')}\n"
            f"  Trend      : {cond}\n\n"
            f"<b>Setup Trading:</b>\n"
            f"  Entry : Rp {s['price']:,}\n"
            f"  TP    : Rp {s['tp']:,} (+{tp_pct}%)\n"
            f"  SL    : Rp {s['sl']:,} (-{sl_pct}%)\n"
            f"  RRR   : 1 : {s.get('rrr', 'N/A')}\n\n"
            f"Sinyal  : <i>{s['alasan']}</i>\n"
            f"Skor AI : {score}/100\n\n"
            f"<b>Rekomendasi: {rek_emoji} {rek}</b>\n"
        )

        # Append macro context di bagian bawah detail
        if macro:
            msg += f"\n{TelegramFormatter.format_macro_context(macro)}"

        msg += "\n⚠️ <i>Bukan rekomendasi finansial.</i>"
        return msg

    # ------------------------------------------------------------------ #
    #  TOP STOCKS
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_top(top_vol: list[dict], top_gainers: list[dict], macro: dict | None = None) -> str:
        msg = "🏆 <b>TOP SAHAM LQ45 HARI INI</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        if macro:
            msg += TelegramFormatter.format_macro_context(macro)
            msg += "\n"

        msg += "🔥 <b>Volume Tertinggi:</b>\n"
        for i, s in enumerate(top_vol, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — {s['volume_ratio']}x rata-rata  (RSI: {s['rsi']})\n"

        msg += "\n🚀 <b>Gainers Terkuat:</b>\n"
        for i, s in enumerate(top_gainers, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — +{s['change_pct']}%  (Skor: {s['score']})\n"

        all_stocks = list({s['symbol']: s for s in top_vol + top_gainers}.values())
        best_rrr   = sorted(all_stocks, key=lambda x: x.get('rrr', 0), reverse=True)[:3]

        msg += "\n🎯 <b>RRR Terbaik:</b>\n"
        for i, s in enumerate(best_rrr, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — RRR 1:{s.get('rrr', 'N/A')}\n"

        return msg

    # ------------------------------------------------------------------ #
    #  MACRO STANDALONE (untuk command /macro)
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_standalone(macro: dict) -> str:
        msg = TelegramFormatter.format_macro_context(macro)
        
        # Tambah penjelasan dampak ke sektor IDX
        data = macro.get('data', {})
        msg += "\n📌 <b>Dampak ke Sektor IDX:</b>\n"

        oil  = data.get('BZ=F', {})
        ni   = data.get('NI=F', {})
        coal = data.get('MTF=F', {})
        dxy  = data.get('DX-Y.NYB', {})

        if oil:
            arah = "positif ✅" if oil['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Minyak naik/turun → BREN, MEDC, ENRG ({arah})\n"
        if ni:
            arah = "positif ✅" if ni['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Nikel → INCO, MDKA, ANTM ({arah})\n"
        if coal:
            arah = "positif ✅" if coal['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Batubara → ADRO, ITMG, PTBA ({arah})\n"
        if dxy:
            if dxy['change_pct'] > 0.3:
                msg += "  • DXY naik → tekanan Rupiah, perbankan & consumer goods negatif ⚠️\n"
            elif dxy['change_pct'] < -0.3:
                msg += "  • DXY turun → Rupiah menguat, inflow ke emerging market ✅\n"

        return msg