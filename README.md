# IDX LQ45 AI Day Trader Bot

Bot Telegram untuk day trading saham LQ45 di Bursa Efek Indonesia (BEI).
Memindai 20 indikator teknikal secara paralel, menyusun trade plan intraday
dengan position sizing berbasis risiko, dan memonitor TP/SL secara real-time.

---

## Arsitektur

```
main.py           — Bot orchestrator, command handler, scheduler
analyzer.py       — 20 indikator teknikal + MTF + IHSG correlation
risk.py           — Position sizing & trade evaluation (RiskEngine)
storage.py        — Persistence: Supabase REST / Postgres DSN / SQLite fallback
notifier.py       — Telegram message formatter
global_macro.py   — Overlay makro global (IHSG, DXY, Oil, Nikel, VIX, dll)
market_session.py — Jam reguler BEI + sesi detection
market_calendar.py— Kalender hari libur IDX 2025–2026
monitor.py        — Real-time TP/SL alert background task
config.py         — Semua parameter dari .env
sql/              — Schema Supabase SQL
systemd/          — Service file untuk systemd
tests/            — Unit tests
```

---

## Command Bot

| Command            | Keterangan                                              |
| ------------------ | ------------------------------------------------------- |
| `/signal`          | Scan LQ45 + makro, tampilkan max 3 trade plan terbaik   |
| `/update`          | Cek harga terkini, hitung P/L trade plan hari ini       |
| `/detail <KODE>`   | Analisa mendalam satu saham (tanpa filter ketat)        |
| `/top`             | Top volume, gainers, dan RRR terbaik dari LQ45          |
| `/macro`           | Kondisi makro global + dampak ke sektor IDX             |
| `/performa`        | Win rate, avg P/L, history 30 hari terakhir             |
| `/watchlist`       | Tampilkan & analisa saham di daftar pantau              |
| `/watch <KODE>`    | Tambah saham ke watchlist (maks 10)                     |
| `/unwatch <KODE>`  | Hapus saham dari watchlist                              |
| `/setmodal <juta>` | Set modal trading (contoh: `/setmodal 10` = Rp 10 juta) |
| `/setrisk <pct>`   | Set risk per trade (contoh: `/setrisk 1.0` = 1%)        |
| `/help`            | Tampilkan semua command                                 |

---

## 20 Indikator Teknikal

| #   | Indikator            | Fungsi                                     |
| --- | -------------------- | ------------------------------------------ |
| 1   | EMA20 vs EMA50       | Trend filter — konfirmasi arah             |
| 2   | RSI (14)             | Momentum — oversold/overbought             |
| 3   | Stochastic (14,3,3)  | Double konfirmasi momentum                 |
| 4   | MACD (12,26,9)       | Crossover & histogram strength             |
| 5   | ATR (14)             | Volatility — dasar TP/SL                   |
| 6   | Volume Ratio         | Spike detection vs 20-bar avg              |
| 7   | Candlestick Pattern  | Hammer, Engulfing, Morning Star, Marubozu  |
| 8   | Market Condition     | Trending vs Sideways score multiplier      |
| 9   | VWAP                 | Institutional benchmark intraday           |
| 10  | Bollinger Bands      | Squeeze detection + lower band touch       |
| 11  | ADX (14)             | Trend strength filter (skip jika ADX < 20) |
| 12  | OBV Divergence       | Volume/price confirmation                  |
| 13  | Support/Resistance   | Multi-level pivot detection                |
| 14  | Gap Detection        | Gap up/down scoring                        |
| 15  | RSI Divergence       | Bullish divergence detection               |
| 16  | Anti-Chasing         | Block entry jika sudah naik >3% dari open  |
| 17  | Bid-Ask Spread Proxy | Filter likuiditas buruk (spread >3%)       |
| 18  | MTF Daily            | Konfirmasi trend dari timeframe harian     |
| 19  | Relative Strength    | Saham lebih kuat dari IHSG = bonus         |
| 20  | IHSG Correlation     | Penalty score jika IHSG turun >1.5%        |

---

## Entry / TP / SL — Professional Grade

**Best Entry** — Bukan selalu market price. Bot menghitung zona optimal dari:

- 🔵 VWAP Pullback
- 🟢 Dekat Support (pivot low + 0.5% buffer)
- 🟢 Lower Bollinger Band
- 🟡 Market price (fallback)

**SL** — `max(swing_low - 0.5%, price - 1.5×ATR)` → lebih ketat, mengikuti struktur pasar.

