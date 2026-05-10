"""
global_macro.py — Analisa kondisi makro global yang berdampak ke IDX.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

MACRO_TICKERS = {
    "^JKSE":    {"label": "IHSG",        "type": "index"},
    "DX-Y.NYB": {"label": "DXY (USD)",   "type": "index"},
    "^TNX":     {"label": "US10Y Yield", "type": "yield"},
    "BZ=F":     {"label": "Brent Oil",   "type": "commodity"},
    "^SPGSIK":  {"label": "Nikel",       "type": "commodity"},   # NI=F → S&P GSCI Nickel
    "NCF=F":    {"label": "Batubara",    "type": "commodity"},   # Newcastle Coal Futures
    "^VIX":     {"label": "VIX (Fear)",  "type": "sentiment"},
    "GC=F":     {"label": "Gold",        "type": "commodity"},   # tambahan: Emas (safe haven indicator)
}

RISK_OFF_RULES = {
    "^VIX":     {"condition": "above",        "value": 25,   "msg": "VIX tinggi (>{value}) — pasar global panik"},
    "DX-Y.NYB": {"condition": "change_above", "value": 0.5,  "msg": "DXY naik tajam — tekanan rupiah & outflow"},
    "^TNX":     {"condition": "above",        "value": 4.5,  "msg": "US10Y Yield tinggi (>{value}%) — risk aversion"},
    "^JKSE":    {"condition": "change_below", "value": -1.0, "msg": "IHSG turun >{value}% hari ini — hati-hati"},
}


class GlobalMacroAnalyzer:
    def __init__(self) -> None:
        self.cache:      dict     = {}
        self.cache_time: datetime | None = None

    def _fetch_all(self) -> dict:
        now = datetime.now()
        if self.cache and self.cache_time and (now - self.cache_time).seconds < 900:
            return self.cache

        results: dict = {}
        for ticker, meta in MACRO_TICKERS.items():
            try:
                df = yf.download(ticker, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if df.empty or len(df) < 2:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]

                latest     = float(df["close"].iloc[-1])
                prev       = float(df["close"].iloc[-2])
                change_pct = round((latest - prev) / prev * 100, 2)

                results[ticker] = {
                    "label":      meta["label"],
                    "type":       meta["type"],
                    "value":      round(latest, 2),
                    "change_pct": change_pct,
                }
            except Exception as exc:
                logger.warning(f"[macro] {ticker}: {exc}")

        self.cache      = results
        self.cache_time = now
        return results

    def get_macro_context(self) -> dict:
        data     = self._fetch_all()
        warnings = self._evaluate_warnings(data)
        # risk_off_mode dibaca dari config di sini agar tidak circular import
        try:
            from config import RISK_OFF_MODE
            risk_mode = RISK_OFF_MODE
        except ImportError:
            risk_mode = "reduce"
        return {
            "data":        data,
            "warnings":    warnings,
            "is_risk_off": len(warnings) >= 2,
            "risk_mode":   risk_mode,
        }

    def check_risk_off(self) -> tuple[bool, list[str]]:
        data     = self._fetch_all()
        warnings = self._evaluate_warnings(data)
        return len(warnings) >= 2, warnings

    def _evaluate_warnings(self, data: dict) -> list[str]:
        warnings: list[str] = []
        for ticker, rule in RISK_OFF_RULES.items():
            if ticker not in data:
                continue
            val = data[ticker]["value"]
            chg = data[ticker]["change_pct"]
            if rule["condition"] == "above" and val > rule["value"]:
                warnings.append(rule["msg"].format(value=rule["value"]))
            elif rule["condition"] == "change_above" and chg > rule["value"]:
                warnings.append(rule["msg"].format(value=rule["value"]))
            elif rule["condition"] == "change_below" and chg < rule["value"]:
                warnings.append(rule["msg"].format(value=abs(rule["value"])))
        return warnings