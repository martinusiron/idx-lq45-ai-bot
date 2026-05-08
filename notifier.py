import logging

logger = logging.getLogger(__name__)


class TelegramFormatter:

    # ------------------------------------------------------------------ #
    #  MACRO CONTEXT
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_context(macro: dict) -> str:
        data        = macro.get('data', {})
        warnings    = macro.get('warnings', [])
        is_risk_off = macro.get('is_risk_off', False)
        risk_mode   = macro.get('risk_mode', 'normal')

        type_emoji = {
            'index':     '📊',
            'yield':     '📈',
            'commodity': '⛽',
            'sentiment': '😨',
        }

        msg = "🌍 <b>Kondisi Makro Global</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"

        for ticker, d in data.items():
            emoji = type_emoji.get(d['type'], '•')
            chg   = d['change_pct']
            sign  = "+" if chg > 0 else ""
            arrow = "🔴" if chg < -0.5 else "🟢" if chg > 0.5 else "⚪"
            msg  += f"{emoji} {d['label']}: <b>{d['value']:,}</b>  {arrow} {sign}{chg}%\n"

        if warnings:
            msg += "\n⚠️ <b>Warning Aktif:</b>\n"
            for w in warnings:
                msg += f"  • {w}\n"

        if is_risk_off:
            mode_text = "ukuran posisi diperkecil" if risk_mode == "reduce" else "trade baru diblokir"
            msg += f"\n🚨 <b>KONDISI RISK-OFF</b> — {mode_text}\n"
        else:
            msg += "\n✅ Kondisi makro relatif kondusif\n"

        return msg

    # ------------------------------------------------------------------ #
    #  MORNING SIGNAL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_morning_signal(signals: list[dict]) -> str:
        top = sorted(signals, key=lambda x: x['score'], reverse=True)[:3]
        mkt_emoji = {'trending_up': '📈', 'sideways': '➡️', 'trending_down': '📉'}

        msg = "🔔 <b>SINYAL PAGI — IDX Day Trader</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, s in enumerate(top, 1):
            cond     = mkt_emoji.get(s.get('market_cond', ''), '❓')
            obv      = "✅" if s.get('obv_ok') else "⚠️"
            sup      = "🛡️" if s.get('near_support') else ""
            entry    = s.get('best_entry', s['price'])
            etype    = s.get('entry_type', 'market')
            tp1      = s.get('tp1', s.get('tp', 0))
            tp2      = s.get('tp2', 0)
            sl       = s['sl']
            tp1_pct  = round((tp1 - entry) / entry * 100, 1) if entry > 0 else 0
            tp2_pct  = round((tp2 - entry) / entry * 100, 1) if entry > 0 and tp2 > 0 else 0
            sl_pct   = round((entry - sl) / entry * 100, 1) if entry > 0 else 0

            entry_label = {
                'market':  '🟡 Market (agresif)',
                'vwap':    '🔵 VWAP Pullback',
                'support': '🟢 Dekat Support',
                'bb_low':  '🟢 Lower BB',
            }.get(etype, '🟡 Market')

            msg += (
                f"<b>{i}. ${s['symbol']}</b>  {cond} {sup}\n"
                f"Harga Pasar : Rp {s['price']:,}\n"
                f"Best Entry  : <b>Rp {entry:,}</b>  ({entry_label})\n"
                f"TP1 (parsial): Rp {tp1:,}  <i>(+{tp1_pct}%)</i>\n"
                f"TP2 (runner) : Rp {tp2:,}  <i>(+{tp2_pct}%)</i>\n"
                f"SL (swing)   : Rp {sl:,}  <i>(-{sl_pct}%)</i>\n"
                f"RRR   : <b>1 : {s.get('rrr', 'N/A')}</b>\n"
                f"Ukuran Posisi: <b>{s.get('lot_count', 0):,} lot</b> / {s.get('qty', 0):,} saham\n"
                f"Notional: Rp {int(s.get('planned_notional', 0)):,} | Risk: Rp {int(s.get('risk_amount', 0)):,}\n"
                f"Skor  : {s['score']}/100\n"
                f"RSI {s['rsi']} | Stoch {s.get('stoch_k','—')} | ADX {s.get('adx','—')} | OBV {obv}\n"
                f"Vol {s['volume_ratio']}x | VWAP {'✅' if s['price'] > s.get('vwap', 0) else '⚠️'} | S/R: {s.get('support','-'):,}/{s.get('resistance','-'):,}\n"
                f"<i>{s['alasan']}</i>\n"
                f"<i>{s.get('size_notes', '')}</i>\n"
                f"{'━'*22}\n\n"
            )

        msg += "⚠️ <i>Bukan rekomendasi finansial. Gunakan manajemen risiko.</i>"
        return msg

    # ------------------------------------------------------------------ #
    #  AFTERNOON UPDATE
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_afternoon_update(updates: list[dict], summary: dict | None = None) -> str:
        msg = "📊 <b>UPDATE SORE — Hasil Hari Ini</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        total_pnl_amount = sum(u.get('pnl_amount', 0) for u in updates)
        total_r = sum(u.get('realized_r', 0) for u in updates)

        for u in updates:
            pnl_pct = u.get('pnl_pct', 0)
            fill_status = u.get('fill_status', 'PENDING')
            status_code = u.get('status', 'OPEN')
            if fill_status == "UNFILLED":
                status = "⚪ NO FILL"
                bar = "⚪"
            elif pnl_pct >= 2.0:
                status = f"✅ {status_code}"
                bar = "🟢" * min(max(int(pnl_pct), 1), 5)
            elif pnl_pct <= -1.0:
                status = f"🔴 {status_code}"
                bar = "🔴" * min(max(int(abs(pnl_pct)), 1), 5)
            else:
                status = f"🟡 {status_code}"
                bar = "🟡"

            sign = "+" if pnl_pct > 0 else ""
            msg += (
                f"<b>{u['symbol']}</b>  →  {status}\n"
                f"Entry Plan: Rp {int(u.get('planned_entry', 0)):,} | Last: Rp {int(u.get('last_price', 0)):,}\n"
                f"P/L: Rp {int(u.get('pnl_amount', 0)):,}  ({sign}{pnl_pct}%) | {u.get('realized_r', 0):+.2f}R\n"
                f"Events: {u.get('events', '-')} | {u.get('exit_reason', '-')}\n"
                f"{bar}\n\n"
            )

        msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"<b>Net Hari Ini: Rp {int(total_pnl_amount):,} | {total_r:+.2f}R</b>\n"
        if summary:
            msg += (
                f"Win/Loss: {summary.get('winners', 0)}/{summary.get('losers', 0)} | "
                f"Unfilled: {summary.get('unfilled', 0)}\n"
            )
        return msg

    # ------------------------------------------------------------------ #
    #  DETAIL
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_detail(s: dict) -> str:
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

        entry    = s.get('best_entry', s['price'])
        etype    = s.get('entry_type', 'market')
        tp1      = s.get('tp1', s.get('tp', 0))
        tp2      = s.get('tp2', 0)
        sl       = s['sl']
        tp1_pct  = round((tp1 - entry) / entry * 100, 1) if entry > 0 else 0
        tp2_pct  = round((tp2 - entry) / entry * 100, 1) if entry > 0 and tp2 > 0 else 0
        sl_pct   = round((entry - sl) / entry * 100, 1) if entry > 0 else 0

        cond_map = {
            'trending_up':   'Uptrend 📈',
            'sideways':      'Sideways ➡️',
            'trending_down': 'Downtrend 📉'
        }
        cond    = cond_map.get(s.get('market_cond', ''), 'Unknown')
        vwap_ok = s['price'] > s.get('vwap', 0)

        entry_label = {
            'market':  '🟡 Market (agresif)',
            'vwap':    '🔵 VWAP Pullback',
            'support': '🟢 Dekat Support',
            'bb_low':  '🟢 Lower BB',
        }.get(etype, '🟡 Market')

        msg = (
            f"📊 <b>Analisa: {s['symbol']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Harga Pasar  : Rp {s['price']:,}\n"
            f"Volume       : {vol_m} ({s['volume_ratio']}x rata-rata)\n"
            f"Pergerakan   : {'+' if s['change_pct'] > 0 else ''}{s['change_pct']}%\n\n"
            f"<b>Indikator Teknikal:</b>\n"
            f"  RSI (14)   : {s['rsi']} {'🔥' if s['rsi'] < 40 else '✅' if s['rsi'] < 60 else '⚠️'}\n"
            f"  Stochastic : {s.get('stoch_k', 'N/A')}\n"
            f"  MACD Hist  : {s.get('macd_hist', 'N/A')}\n"
            f"  ADX        : {s.get('adx', 'N/A')} {'💪' if s.get('adx', 0) > 35 else '✅' if s.get('adx', 0) > 25 else '⚠️'}\n"
            f"  VWAP       : Rp {s.get('vwap', 0):,}  {'✅ Above' if vwap_ok else '⚠️ Below'}\n"
            f"  BB %B      : {s.get('bb_pct', 'N/A')} {'🔥 Oversold' if s.get('bb_pct', 0.5) < 0.2 else ''}\n"
            f"  OBV        : {'✅ Konfirmasi' if s.get('obv_ok') else '⚠️ Divergence'}\n"
            f"  Support    : Rp {s.get('support', '-'):,} {'🛡️' if s.get('near_support') else ''}\n"
            f"  Resistance : Rp {s.get('resistance', '-'):,}\n"
            f"  ATR        : {s.get('atr', 'N/A')}\n"
            f"  Trend      : {cond}\n\n"
            f"<b>🎯 Setup Trading:</b>\n"
            f"  Best Entry  : <b>Rp {entry:,}</b>  ({entry_label})\n"
            f"  TP1 (parsial): Rp {tp1:,}  (+{tp1_pct}%)\n"
            f"  TP2 (runner) : Rp {tp2:,}  (+{tp2_pct}%)\n"
            f"  SL (swing)   : Rp {sl:,}  (-{sl_pct}%)\n"
            f"  RRR          : 1 : {s.get('rrr', 'N/A')}\n\n"
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
            msg += f"  {i}. <b>{s['symbol']}</b> — {s['volume_ratio']}x  (RSI: {s['rsi']} | ADX: {s.get('adx','—')})\n"

        msg += "\n🚀 <b>Gainers Terkuat:</b>\n"
        for i, s in enumerate(top_gainers, 1):
            msg += f"  {i}. <b>{s['symbol']}</b> — +{s['change_pct']}%  (Skor: {s['score']})\n"

        all_stocks = list({s['symbol']: s for s in top_vol + top_gainers}.values())
        best_rrr   = sorted(all_stocks, key=lambda x: x.get('rrr', 0), reverse=True)[:3]

        msg += "\n🎯 <b>RRR Terbaik:</b>\n"
        for i, s in enumerate(best_rrr, 1):
            vwap_ok = s['price'] > s.get('vwap', 0)
            msg += f"  {i}. <b>{s['symbol']}</b> — RRR 1:{s.get('rrr','N/A')}  VWAP {'✅' if vwap_ok else '⚠️'}\n"

        return msg

    # ------------------------------------------------------------------ #
    #  MACRO STANDALONE
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_macro_standalone(macro: dict) -> str:
        msg  = TelegramFormatter.format_macro_context(macro)
        data = macro.get('data', {})

        msg += "\n📌 <b>Dampak ke Sektor IDX:</b>\n"

        oil  = data.get('BZ=F', {})
        ni   = data.get('NI=F', {})
        coal = data.get('MTF=F', {})
        dxy  = data.get('DX-Y.NYB', {})

        if oil:
            arah = "positif ✅" if oil['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Minyak → BREN, MEDC, ENRG ({arah})\n"
        if ni:
            arah = "positif ✅" if ni['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Nikel  → INCO, MDKA, ANTM ({arah})\n"
        if coal:
            arah = "positif ✅" if coal['change_pct'] > 0 else "negatif ⚠️"
            msg += f"  • Batubara → ADRO, ITMG, PTBA ({arah})\n"
        if dxy:
            if dxy['change_pct'] > 0.3:
                msg += "  • DXY naik → tekanan Rupiah, banking & consumer negatif ⚠️\n"
            elif dxy['change_pct'] < -0.3:
                msg += "  • DXY turun → Rupiah menguat, inflow EM ✅\n"

        return msg
