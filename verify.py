#!/usr/bin/env python3
"""
verify.py — Pre-flight check sebelum deploy/restart bot.
Jalankan: python3 verify.py
Semua check harus ✅ sebelum bot distart.
"""
from __future__ import annotations
import sys
import os

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
errors   = []
warnings = []


def check(label: str, fn, fatal: bool = True):
    try:
        result = fn()
        print(f"  {PASS} {label}" + (f" — {result}" if result else ""))
    except Exception as e:
        icon = FAIL if fatal else WARN
        print(f"  {icon} {label} — {e}")
        (errors if fatal else warnings).append(label)


print("\n📋 IDX Day Trader Bot — Pre-flight Check\n" + "="*45)

# ── 1. Python version ──────────────────────────────────────────────────
print("\n[1] Python")
check("Python >= 3.11", lambda: (
    f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11) else (_ for _ in ()).throw(RuntimeError("Python 3.11+ dibutuhkan"))
))

# ── 2. Libraries ───────────────────────────────────────────────────────
print("\n[2] Libraries")
def chk_lib(name, import_name=None):
    import importlib
    mod = importlib.import_module(import_name or name)
    ver = getattr(mod, "__version__", "?")
    return ver

check("yfinance",             lambda: chk_lib("yfinance"))
check("pandas",               lambda: chk_lib("pandas"))
check("numpy",                lambda: chk_lib("numpy"))
check("ta",                   lambda: chk_lib("ta"))
check("pytz",                 lambda: chk_lib("pytz"))
check("requests",             lambda: chk_lib("requests"))
check("python-telegram-bot",  lambda: chk_lib("telegram"))
check("python-dotenv",        lambda: chk_lib("dotenv"))
check("psycopg (opsional)",   lambda: chk_lib("psycopg"), fatal=False)

# ── 3. Environment Variables ───────────────────────────────────────────
print("\n[3] Environment Variables")
from dotenv import load_dotenv
load_dotenv()

def env_check(key, secret=False):
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Tidak ditemukan di .env")
    return "***" if secret else val[:30] + ("..." if len(val) > 30 else "")

check("TELEGRAM_TOKEN",          lambda: env_check("TELEGRAM_TOKEN", secret=True))
check("TELEGRAM_CHAT_ID",        lambda: env_check("TELEGRAM_CHAT_ID"))
check("SUPABASE_URL", lambda: env_check("SUPABASE_URL"))
check("SUPABASE_SERVICE_ROLE_KEY", lambda: env_check("SUPABASE_SERVICE_ROLE_KEY", secret=True))
check("ACCOUNT_SIZE",            lambda: env_check("ACCOUNT_SIZE"), fatal=False)
check("RISK_PER_TRADE_PCT",      lambda: env_check("RISK_PER_TRADE_PCT"), fatal=False)

# ── 4. Config imports ──────────────────────────────────────────────────
print("\n[4] Config Module")
def check_config():
    from config import (
        TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
        ACCOUNT_SIZE, RISK_PER_TRADE_PCT, DAILY_MAX_LOSS_R, MAX_OPEN_POSITIONS,
        LOT_SIZE, BUY_FEE_PCT, SELL_FEE_PCT, SLIPPAGE_PCT, PARTIAL_EXIT_RATIO,
        RISK_OFF_MODE, RISK_OFF_SIZE_MULTIPLIER, DATABASE_URL, DB_PATH, TIMEZONE,
        LQ45_SYMBOLS, HIGH_PROB_THRESHOLD, MIN_RRR, DATA_PERIOD, DATA_INTERVAL,
        MIN_VOLUME_RATIO, MIN_VOLUME_ABS, MIN_ADX, MAX_SPREAD_PCT,
    )
    assert len(LQ45_SYMBOLS) > 0, "LQ45_SYMBOLS kosong"
    return f"{len(LQ45_SYMBOLS)} saham, backend threshold={HIGH_PROB_THRESHOLD}"

