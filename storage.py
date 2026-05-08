from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any

import requests

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    dict_row = None


SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS trades (
        trade_date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal_timestamp TEXT NOT NULL,
        market_price_at_signal REAL NOT NULL,
        planned_entry REAL NOT NULL,
        sl REAL NOT NULL,
        tp1 REAL NOT NULL,
        tp2 REAL NOT NULL,
        rrr REAL NOT NULL,
        score REAL NOT NULL,
        risk_off INTEGER NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL,
        lot_count INTEGER NOT NULL,
        risk_amount REAL NOT NULL,
        planned_notional REAL NOT NULL,
        size_mode TEXT NOT NULL,
        size_notes TEXT NOT NULL,
        analyzer_snapshot TEXT NOT NULL,
        status TEXT NOT NULL,
        fill_status TEXT NOT NULL DEFAULT 'PENDING',
        filled_at TEXT,
        filled_price REAL,
        last_price REAL,
        exit_price REAL,
        exit_reason TEXT,
        pnl_amount REAL DEFAULT 0,
        pnl_pct REAL DEFAULT 0,
        realized_r REAL DEFAULT 0,
        events TEXT,
        finalized INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlists (
        user_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, symbol)
    )
    """,
]


POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS trades (
        trade_date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal_timestamp TEXT NOT NULL,
        market_price_at_signal DOUBLE PRECISION NOT NULL,
        planned_entry DOUBLE PRECISION NOT NULL,
        sl DOUBLE PRECISION NOT NULL,
        tp1 DOUBLE PRECISION NOT NULL,
        tp2 DOUBLE PRECISION NOT NULL,
        rrr DOUBLE PRECISION NOT NULL,
        score DOUBLE PRECISION NOT NULL,
        risk_off BOOLEAN NOT NULL DEFAULT FALSE,
        qty INTEGER NOT NULL,
        lot_count INTEGER NOT NULL,
        risk_amount DOUBLE PRECISION NOT NULL,
        planned_notional DOUBLE PRECISION NOT NULL,
        size_mode TEXT NOT NULL,
        size_notes TEXT NOT NULL,
        analyzer_snapshot TEXT NOT NULL,
        status TEXT NOT NULL,
        fill_status TEXT NOT NULL DEFAULT 'PENDING',
        filled_at TEXT,
        filled_price DOUBLE PRECISION,
        last_price DOUBLE PRECISION,
        exit_price DOUBLE PRECISION,
        exit_reason TEXT,
        pnl_amount DOUBLE PRECISION DEFAULT 0,
        pnl_pct DOUBLE PRECISION DEFAULT 0,
        realized_r DOUBLE PRECISION DEFAULT 0,
        events TEXT,
        finalized BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlists (
        user_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, symbol)
    )
    """,
]


