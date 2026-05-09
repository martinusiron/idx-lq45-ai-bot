"""
market_calendar.py — Kalender hari libur bursa IDX 2025-2026.
Melengkapi market_session.py yang sudah ada di repo.
Source: BEI official calendar + Keputusan Bersama Kementerian.
"""
from __future__ import annotations
from datetime import date, timedelta

IDX_HOLIDAYS: set[date] = {
    # 2025
    date(2025, 1, 1),   date(2025, 1, 27),  date(2025, 1, 29),
    date(2025, 3, 28),  date(2025, 3, 31),  date(2025, 4, 1),
    date(2025, 4, 2),   date(2025, 4, 3),   date(2025, 4, 4),
    date(2025, 4, 7),   date(2025, 4, 18),  date(2025, 5, 1),
    date(2025, 5, 12),  date(2025, 5, 29),  date(2025, 6, 1),
    date(2025, 6, 6),   date(2025, 6, 27),  date(2025, 8, 17),
    date(2025, 8, 18),  date(2025, 9, 5),   date(2025, 12, 25),
    date(2025, 12, 26),
    # 2026
    date(2026, 1, 1),   date(2026, 1, 17),  date(2026, 2, 17),
    date(2026, 3, 19),  date(2026, 3, 20),  date(2026, 3, 23),
    date(2026, 3, 24),  date(2026, 3, 25),  date(2026, 3, 26),
    date(2026, 3, 27),  date(2026, 5, 1),   date(2026, 5, 2),
    date(2026, 5, 14),  date(2026, 5, 26),  date(2026, 6, 1),
    date(2026, 8, 17),  date(2026, 12, 25),
}


def is_trading_day(d: date | None = None) -> bool:
    if d is None:
        d = date.today()
    return d.weekday() < 5 and d not in IDX_HOLIDAYS


def is_safe_trading_time(hour: int, minute: int = 0) -> bool:
    """
    Waktu aman entry — hindari:
    - Pre-opening  : sebelum 09:15
    - Jeda sesi    : 12:00–13:45
    - Pre-closing  : setelah 14:55
    """
    t = hour * 60 + minute
    s1 = 9 * 60 + 15  <= t <= 11 * 60 + 45
    s2 = 13 * 60 + 45 <= t <= 14 * 60 + 55
    return s1 or s2


def next_trading_day(d: date | None = None) -> date:
    if d is None:
        d = date.today()
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d
