
import requests
import json

API_KEY = "631be76d-2000-53c6-5a71-43bef863"

def test_goapi():
    # Test getting daily prices for BBCA
    url = "https://api.goapi.io/v2/stock/idx/prices"
    params = {
        "symbols": "BBCA",
        "api_key": API_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        print("Prices Status Code:", response.status_code)
        if response.status_code == 200:
            print("Prices Response:", json.dumps(response.json(), indent=2))
        else:
            print("Prices Error:", response.text)
    except Exception as e:
        print("Prices Exception:", e)

    # Test getting candles for BBCA
    # Based on common GoAPI patterns
    url_candles = f"https://api.goapi.io/v2/stock/idx/tickers/BBCA/candles"
    params_candles = {
        "api_key": API_KEY,
        "from": "2026-05-11",
        "to": "2026-05-12"
    }
    
    try:
        response = requests.get(url_candles, params=params_candles)
        print("\nCandles Status Code:", response.status_code)
        if response.status_code == 200:
            print("Candles Response (first 2):", json.dumps(response.json()["data"]["results"][:2], indent=2))
        else:
            print("Candles Error:", response.text)
    except Exception as e:
        print("Candles Exception:", e)

if __name__ == "__main__":
    test_goapi()
