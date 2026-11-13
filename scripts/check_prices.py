import requests
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))

def ts(t):
    return datetime.fromtimestamp(t, BJ).strftime("%m-%d %H:%M")

def get(url, params=None):
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    return r.json()

print("=== ZEC cross-check: direct API, no cache ===")
try:
    t = get("https://api.gateio.ws/api/v4/futures/usdt/tickers", {"contract": "ZEC_USDT"})[0]
    print("Gate  perp : last=%s  24h[%s ~ %s]  %s%%" % (t["last"], t["low_24h"], t["high_24h"], t["change_percentage"]))
except Exception as e:
    print("Gate ERR:", e)
try:
    d = get("https://fapi.binance.com/fapi/v1/ticker/24hr", {"symbol": "ZECUSDT"})
    print("BN   perp : last=%s  24h[%s ~ %s]  %s%%" % (d["lastPrice"], d["lowPrice"], d["highPrice"], d["priceChangePercent"]))
except Exception as e:
    print("BN ZEC ERR:", e)
try:
    d = get("https://www.okx.com/api/v5/market/ticker", {"instId": "ZEC-USDT-SWAP"})
    print("OKX  perp : last=%s" % d["data"][0]["last"])
except Exception as e:
    print("OKX ERR:", e)

print()
print("=== ZEC 1h candles (Gate, last 24, oldest->newest) ===")
try:
    cs = get("https://api.gateio.ws/api/v4/futures/usdt/candlesticks", {"contract": "ZEC_USDT", "interval": "1h", "limit": 24})
    for c in reversed(cs):
        print("%s  O=%s H=%s L=%s C=%s" % (ts(c["t"]), c["o"], c["h"], c["l"], c["c"]))
except Exception as e:
    print("Gate candles ERR:", e)

print()
print("=== ETH verify ===")
try:
    d = get("https://fapi.binance.com/fapi/v1/ticker/24hr", {"symbol": "ETHUSDT"})
    print("BN   perp : last=%s  24h[%s ~ %s]  %s%%" % (d["lastPrice"], d["lowPrice"], d["highPrice"], d["priceChangePercent"]))
except Exception as e:
    print("BN ETH ERR:", e)
print("ETH 4h closes (last 6, oldest->newest):")
try:
    ks = get("https://fapi.binance.com/fapi/v1/klines", {"symbol": "ETHUSDT", "interval": "4h", "limit": 6})
    for k in reversed(ks):
        print("%s  O=%.1f H=%.1f L=%.1f C=%.1f" % (ts(k[0] / 1000), float(k[1]), float(k[2]), float(k[3]), float(k[4])))
except Exception as e:
    print("BN 4h ERR:", e)
print("ETH 1h (last 14, oldest->newest):")
try:
    ks = get("https://fapi.binance.com/fapi/v1/klines", {"symbol": "ETHUSDT", "interval": "1h", "limit": 14})
    for k in reversed(ks):
        print("%s  O=%.1f H=%.1f L=%.1f C=%.1f" % (ts(k[0] / 1000), float(k[1]), float(k[2]), float(k[3]), float(k[4])))
except Exception as e:
    print("BN 1h ERR:", e)
