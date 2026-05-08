## IDX LQ45 Day Trader Bot

Bot Telegram untuk memindai saham LQ45, menyusun trade plan intraday, dan mencatat journal hasil harian dengan aturan risiko yang eksplisit.

### Yang Sudah Diubah

- Sinyal pagi sekarang disimpan sebagai `trade plan` di database persisten, bukan hanya state in-memory.
- Ukuran posisi dihitung dari `risk per trade`, `lot size`, fee, dan slippage.
- Saat `risk-off`, ukuran posisi bisa diperkecil atau diblokir via config.
- Update trade memakai `planned entry`, bukan harga snapshot saat sinyal.
- Watchlist persisten di database.
- Market hours sekarang sadar sesi BEI reguler, termasuk jeda siang dan sesi Jumat.
- Storage mendukung `Supabase service-role REST`, `Supabase/Postgres DSN`, dan `SQLite fallback`.

### Arsitektur Inti

- [main.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/main.py): orchestration bot, command handler, journaling flow.
- [analyzer.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/analyzer.py): scan teknikal dan level entry/TP/SL.
- [risk.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/risk.py): position sizing dan evaluasi hasil trade.
- [storage.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/storage.py): journal dan watchlist persistence untuk Supabase REST, Postgres DSN, atau SQLite fallback.
- [market_session.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/market_session.py): jam reguler BEI.
- [global_macro.py](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/global_macro.py): overlay makro dan deteksi risk-off.
- [sql/supabase_schema.sql](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/sql/supabase_schema.sql): schema awal untuk Supabase SQL Editor.

### Risk Model Default

- Modal acuan: `Rp 100.000.000`
- Risk per trade: `0.50%`
- Max posisi aktif: `3`
- Daily stop: `-1.5R`
- Partial exit: `50% di TP1`, sisa posisi diproteksi ke breakeven
- Biaya default:
  - Buy fee `0.15%`
  - Sell fee `0.25%`
  - Slippage `0.05%`

Semua parameter di atas bisa diubah lewat `.env`.

### Environment

Salin `.env.example` ke `.env`, lalu isi minimal:

```env
TELEGRAM_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id
```

Opsi penting lain:

```env
ACCOUNT_SIZE=100000000
RISK_PER_TRADE_PCT=0.005
DAILY_MAX_LOSS_R=1.5
MAX_OPEN_POSITIONS=3
RISK_OFF_MODE=reduce
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

Urutan backend:

1. Jika `SUPABASE_DB_URL` diisi, bot pakai direct Postgres DSN.
2. Jika `SUPABASE_URL` dan `SUPABASE_SERVICE_ROLE_KEY` diisi, bot pakai Supabase REST backend.
3. Jika tidak ada keduanya, bot fallback ke `DB_PATH` lokal.

### Setup Supabase

1. Buat project Supabase.
2. Isi `.env` dengan:
   `SUPABASE_URL`
   `SUPABASE_ANON_KEY`
   `SUPABASE_SERVICE_ROLE_KEY`
3. Jalankan schema dari [sql/supabase_schema.sql](/Users/martinusironsijabat/go/src/idx-lq45-ai-bot/sql/supabase_schema.sql:1) di SQL Editor Supabase.
4. Opsional: kalau kamu lebih suka direct Postgres, isi `SUPABASE_DB_URL` dengan pooled DSN.

Catatan:

- Bot sekarang mendukung **dua mode Supabase**:
  - `service-role REST` via `supabase-py`
  - `direct Postgres DSN`
- Untuk config yang kamu kirim, mode yang dipakai adalah `service-role REST`.
- `SUPABASE_SERVICE_ROLE_KEY` hanya boleh ada di backend/server. Jangan expose ke frontend.

### Menjalankan Lokal

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### Menjalankan Test

```bash
python3 -m unittest discover -s tests
```

### Catatan Produk

- Sumber data masih `yfinance`, jadi ini belum execution-grade.
- Journal sekarang lebih realistis karena mempertimbangkan fill limit entry, fee, slippage, dan partial take profit.
- Kalender BEI libur nasional belum diintegrasikan; market session baru mencakup jam reguler harian.
- Untuk production, `SUPABASE_SERVICE_ROLE_KEY` wajib disimpan hanya di environment server.
