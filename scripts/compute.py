# -*- coding: utf-8 -*-
"""多周期技术指标计算 + 信号摘要, 输出 summary.json 供 HTML 与最终分析使用"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

CN_TZ = timezone(timedelta(hours=8))
TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
TF_LABEL = {"1m": "1分钟", "5m": "5分钟", "15m": "15分钟", "1h": "1小时", "4h": "4小时", "1d": "日线"}


def ma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals, n):
    out = [None] * len(vals)
    k = 2.0 / (n + 1)
    prev = None
    for i, v in enumerate(vals):
        prev = v if prev is None else v * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, n=14):
    out = [None] * len(closes)
    ag, al = 0.0, 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i <= n:
            ag += g / n
            al += l / n
            if i == n:
                out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        else:
            ag = (ag * (n - 1) + g) / n
            al = (al * (n - 1) + l) / n
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def kdj(rows, n=9):
    k_out, d_out, j_out = [None] * len(rows), [None] * len(rows), [None] * len(rows)
    k, d = 50.0, 50.0
    for i, r in enumerate(rows):
        lo = min(x[3] for x in rows[max(0, i - n + 1):i + 1])
        hi = max(x[2] for x in rows[max(0, i - n + 1):i + 1])
        rsv = 50.0 if hi == lo else (r[4] - lo) / (hi - lo) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        k_out[i], d_out[i], j_out[i] = k, d, 3 * k - 2 * d
    return k_out, d_out, j_out


def boll(closes, n=20, mult=2.0):
    mid = ma(closes, n)
    up, low = [None] * len(closes), [None] * len(closes)
    for i in range(n - 1, len(closes)):
        win = closes[i - n + 1:i + 1]
        m = mid[i]
        var = sum((x - m) ** 2 for x in win) / n
        sd = var ** 0.5
        up[i], low[i] = m + mult * sd, m - mult * sd
    return up, mid, low


def atr(rows, n=14):
    out = [None] * len(rows)
    trs = [0.0] * len(rows)
    for i, r in enumerate(rows):
        if i == 0:
            trs[i] = r[2] - r[3]
        else:
            pc = rows[i - 1][4]
            trs[i] = max(r[2] - r[3], abs(r[2] - pc), abs(r[3] - pc))
    a = 0.0
    for i, t in enumerate(trs):
        if i < n:
            a += t / n
            if i == n - 1:
                out[i] = a
        else:
            a = (a * (n - 1) + t) / n
            out[i] = a
    return out


def macd(closes):
    e12, e26 = ema(closes, 12), ema(closes, 26)
    dif = [None if e12[i] is None or e26[i] is None else e12[i] - e26[i] for i in range(len(closes))]
    valid = [x for x in dif if x is not None]
    dea_v = ema(valid, 9)
    dea = [None] * len(closes)
    hist = [None] * len(closes)
    off = len(closes) - len(valid)
    for i, v in enumerate(dea_v):
        dea[off + i] = v
        hist[off + i] = 2 * (dif[off + i] - v)
    return dif, dea, hist


def last_cross(fast, slow, max_look=30):
    """最近一次金叉(+)/死叉(-)距今天数; 无则0"""
    start = max(1, len(fast) - 1 - max_look)
    for i in range(len(fast) - 1, start - 1, -1):
        a, b = fast[i], fast[i - 1]
        c, d = slow[i], slow[i - 1]
        if None in (a, b, c, d):
            break
        if b <= d and a > c:
            return len(fast) - 1 - i, "+"
        if b >= d and a < c:
            return len(fast) - 1 - i, "-"
    return 0, ""


def swing_points(rows, k=3):
    """分形摆动高低点"""
    highs, lows = [], []
    for i in range(k, len(rows) - k):
        win = rows[i - k:i + k + 1]
        if rows[i][2] == max(x[2] for x in win):
            highs.append((rows[i][0], rows[i][2]))
        if rows[i][3] == min(x[3] for x in win):
            lows.append((rows[i][0], rows[i][3]))
    return highs, lows


def cluster_levels(levels, cur, tol=0.006, each_side=3):
    """摆动点聚合成支撑阻力: 当前价上方/下方各取最近 each_side 个"""
    lv = sorted(x[1] for x in levels)
    groups = []
    for p in lv:
        if groups and abs(p - groups[-1][-1]) / cur <= tol:
            groups[-1].append(p)
        else:
            groups.append([p])
    merged = [(sum(g) / len(g), len(g)) for g in groups if abs(sum(g) / len(g) - cur) / cur >= 0.0005]
    above = sorted([x for x in merged if x[0] > cur], key=lambda x: x[0])[:each_side]
    below = sorted([x for x in merged if x[0] < cur], key=lambda x: -x[0])[:each_side]
    res = [{"price": round(p, 2), "hits": c, "type": "阻力" if p > cur else "支撑"}
           for p, c in above + below]
    res.sort(key=lambda x: -x["price"])
    return res


def yesterday_ohl(h1, daily):
    """按北京时间自然日聚合1hK线, 返回最近一个完整交易日的(开,高,低,收)"""
    days = {}
    for r in h1:
        d = datetime.fromtimestamp(r[0] / 1000, CN_TZ).date()
        days.setdefault(d, []).append(r)
    if not days:
        r = daily[-2]
        return r[1], r[2], r[3], r[4]
    ordered = sorted(days)
    rows = days[ordered[-1]]
    if len(rows) < 24 and len(ordered) > 1:  # 最后一天进行中 → 取前一天
        rows = days[ordered[-2]]
    return rows[0][1], max(r[2] for r in rows), min(r[3] for r in rows), rows[-1][4]


def nearest_above(vals, ref):
    c = [x for x in vals if x is not None and x > ref]
    return min(c) if c else None


def nearest_below(vals, ref):
    c = [x for x in vals if x is not None and x < ref]
    return max(c) if c else None


def first_above(cands, ref):
    for x in cands:
        if x is not None and x > ref:
            return x
    return None


def first_below(cands, ref):
    for x in cands:
        if x is not None and x < ref:
            return x
    return None


# ===================== 动态策略引擎 =====================

def detect_exhaustion(tfs_data, s):
    """趋势衰竭检测: 三类信号 -> 供regime降级(趋势末端严禁单边满配额)
    A. 5m放量波次量能递减(上攻/下杀动能衰竭)  B. 形态突破失败(曾突破又跌回触发线)
    C. 1h RSI背离"""
    cur = s["meta"]["lastPrice"]
    warns = []
    rows = tfs_data["5m"][-90:-1]
    vols = [r[5] for r in rows]
    if len(vols) >= 60 and sum(vols[-40:]) > 0:
        avg = sum(vols[-40:]) / 40
        waves, cur_wave = [], []
        for r in rows:
            if r[5] / avg >= 1.5:
                cur_wave.append((r[5] / avg, r[4] > r[1]))
            elif cur_wave:
                waves.append(cur_wave)
                cur_wave = []
        if cur_wave:
            waves.append(cur_wave)
        for up in (True, False):
            ws = [w for w in waves if sum(1 for _, u in w if u == up) * 2 > len(w)]
            if len(ws) >= 3:
                peaks = [max(v for v, _ in w) for w in ws[-3:]]
                if peaks[0] > peaks[1] > peaks[2]:
                    warns.append("5m三波%s量能递减(%.1f→%.1f→%.1f), %s动能衰竭"
                                 % ("上攻" if up else "下杀", peaks[0], peaks[1], peaks[2],
                                    "追涨" if up else "追跌"))
                    break
    rows15 = tfs_data["15m"][-36:]
    if rows15:
        hi15, lo15 = max(r[2] for r in rows15), min(r[3] for r in rows15)
        for p in s.get("patterns") or []:
            if p["period"] in ("5分钟", "1分钟"):
                continue
            if p["dir"] == "多" and cur < p["line"] < hi15:
                warns.append("%s·%s突破失败: 现价%.0f跌回触发线%.0f下方"
                             % (p["period"], p["name"], cur, p["line"]))
                break
            if p["dir"] == "空" and cur > p["line"] > lo15:
                warns.append("%s·%s跌破失败: 现价%.0f收复触发线%.0f上方"
                             % (p["period"], p["name"], cur, p["line"]))
                break
    div = s["timeframes"]["1h"].get("divergence")
    if div:
        warns.append("1h " + div)
    return warns[:3]


def detect_regime(s):
    """行情状态识别: 大周期评分合力 + MA20位置 + 布林带宽 -> 6种状态之一"""
    t, cur = s["timeframes"], s["meta"]["lastPrice"]
    big = t["1d"]["score"] + t["4h"]["score"]
    mom = t["1h"]["score"]
    ma20_4h = t["4h"]["ma20"] or cur
    a4 = t["4h"]["atr"] or cur * 0.01
    bu, _, bl = t["4h"]["boll"] or [None, None, None]
    squeeze = bool(bu and bl and (bu - bl) < 2.2 * a4)
    small = "1小时动能偏弱(回调段)" if mom <= -2 else ("1小时动能偏强" if mom >= 2 else "1小时动能中性")

    if big >= 7 and cur > ma20_4h:
        ret = {"key": "strong_up", "name": "强多头趋势", "bias": 2,
               "desc": "日线与4小时评分合力%+d, 价格站稳4h MA20上方, %s" % (big, small),
               "plan": "只顺势做多, 回踩趋势带即机会, 不留逆势空单"}
    elif big >= 3:
        ret = {"key": "up", "name": "偏多趋势", "bias": 1,
               "desc": "大周期评分合力%+d, %s" % (big, small),
               "plan": "以做多为主, 保留一条反抽压力带的防守空单"}
    elif big <= -7 and cur < ma20_4h:
        ret = {"key": "strong_down", "name": "强空头趋势", "bias": -2,
               "desc": "日线与4小时评分合力%+d, 价格失守4h MA20, %s" % (big, small),
               "plan": "只顺势做空, 反抽压力带即空, 不留逆势多单"}
    elif big <= -3:
        ret = {"key": "down", "name": "偏空趋势", "bias": -1,
               "desc": "大周期评分合力%+d, %s" % (big, small),
               "plan": "以做空为主, 保留一条深蹲强支撑的防守多单"}
    elif squeeze:
        ret = {"key": "squeeze", "name": "低波动收缩", "bias": 0,
               "desc": "4h布林带宽仅%.1f倍ATR, 大周期评分合力%+d方向不明" % ((bu - bl) / a4, big),
               "plan": "波动收缩待方向选择, 突破前以观望为主, 双向预案已备"}
    else:
        ret = {"key": "range", "name": "区间震荡", "bias": 0,
               "desc": "大周期评分合力%+d方向不明, %s" % (big, small),
               "plan": "区间下沿低吸、上沿高抛, 有效突破区间再追方向"}
    # 衰竭降级: 趋势末端出现量能递减/突破失败/背离 -> 状态降一级, 配额由单边转双向
    ex = s.get("exhaustion") or []
    if ex:
        demote = {"strong_up": ("up", "偏多趋势·动能衰竭", 1),
                  "up": ("range", "区间震荡·多头动能衰竭", 0),
                  "strong_down": ("down", "偏空趋势·动能衰竭", -1),
                  "down": ("range", "区间震荡·空头动能衰竭", 0)}
        if ret["key"] in demote:
            k, name, bias = demote[ret["key"]]
            ret = {"key": k, "name": name, "bias": bias,
                   "desc": ret["desc"] + "; ⚠衰竭信号: " + "; ".join(ex),
                   "plan": "趋势动能衰竭: 顺趋势单只做回踩位且减半仓位, 必须保留反向防守预案, 等待方向重新确认"}
    return ret


def build_ctx(s):
    """把策略引擎需要的行情要素抽成扁平上下文"""
    m, t, pv, lv = s["meta"], s["timeframes"], s["pivots"], s["levels"]
    sw = s.get("swings", {})
    cur = m["lastPrice"]
    res = sorted(x["price"] for x in lv if x["type"] == "阻力")
    sup = sorted((x["price"] for x in lv if x["type"] == "支撑"), reverse=True)
    b1h = t["1h"]["boll"] or [None, None, None]
    return {
        "cur": cur, "atr4": t["4h"]["atr"] or cur * 0.01,
        "r": res, "s": sup,
        "r1": res[0] if res else pv["R1"],
        "r2": res[1] if len(res) > 1 else pv["R2"],
        "s1": sup[0] if sup else pv["S1"],
        "s2": sup[1] if len(sup) > 1 else pv["S2"],
        "ma20_1h": t["1h"]["ma20"] or cur,
        "ma20_4h": t["4h"]["ma20"] or cur,
        "ma5_1d": t["1d"]["ma5"] or cur,
        "boll_up_1h": b1h[0], "boll_lo_1h": b1h[2],
        "sw_hi": sw.get("h1"), "sw_lo": sw.get("l1"),
        "mom1h": t["1h"]["score"],
        "lo5m": sw.get("recent5mLow", cur),
        "hi24": m["high24h"], "lo24": m["low24h"], "pv": pv,
        "patterns": s.get("patterns") or [],
    }


# ============ 经典图表形态识别(16形态框架: 形态→方向→入场→SL→TP度量投影) ============

def _slope(points):
    """摆动点线性回归斜率(价格/根)"""
    n = len(points)
    if n < 2:
        return 0.0
    ys = [p[1] for p in points]
    mx = (n - 1) / 2
    my = sum(ys) / n
    num = sum((i - mx) * (y - my) for i, y in enumerate(ys))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0


def _line_at(points, last_ts, bar_ms):
    """回归趋势线外推到最新K线的取值"""
    if not points:
        return None
    gap = (last_ts - points[-1][0]) / bar_ms if bar_ms else 0
    return points[-1][1] + _slope(points) * max(gap, 0)


def _extreme_between(points, t_from, t_to, fn):
    c = [x[1] for x in points if t_from < x[0] < t_to]
    return fn(c) if c else None


def _mk_pat(pid, name, direction, line, sl, tp, cur, a, label, why, conf):
    """形态对象: line=触发线(颈线/边界/趋势线), sl=形态失效位, tp=度量投影目标"""
    if direction == "空":
        st = "等待跌破" if cur > line else "已破线·等回抽确认"
    else:
        st = "等待突破" if cur < line else "已突破·等回踩确认"
    return {"id": pid, "name": name, "dir": direction, "period": label, "conf": conf,
            "line": round(line, 2), "sl": round(sl, 2), "tp": round(tp, 2),
            "status": st, "reason": why}


def _pat_hs(highs, lows, cur, a, label):
    """头肩顶/头肩底(反头肩): 颈线=两肩间低谷/高峰连线, TP=头到颈线深度投影"""
    out = []
    if len(highs) >= 3 and len(lows) >= 2:
        (ta, pa), (tb, pb), (tc, pc) = highs[-3:]
        g1 = _extreme_between(lows, ta, tb, min)
        g2 = _extreme_between(lows, tb, tc, min)
        if g1 and g2 and pb > pa and pb > pc and abs(pa - pc) / cur < 0.025 \
                and pb - max(pa, pc) > 0.8 * a and pb - min(g1, g2) > 1.5 * a:
            neck = (g1 + g2) / 2
            if neck < min(pa, pc) - 0.6 * a and neck - (pb - neck) < neck - 0.8 * a:
                out.append(_mk_pat(
                    "hs_top", "头肩顶", "空", neck, max(pa, pc) + 0.4 * a,
                    neck - (pb - neck), cur, a, label,
                    "左肩%d-头%d-右肩%d, 颈线%d; 头到颈线深度%d, 跌破后按深度投影目标%d"
                    % (pa, pb, pc, neck, pb - neck, neck - (pb - neck)), 0.92))
    if len(lows) >= 3 and len(highs) >= 2:
        (ta, pa), (tb, pb), (tc, pc) = lows[-3:]
        p1 = _extreme_between(highs, ta, tb, max)
        p2 = _extreme_between(highs, tb, tc, max)
        if p1 and p2 and pb < pa and pb < pc and abs(pa - pc) / cur < 0.025 \
                and min(pa, pc) - pb > 0.8 * a and max(p1, p2) - pb > 1.5 * a:
            neck = (p1 + p2) / 2
            if neck > max(pa, pc) + 0.6 * a and neck + (neck - pb) > neck + 0.8 * a:
                out.append(_mk_pat(
                    "hs_bottom", "头肩底(反头肩)", "多", neck, min(pa, pc) - 0.4 * a,
                    neck + (neck - pb), cur, a, label,
                    "左肩%d-头%d-右肩%d, 颈线%d; 头到颈线深度%d, 突破颈线后按深度投影目标%d"
                    % (pa, pb, pc, neck, neck - pb, neck + (neck - pb)), 0.92))
    return out


def _pat_double(highs, lows, cur, a, label):
    """双顶/双底: 颈线=中间谷/峰, TP=顶部到颈线深度投影"""
    out = []
    if len(highs) >= 2 and len(lows) >= 1:
        (ta, h1), (tb, h2) = highs[-2], highs[-1]
        g = _extreme_between(lows, ta, tb, min)
        if g and abs(h1 - h2) / cur < 0.012 and min(h1, h2) - g > 1.2 * a:
            top = (h1 + h2) / 2
            out.append(_mk_pat(
                "double_top", "双顶", "空", g, max(h1, h2) + 0.3 * a,
                g - (top - g), cur, a, label,
                "两个高点%d/%d基本同高, 中间回落到颈线%d; 双顶高度%d, 跌破颈线后投影目标%d"
                % (h1, h2, g, top - g, g - (top - g)), 0.82))
    if len(lows) >= 2 and len(highs) >= 1:
        (ta, l1), (tb, l2) = lows[-2], lows[-1]
        g = _extreme_between(highs, ta, tb, max)
        if g and abs(l1 - l2) / cur < 0.012 and g - max(l1, l2) > 1.2 * a:
            bot = (l1 + l2) / 2
            out.append(_mk_pat(
                "double_bottom", "双底", "多", g, min(l1, l2) - 0.3 * a,
                g + (g - bot), cur, a, label,
                "两个低点%d/%d基本同低, 中间反弹到颈线%d; 双底高度%d, 突破颈线后投影目标%d"
                % (l1, l2, g, g - bot, g + (g - bot)), 0.82))
    return out


def _pat_triple(highs, lows, cur, a, label):
    """三重顶/三重底"""
    out = []
    if len(highs) >= 3 and len(lows) >= 2:
        (ta, h1), (tb, h2), (tc, h3) = highs[-3:]
        g1 = _extreme_between(lows, ta, tb, min)
        g2 = _extreme_between(lows, tb, tc, min)
        if g1 and g2 and max(h1, h2, h3) / min(h1, h2, h3) - 1 < 0.012 \
                and min(h1, h2, h3) - min(g1, g2) > 1.2 * a:
            top = (h1 + h2 + h3) / 3
            neck = (g1 + g2) / 2
            out.append(_mk_pat(
                "triple_top", "三重顶", "空", neck, max(h1, h2, h3) + 0.3 * a,
                neck - (top - neck), cur, a, label,
                "三个高点%d/%d/%d同高, 颈线%d; 三次冲高不破=强阻力, 跌破颈线投影目标%d"
                % (h1, h2, h3, neck, neck - (top - neck)), 0.86))
    if len(lows) >= 3 and len(highs) >= 2:
        (ta, l1), (tb, l2), (tc, l3) = lows[-3:]
        g1 = _extreme_between(highs, ta, tb, max)
        g2 = _extreme_between(highs, tb, tc, max)
        if g1 and g2 and 1 - min(l1, l2, l3) / max(l1, l2, l3) < 0.012 \
                and max(g1, g2) - max(l1, l2, l3) > 1.2 * a:
            bot = (l1 + l2 + l3) / 3
            neck = (g1 + g2) / 2
            out.append(_mk_pat(
                "triple_bottom", "三重底", "多", neck, min(l1, l2, l3) - 0.3 * a,
                neck + (neck - bot), cur, a, label,
                "三个低点%d/%d/%d同低, 颈线%d; 三次探底不破=强支撑, 突破颈线投影目标%d"
                % (l1, l2, l3, neck, neck + (neck - bot)), 0.86))
    return out


def _pat_tri_wedge(highs, lows, cur, a, label, last_ts, bar_ms):
    """三角形(水平边+斜边)与楔形(两条同向收敛斜边), TP=最宽处高度投影"""
    out = []
    if len(highs) >= 3 and len(lows) >= 3:
        h3, l3 = highs[-3:], lows[-3:]
        # 外推跨度过大(摆动点太久远)会失真, 限制外推gap不超过摆动点自身跨度1.5倍
        if bar_ms:
            for pts in (h3, l3):
                span = pts[-1][0] - pts[0][0]
                if span > 0 and (last_ts - pts[-1][0]) > 1.5 * span:
                    return out
        sh, sl_ = _slope(h3), _slope(l3)
        hh = _line_at(h3, last_ts, bar_ms)
        ll = _line_at(l3, last_ts, bar_ms)
        if hh is None or ll is None or hh <= ll or abs(hh - ll) < 1.0 * a:
            return out
        span_h = abs(sh) * 2
        span_l = abs(sl_) * 2
        flat_h, flat_l = span_h < 0.6 * a, span_l < 0.6 * a
        width = abs(h3[0][1] - l3[0][1])
        if flat_h and not flat_l and sl_ > 0:  # 上升三角形: 水平阻力+抬升支撑
            out.append(_mk_pat(
                "asc_tri", "上升三角形", "多", hh, l3[-1][1] - 0.4 * a,
                hh + width, cur, a, label,
                "阻力%d三次不破+低点抬升; 三角形高度%d, 突破阻力后投影目标%d"
                % (hh, width, hh + width), 0.72))
        elif flat_l and not flat_h and sh < 0:  # 下降三角形: 水平支撑+降低阻力
            out.append(_mk_pat(
                "desc_tri", "下降三角形", "空", ll, h3[-1][1] + 0.4 * a,
                ll - width, cur, a, label,
                "支撑%d三次不破+高点降低; 三角形高度%d, 跌破支撑后投影目标%d"
                % (ll, width, ll - width), 0.72))
        elif sh > 0 and sl_ > 0 and sl_ > sh:  # 上升楔形: 两线上行收敛 → 看跌
            out.append(_mk_pat(
                "rise_wedge", "上升楔形", "空", ll, hh + 0.3 * a,
                ll - width, cur, a, label,
                "高低点同步上行但收敛(支撑升得更快), 量能常萎缩; 跌破下轨%d后投影目标%d"
                % (ll, ll - width), 0.68))
        elif sh < 0 and sl_ < 0 and sh < sl_:  # 下降楔形: 两线下行收敛 → 看涨
            out.append(_mk_pat(
                "fall_wedge", "下降楔形", "多", hh, ll - 0.3 * a,
                hh + width, cur, a, label,
                "高低点同步下行但收敛(阻力降得更快), 跌势衰竭信号; 突破上轨%d后投影目标%d"
                % (hh, hh + width), 0.68))
    return out


def _pat_flag(rows, cur, a, label):
    """旗形: 急涨/急跌旗杆 + 窄幅逆势旗面, TP=旗杆高度投影"""
    out = []
    if len(rows) < 50:
        return out
    pole, flag = rows[:-14], rows[-14:]
    pole_h = max(r[2] for r in pole[-34:]) if len(pole) >= 34 else max(r[2] for r in pole)
    pole_l = min(r[3] for r in pole[-34:]) if len(pole) >= 34 else min(r[3] for r in pole)
    pole_size = pole_h - pole_l
    if pole_size < 3.2 * a:
        return out
    f_hi, f_lo = max(r[2] for r in flag), min(r[3] for r in flag)
    if f_hi - f_lo > 2.8 * a or f_hi > pole_h or f_lo < pole_l:
        return out
    up = pole[-1][4] > pole[0][1]
    if up:  # 牛旗: 回调整理后延续升势
        out.append(_mk_pat(
            "bull_flag", "牛旗", "多", f_hi, f_lo - 0.3 * a, f_hi + pole_size,
            cur, a, label,
            "旗杆急涨%d点后窄幅回调%d点(量能萎缩), 突破旗面上沿%d后按旗杆高度投影目标%d"
            % (round(pole_size), round(f_hi - f_lo), f_hi, f_hi + pole_size), 0.78))
    else:  # 熊旗
        out.append(_mk_pat(
            "bear_flag", "熊旗", "空", f_lo, f_hi + 0.3 * a, f_lo - pole_size,
            cur, a, label,
            "旗杆急跌%d点后窄幅反弹%d点(量能萎缩), 跌破旗面下沿%d后按旗杆高度投影目标%d"
            % (round(pole_size), round(f_hi - f_lo), f_lo, f_lo - pole_size), 0.78))
    return out


def _pat_rect(highs, lows, cur, a, label):
    """矩形: 高点低点双双走平, TP=矩形高度投影"""
    out = []
    if len(highs) >= 3 and len(lows) >= 3:
        h3, l3 = highs[-3:], lows[-3:]
        if abs(_slope(h3)) * 2 < 0.6 * a and abs(_slope(l3)) * 2 < 0.6 * a:
            top = sum(x[1] for x in h3) / 3
            bot = sum(x[1] for x in l3) / 3
            if top - bot > 1.8 * a:
                if cur - bot < top - cur:  # 距上沿近 → 突破上沿做多
                    out.append(_mk_pat(
                        "rect_up", "矩形(向上突破)", "多", top, (top + bot) / 2,
                        top + (top - bot), cur, a, label,
                        "上下沿%d/%d双双走平, 现价靠上沿; 突破上沿后按矩形高度%d投影目标%d"
                        % (top, bot, round(top - bot), top + (top - bot)), 0.65))
                else:
                    out.append(_mk_pat(
                        "rect_dn", "矩形(向下跌破)", "空", bot, (top + bot) / 2,
                        bot - (top - bot), cur, a, label,
                        "上下沿%d/%d双双走平, 现价靠下沿; 跌破下沿后按矩形高度%d投影目标%d"
                        % (top, bot, round(top - bot), bot - (top - bot)), 0.65))
    return out


def detect_patterns(rows, cur, label="", min_conf=0.0):
    """对单周期K线做经典形态识别, 返回按置信度降序的形态列表; 小周期噪声大用min_conf过滤"""
    if len(rows) < 40:
        return []
    rows = rows[-90:]
    highs, lows = swing_points(rows, k=3)
    if len(highs) < 2 or len(lows) < 1:  # 双顶/双底只需1个谷/峰, 其余形态各自再校验
        return []
    a = atr(rows)[-1] or cur * 0.01
    bar_ms = rows[1][0] - rows[0][0] if len(rows) > 1 else 0
    out = []
    out += _pat_hs(highs, lows, cur, a, label)
    out += _pat_double(highs, lows, cur, a, label)
    out += _pat_triple(highs, lows, cur, a, label)
    out += _pat_tri_wedge(highs, lows, cur, a, label, rows[-1][0], bar_ms)
    out += _pat_flag(rows, cur, a, label)
    out += _pat_rect(highs, lows, cur, a, label)
    out = [p for p in out if p["conf"] >= min_conf]
    out.sort(key=lambda p: p["conf"], reverse=True)
    return out


# 形态周期权重: 周期越小信号越不可靠, 排序分数与仓位按权重打折
TF_WEIGHT = {"4小时": 1.0, "1小时": 0.8, "15分钟": 0.6, "5分钟": 0.45, "1分钟": 0.3}


def f_pattern(ctx, regime):
    """形态策略工厂: 识别到的经典形态转成可执行方案(入场=触发线, SL=失效位, TP=度量投影)"""
    a, cur = ctx["atr4"], ctx["cur"]
    pats = [p for p in ctx["patterns"] if p["line"] and abs(p["line"] - cur) <= 2.5 * a]
    if not pats:
        return None
    want = "多" if regime["bias"] > 0 else ("空" if regime["bias"] < 0 else None)

    def rank(p):
        # 顺方向优先, 其次置信度+周期权重(大周期形态天然更可靠)
        return ((p["dir"] == want) if want else False,
                p["conf"] + TF_WEIGHT.get(p["period"], 0.5) * 0.15)

    pats.sort(key=rank, reverse=True)
    p = pats[0]
    line, sl, tp = p["line"], p["sl"], p["tp"]
    w = TF_WEIGHT.get(p["period"], 0.5)
    if p["dir"] == "多":
        if not (sl < line < tp):
            return None
        zone, t1, t2 = [line, line + 0.12 * a], tp, tp + 0.7 * a
    else:
        if not (tp < line < sl):
            return None
        zone, t1, t2 = [line - 0.12 * a, line], tp, tp - 0.7 * a
    if (t2 - t1) * (1 if p["dir"] == "多" else -1) < 0.3 * a:
        return None
    st = "等待突破" if (p["dir"] == "多") == (cur < line) else "已破线·等回踩/回抽确认"
    if p["dir"] == "多":
        trig_txt = "有效突破%d → 回踩%d–%d企稳进场(急拉不回则放弃)" % (round(line), round(zone[0]), round(zone[1]))
    else:
        trig_txt = "有效跌破%d → 反抽%d–%d滞涨进场(急跌无反抽则放弃)" % (round(line), round(zone[0]), round(zone[1]))
    plan = _mk_plan(
        "pattern_" + p["id"], p["dir"], "%s(%s)·%s" % (p["name"], p["period"], "看涨" if p["dir"] == "多" else "看跌"),
        p["reason"],
        trig_txt,
        zone, sl, t1, t2, ctx, status=st)
    if plan and plan["size"]:
        plan["size"] = round(plan["size"] * w, 1)  # 小周期形态可靠性低, 仓位打折
        plan["eff"] = w  # 排序有效权重
    return plan


def _zone_status(cur, direction, lo, hi, a):
    """现价与入场区关系 -> 状态文案"""
    if direction == "多":
        if cur > hi + 0.3 * a:
            return "等待回踩"
        if cur >= lo - 0.3 * a:
            return "区间内·等企稳信号"
        return "区间已失守·等收复"
    if cur < lo - 0.3 * a:
        return "等待反抽"
    if cur <= hi + 0.3 * a:
        return "区间内·等滞涨信号"
    return "区间已突破·等回落"


def _mk_plan(pid, direction, name, reason, trig, zone, sl, t1, t2, ctx, status=None):
    lo, hi = round(zone[0]), round(zone[1])
    sl, t1, t2 = round(sl), round(t1), round(t2)
    mid = (lo + hi) / 2
    risk = (mid - sl) if direction == "多" else (sl - mid)
    rr = ((t1 - mid) if direction == "多" else (mid - t1)) / risk if risk > 0 else 0
    return {
        "id": pid, "dir": direction, "name": name, "reason": reason, "trig": trig,
        "zone": [lo, hi], "sl": sl, "t1": t1, "t2": t2,
        "rr": round(rr, 2) if rr > 0 else None,
        "size": round(150 / risk, 1) if risk > 0 else None,
        "status": status or _zone_status(ctx["cur"], direction, lo, hi, ctx["atr4"]),
    }


def f_long_pullback(ctx, regime):
    """回踩4h趋势带接多: 4h MA20生命线"""
    cur, a = ctx["cur"], ctx["atr4"]
    anchor = ctx["ma20_4h"]
    if not (anchor < cur and cur - anchor <= 3.0 * a):
        return None
    lo, hi = anchor - 0.3 * a, anchor + 0.25 * a
    sl = lo - 0.5 * a
    t1 = first_above([ctx["sw_hi"], ctx["boll_up_1h"], ctx["r1"], ctx["hi24"]], hi) or cur + a
    t2 = first_above([ctx["r1"], ctx["r2"]], t1 + 0.2 * a) or t1 + a
    return _mk_plan(
        "long_pullback", "多", "回踩4h趋势带(≈%d)接多" % round(anchor),
        "4h MA20在现价下方%.1f ATR处, 是本轮趋势的生命线" % ((cur - anchor) / a),
        "回踩%d–%d后5分钟止跌确认(长下影/吞没阳+MACD翻红)" % (round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx)


def f_long_deep(ctx, regime):
    """深蹲接多: 更下方的强支撑共振带"""
    cur, a = ctx["cur"], ctx["atr4"]
    anchors = [x for x in (ctx["ma5_1d"], ctx["s1"], ctx["pv"]["S1"]) if x and x < cur - 0.8 * a]
    if not anchors:
        return None
    top = max(anchors)
    lo = max(min(anchors), top - 0.6 * a)
    lo = min(lo, top - 0.2 * a)  # 单锚点时保证带至少0.2 ATR宽
    hi = top
    sl = lo - 0.5 * a
    t1 = first_above([ctx["ma20_4h"], ctx["sw_hi"], ctx["r1"]], hi) or cur + a
    t2 = first_above([ctx["sw_hi"], ctx["r1"], ctx["r2"]], t1 + 0.2 * a) or t1 + a
    return _mk_plan(
        "long_deep", "多", "深蹲强支撑带(%d–%d)接多" % (round(lo), round(hi)),
        "日线MA5/分形支撑/枢轴S1共振于该带, 距现价%.1f ATR" % ((cur - top) / a),
        "急跌至%d–%d企稳(4h级长下影/放量止跌)" % (round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx)


def f_long_breakout(ctx, regime):
    """突破追多: 现价上方最近的结构压力"""
    cur, a = ctx["cur"], ctx["atr4"]
    trig = first_above([ctx["sw_hi"], ctx["boll_up_1h"], ctx["r1"], ctx["hi24"]], cur + 0.05 * a)
    if trig is None or trig - cur > 2.5 * a:
        return None
    lo, hi = trig - 0.1 * a, trig
    sl = lo - 0.3 * a
    t1 = first_above([ctx["r1"], ctx["r2"], ctx["pv"]["R1"]], trig + 0.2 * a) or trig + a
    t2 = first_above([ctx["r2"], ctx["pv"]["R2"]], t1 + 0.2 * a) or t1 + a
    return _mk_plan(
        "long_breakout", "多", "突破%d追多(右侧轻仓)" % round(trig),
        "该处为1h摆动高/布林上轨/阻力中最近的结构压力, 现价距其%.1f ATR" % ((trig - cur) / a),
        "5分钟放量突破%d → 回踩%d–%d不破进场(急拉不回则放弃)" % (round(trig), round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx,
        status="等待突破" if cur < trig else "已突破·等回踩确认")


def f_long_range(ctx, regime):
    """区间下沿低吸(仅震荡/收缩行情)"""
    if regime["key"] not in ("range", "squeeze"):
        return None
    cur, a = ctx["cur"], ctx["atr4"]
    below = [x for x in (ctx["s1"], ctx["boll_lo_1h"], ctx["pv"]["S1"]) if x and x < cur]
    if not below:
        return None
    edge = max(below)
    if cur - edge > 3.0 * a:
        return None
    lo, hi = edge, edge + 0.3 * a
    sl = lo - 0.4 * a
    t1 = first_above([ctx["pv"]["P"], ctx["ma20_1h"]], hi) or cur + 0.5 * a
    t2 = first_above([ctx["r1"], ctx["hi24"]], t1 + 0.2 * a) or t1 + a
    return _mk_plan(
        "long_range", "多", "区间下沿(%d)低吸" % round(edge),
        "震荡行情, 该处为支撑/布林下轨/枢轴S1中最贴近现价的一档",
        "回踩%d–%d止跌企稳即接" % (round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx)


def f_short_rebound(ctx, regime):
    """反抽压力带做空: 4h MA20/最近阻力"""
    cur, a = ctx["cur"], ctx["atr4"]
    anchors = [x for x in (ctx["ma20_4h"], ctx["r1"]) if x and x > cur + 0.3 * a]
    if not anchors:
        return None
    bot = min(anchors)
    if bot - cur > 3.0 * a:
        return None
    lo, hi = bot, bot + 0.35 * a
    sl = hi + 0.5 * a
    t1 = first_below([ctx["sw_lo"], ctx["boll_lo_1h"], ctx["s1"], ctx["lo24"]], lo) or cur - a
    t2 = first_below([ctx["s1"], ctx["s2"], ctx["pv"]["S2"]], t1 - 0.2 * a) or t1 - a
    return _mk_plan(
        "short_rebound", "空", "反抽压力带(%d–%d)做空" % (round(lo), round(hi)),
        "4h MA20/最近阻力位于现价上方%.1f ATR, 反抽滞涨即空" % ((bot - cur) / a),
        "反弹至%d–%d后5分钟滞涨(长上影/吞没阴+MACD翻绿)" % (round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx)


def f_short_breakdown(ctx, regime):
    """破位追空: 跌破下方最近结构支撑"""
    cur, a = ctx["cur"], ctx["atr4"]
    trig = first_below([ctx["sw_lo"], ctx["boll_lo_1h"], ctx["s1"], ctx["lo24"]], cur - 0.05 * a)
    if trig is None or cur - trig > 2.5 * a:
        return None
    lo, hi = trig, trig + 0.1 * a
    sl = hi + 0.3 * a
    t1 = first_below([ctx["s1"], ctx["s2"], ctx["pv"]["S2"]], trig - 0.2 * a) or trig - a
    t2 = first_below([ctx["s2"], ctx["pv"]["S3"]], t1 - 0.2 * a) or t1 - a
    return _mk_plan(
        "short_breakdown", "空", "跌破%d追空(右侧轻仓)" % round(trig),
        "该处为1h摆动低/布林下轨/支撑中最近的结构支撑, 现价距其%.1f ATR" % ((cur - trig) / a),
        "5分钟放量跌破%d → 反抽%d–%d滞涨进场(急跌无反抽则放弃)" % (round(trig), round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx,
        status="等待破位" if cur > trig else "已破位·等反抽确认")


def f_short_range(ctx, regime):
    """区间上沿高抛(仅震荡/收缩行情)"""
    if regime["key"] not in ("range", "squeeze"):
        return None
    cur, a = ctx["cur"], ctx["atr4"]
    above = [x for x in (ctx["r1"], ctx["boll_up_1h"], ctx["pv"]["R1"]) if x and x > cur]
    if not above:
        return None
    edge = min(above)
    if edge - cur > 3.0 * a:
        return None
    lo, hi = edge - 0.3 * a, edge
    sl = hi + 0.4 * a
    t1 = first_below([ctx["pv"]["P"], ctx["ma20_1h"]], lo) or cur - 0.5 * a
    t2 = first_below([ctx["s1"], ctx["lo24"]], t1 - 0.2 * a) or t1 - a
    return _mk_plan(
        "short_range", "空", "区间上沿(%d)高抛" % round(edge),
        "震荡行情, 该处为阻力/布林上轨/枢轴R1中最贴近现价的一档",
        "反弹至%d–%d滞涨即空" % (round(lo), round(hi)),
        [lo, hi], sl, t1, t2, ctx)


def f_fail_line(ctx, regime):
    """动态防线: 方向随行情状态切换"""
    cur, a = ctx["cur"], ctx["atr4"]
    if regime["bias"] >= 0:
        below = [x for x in (ctx["sw_lo"], ctx["lo24"], ctx["pv"]["S1"]) if x and x < cur]
        far = [x for x in below if cur - x >= 0.5 * a]
        line = max(far) if far else (min(below) if below else cur - 3 * a)
        return {"id": "fail_line", "dir": "风控", "name": "多头防线",
                "reason": "跌破该结构低点意味着回调升级为趋势转弱, 是做多思路的总开关",
                "trig": "4小时收盘跌破%d → 多单全撤、思路切换" % round(line),
                "zone": [round(line), round(line)], "sl": None, "t1": None, "t2": None,
                "rr": None, "size": None, "status": "监控中"}
    above = [x for x in (ctx["sw_hi"], ctx["hi24"], ctx["pv"]["R1"]) if x and x > cur]
    far = [x for x in above if x - cur >= 0.5 * a]
    line = min(far) if far else (max(above) if above else cur + 3 * a)
    return {"id": "fail_line", "dir": "风控", "name": "空头防线",
            "reason": "升破该结构高点意味着反弹升级为趋势转强, 是做空思路的总开关",
            "trig": "4小时收盘升破%d → 空单回补、思路切换" % round(line),
            "zone": [round(line), round(line)], "sl": None, "t1": None, "t2": None,
            "rr": None, "size": None, "status": "监控中"}


FACTORIES = [f_long_pullback, f_long_deep, f_long_breakout, f_long_range,
             f_short_rebound, f_short_breakdown, f_short_range, f_pattern]


def _select(cands, regime, ctx):
    """按行情状态过滤+配额+排序, 返回3-5条方案"""
    cur, a, bias = ctx["cur"], ctx["atr4"], regime["bias"]

    def score(p):
        sc = (p["rr"] or 0) * p.get("eff", 1.0)  # 小周期形态RR按周期权重打折
        d = 1 if p["dir"] == "多" else -1
        if bias * d > 0:
            sc += 2.0
        elif bias * d < 0:
            sc -= 2.5
        sc -= abs(cur - sum(p["zone"]) / 2) / a * 0.3
        # 短线动能逆风: 1h评分与开仓方向相反且动能明确(<=-2做多/>=2做空)时压分
        m1 = ctx.get("mom1h")
        if m1 is not None and d * m1 <= -2:
            sc -= 1.5
        # 贴位压分: 入场区中点到反向最近关键位空间不足0.5倍ATR, 盈亏比打折
        mid = sum(p["zone"]) / 2
        if d > 0:
            block = min((x for x in ctx["r"] if x > mid), default=None)
            if block is not None and block - mid < 0.5 * a:
                sc -= 1.2
        else:
            block = min((x for x in ctx["s"] if x < mid), default=None)
            if block is not None and mid - block < 0.5 * a:
                sc -= 1.2
        return sc

    keep = [p for p in cands if p["rr"] is not None and p["rr"] >= 1.2]
    keep.sort(key=score, reverse=True)
    quota = {"strong_up": {"多": 3, "空": 0}, "up": {"多": 2, "空": 1},
             "range": {"多": 2, "空": 2}, "squeeze": {"多": 2, "空": 2},
             "down": {"多": 1, "空": 2}, "strong_down": {"多": 0, "空": 3}}[regime["key"]]
    q = dict(quota)
    picked = []
    for p in keep:
        if q.get(p["dir"], 0) <= 0:
            continue
        mid = sum(p["zone"]) / 2
        if any(o["dir"] == p["dir"] and abs(mid - sum(o["zone"]) / 2) < 0.6 * a for o in picked):
            continue
        picked.append(p)
        q[p["dir"]] -= 1
    if not picked:  # 全被RR过滤时降级保底: 优先顺方向, 不看RR阈值
        want = "多" if bias >= 0 else "空"
        pool = [p for p in cands if p["rr"] and p["dir"] == want]
        picked = sorted(pool, key=lambda p: p["rr"], reverse=True)[:2] \
            or sorted((p for p in cands if p["rr"]), key=lambda p: p["rr"], reverse=True)[:2]
    picked = picked[:4]
    picked.append(f_fail_line(ctx, regime))
    return picked


def build_plans(s):
    """动态策略引擎: 识别行情状态 -> 工厂产出候选 -> 按状态配额筛选 (对话与报告共用此数据源)"""
    regime = detect_regime(s)
    ctx = build_ctx(s)
    cands = [p for f in FACTORIES for p in [f(ctx, regime)] if p]
    return _select(cands, regime, ctx)


def analyze_tf(rows):
    closes = [r[4] for r in rows]
    vols = [r[5] for r in rows]
    n = len(rows) - 1  # 最新(可能未收盘)
    last = closes[n]
    m5, m10, m20, m60 = ma(closes, 5), ma(closes, 10), ma(closes, 20), ma(closes, 60)
    dif, dea, hist = macd(closes)
    r14 = rsi(closes)
    kk, dd, jj = kdj(rows)
    bu, bm, bl = boll(closes)
    a14 = atr(rows)
    px_bars, cross = last_cross(dif, dea)
    k_bars, k_cross = last_cross(kk, dd)

    score = 0
    score += 1 if last > m20[n] else -1
    if m60[n]:
        score += 1 if last > m60[n] else -1
    score += 1 if m5[n] > m20[n] else -1
    if hist[n] is not None:
        score += 1 if hist[n] > 0 else -1
        if hist[n - 1] is not None and hist[n] is not None:
            score += 1 if hist[n] > hist[n - 1] else -1
    rv = r14[n]
    score += 1 if rv and rv > 55 else (-1 if rv and rv < 45 else 0)
    score += 1 if kk[n] > dd[n] else -1

    # 前高前低(近期60根, 不含最新)
    win = rows[-61:-1]
    hi60 = max(x[2] for x in win)
    lo60 = min(x[3] for x in win)

    return {
        "close": round(last, 2),
        "chgPct": round((last / closes[n - 1] - 1) * 100, 3),
        "ma5": round(m5[n], 2), "ma10": round(m10[n], 2),
        "ma20": round(m20[n], 2), "ma60": round(m60[n], 2) if m60[n] else None,
        "ma20Slope": round((m20[n] / m20[n - 5] - 1) * 100, 3),
        "boll": [round(x, 2) for x in (bu[n], bm[n], bl[n])],
        "pctB": round((last - bl[n]) / (bu[n] - bl[n]), 3) if bu[n] and bu[n] != bl[n] else None,
        "dif": round(dif[n], 3), "dea": round(dea[n], 3), "hist": round(hist[n], 3),
        "macdCross": {"barsAgo": px_bars, "dir": cross},
        "rsi": round(rv, 1) if rv else None,
        "kdj": [round(kk[n], 1), round(dd[n], 1), round(jj[n], 1)],
        "kdjCross": {"barsAgo": k_bars, "dir": k_cross},
        "atr": round(a14[n], 2),
        "volRatio": round(vols[n] / (sum(vols[-21:-1]) / 20), 2),
        "hi60": round(hi60, 2), "lo60": round(lo60, 2),
        "score": score,
        "verdict": "偏多" if score >= 3 else ("偏空" if score <= -3 else "震荡"),
    }


def main():
    with open("klines.json", encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meta"]
    last = meta["lastPrice"]
    daily = data["timeframes"]["1d"]

    # 经典枢轴点(昨日K线: 北京时间自然日聚合, 与数据源日线切分口径无关)
    po, ph, pl, pc = yesterday_ohl(data["timeframes"]["1h"], daily)
    P = (ph + pl + pc) / 3
    R1 = 2 * P - pl
    S1 = 2 * P - ph
    R2 = P + (ph - pl)
    S2 = P - (ph - pl)
    R3 = ph + 2 * (P - pl)
    S3 = pl - 2 * (ph - P)
    pivots = {"P": round(P, 2), "R1": round(R1, 2), "R2": round(R2, 2), "R3": round(R3, 2),
              "S1": round(S1, 2), "S2": round(S2, 2), "S3": round(S3, 2)}

    # 4h 摆动点 -> 关键位
    h4, l4 = swing_points(data["timeframes"]["4h"][-240:])
    levels = cluster_levels(h4[-40:] + l4[-40:], last)

    tfs = {}
    for tf in TFS:
        tfs[tf] = analyze_tf(data["timeframes"][tf])

    # RSI 背离检测(1h, 简化: 近60根 价格与RSI 同创新高/新低对比)
    rows1h = data["timeframes"]["1h"][-60:]
    closes = [r[4] for r in rows1h]
    r14 = rsi(closes)
    div = None
    if closes[-1] > closes[-20] * 1.005 and r14[-1] < r14[-20] - 2:
        div = "顶背离: 价格走高但RSI走弱"
    elif closes[-1] < closes[-20] * 0.995 and r14[-1] > r14[-20] + 2:
        div = "底背离: 价格走低但RSI走强"
    tfs["1h"]["divergence"] = div

    summary = {
        "meta": meta,
        "fetchedAt": data["fetchedAt"],
        "pivots": pivots,
        "levels": levels,
        "timeframes": tfs,
        "tfLabel": TF_LABEL,
        "trendMatrix": [{"tf": TF_LABEL[tf], **{k: v for k, v in tfs[tf].items()}} for tf in TFS],
    }

    # 1h 摆动点(策略用): 现价上方/下方最近的摆动高低 + 近12根5m高低
    h1s, l1s = swing_points(data["timeframes"]["1h"][-120:])
    summary["swings"] = {
        "h1": nearest_above([x[1] for x in h1s], last),
        "l1": nearest_below([x[1] for x in l1s], last),
        "recent5mLow": min(r[3] for r in data["timeframes"]["5m"][-13:-1]),
        "recent5mHigh": max(r[2] for r in data["timeframes"]["5m"][-13:-1]),
    }
    # 经典图表形态识别(全周期): 4h主结构/1h/15m全收, 5m/1m噪声大只收高置信度形态
    patterns = detect_patterns(data["timeframes"]["4h"], last, "4小时")
    patterns += detect_patterns(data["timeframes"]["1h"][-150:], last, "1小时")
    patterns += detect_patterns(data["timeframes"]["15m"][-150:], last, "15分钟")
    patterns += detect_patterns(data["timeframes"]["5m"][-150:], last, "5分钟", min_conf=0.75)
    patterns += detect_patterns(data["timeframes"]["1m"][-150:], last, "1分钟", min_conf=0.75)
    summary["patterns"] = patterns
    summary["exhaustion"] = detect_exhaustion(data["timeframes"], summary)
    summary["regime"] = detect_regime(summary)
    summary["plans"] = build_plans(summary)
    with open("summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)

    print("多周期评分与结论:")
    for tf in TFS:
        t = tfs[tf]
        print("  %-3s %-5s 分数%+d  收%.2f  MA20:%s  MACD%s(%d根前)  RSI:%s  KDJ%s  量比%.2f" % (
            tf, t["verdict"], t["score"], t["close"],
            "上" if t["close"] > t["ma20"] else "下",
            t["macdCross"]["dir"] or "—", t["macdCross"]["barsAgo"],
            t["rsi"], t["kdjCross"]["dir"] or "—", t["volRatio"]))
    print("枢轴:", pivots)
    print("关键位(4h分形):")
    for lv in levels:
        print("  %s %.2f (触及%d次)" % (lv["type"], lv["price"], lv["hits"]))
    if tfs["1h"].get("divergence"):
        print("1h背离:", tfs["1h"]["divergence"])
    if summary["patterns"]:
        print("图表形态识别(经典16形态, 全周期):")
        for p in summary["patterns"][:8]:
            print("  %s·%s·%s 触发线%.0f SL%.0f TP%.0f [%s]" % (
                p["name"], p["period"], "看涨" if p["dir"] == "多" else "看跌",
                p["line"], p["sl"], p["tp"], p["status"]))
        if len(summary["patterns"]) > 8:
            print("  ...共%d个形态" % len(summary["patterns"]))
    reg = summary["regime"]
    print("行情状态: %s(bias %+d) %s | 基调: %s" % (reg["name"], reg["bias"], reg["desc"], reg["plan"]))
    print("动态策略方案:")
    for p in summary["plans"]:
        if p["dir"] == "风控":
            print("  [%s] %s" % (p["name"], p["trig"]))
        else:
            print("  [%s] %s | 区%d-%d 损%d T%d/%d RR%s %sETH [%s]" % (
                p["name"], p["trig"], p["zone"][0], p["zone"][1], p["sl"], p["t1"], p["t2"],
                p["rr"], p["size"], p["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
