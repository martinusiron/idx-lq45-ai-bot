import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Mapping ticker → label ────────────────────────────────────────────────────
MACRO_TICKERS = {
    '^JKSE':    {'label': 'IHSG',          'type': 'index'},
    'DX-Y.NYB': {'label': 'DXY (USD)',     'type': 'index'},
    '^TNX':     {'label': 'US10Y Yield',   'type': 'yield'},
    'BZ=F':     {'label': 'Brent Oil',     'type': 'commodity'},
    'NI=F':     {'label': 'Nikel',         'type': 'commodity'},
    'MTF=F':    {'label': 'Batubara',      'type': 'commodity'},
    '^VIX':     {'label': 'VIX (Fear)',    'type': 'sentiment'},
}

# ── Threshold untuk filter global ────────────────────────────────────────────
RISK_OFF_RULES = {
    '^VIX':     {'condition': 'above', 'value': 25,   'msg': 'VIX tinggi (>{value}) — pasar global panik'},
    'DX-Y.NYB': {'condition': 'change_above', 'value': 0.5, 'msg': 'DXY naik tajam — tekanan rupiah & outflow'},
    '^TNX':     {'condition': 'above', 'value': 4.5,  'msg': 'US10Y Yield tinggi (>{value}%) — risk aversion'},
    '^JKSE':    {'condition': 'change_below', 'value': -1.0, 'msg': 'IHSG turun >{value}% hari ini — hati-hati'},
}


class GlobalMacroAnalyzer:
    """
    Analisa kondisi makro global yang berdampak ke IDX.
    
    Dua fungsi utama:
    1. get_macro_context() — ambil data semua indikator untuk ditampilkan
    2. check_risk_off()    — cek apakah kondisi global sedang risk-off
                             (filter untuk batalkan/kurangi sinyal BUY)
    """

    def __init__(self):
        self.cache       = {}   # cache hasil fetch agar tidak double request
        self.cache_time  = None

    def _fetch_all(self) -> dict:
        """Fetch semua macro ticker sekaligus, cache hasilnya."""
        import datetime
        now = datetime.datetime.now()

        # Cache 15 menit — cukup untuk intraday
        if self.cache and self.cache_time:
            delta = (now - self.cache_time).seconds
            if delta < 900:
                return self.cache

        results = {}
        for ticker, meta in MACRO_TICKERS.items():
            try:
                df = yf.download(ticker, period='5d', interval='1d',
                                 progress=False, auto_adjust=True)
                if df.empty or len(df) < 2:
                    continue

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]

                latest     = float(df['close'].iloc[-1])
                prev       = float(df['close'].iloc[-2])
                change_pct = round((latest - prev) / prev * 100, 2)

                results[ticker] = {
                    'label':      meta['label'],
                    'type':       meta['type'],
                    'value':      round(latest, 2),
                    'change_pct': change_pct,
                }
            except Exception as e:
                logger.warning(f"[macro] {ticker} fetch error: {e}")

        self.cache      = results
        self.cache_time = now
        return results

    def get_macro_context(self) -> dict:
        """
        Return dict semua indikator makro + status risk-off.
        Dipakai untuk ditampilkan di notifikasi sinyal.
        """
        data     = self._fetch_all()
        warnings = self._evaluate_warnings(data)
        return {
            'data':     data,
            'warnings': warnings,
            'is_risk_off': len(warnings) >= 2,  # risk-off jika 2+ warning aktif
        }

    def check_risk_off(self) -> tuple[bool, list[str]]:
        """
        Return (is_risk_off: bool, alasan: list[str])
        Dipakai sebagai filter di job_morning_signal.
        """
        data     = self._fetch_all()
        warnings = self._evaluate_warnings(data)
        return len(warnings) >= 2, warnings

    def _evaluate_warnings(self, data: dict) -> list[str]:
        warnings = []
        for ticker, rule in RISK_OFF_RULES.items():
            if ticker not in data:
                continue
            d   = data[ticker]
            val = d['value']
            chg = d['change_pct']

            if rule['condition'] == 'above' and val > rule['value']:
                warnings.append(rule['msg'].format(value=rule['value']))
            elif rule['condition'] == 'change_above' and chg > rule['value']:
                warnings.append(rule['msg'].format(value=rule['value']))
            elif rule['condition'] == 'change_below' and chg < rule['value']:
                warnings.append(rule['msg'].format(value=abs(rule['value'])))
        return warnings