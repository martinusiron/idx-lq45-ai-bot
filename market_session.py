from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

import pytz


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time


class IDXMarketSession:
    def __init__(self, tz_name: str = "Asia/Jakarta"):
        self.tz = pytz.timezone(tz_name)
        self.weekday_windows = {
            0: (
                SessionWindow("session_1", time(9, 0), time(12, 0)),
                SessionWindow("session_2", time(13, 30), time(15, 49, 59)),
            ),
            1: (
                SessionWindow("session_1", time(9, 0), time(12, 0)),
                SessionWindow("session_2", time(13, 30), time(15, 49, 59)),
            ),
            2: (
                SessionWindow("session_1", time(9, 0), time(12, 0)),
                SessionWindow("session_2", time(13, 30), time(15, 49, 59)),
            ),
            3: (
                SessionWindow("session_1", time(9, 0), time(12, 0)),
                SessionWindow("session_2", time(13, 30), time(15, 49, 59)),
            ),
            4: (
                SessionWindow("session_1", time(9, 0), time(11, 30)),
                SessionWindow("session_2", time(14, 0), time(15, 49, 59)),
            ),
        }

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def localize(self, dt: datetime | None = None) -> datetime:
        dt = dt or self.now()
        if dt.tzinfo is None:
            return self.tz.localize(dt)
        return dt.astimezone(self.tz)

    def get_status(self, dt: datetime | None = None) -> str:
        now = self.localize(dt)
        if now.weekday() >= 5:
            return "closed"

        current_time = now.time()
        windows = self.weekday_windows[now.weekday()]

        for window in windows:
            if window.start <= current_time <= window.end:
                return window.name

        if windows[0].end < current_time < windows[1].start:
            return "lunch_break"

        return "closed"

    def is_regular_session(self, dt: datetime | None = None) -> bool:
        return self.get_status(dt) in {"session_1", "session_2"}

    def human_schedule(self, weekday: int | None = None) -> str:
        if weekday is None:
            weekday = self.now().weekday()

        if weekday in (0, 1, 2, 3):
            return "09:00-12:00 & 13:30-15:49 WIB"
        if weekday == 4:
            return "09:00-11:30 & 14:00-15:49 WIB"
        return "Bursa tutup"
