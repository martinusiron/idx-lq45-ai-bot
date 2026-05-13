"""
Probe semua kemungkinan GoAPI endpoint untuk broker summary.
"""
import requests

API_KEY = "631be76d-2000-53c6-5a71-43bef863"
SYMBOL  = "BBCA"
DATE    = "2026-05-12"

HEADERS = {"Authorization": API_KEY, "accept": "application/json"}
PARAMS  = {"api_key": API_KEY, "date": DATE}

ENDPOINTS = [
    f"https://api.goapi.io/stock/idx/{SYMBOL}/broker-summary",
    f"https://api.goapi.io/stock/idx/{SYMBOL}/broker",
    f"https://api.goapi.io/stock/idx/{SYMBOL}/brokers",
    f"https://api.goapi.io/stock/idx/broker-summary",
    f"https://api.goapi.io/stock/idx/broker",
    f"https://api.goapi.io/v2/stock/idx/{SYMBOL}/broker-summary",
    # Try foreign flow
    f"https://api.goapi.io/stock/idx/{SYMBOL}/foreign",
    f"https://api.goapi.io/stock/idx/{SYMBOL}/net-foreign",
    f"https://api.goapi.io/stock/idx/foreign-flow",
    # Try indicators
    f"https://api.goapi.io/stock/idx/{SYMBOL}/indicators",
    f"https://api.goapi.io/stock/idx/indicators",
]

print(f"{'='*60}")
print(f"GoAPI Broker Summary Probe")
print(f"{'='*60}\n")

for url in ENDPOINTS:
    try:
        r = requests.get(url, params=PARAMS, headers=HEADERS, timeout=8)
        status = r.status_code
        body = r.text[:200]
        print(f"[{status}] {url.replace('https://api.goapi.io', '')}")
        if status == 200:
            print(f"         ✅ BERHASIL: {body}")
        print()
    except Exception as e:
        print(f"[ERR] {url}: {e}\n")
