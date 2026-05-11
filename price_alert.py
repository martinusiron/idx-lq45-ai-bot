"""
price_alert.py — Custom price alert system.
User set alert: /alert BBCA 9200 (notif saat harga >= 9200)
               /alert BBCA 8800 bawah (notif saat harga <= 8800)
               /alerts — lihat semua alert aktif
               /delalert BBCA — hapus alert saham
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import pytz
import yfinance as yf

from market_calendar import is_trading_day, is_safe_trading_time

logger = logging.getLogger(__name__)
TZ = pytz.timezone("Asia/Jakarta")


class PriceAlertManager:
    """
    Simpan dan monitor price alert per user.
    Structure: {user_id: [{symbol, target, direction, created_at, chat_id}]}
    """

    def __init__(self, app) -> None:
        self.app      = app
        self.alerts:  dict[str, list[dict]] = {}   # user_id → list alerts
        self.running  = False

    # ── CRUD ──────────────────────────────────────────────────────────
    def add_alert(self, user_id: str, chat_id: str, symbol: str,
                  target: float, direction: str) -> bool:
        """direction: 'atas' (>=target) atau 'bawah' (<=target)"""
        if user_id not in self.alerts:
            self.alerts[user_id] = []

        # Max 5 alert per user
        if len(self.alerts[user_id]) >= 5:
            return False

        # Hapus alert lama untuk saham yang sama & direction yang sama
        self.alerts[user_id] = [
            a for a in self.alerts[user_id]
            if not (a["symbol"] == symbol and a["direction"] == direction)
        ]

        self.alerts[user_id].append({
            "symbol":     symbol,
            "target":     target,
            "direction":  direction,
            "chat_id":    chat_id,
            "created_at": datetime.now(TZ).isoformat(),
            "triggered":  False,
        })
        return True

    def remove_alert(self, user_id: str, symbol: str) -> int:
        """Hapus semua alert untuk satu saham. Return jumlah yang dihapus."""
        if user_id not in self.alerts:
            return 0
        before = len(self.alerts[user_id])
        self.alerts[user_id] = [a for a in self.alerts[user_id] if a["symbol"] != symbol]
        return before - len(self.alerts[user_id])

    def get_alerts(self, user_id: str) -> list[dict]:
        return self.alerts.get(user_id, [])

    def get_all_active(self) -> list[dict]:
        """Flatten semua alert dari semua user untuk monitoring."""
        result = []
        for user_id, alerts in self.alerts.items():
            for a in alerts:
                if not a["triggered"]:
                    result.append({**a, "user_id": user_id})
        return result

    # ── Price Fetch ───────────────────────────────────────────────────
    @staticmethod
    def _fetch_price(symbol: str) -> float | None:
        try:
            df = yf.download(f"{symbol}.JK", period="1d", interval="1m",
                             progress=False, auto_adjust=True)
            if df.empty:
                return None
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            return float(df["close"].iloc[-1])
        except Exception as exc:
            logger.warning(f"[alert] fetch {symbol}: {exc}")
            return None

    # ── Monitor Loop ──────────────────────────────────────────────────
    async def _send_alert(self, chat_id: str, msg: str) -> None:
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as exc:
            logger.error(f"[alert] send error: {exc}")

    async def check_all(self) -> None:
        active = self.get_all_active()
        if not active:
            return

        # Deduplicate: fetch setiap symbol sekali saja
        symbols  = list({a["symbol"] for a in active})
        prices   = {}
        loop     = asyncio.get_event_loop()
        fetched  = await asyncio.gather(*[
            loop.run_in_executor(None, self._fetch_price, sym)
            for sym in symbols
        ])
        for sym, price in zip(symbols, fetched):
            if price:
                prices[sym] = price

        triggered_keys = []
        for a in active:
            sym   = a["symbol"]
            price = prices.get(sym)
            if price is None:
                continue

            hit = (
                (a["direction"] == "atas"  and price >= a["target"]) or
                (a["direction"] == "bawah" and price <= a["target"])
            )

            if hit:
                arrow = "🚀" if a["direction"] == "atas" else "🔻"
                msg   = (
                    f"{arrow} <b>PRICE ALERT — {sym}</b>\n"
                    f"Harga   : Rp {int(price):,}\n"
                    f"Target  : Rp {int(a['target']):,} ({a['direction']})\n"
                    f"<i>Alert otomatis dihapus setelah triggered.</i>"
                )
                await self._send_alert(a["chat_id"], msg)
                triggered_keys.append((a["user_id"], sym, a["direction"]))
                logger.info(f"[alert] TRIGGERED: {sym} @ {price} (target {a['target']} {a['direction']})")

        # Hapus alert yang sudah triggered
        for user_id, sym, direction in triggered_keys:
            if user_id in self.alerts:
                self.alerts[user_id] = [
                    x for x in self.alerts[user_id]
                    if not (x["symbol"] == sym and x["direction"] == direction)
                ]

    async def run_loop(self) -> None:
        """Check setiap 5 menit saat jam bursa."""
        self.running = True
        logger.info("🔔 Price alert monitor started.")
        while self.running:
            now = datetime.now(TZ)
            if is_trading_day(now.date()) and is_safe_trading_time(now.hour, now.minute):
                await self.check_all()
            await asyncio.sleep(5 * 60)

    def stop(self) -> None:
        self.running = False