**TP1** — Resistance terdekat - 0.5% → take partial profit (50-70% posisi).

**TP2** — Fibonacci 1.618 extension dari swing → biarkan runner jalan.

**RRR** — Dihitung dari `best_entry → TP1 / best_entry → SL`, minimum 1.3.

---

## Risk Model Default

| Parameter        | Default        | Env Key              |
| ---------------- | -------------- | -------------------- |
| Modal acuan      | Rp 100.000.000 | `ACCOUNT_SIZE`       |
| Risk per trade   | 0.50%          | `RISK_PER_TRADE_PCT` |
| Max posisi aktif | 3              | `MAX_OPEN_POSITIONS` |
| Daily stop       | -1.5R          | `DAILY_MAX_LOSS_R`   |
| Partial exit TP1 | 50%            | `PARTIAL_EXIT_RATIO` |
| Buy fee          | 0.15%          | `BUY_FEE_PCT`        |
| Sell fee         | 0.25%          | `SELL_FEE_PCT`       |
| Slippage         | 0.05%          | `SLIPPAGE_PCT`       |
| Risk-off mode    | reduce         | `RISK_OFF_MODE`      |

Ubah via `/setmodal` dan `/setrisk` di bot, atau langsung di `.env`.

---

## Scheduler Otomatis

| Waktu               | Aksi                                          |
| ------------------- | --------------------------------------------- |
| **09:25 WIB**       | Scan LQ45 + kirim trade plan pagi             |
| **15:25 WIB**       | Evaluasi P/L + kirim update sore              |
| **Setiap 15 menit** | Monitor TP/SL, kirim alert real-time saat hit |
| **Hari libur IDX**  | Semua job skip otomatis (market_calendar.py)  |

---

## Makro Global yang Dipantau

| Ticker     | Indikator             | Sektor IDX yang Terpengaruh |
| ---------- | --------------------- | --------------------------- |
| `^JKSE`    | IHSG                  | Semua saham                 |
| `DX-Y.NYB` | US Dollar Index       | Banking, Consumer, Semua    |
| `^TNX`     | US 10Y Treasury Yield | Risk appetite               |
| `BZ=F`     | Brent Oil             | BREN, MEDC, ENRG            |
| `NI=F`     | Nikel                 | INCO, MDKA, ANTM            |
| `MTF=F`    | Batubara              | ADRO, ITMG, PTBA            |
| `^VIX`     | Fear & Greed Index    | Sentimen global             |

---

## Environment

Salin `.env.example` ke `.env`, isi minimal:

```env
TELEGRAM_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# Supabase (gunakan service role untuk bypass RLS)
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Risk Management
ACCOUNT_SIZE=100000000
RISK_PER_TRADE_PCT=0.005
DAILY_MAX_LOSS_R=1.5
MAX_OPEN_POSITIONS=3
```

---

## Setup Supabase

1. Buat project di [supabase.com](https://supabase.com)
2. Isi `.env` dengan URL dan keys
3. Jalankan schema di **SQL Editor Supabase**:
   ```sql
   -- Copy-paste isi sql/supabase_schema.sql
   ```
4. Bot otomatis detect backend: Supabase REST → Postgres DSN → SQLite fallback

---

## Deploy ke Server

```bash
git clone https://github.com/martinusiron/idx-lq45-ai-bot.git
cd idx-lq45-ai-bot
cp .env.example .env
nano .env  # isi semua credentials

sudo bash deploy.sh
```

Cek log:

```bash
journalctl -u lq45-signal-bot -f
```

---

## Menjalankan Lokal

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install ta  # eksplisit, karena kadang tidak ter-install via requirements
python3 main.py
```

---

## Menjalankan Test

```bash
python3 -m unittest discover -s tests
```

---

## Catatan Penting

- Data dari `yfinance` delay ~15 menit — **bukan untuk live execution**.
- `SUPABASE_SERVICE_ROLE_KEY` **hanya di backend/server**, jangan expose ke frontend.
- Kalender libur IDX 2025–2026 di `market_calendar.py` — update setiap awal tahun.
- Anti-chasing aktif: bot tidak akan rekomendasikan saham yang sudah naik >3% dari open.
- Untuk production grade, pertimbangkan data feed berbayar (IDX API, Bloomberg).

---

⚠️ _Disclaimer: Bot ini untuk edukasi dan alat bantu analisa. Bukan rekomendasi finansial. Trading saham mengandung risiko kerugian. Selalu gunakan manajemen risiko yang ketat._
