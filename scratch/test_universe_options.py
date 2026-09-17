import sys
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

symbols = ['RELIANCE', 'INFY', 'BAJFINANCE', 'TATAMOTORS', 'HDFCBANK', 'ICICIBANK', 'TCS', 'TVSMOTOR', 'NIFTY', 'BANKNIFTY']
for s in symbols:
    url = f"http://127.0.0.1:8000/market/option-price?symbol={s}&option_type=CE"
    r = requests.get(url, timeout=5)
    if r.status_code == 200:
        d = r.json()
        print(f"{d['symbol']:12} -> {d['display_symbol']:22} | Expiry: {d['expiry_date']} ({int(d['days_to_expiry'])}d) | Spot: {d['spot_price']} | Premium: {d['premium']} | Lot: {d['lot_size']} | {d['source']}")
    else:
        print(s, "FAILED:", r.status_code)
