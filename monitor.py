"""
monitor.py — Real-time TP/SL alert monitor.
Cek harga setiap 15 menit saat jam bursa, kirim alert Telegram saat hit.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import pytz
import pandas as pd
import yfinance as yf
import requests

from config import GOAPI_API_KEY
from market_calendar import is_trading_day, is_safe_trading_time

logger = logging.getLogger(__name__)
TZ = pytz.timezone("Asia/Jakarta")


class SignalMonitor:
    """Background monitor untuk real-time TP/SL alert."""

    def __init__(self, app, storage) -> None:
        self.app        = app
        self.storage    = storage
        self.running    = False
        self._goapi_ok  = True  # Circuit breaker: False jika quota habis

    def _fetch_price(self, symbol: str) -> float | None:
        """Fetch harga terakhir. Prioritas GoAPI, fallback ke yfinance."""
        if GOAPI_API_KEY and self._goapi_ok:
            try:
                url = "https://api.goapi.io/stock/idx/prices"
                params = {
                    "symbols": symbol.upper().replace(".JK", ""),
                    "api_key": GOAPI_API_KEY
                }
                headers = {"Authorization": GOAPI_API_KEY}
                resp = requests.get(url, params=params, headers=headers, timeout=10)

                if resp.status_code in (402, 429):
                    logger.warning("[monitor] GoAPI quota habis! Beralih ke yfinance.")
                    self._goapi_ok = False
                elif resp.status_code == 200:
                    data = resp.json()
                    msg  = data.get("message", "").lower()
                    if any(kw in msg for kw in ("quota", "limit", "exceeded", "upgrade")):
                        logger.warning(f"[monitor] GoAPI quota dari body: '{msg}'")
                        self._goapi_ok = False
                    elif data.get("status") == "success":
                        results = data.get("data", {}).get("results", [])
                        for res in results:
                            if res.get("symbol", "") == params["symbols"]:
                                return float(res.get("close") or res.get("last") or 0)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                logger.warning(f"[monitor] GoAPI tidak bisa dihubungi, fallback ke yfinance")
            except Exception as e:
                logger.warning(f"[monitor] GoAPI fetch error: {e}")

        # Fallback ke yfinance
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith(".JK") else symbol
            df = yf.download(ticker, period="1d", interval="1m",
                             progress=False, auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                return float(df["close"].iloc[-1])
        except Exception as exc:
            logger.warning(f"[monitor] yf fetch error: {exc}")
        return None

    async def _alert(self, chat_id: str, msg: str) -> None:
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as exc:
            logger.error(f"[monitor] send_message: {exc}")

    async def check_once(self, chat_id: str, trade_date: str) -> None:
        """Cek semua trade aktif hari ini."""
        trades = self.storage.get_active_trade_plans(trade_date)
        if not trades:
            return

        logger.info(f"[monitor] Checking {len(trades)} active trades...")

        for trade in trades:
            sym   = trade["symbol"]
            tp1   = float(trade.get("tp1", 0))
            tp2   = float(trade.get("tp2", 0))
            sl    = float(trade.get("sl", 0))
            entry = float(trade.get("planned_entry") or trade.get("best_entry") or 0)
            if entry == 0:
                continue

            price = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_price, sym
            )
            if price is None:
                continue

            pnl = round((price - entry) / entry * 100, 2)

            if sl > 0 and price <= sl:
                self.storage.update_trade_result(
                    trade_date, sym,
                    {"status": "SL_HIT", "exit_price": price,
                     "exit_reason": "SL", "pnl_pct": pnl, "finalized": True}
                )
                await self._alert(chat_id,
                    f"🔴 <b>STOP LOSS HIT — {sym}</b>\n"
                    f"Harga  : Rp {int(price):,}\n"
                    f"SL     : Rp {int(sl):,}\n"
                    f"P/L    : <b>{pnl}%</b>\n"
                    f"<i>Cut loss sekarang. Proteksi modal lebih penting.</i>"
                )
            elif tp2 > 0 and price >= tp2:
                self.storage.update_trade_result(
                    trade_date, sym,
                    {"status": "TP2_HIT", "exit_price": price,
                     "exit_reason": "TP2", "pnl_pct": pnl, "finalized": True}
                )
                await self._alert(chat_id,
                    f"🚀 <b>TP2 TERCAPAI — {sym}</b>\n"
                    f"Harga  : Rp {int(price):,}\n"
                    f"TP2    : Rp {int(tp2):,}\n"
                    f"P/L    : <b>+{pnl}%</b>\n"
                    f"<i>Full profit! Tutup semua posisi. 🎉</i>"
                )
            elif tp1 > 0 and price >= tp1:
                self.storage.update_trade_result(
                    trade_date, sym,
                    {"status": "TP1_HIT", "exit_price": price,
                     "exit_reason": "TP1", "pnl_pct": pnl}
                )
                await self._alert(chat_id,
                    f"✅ <b>TP1 TERCAPAI — {sym}</b>\n"
                    f"Harga  : Rp {int(price):,}\n"
                    f"TP1    : Rp {int(tp1):,}\n"
                    f"P/L    : <b>+{pnl}%</b>\n"
                    f"<i>Ambil parsial profit (50-70%). Geser SL ke entry.</i>"
                )

    async def run_loop(self, chat_id: str, trade_date_fn) -> None:
        """Loop setiap 15 menit saat jam bursa."""
        self.running = True
        logger.info("🔍 Signal monitor started.")
        while self.running:
            now = datetime.now(TZ)
            if is_trading_day(now.date()) and is_safe_trading_time(now.hour, now.minute):
                await self.check_once(chat_id, trade_date_fn())
            await asyncio.sleep(15 * 60)

    def stop(self) -> None:
        self.running = False
        logger.info("🛑 Signal monitor stopped.")
