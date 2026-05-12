"""
market_calendar.py — Kalender hari libur bursa IDX 2025-2026.
Melengkapi market_session.py yang sudah ada di repo.
Source: BEI official calendar + Keputusan Bersama Kementerian.
"""
from __future__ import annotations
from datetime import date, timedelta

IDX_HOLIDAYS: set[date] = {
    # ── 2025 ──────────────────────────────────────────────────────────
    date(2025, 1, 1),   # Tahun Baru Masehi
    date(2025, 1, 27),  # Isra Mikraj
    date(2025, 1, 29),  # Tahun Baru Imlek
    date(2025, 3, 28),  # Cuti Bersama Nyepi
    date(2025, 3, 31),  # Hari Suci Nyepi
    date(2025, 4, 1),   # Cuti Bersama Idul Fitri
    date(2025, 4, 2),   # Idul Fitri
    date(2025, 4, 3),   # Idul Fitri
    date(2025, 4, 4),   # Cuti Bersama Idul Fitri
    date(2025, 4, 7),   # Cuti Bersama Idul Fitri
    date(2025, 4, 18),  # Wafat Yesus Kristus
    date(2025, 5, 1),   # Hari Buruh
    date(2025, 5, 12),  # Idul Adha (jika bursa libur)
    date(2025, 5, 29),  # Kenaikan Yesus Kristus
    date(2025, 6, 1),   # Hari Lahir Pancasila
    date(2025, 6, 6),   # Cuti Bersama Idul Adha
    date(2025, 6, 27),  # Tahun Baru Islam
    date(2025, 8, 17),  # HUT RI
    date(2025, 8, 18),  # Cuti Bersama HUT RI
    date(2025, 9, 5),   # Maulid Nabi
    date(2025, 12, 25), # Natal
    date(2025, 12, 26), # Cuti Bersama Natal

    # ── 2026 (Sumber Resmi: BEI Peng-00171/BEI.POP/09-2025) ──────────
    date(2026, 1, 1),   # Tahun Baru Masehi
    date(2026, 1, 16),  # Isra Mikraj Nabi Muhammad SAW
    date(2026, 2, 16),  # Cuti Bersama Tahun Baru Imlek
    date(2026, 2, 17),  # Tahun Baru Imlek 2577 Kongzili
    date(2026, 3, 18),  # Cuti Bersama Hari Suci Nyepi
    date(2026, 3, 19),  # Hari Suci Nyepi Tahun Baru Saka 1948
    date(2026, 3, 20),  # Cuti Bersama Idul Fitri 1447 H
    date(2026, 3, 23),  # Cuti Bersama Idul Fitri 1447 H
    date(2026, 3, 24),  # Idul Fitri 1447 H (hari 1)
    date(2026, 3, 25),  # Idul Fitri 1447 H (hari 2)
    date(2026, 3, 26),  # Cuti Bersama Idul Fitri 1447 H
    date(2026, 3, 27),  # Cuti Bersama Idul Fitri 1447 H
    date(2026, 4, 3),   # Wafat Yesus Kristus
    date(2026, 5, 1),   # Hari Buruh Internasional
    date(2026, 5, 14),  # Kenaikan Yesus Kristus
    date(2026, 5, 15),  # Cuti Bersama Kenaikan Yesus Kristus
    date(2026, 5, 27),  # Hari Raya Idul Adha 1447 H
    date(2026, 5, 28),  # Cuti Bersama Idul Adha 1447 H
    date(2026, 8, 17),  # HUT Kemerdekaan RI
    date(2026, 12, 25), # Natal
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
