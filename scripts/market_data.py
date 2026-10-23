"""Technical snapshot for the traded instruments, built from Yahoo Finance history.

Usage: python scripts/market_data.py [SYMBOL ...]   (default: all instruments)
Prints JSON: trend, momentum, volatility, support/resistance levels and a
historical "similar setup" study for each instrument, plus macro context.
Standard library only, so it runs in any sandbox.
"""
import json
import statistics
import sys
import urllib.parse
import urllib.request

# Walt market -> Yahoo symbol of the underlying
INSTRUMENTS = {
    "US100": "^NDX",
    "NVDA": "NVDA",
    "XAU": "GC=F",
}
MACRO = {
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "US10Y": "^TNX",
    "SPX": "^GSPC",
}


def fetch(symbol, interval, range_):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?interval={interval}&range={range_}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(res.get("timestamp") or []):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None not in (o, h, l, c):
            bars.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    return bars, res["meta"]


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def rsi(closes, n=14):
    if len(closes) <= n:
        return None
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        gains.append(max(b - a, 0))
        losses.append(max(a - b, 0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(bars, n=14):
    if len(bars) <= n:
        return None
    trs = [max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"]))
           for p, b in zip(bars[:-1], bars[1:])]
    return sum(trs[-n:]) / n


def pivots(bars, k=3):
    """Swing highs/lows: bar extreme beyond k bars on both sides."""
    highs, lows = [], []
    for i in range(k, len(bars) - k):
        win = bars[i - k:i + k + 1]
        if bars[i]["h"] == max(b["h"] for b in win):
            highs.append(bars[i]["h"])
        if bars[i]["l"] == min(b["l"] for b in win):
            lows.append(bars[i]["l"])
    return highs, lows


def cluster(levels, tol):
    """Merge nearby levels; strength = how many swings touched the zone."""
    out = []
    for lv in sorted(levels):
        if out and lv - out[-1]["price"] <= tol:
            z = out[-1]
            z["price"] = (z["price"] * z["touches"] + lv) / (z["touches"] + 1)
            z["touches"] += 1
        else:
            out.append({"price": lv, "touches": 1})
    return out


def levels(bars, price, a):
    highs, lows = pivots(bars)
    zones = cluster(highs + lows, tol=a * 0.5)
    sup = sorted([z for z in zones if z["price"] < price], key=lambda z: -z["price"])[:4]
    res = sorted([z for z in zones if z["price"] > price], key=lambda z: z["price"])[:4]
    r = lambda zs: [{"price": round(z["price"], 2), "touches": z["touches"],
                     "dist_pct": round((z["price"] / price - 1) * 100, 2)} for z in zs]
    return {"support": r(sup), "resistance": r(res)}


def similar_setups(closes, horizon=5):
    """Find past days whose 5d return and RSI resemble today; report what followed."""
    if len(closes) < 60:
        return None
    rsis = [rsi(closes[:i + 1]) for i in range(len(closes))]
    ret5 = lambda i: closes[i] / closes[i - 5] - 1
    now_r, now_rsi = ret5(len(closes) - 1), rsis[-1]
    fwd = []
    for i in range(20, len(closes) - horizon):
        if rsis[i] is None:
            continue
        if abs(ret5(i) - now_r) < 0.015 and abs(rsis[i] - now_rsi) < 7:
            fwd.append(closes[i + horizon] / closes[i] - 1)
    if len(fwd) < 5:
        return {"matches": len(fwd), "note": "too few matches to be meaningful"}
    return {
        "matches": len(fwd),
        "horizon_days": horizon,
        "up_share_pct": round(100 * sum(f > 0 for f in fwd) / len(fwd), 1),
        "median_fwd_pct": round(100 * statistics.median(fwd), 2),
        "worst_fwd_pct": round(100 * min(fwd), 2),
        "best_fwd_pct": round(100 * max(fwd), 2),
    }


def analyze(name, symbol):
    daily, meta = fetch(symbol, "1d", "2y")
    hourly, _ = fetch(symbol, "60m", "1mo")
    closes = [b["c"] for b in daily]
    hcloses = [b["c"] for b in hourly]
    price = meta.get("regularMarketPrice") or closes[-1]
    a = atr(daily)
    pct = lambda n: round((closes[-1] / closes[-1 - n] - 1) * 100, 2) if len(closes) > n else None
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    return {
        "instrument": name,
        "yahoo_symbol": symbol,
        "underlying_price": round(price, 2),
        "last_bar_utc": daily[-1]["t"],
        "returns_pct": {"1d": pct(1), "5d": pct(5), "20d": pct(20), "60d": pct(60)},
        "trend": {
            "sma20": s20 and round(s20, 2), "sma50": s50 and round(s50, 2),
            "sma200": s200 and round(s200, 2),
            "above_sma50": s50 and price > s50, "above_sma200": s200 and price > s200,
            "sma50_vs_200": s50 and s200 and ("golden" if s50 > s200 else "death"),
        },
        "momentum": {
            "rsi14_daily": rsi(closes) and round(rsi(closes), 1),
            "rsi14_hourly": rsi(hcloses) and round(rsi(hcloses), 1),
        },
        "volatility": {
            "atr14_daily": a and round(a, 2),
            "atr14_daily_pct": a and round(a / price * 100, 2),
            "atr14_hourly": atr(hourly) and round(atr(hourly), 2),
        },
        "range": {
            "high_20d": round(max(b["h"] for b in daily[-20:]), 2),
            "low_20d": round(min(b["l"] for b in daily[-20:]), 2),
            "high_52w": round(max(b["h"] for b in daily[-252:]), 2),
            "low_52w": round(min(b["l"] for b in daily[-252:]), 2),
        },
        "levels_daily": levels(daily[-120:], price, a),
        "levels_hourly": levels(hourly, price, atr(hourly) or a),
        "similar_setups_history": similar_setups(closes),
    }


def macro():
    out = {}
    for name, sym in MACRO.items():
        try:
            bars, meta = fetch(sym, "1d", "1mo")
            c = [b["c"] for b in bars]
            out[name] = {"last": round(c[-1], 2), "chg_5d_pct": round((c[-1] / c[-6] - 1) * 100, 2)}
        except Exception as e:  # macro is context only; never fail the run on it
            out[name] = {"error": str(e)}
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or list(INSTRUMENTS)
    result = {"instruments": {}, "macro": macro()}
    for n in names:
        try:
            result["instruments"][n] = analyze(n, INSTRUMENTS[n])
        except Exception as e:
            result["instruments"][n] = {"error": str(e)}
    print(json.dumps(result, indent=1, ensure_ascii=False))
