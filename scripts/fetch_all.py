# -*- coding: utf-8 -*-
"""ETH/USDT 永续多周期抓取 v4
策略: Gate 永续为主(带重试), 探活失败整轮跳过;
K线失败周期按 Gate → HTX(api.hbdm.vn) → Hyperliquid 降级;
meta 同链路 Gate → HTX → Hyperliquid, 三者都提供永续资金费率/持仓量。
注意: Hyperliquid 资金费率按小时结算, 写入前统一折算成 8h 口径。
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
HTX_PERIOD = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "60min", "4h": "4hour", "1d": "1day"}
HL_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


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


def _post(url, payload, timeout=8, retries=4):
    # Hyperliquid 偶发 SSL 握手失败, 多给一次重试
    last = None
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=timeout, headers=H)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.3 * (i + 1))
    raise last


def gate_alive():
    # 轻量探活: 一次4秒超时, 挂了就整轮跳过 Gate, 避免全周期重试拖时间
    try:
        _get("https://fx-api.gateio.ws/api/v4/futures/usdt/tickers",
             {"contract": "ETH_USDT"}, timeout=4, retries=1)
        return True
    except Exception:
        return False


def gate_klines(tf):
    data = _get("https://fx-api.gateio.ws/api/v4/futures/usdt/candlesticks",
                {"contract": "ETH_USDT", "interval": tf, "limit": BARS})
    rows = sorted([[int(x["t"]) * 1000, float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]),
                    float(x["v"]) * 0.01, float(x.get("sum") or 0)] for x in data], key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("gate %s rows=%d" % (tf, len(rows)))
    return rows


def htx_klines(tf):
    data = _get("https://api.hbdm.vn/linear-swap-ex/market/history/kline",
                {"contract_code": "ETH-USDT", "period": HTX_PERIOD[tf], "size": BARS})
    if data.get("status") != "ok" or not data.get("data"):
        raise RuntimeError("htx %s status=%s" % (tf, data.get("status")))
    # id(秒) o h l c, amount=成交量(ETH), trade_turnover=成交额(USDT); 新->旧
    rows = sorted([[int(x["id"]) * 1000, float(x["open"]), float(x["high"]), float(x["low"]),
                    float(x["close"]), float(x.get("amount") or 0), float(x.get("trade_turnover") or 0)]
                   for x in data["data"]], key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("htx %s rows=%d" % (tf, len(rows)))
    return rows


def hl_klines(tf):
    start = int(time.time() * 1000) - (BARS + 2) * HL_SEC[tf] * 1000
    data = _post("https://api.hyperliquid.xyz/info",
                 {"type": "candleSnapshot",
                  "req": {"coin": "ETH", "interval": tf, "startTime": start}})
    # t(ms) o h l c v(ETH), 无成交额, 用收盘价估算 USDT 额
    rows = sorted([[int(x["t"]), float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]),
                    float(x["v"]), float(x["v"]) * float(x["c"])] for x in data], key=lambda r: r[0])
    if len(rows) < 60:
        raise RuntimeError("hl %s rows=%d" % (tf, len(rows)))
    return rows


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


def htx_meta():
    tk = _get("https://api.hbdm.vn/linear-swap-ex/market/detail/merged",
              {"contract_code": "ETH-USDT"})["tick"]
    fr = _get("https://api.hbdm.vn/linear-swap-api/v1/swap_funding_rate",
              {"contract_code": "ETH-USDT"})["data"]
    oi = _get("https://api.hbdm.vn/linear-swap-api/v1/swap_open_interest",
              {"contract_code": "ETH-USDT"})["data"][0]
    # merged 接口的 open/high/low 是"当日"口径, 24h 指标用最近 25 根 1h K线自己算
    ks = sorted(_get("https://api.hbdm.vn/linear-swap-ex/market/history/kline",
                     {"contract_code": "ETH-USDT", "period": "60min", "size": 25})["data"],
                key=lambda x: int(x["id"]))
    win = ks[-24:]
    last = float(tk["close"])
    ref = float(ks[-25]["close"]) if len(ks) >= 25 else last
    m = {}
    m["lastPrice"] = last
    m["chg24hPct"] = round((last / ref - 1) * 100, 3) if ref else 0.0
    m["high24h"] = max(float(x["high"]) for x in win)
    m["low24h"] = min(float(x["low"]) for x in win)
    m["vol24hQuote"] = float(tk.get("trade_turnover") or 0)
    m["markPrice"] = last
    try:
        idx = _get("https://api.hbdm.vn/linear-swap-api/v1/swap_index",
                   {"contract_code": "ETH-USDT"})["data"][0]
        m["indexPrice"] = float(idx.get("index_price") or last)
    except Exception:
        m["indexPrice"] = last
    m["fundingRate"] = float(fr.get("funding_rate") or 0)
    m["nextFundingTime"] = int(fr.get("funding_time") or 0)
    m["openInterestETH"] = round(float(oi.get("amount") or 0))
    m["openInterestUSD"] = round(float(oi.get("value") or 0))
    return m


def hl_meta():
    data = _post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    ctx = data[1][[u["name"] for u in data[0]["universe"]].index("ETH")]
    last = float(ctx.get("midPx") or ctx.get("markPx"))
    prev = float(ctx.get("prevDayPx") or last)
    # 该源不给 24h 高低, 用最近 24 根 1h K线聚合
    highs, lows = [], []
    try:
        cs = _post("https://api.hyperliquid.xyz/info",
                   {"type": "candleSnapshot",
                    "req": {"coin": "ETH", "interval": "1h",
                            "startTime": int(time.time() * 1000) - 25 * 3600 * 1000}})
        highs = [float(c["h"]) for c in cs[-24:]]
        lows = [float(c["l"]) for c in cs[-24:]]
    except Exception:
        pass
    m = {}
    m["lastPrice"] = last
    m["chg24hPct"] = round((last / prev - 1) * 100, 3) if prev else 0.0
    m["high24h"] = max(highs) if highs else last
    m["low24h"] = min(lows) if lows else last
    m["vol24hQuote"] = float(ctx.get("dayNtlVlm") or 0)
    m["markPrice"] = float(ctx.get("markPx") or last)
    m["indexPrice"] = float(ctx.get("oraclePx") or last)
    # 每小时结算, 折算成 8h 口径后再写入
    m["fundingRate"] = float(ctx.get("funding") or 0) * 8
    nxt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    m["nextFundingTime"] = int(nxt.timestamp() * 1000)
    m["openInterestETH"] = round(float(ctx.get("openInterest") or 0))
    m["openInterestUSD"] = round(m["openInterestETH"] * last)
    return m


def main():
    t0 = time.time()
    result = {"exchange": "gateio", "label": "Gate.io ETH/USDT 永续", "timeframes": {}, "meta": {}}
    src_map = {}

    # K线: Gate -> HTX -> Hyperliquid, 逐周期降级, 并发3
    use_gate = gate_alive()
    if not use_gate:
        print("[INFO] Gate 探活失败, 本轮跳过 Gate")

    def fetch_kline(tf):
        chain = ([(gate_klines, "Gate")] if use_gate else []) + [(htx_klines, "HTX"), (hl_klines, "HL")]
        err = None
        for fn, src in chain:
            try:
                return src, fn(tf)
            except Exception as e:
                err = e
        raise RuntimeError("%s 三个源都失败: %s" % (tf, err))

    with ThreadPoolExecutor(3) as ex:
        futs = {tf: ex.submit(fetch_kline, tf) for tf in TFS}
        for tf in TFS:
            try:
                src, rows = futs[tf].result()
                result["timeframes"][tf] = rows
                src_map[tf] = src
            except Exception as e:
                print("[ERR] %s" % e)
                sys.exit(1)

    # meta: Gate 优先, 其次 HTX, 最后 Hyperliquid(费率折算8h)
    for fn, label, ex_name in ((gate_meta, "Gate.io ETH/USDT 永续", "gateio"),
                               (htx_meta, "HTX 火币 ETH/USDT 永续(备用源)", "htx"),
                               (hl_meta, "Hyperliquid ETH 永续(备用源, 费率已折算为8h)", "hyperliquid")):
        try:
            result["meta"] = fn()
            result["label"] = label
            result["exchange"] = ex_name
            break
        except Exception:
            continue
    if not result["meta"]:
        print("[ERR] 三个源的 meta 都失败")
        sys.exit(1)

    # K线来源与 meta 源不一致时, 在 label 里如实标出
    src_name = {"gateio": "Gate", "htx": "HTX", "hyperliquid": "HL"}[result["exchange"]]
    off = [(tf, s) for tf, s in src_map.items() if s != src_name]
    if off:
        result["label"] += " (混合: " + ", ".join("%s=%s" % (k, v) for k, v in off) + ")"

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