class TradingStorage:
    def __init__(
        self,
        sqlite_path: str,
        database_url: str | None = None,
        supabase_url: str | None = None,
        supabase_service_role_key: str | None = None,
    ):
        self.sqlite_path = sqlite_path
        self.database_url = database_url
        self.supabase_url = supabase_url
        self.supabase_service_role_key = supabase_service_role_key
        self.backend = self._detect_backend()
        self.placeholder = "%s" if self.backend == "postgres" else "?"
        self.supabase_rest_url = None
        self.supabase_headers: dict[str, str] | None = None

        if self.backend == "sqlite":
            db_dir = os.path.dirname(sqlite_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        elif self.backend == "postgres":
            if psycopg is None:
                raise RuntimeError(
                    "Postgres backend dipilih tetapi dependency `psycopg` belum terpasang."
                )
        elif self.backend == "supabase":
            self.supabase_rest_url = self.supabase_url.rstrip("/") + "/rest/v1"
            self.supabase_headers = {
                "apikey": self.supabase_service_role_key,
                "Authorization": f"Bearer {self.supabase_service_role_key}",
                "Content-Type": "application/json",
            }

        self._init_db()

    def _detect_backend(self) -> str:
        if self.database_url and self.database_url.startswith(("postgres://", "postgresql://")):
            return "postgres"
        if self.supabase_url and self.supabase_service_role_key:
            return "supabase"
        return "sqlite"

    def describe_backend(self) -> str:
        if self.backend == "postgres":
            return "postgres"
        if self.backend == "supabase":
            return "supabase-rest"
        return "sqlite"

    def healthcheck(self) -> None:
        if self.backend == "sqlite":
            self._fetchone("SELECT 1 AS ok")
            return
        if self.backend == "postgres":
            self._fetchone("SELECT 1 AS ok")
            return
        try:
            self._supabase_request("GET", "watchlists", params={"select": "symbol", "limit": 1})
        except Exception as exc:  # pragma: no cover - networked path
            raise RuntimeError(
                "Supabase tidak siap. Pastikan URL/key benar dan tabel sudah dibuat "
                "menggunakan sql/supabase_schema.sql."
            ) from exc

    def _connect(self):
        if self.backend == "postgres":
            return psycopg.connect(self.database_url, row_factory=dict_row)
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _as_dicts(rows: list[Any]) -> list[dict]:
        return [dict(row) for row in rows]

    def _execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self._connect() as conn:
            conn.execute(query, params)
            conn.commit()

    def _executemany(self, query: str, params_list: list[tuple[Any, ...]]) -> None:
        if not params_list:
            return
        with self._connect() as conn:
            conn.executemany(query, params_list)
            conn.commit()

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return self._as_dicts(rows)

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def _init_db(self):
        if self.backend == "supabase":
            return
        schema = POSTGRES_SCHEMA if self.backend == "postgres" else SQLITE_SCHEMA
        with self._connect() as conn:
            for stmt in schema:
                conn.execute(stmt)
            conn.commit()

    def replace_trade_plans(self, trade_date: str, trades: list[dict]):
        now = datetime.utcnow().isoformat()
        if self.backend == "supabase":
            self._supabase_request(
                "DELETE",
                "trades",
                params={"trade_date": f"eq.{trade_date}", "finalized": "eq.false"},
            )
            if not trades:
                return
            payload = [
                {
                    "trade_date": trade["trade_date"],
                    "symbol": trade["symbol"],
                    "signal_timestamp": trade["signal_timestamp"],
                    "market_price_at_signal": trade["price"],
                    "planned_entry": trade["best_entry"],
                    "sl": trade["sl"],
                    "tp1": trade["tp1"],
                    "tp2": trade["tp2"],
                    "rrr": trade["rrr"],
                    "score": trade["score"],
                    "risk_off": bool(trade["risk_off"]),
                    "qty": trade["qty"],
                    "lot_count": trade["lot_count"],
                    "risk_amount": trade["risk_amount"],
                    "planned_notional": trade["planned_notional"],
                    "size_mode": trade["size_mode"],
                    "size_notes": trade["size_notes"],
                    "analyzer_snapshot": trade["analyzer_snapshot"],
                    "status": "PLANNED",
                    "fill_status": "PENDING",
                    "created_at": now,
                    "updated_at": now,
                }
                for trade in trades
            ]
            self._supabase_request(
                "POST",
                "trades",
                params={"on_conflict": "trade_date,symbol"},
                json=payload,
                extra_headers={"Prefer": "resolution=merge-duplicates"},
            )
            return

        self._execute(
            f"DELETE FROM trades WHERE trade_date = {self.placeholder} AND finalized = {self._false_value()}",
            (trade_date,),
        )

        insert_sql = """
            INSERT INTO trades (
                trade_date, symbol, signal_timestamp, market_price_at_signal,
                planned_entry, sl, tp1, tp2, rrr, score, risk_off, qty, lot_count,
                risk_amount, planned_notional, size_mode, size_notes, analyzer_snapshot,
                status, fill_status, created_at, updated_at
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p},
                      {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
        """.format(p=self.placeholder)

        rows = [
            (
                trade["trade_date"],
                trade["symbol"],
                trade["signal_timestamp"],
                trade["price"],
                trade["best_entry"],
                trade["sl"],
                trade["tp1"],
                trade["tp2"],
                trade["rrr"],
                trade["score"],
                self._bool_value(trade["risk_off"]),
                trade["qty"],
                trade["lot_count"],
                trade["risk_amount"],
                trade["planned_notional"],
                trade["size_mode"],
                trade["size_notes"],
                trade["analyzer_snapshot"],
                "PLANNED",
                "PENDING",
                now,
                now,
            )
            for trade in trades
        ]
        self._executemany(insert_sql, rows)

    def update_trade_result(self, trade_date: str, symbol: str, result: dict):
        now = datetime.utcnow().isoformat()
        if self.backend == "supabase":
            self._supabase_request(
                "PATCH",
                "trades",
                params={"trade_date": f"eq.{trade_date}", "symbol": f"eq.{symbol}"},
                json={
                    "status": result["status"],
                    "fill_status": result["fill_status"],
                    "filled_at": result["filled_at"],
                    "filled_price": result["filled_price"],
                    "last_price": result["last_price"],
                    "exit_price": result["exit_price"],
                    "exit_reason": result["exit_reason"],
                    "pnl_amount": result["pnl_amount"],
                    "pnl_pct": result["pnl_pct"],
                    "realized_r": result["realized_r"],
                    "events": result["events"],
                    "finalized": bool(result["finalized"]),
                    "updated_at": now,
                },
            )
            return

        sql = """
            UPDATE trades
            SET status = {p}, fill_status = {p}, filled_at = {p}, filled_price = {p},
                last_price = {p}, exit_price = {p}, exit_reason = {p}, pnl_amount = {p},
                pnl_pct = {p}, realized_r = {p}, events = {p}, finalized = {p}, updated_at = {p}
            WHERE trade_date = {p} AND symbol = {p}
        """.format(p=self.placeholder)
        self._execute(
            sql,
            (
                result["status"],
                result["fill_status"],
                result["filled_at"],
                result["filled_price"],
                result["last_price"],
                result["exit_price"],
                result["exit_reason"],
                result["pnl_amount"],
                result["pnl_pct"],
                result["realized_r"],
                result["events"],
                self._bool_value(result["finalized"]),
                now,
                trade_date,
                symbol,
            ),
        )

    def get_trade_plans(self, trade_date: str, include_finalized: bool = True) -> list[dict]:
        if self.backend == "supabase":
            params = {
                "select": "*",
                "trade_date": f"eq.{trade_date}",
                "order": "score.desc,symbol.asc",
            }
            if not include_finalized:
                params["finalized"] = "eq.false"
            return self._supabase_request("GET", "trades", params=params)

        sql = f"SELECT * FROM trades WHERE trade_date = {self.placeholder}"
        params: list[Any] = [trade_date]
        if not include_finalized:
            sql += f" AND finalized = {self._false_value()}"
        sql += " ORDER BY score DESC, symbol ASC"
        return self._fetchall(sql, tuple(params))

    def get_active_trade_plans(self, trade_date: str) -> list[dict]:
        return self.get_trade_plans(trade_date, include_finalized=False)

    def get_daily_realized_r(self, trade_date: str) -> float:
        if self.backend == "supabase":
            rows = self._supabase_request(
                "GET",
                "trades",
                params={
                    "select": "realized_r",
                    "trade_date": f"eq.{trade_date}",
                    "finalized": "eq.true",
                },
            )
            return round(sum(float(row.get("realized_r") or 0) for row in rows), 4)

        row = self._fetchone(
            f"""
            SELECT COALESCE(SUM(realized_r), 0) AS total_r
            FROM trades
            WHERE trade_date = {self.placeholder} AND finalized = {self._true_value()}
            """,
            (trade_date,),
        )
        return float(row["total_r"]) if row else 0.0

    def get_today_summary(self, trade_date: str) -> dict:
        if self.backend == "supabase":
            rows = self._supabase_request(
                "GET",
                "trades",
                params={
                    "select": "pnl_amount,realized_r,fill_status",
                    "trade_date": f"eq.{trade_date}",
                },
            )
            return {
                "total_trades": len(rows),
                "total_pnl_amount": round(sum(float(row.get("pnl_amount") or 0) for row in rows), 2),
                "total_realized_r": round(sum(float(row.get("realized_r") or 0) for row in rows), 4),
                "winners": sum(1 for row in rows if float(row.get("pnl_amount") or 0) > 0),
                "losers": sum(1 for row in rows if float(row.get("pnl_amount") or 0) < 0),
                "unfilled": sum(1 for row in rows if row.get("fill_status") == "UNFILLED"),
            }

        row = self._fetchone(
            f"""
            SELECT
                COUNT(*) AS total_trades,
                COALESCE(SUM(pnl_amount), 0) AS total_pnl_amount,
                COALESCE(SUM(realized_r), 0) AS total_realized_r,
                COALESCE(SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END), 0) AS winners,
                COALESCE(SUM(CASE WHEN pnl_amount < 0 THEN 1 ELSE 0 END), 0) AS losers,
                COALESCE(SUM(CASE WHEN fill_status = 'UNFILLED' THEN 1 ELSE 0 END), 0) AS unfilled
            FROM trades
            WHERE trade_date = {self.placeholder}
            """,
            (trade_date,),
        )
        return row or {}

    def add_watch_symbol(self, user_id: str, symbol: str):
        now = datetime.utcnow().isoformat()
        if self.backend == "supabase":
            self._supabase_request(
                "POST",
                "watchlists",
                params={"on_conflict": "user_id,symbol"},
                json={"user_id": user_id, "symbol": symbol, "created_at": now},
                extra_headers={"Prefer": "resolution=merge-duplicates"},
            )
            return

        if self.backend == "postgres":
            sql = f"""
                INSERT INTO watchlists (user_id, symbol, created_at)
                VALUES ({self.placeholder}, {self.placeholder}, {self.placeholder})
                ON CONFLICT (user_id, symbol) DO NOTHING
            """
        else:
            sql = f"""
                INSERT OR IGNORE INTO watchlists (user_id, symbol, created_at)
                VALUES ({self.placeholder}, {self.placeholder}, {self.placeholder})
            """
        self._execute(sql, (user_id, symbol, now))

    def remove_watch_symbol(self, user_id: str, symbol: str) -> bool:
        if self.backend == "supabase":
            response = self._supabase_request(
                "DELETE",
                "watchlists",
                params={"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
                extra_headers={"Prefer": "return=representation"},
            )
            return bool(response)

        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM watchlists WHERE user_id = {self.placeholder} AND symbol = {self.placeholder}",
                (user_id, symbol),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

    def get_watchlist(self, user_id: str) -> list[str]:
        if self.backend == "supabase":
            rows = self._supabase_request(
                "GET",
                "watchlists",
                params={"select": "symbol", "user_id": f"eq.{user_id}", "order": "created_at.asc"},
            )
            return [row["symbol"] for row in rows]

        rows = self._fetchall(
            f"SELECT symbol FROM watchlists WHERE user_id = {self.placeholder} ORDER BY created_at ASC",
            (user_id,),
        )
        return [row["symbol"] for row in rows]

    def _bool_value(self, value: bool) -> bool | int:
        return bool(value) if self.backend == "postgres" else int(bool(value))

    def _true_value(self) -> str:
        return "TRUE" if self.backend == "postgres" else "1"

    def _false_value(self) -> str:
        return "FALSE" if self.backend == "postgres" else "0"

    def _supabase_request(
        self,
        method: str,
        table: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> list[dict]:
        headers = dict(self.supabase_headers or {})
        if extra_headers:
            headers.update(extra_headers)
        response = requests.request(
            method=method,
            url=f"{self.supabase_rest_url}/{table}",
            headers=headers,
            params=params,
            json=json,
            timeout=15,
        )
        response.raise_for_status()
        if not response.text.strip():
            return []
        return response.json()
