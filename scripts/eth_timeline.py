import json
import urllib.request
import datetime


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def show(title, interval, limit):
    ks = get(
        f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract=ETH_USDT&interval={interval}&limit={limit}"
    )
    print(f"=== ETH {interval} (Gate, oldest->newest) ===")
    for k in ks:
        ts = datetime.datetime.fromtimestamp(k["t"]).strftime("%m-%d %H:%M")
        print(
            f"{ts}  O={float(k['o']):.2f} H={float(k['h']):.2f} "
            f"L={float(k['l']):.2f} C={float(k['c']):.2f}"
        )
    print()


show("4h", "4h", 8)
show("1h", "1h", 20)
