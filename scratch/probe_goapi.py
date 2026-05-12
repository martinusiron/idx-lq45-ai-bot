"""
Probe endpoint historical yang benar berdasarkan Swagger URL pattern.
"""
import requests
import json

API_KEY = "631be76d-2000-53c6-5a71-43bef863"
SYMBOL  = "BBCA"

HEADERS = {
    "Authorization": API_KEY,
    "accept": "application/json"
}

ENDPOINTS_TO_TEST = [
    # Pattern dari Swagger: get_stock_idx__symbol__historical
    ("GET historical (correct path)", f"https://api.goapi.io/stock/idx/{SYMBOL}/historical"),
    ("GET historical (correct path v2)", f"https://api.goapi.io/v2/stock/idx/{SYMBOL}/historical"),

    # Harga terakhir yang sudah WORK
    ("GET prices (confirmed)",       "https://api.goapi.io/stock/idx/prices"),

    # Coba juga trailing tickers
    ("GET all-stock prices",         "https://api.goapi.io/stock/idx/all-stock"),
]

PARAMS_HIST = {
    "api_key": API_KEY,
    "from": "2026-05-01",
    "to":   "2026-05-12",
    "interval": "15m",
}
PARAMS_PRICE = {
    "api_key": API_KEY,
    "symbols": SYMBOL
}

print(f"{'='*60}")
print(f"GoAPI Endpoint Probe Round 2")
print(f"{'='*60}\n")

for label, url in ENDPOINTS_TO_TEST:
    is_price = "prices" in url or "all-stock" in url
    params   = PARAMS_PRICE if is_price else PARAMS_HIST

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        status = resp.status_code
        body   = resp.text[:300]
        print(f"[{status}] {label}")
        print(f"         URL: {resp.url}")
        print(f"         Body: {body}")
        print()
    except Exception as e:
        print(f"[ERR] {label}: {e}\n")