check("Semua variabel config ter-import", check_config)

# ── 5. Module imports ──────────────────────────────────────────────────
print("\n[5] Module Imports")
check("analyzer",        lambda: __import__("analyzer") and "OK")
check("notifier",        lambda: __import__("notifier") and "OK")
check("global_macro",    lambda: __import__("global_macro") and "OK")
check("market_session",  lambda: __import__("market_session") and "OK")
check("market_calendar", lambda: __import__("market_calendar") and "OK")
check("risk",            lambda: __import__("risk") and "OK")
check("storage",         lambda: __import__("storage") and "OK")
check("monitor",         lambda: __import__("monitor") and "OK")

# ── 6. Storage connectivity ────────────────────────────────────────────
print("\n[6] Storage Backend")
def check_storage():
    from config import DB_PATH, DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    from storage import TradingStorage
    s = TradingStorage(
        sqlite_path=DB_PATH,
        database_url=DATABASE_URL,
        supabase_url=SUPABASE_URL,
        supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY,
    )
    s.healthcheck()
    return s.describe_backend()

check("Storage healthcheck", check_storage)

# ── 7. Analyzer quick test ─────────────────────────────────────────────
print("\n[7] Analyzer — Quick Fetch Test")
def check_analyzer():
    from analyzer import StockAnalyzer
    a  = StockAnalyzer()
    df = a.fetch_data("BBCA")
    if df is None:
        raise RuntimeError("fetch_data BBCA return None")
    return f"{len(df)} rows fetched, cols={list(df.columns[:3])}"

check("fetch_data BBCA", check_analyzer)

def check_ihsg():
    from analyzer import StockAnalyzer
    chg = StockAnalyzer().fetch_ihsg()
    if chg is None:
        raise RuntimeError("fetch_ihsg return None")
    return f"IHSG change: {chg}%"

check("fetch_ihsg IHSG", check_ihsg)

# ── 8. Macro check ─────────────────────────────────────────────────────
print("\n[8] Global Macro")
def check_macro():
    from global_macro import GlobalMacroAnalyzer
    ctx = GlobalMacroAnalyzer().get_macro_context()
    n = len(ctx.get("data", {}))
    if n == 0:
        raise RuntimeError("Tidak ada data makro berhasil difetch")
    return f"{n} tickers fetched, risk_off={ctx.get('is_risk_off')}"

check("GlobalMacroAnalyzer", check_macro)

# ── 9. Market calendar ─────────────────────────────────────────────────
print("\n[9] Market Calendar")
def check_calendar():
    from market_calendar import is_trading_day, is_safe_trading_time
    from datetime import date
    today = date.today()
    return f"Today={today}, is_trading_day={is_trading_day(today)}"

check("market_calendar", check_calendar)

# ── 10. Telegram connectivity ──────────────────────────────────────────
print("\n[10] Telegram")
def check_telegram():
    import asyncio
    from telegram import Bot
    from config import TELEGRAM_TOKEN
    async def _ping():
        bot = Bot(token=TELEGRAM_TOKEN)
        me  = await bot.get_me()
        return f"@{me.username}"
    return asyncio.run(_ping())

check("Telegram Bot getMe", check_telegram)

# ── Summary ────────────────────────────────────────────────────────────
print("\n" + "="*45)
if errors:
    print(f"\n{FAIL} {len(errors)} ERROR — Bot TIDAK akan bisa start:")
    for e in errors:
        print(f"   • {e}")
    print("\nPerbaiki error di atas sebelum restart bot.\n")
    sys.exit(1)
elif warnings:
    print(f"\n{WARN} {len(warnings)} WARNING (non-fatal):")
    for w in warnings:
        print(f"   • {w}")
    print(f"\n{PASS} Bot BISA distart, tapi ada dependency opsional yang hilang.\n")
else:
    print(f"\n{PASS} Semua check passed! Bot siap distart.\n")
    print("  sudo systemctl restart lq45-signal-bot\n")
