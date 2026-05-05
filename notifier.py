import logging

logger = logging.getLogger(__name__)

class TelegramFormatter:
    # Mengubah format menjadi Text Generator untuk dipakai di main.py
    
    @staticmethod
    def format_morning_signal(signals):
        msg = "📈 <b>Rekomendasi Pagi (09:25 WIB)</b>\n\n"
        for i, s in enumerate(signals[:3], 1):
            msg += (f"<b>{i}. {s['symbol']}</b>\n"
                    f"Entry: {s['price']}\n"
                    f"TP: {s['tp']} (+4%)\n"
                    f"SL: {s['sl']}\n"
                    f"Alasan: {s['alasan']}\n\n")
        return msg

    @staticmethod
    def format_afternoon_update(updates):
        msg = "📉 <b>Update Sore (15:25 WIB)</b>\n\n"
        for s in updates:
            # Jika profit > 3% atau loss > 2.5%, status SELL
            if s['pnl'] >= 3.0 or s['pnl'] <= -2.5:
                status = "SELL ✅"
                alasan_akhir = "Target/SL Tercapai"
            else:
                status = "HOLD ⏳"
                alasan_akhir = "Momentum masih dipertahankan"

            msg += (f"<b>{s['symbol']} → {status}</b>\n"
                    f"Harga: {s['current_price']} ({s['pnl']}%)\n"
                    f"Alasan: {alasan_akhir}\n\n")
        return msg

    @staticmethod
    def format_detail(s):
        vol_m = f"{s['volume_real'] / 1000000:.1f}M"
        rek = "BUY" if s['score'] >= 75 else "HOLD" if s['score'] >= 50 else "SELL"
        
        msg = (f"📊 <b>{s['symbol']}</b>\n\n"
               f"Harga: {s['price']:,}\n"
               f"Volume: {vol_m}\n"
               f"Freq / Net: N/A (API Gratis)\n\n"
               f"<b>Analisa:</b>\n"
               f"- {s['alasan']}\n"
               f"- Skor AI: {s['score']}/100\n"
               f"- RSI: {s['rsi']}\n\n"
               f"<b>Rekomendasi: {rek}</b>")
        return msg

    @staticmethod
    def format_top(top_vol, top_gainers):
        msg = "🏆 <b>TOP SAHAM LQ45</b>\n\n"
        msg += "🔥 <b>Volume Tertinggi:</b>\n"
        for s in top_vol:
            msg += f"- {s['symbol']} (Vol: {s['volume_ratio']}x rata-rata)\n"
        msg += "\n🚀 <b>Pergerakan Paling Aktif:</b>\n"
        for s in top_gainers:
            msg += f"- {s['symbol']} (+{s['change_pct']}%)\n"
        return msg