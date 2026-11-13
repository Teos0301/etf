# -*- coding: utf-8 -*-
"""组装交互式K线报告: 读 klines.json + summary.json -> 自包含HTML(工作区)"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import compute as C

CN_TZ = timezone(timedelta(hours=8))
TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
MAX_BARS = 500  # 每周期嵌入根数
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ETH永续合约_多周期K线分析.html")


def round_or_none(arr, nd=2):
    return [None if v is None else round(v, nd) for v in arr]


def build_tf_data(rows):
    closes = [r[4] for r in rows]
    if len(rows) > MAX_BARS:
        rows = rows[-MAX_BARS:]
        closes = closes[-MAX_BARS:]
    m5, m10, m20, m60 = C.ma(closes, 5), C.ma(closes, 10), C.ma(closes, 20), C.ma(closes, 60)
    bu, bm, bl = C.boll(closes)
    dif, dea, hist = C.macd(closes)
    r14 = C.rsi(closes)
    return {
        "k": [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows],
        "ma5": round_or_none(m5), "ma10": round_or_none(m10),
        "ma20": round_or_none(m20), "ma60": round_or_none(m60),
        "bu": round_or_none(bu), "bm": round_or_none(bm), "bl": round_or_none(bl),
        "dif": round_or_none(dif, 3), "dea": round_or_none(dea, 3), "hist": round_or_none(hist, 3),
        "rsi": round_or_none(r14, 1),
    }


def strategy_html(s):
    m = s["meta"]
    t = s["timeframes"]
    reg = s.get("regime") or {"name": "中性", "desc": "", "plan": "", "bias": 0}

    stance = "<b>%s</b>——%s。<br/>当前策略基调：<b>%s</b>。" % (reg["name"], reg["desc"], reg["plan"])
    if t["1h"]["score"] <= -2:
        stance += "短线处回调段，回踩不追价、等企稳信号再进场。"
    elif t["1h"]["score"] >= 2:
        stance += "短线动能延续，回踩幅度可能有限，踏空勿追。"

    fr = m["fundingRate"] * 100
    if fr < 0:
        fr_txt = ("当前资金费率 %+.4f%%（空头付给多头）。空头拥挤，属<b>反向情绪指标：对上涨不构成压力</b>，上攻易触发轧空。" % fr)
    elif fr > 0.05:
        fr_txt = "当前资金费率 %+.4f%%（多头付给空头），多头情绪偏热，<b>警惕高位回调或多杀多</b>。" % fr
    else:
        fr_txt = "当前资金费率 %+.4f%%（多头付给空头），处于正常区间，情绪温和，对行情无显著压力。" % fr

    html = ["<h2>策略结论（基于抓取时刻数据自动生成）</h2>",
            "<h4>① 大势判断</h4><p>%s</p>" % stance,
            "<p>%s 全网持仓约 <span class='kv'>%.0f 万 ETH</span>，24h成交 <span class='kv'>%.1f 亿USDT</span>。</p>"
            % (fr_txt, m.get("openInterestETH", 0) / 1e4, m["vol24hQuote"] / 1e8)]
    if t["1h"].get("divergence"):
        html.append("<p>注意：1小时出现<b>%s</b>，追高需谨慎。</p>" % t["1h"]["divergence"])

    pats = s.get("patterns") or []
    if pats:
        up = "<span style='color:var(--up)'>看涨</span>"
        dn = "<span style='color:var(--dn)'>看跌</span>"
        shown = sorted(pats, key=lambda p: (-C.TF_WEIGHT.get(p["period"], 0.5), -p["conf"]))[:8]
        items = "".join(
            "<li><b>%s（%s · %s）</b>：%s；入场=有效%s触发线 <span class='kv'>%.0f</span>，SL=%.0f（形态失效位），TP=%.0f（高度投影）—— <b>%s</b></li>"
            % (p["name"], p["period"], up if p["dir"] == "多" else dn, p["reason"],
               "突破" if p["dir"] == "多" else "跌破", p["line"], p["sl"], p["tp"], p["status"])
            for p in shown)
        html.append("<h4>② 图表形态识别（全周期：4h/1h/15m/5m/1m；形态 → 方向 → 入场 → SL → TP高度投影）</h4><ul>%s</ul>"
                    "<p class='note'>小周期(5m/1m)形态噪声大，仅收录头肩/双顶底/三重/旗等高置信度形态；"
                    "形态方案入选操作表时，仓位与排序按周期权重打折（4h=1.0 → 1m=0.3）。</p>"
                    % items)

    plans = s.get("plans") or []
    if plans:
        rows = []
        for p in plans:
            if p["dir"] == "风控":
                rows.append("<tr><td>%s</td><td>%s</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>%s</td></tr>"
                            % (p["name"], p["trig"], p["status"]))
            else:
                zone = ("%d–%d" % (p["zone"][0], p["zone"][1])) if p["zone"][0] != p["zone"][1] else str(p["zone"][0])
                mark = ("<span style='color:var(--up)'>▲多</span>" if p["dir"] == "多"
                        else "<span style='color:var(--dn)'>▼空</span>")
                rows.append("<tr><td>%s %s</td><td>%s</td><td>%s</td><td>%d</td><td>%d / %d</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                            % (mark, p["name"], p["trig"], zone, p["sl"], p["t1"], p["t2"],
                               ("%.1f:1" % p["rr"]) if p["rr"] else "—",
                               ("%s" % p["size"]) if p["size"] else "—", p["status"]))
        html.append("<h4>③ 操作方案（由行情状态+图表形态实时生成，与对话策略同源）</h4>"
                    "<table class='ptable'><tr><th>方案</th><th>触发</th><th>入场区</th><th>止损</th><th>目标 T1/T2</th><th>盈亏比</th><th>仓位*</th><th>状态</th></tr>"
                    + "".join(rows) + "</table>")
        html.append("<p class='note'>* 仓位按本金1万USDT、单笔风险1.5%（150U）计算的可开ETH数（含杠杆）。防线行仓位一栏为风险监控，无可开仓位。形态策略的T1为形态高度度量投影。</p>")

        html.append("<h4>④ 方案生成逻辑（为什么此刻是这几条）</h4><ul>"
                    + "".join("<li><b>%s</b>：%s</li>" % (p["name"], p["reason"]) for p in plans)
                    + "</ul>")

    html.append("<h4>⑤ 执行纪律</h4>")
    html.append("<ul>"
                "<li>方向看4小时/日线，节奏看1小时，入场看5分钟；1分钟图只用于<b>精确找入场点</b></li>"
                "<li>杠杆 ≤ <span class='kv'>3–5倍</span>，单笔风险 ≤ 账户 <span class='kv'>1.5%%</span>；逆势防守单仓位再减半</li>"
                "<li>触发条件不出现就不动手——<b>没等到位置就追，等于放弃盈亏比</b></li>"
                "<li>资金费率每8小时结算（下期 %s）</li></ul>"
                % datetime.fromtimestamp(m["nextFundingTime"] / 1000, CN_TZ).strftime("%H:%M"))
    html.append("<div class='note'>以上方案由程序在抓取时刻(%s)先识别行情状态与全周期图表形态（4h/1h/15m/5m/1m，头肩/双顶底/三重/三角/楔/旗/矩形），"
                "再从8类策略模板中筛选生成。形态策略遵循「有效突破触发线 → 形态失效位止损 → 高度度量投影止盈」框架。"
                "<b>执行细则</b>：①「放量」= 突破/破位那根5分钟K线成交量 ≥ 前20根均量×1.5（缩量破线视为假突破，不追）；"
                "② 突破/破位类方案均为「破线 → 回踩/反抽入场区不破 → 进场」的两步流程，若行情急走不回抽，则该笔放弃、不追单。"
                "与对话中给出的策略同一数据源。行情瞬息万变，执行前请以最新K线复核。本内容不构成投资建议。</div>" % s["fetchedAt"])
    return "".join(html)


def main():
    with open("klines.json", encoding="utf-8") as f:
        raw = json.load(f)
    with open("summary.json", encoding="utf-8") as f:
        s = json.load(f)

    m = s["meta"]
    data = {tf: build_tf_data(raw["timeframes"][tf]) for tf in TFS}
    payload = {
        "data": data,
        "meta": m,
        "pivots": s["pivots"],
        "levels": s["levels"],
        "trendMatrix": s["trendMatrix"],
        "tfLabel": s["tfLabel"],
        "fetchedAt": s["fetchedAt"],
        "sourceLabel": raw["label"],
        "nextFundingStr": datetime.fromtimestamp(m["nextFundingTime"] / 1000, CN_TZ).strftime("%H:%M"),
        "strategyHTML": strategy_html(s),
    }
    with open("report_template.html", encoding="utf-8") as f:
        tpl = f.read()
    html = tpl.replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成:", OUT, "(%.1f KB)" % (len(html.encode("utf-8")) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
