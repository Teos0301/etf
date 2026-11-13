# -*- coding: utf-8 -*-
"""ETH/USDT 永续多周期抓取 v3
策略: 欧易优先(带重试, 偶发断连自动恢复), K线失败的周期先走币安国内镜像(快, 现货),
再不行用 Gate 永续补齐; meta 欧易→Gate(保永续费率/持仓)→币安镜像兜底。
输出 klines.json: {timeframes:{tf:[[ts_ms,o,h,l,c,vol_eth,vol_usdt]...]}...}
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import requests

CN_TZ = timezone(timedelta(hours=8))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

BARS = 300
TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
OKX_BAR = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}


def _get(url, params=None, timeout=8, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=H)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.25 * (i + 1))
    raise last


def okx_alive():
    # 轻量探活: 一次4秒超时, 挂了就整轮跳过OKX, 避免全周期重试拖时间
    try:
        _get("https://www.okx.com/api/v5/public/time", timeout=4, retries=1)
        return True
    except Exception:
        return False


def okx_klines(tf):
    data = _get("https://www.okx.com/api/v5/market/candles",
                {"instId": "ETH-USDT-SWAP", "bar": OKX_BAR[tf], "limit": BARS})
    if str(data.get("code")) != "0" or not data.get("data"):
        raise RuntimeError("okx %s code=%s" % (tf, data.get("code")))
    # [ts,o,h,l,c,vol张,volCcy(ETH),volCcyQuote(USDT),confirm] 新->旧
    rows = sorted([[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                    float(k[6] if len(k) > 6 else k[5]),
                    float(k[7] if len(k) > 7 else 0)] for k in data["data"]],
                  key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("okx %s rows=%d" % (tf, len(rows)))
    return rows


def gate_klines(tf):
    data = _get("https://fx-api.gateio.ws/api/v4/futures/usdt/candlesticks",
                {"contract": "ETH_USDT", "interval": tf, "limit": BARS})
    rows = sorted([[int(x["t"]) * 1000, float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]),
                    float(x["v"]) * 0.01, float(x.get("sum") or 0)] for x in data], key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("gate %s rows=%d" % (tf, len(rows)))
    return rows


def binance_vision_klines(tf):
    # data-api.binance.vision 是币安官方"仅行情"域名, 国内可直连; 只有现货, 无合约
    data = _get("https://data-api.binance.vision/api/v3/klines",
                {"symbol": "ETHUSDT", "interval": tf, "limit": BARS})
    # [开时间,o,h,l,c,量ETH,收时间,成交额USDT,...]
    rows = sorted([[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                    float(k[5]), float(k[7])] for k in data], key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("binance %s rows=%d" % (tf, len(rows)))
    return rows


def binance_vision_meta():
    tk = _get("https://data-api.binance.vision/api/v3/ticker/24hr", {"symbol": "ETHUSDT"})
    m = {}
    m["lastPrice"] = float(tk["lastPrice"])
    m["chg24hPct"] = float(tk["priceChangePercent"])
    m["high24h"] = float(tk["highPrice"])
    m["low24h"] = float(tk["lowPrice"])
    m["vol24hQuote"] = float(tk["quoteVolume"])
    m["markPrice"] = m["lastPrice"]
    m["indexPrice"] = m["lastPrice"]
    m["fundingRate"] = 0.0
    m["nextFundingTime"] = 0
    m["openInterestETH"] = 0
    m["openInterestUSD"] = 0
    return m


def okx_meta():
    tk = _get("https://www.okx.com/api/v5/market/ticker", {"instId": "ETH-USDT-SWAP"})["data"][0]
    fr = _get("https://www.okx.com/api/v5/public/funding-rate", {"instId": "ETH-USDT-SWAP"})["data"][0]
    oi = _get("https://www.okx.com/api/v5/public/open-interest",
              {"instType": "SWAP", "instId": "ETH-USDT-SWAP"})["data"][0]
    m = {}
    m["lastPrice"] = float(tk["last"])
    m["chg24hPct"] = round((float(tk["last"]) / float(tk["open24h"]) - 1) * 100, 3)
    m["high24h"] = float(tk["high24h"])
    m["low24h"] = float(tk["low24h"])
    m["vol24hQuote"] = float(tk.get("volCcy24h") or 0) * float(tk["last"])
    m["fundingRate"] = float(fr["fundingRate"])
    m["nextFundingTime"] = int(fr["nextFundingTime"])
    m["openInterestETH"] = round(float(oi.get("oiCcy") or 0))
    m["openInterestUSD"] = round(m["openInterestETH"] * m["lastPrice"])
    try:
        mp = _get("https://www.okx.com/api/v5/public/mark-price",
                  {"instId": "ETH-USDT-SWAP", "markPxType": "index_price_1"})["data"][0]
        m["markPrice"] = float(mp["markPx"])
        m["indexPrice"] = float(mp.get("indexPx") or 0)
    except Exception:
        m["markPrice"] = float(fr.get("markPx") or 0)
        m["indexPrice"] = 0.0
    try:
        fh = _get("https://www.okx.com/api/v5/public/funding-rate-history",
                  {"instId": "ETH-USDT-SWAP", "limit": "8"})["data"]
        m["fundingHistory"] = [[int(x.get("fundingTime") or x.get("ts") or 0),
                                float(x["fundingRate"])] for x in reversed(fh)]
    except Exception:
        pass
    return m


def gate_meta():
    tk = _get("https://fx-api.gateio.ws/api/v4/futures/usdt/tickers", {"contract": "ETH_USDT"})
    if isinstance(tk, list):
        tk = tk[0]
    ct = _get("https://fx-api.gateio.ws/api/v4/futures/usdt/contracts/ETH_USDT")
    m = {}
    m["lastPrice"] = float(tk["last"])
    m["chg24hPct"] = float(tk.get("change_percentage") or 0)
    m["high24h"] = float(tk.get("high_24h") or 0)
    m["low24h"] = float(tk.get("low_24h") or 0)
    m["vol24hQuote"] = float(tk.get("volume_24h_quote") or 0)
    m["markPrice"] = float(tk.get("mark_price") or 0)
    m["indexPrice"] = float(tk.get("index_price") or 0)
    m["fundingRate"] = float(ct.get("funding_rate") or 0)
    m["nextFundingTime"] = int(ct.get("funding_next_apply") or 0) * 1000
    m["openInterestETH"] = round(float(ct.get("position_size") or 0) * 0.01)
    m["openInterestUSD"] = round(m["openInterestETH"] * m["lastPrice"])
    return m


def main():
    t0 = time.time()
    result = {"exchange": "okx", "label": "欧易 OKX ETH-USDT 永续", "timeframes": {}, "meta": {}}
    src_map = {}

    # K线: 欧易并发3, 失败周期先试币安镜像(快)再用 Gate 补
    use_okx = okx_alive()
    if not use_okx:
        print("[INFO] OKX 探活失败, 本轮跳过欧易")
    with ThreadPoolExecutor(3) as ex:
        futs = {tf: ex.submit(okx_klines, tf) for tf in TFS} if use_okx else {}
        failed = [] if use_okx else list(TFS)
        for tf in TFS:
            if tf in futs:
                try:
                    result["timeframes"][tf] = futs[tf].result()
                    src_map[tf] = "OKX"
                except Exception:
                    failed.append(tf)
    for tf in failed:
        for fn, src in ((binance_vision_klines, "Binance"), (gate_klines, "Gate")):
            try:
                result["timeframes"][tf] = fn(tf)
                src_map[tf] = src
                break
            except Exception:
                continue
        if tf not in src_map:
            print("[ERR] %s 三个源都失败" % tf)
            sys.exit(1)

    # meta: 欧易优先, Gate 保永续费率/持仓, 都挂才用币安现货镜像
    if use_okx:
        try:
            result["meta"] = okx_meta()
        except Exception:
            pass
    if not result["meta"]:
        try:
            result["meta"] = gate_meta()
            result["label"] = "Gate.io ETH/USDT 永续(备用源)"
            result["exchange"] = "gateio"
        except Exception:
            result["meta"] = binance_vision_meta()
            result["label"] = "币安现货镜像 binance.vision (ETHUSDT)"
            result["exchange"] = "binance-spot"

    mixed = len(set(src_map.values())) > 1
    if mixed:
        result["label"] += " (混合: " + ", ".join("%s=%s" % (k, v) for k, v in src_map.items() if v != "OKX") + ")"

    result["fetchedAt"] = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    result["fetchedTs"] = int(time.time() * 1000)
    with open("klines.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    m = result["meta"]
    print("=" * 50)
    print("数据源: %s  总耗时 %.1fs" % (result["label"], time.time() - t0))
    print("最新价: %.2f  标记: %.2f  指数: %.2f  24h: %+.2f%%" % (
        m["lastPrice"], m.get("markPrice", 0), m.get("indexPrice", 0), m["chg24hPct"]))
    print("24h高/低: %.2f / %.2f  24h额: %.1f亿U" % (m["high24h"], m["low24h"], m["vol24hQuote"] / 1e8))
    print("资金费率: %+.4f%%  结算: %s  持仓: %s ETH" % (
        m["fundingRate"] * 100,
        datetime.fromtimestamp(m["nextFundingTime"] / 1000, CN_TZ).strftime("%H:%M"),
        format(m["openInterestETH"], ",")))
    if m.get("fundingHistory"):
        print("费率历史: " + " ".join("%+.4f%%" % (r[1] * 100) for r in m["fundingHistory"]))
    for tf in TFS:
        rows = result["timeframes"][tf]
        b = datetime.fromtimestamp(rows[-1][0] / 1000, CN_TZ).strftime("%H:%M")
        print("  %-3s: %d根[%s] 最新收:%.2f (%s)" % (tf, len(rows), b, rows[-1][4], src_map.get(tf, "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
