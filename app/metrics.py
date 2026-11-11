"""Beräkning av mätetal från kursdata. Alla avkastningar är i procent och i
aktiens egen handelsvaluta (justerade för utdelningar och splittar)."""
from __future__ import annotations

import math
from datetime import timedelta

import pandas as pd

from . import db, indicators

# Kalenderperioder: jämförelsedagen är sista stängningen på eller före datumet
# "senaste datum minus perioden". Det är så Avanza och Yahoo räknar 1m/6m.
CAL_PERIODS = {"1w": pd.DateOffset(days=7), "1m": pd.DateOffset(months=1), "3m": pd.DateOffset(months=3),
               "6m": pd.DateOffset(months=6), "1y": pd.DateOffset(years=1)}
RET_KEYS = ["r_1d", "r_1w", "r_1m", "r_3m", "r_6m", "r_ytd", "r_1y"]
RANGE_DAYS = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "2y": 731}


def price_df(ticker: str) -> pd.DataFrame | None:
    with db.connect() as con:
        rows = con.execute(
            "SELECT date, high, low, close, volume FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date",
            (ticker,),
        ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([tuple(r) for r in rows], columns=["date", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def _pct(a, b):
    if a is None or b is None:
        return None
    try:
        if b == 0 or math.isnan(a) or math.isnan(b):
            return None
    except TypeError:
        return None
    return (a / b - 1) * 100


def _rsi(close: pd.Series, n: int = 14):
    if len(close) < n + 1:
        return None
    d = close.diff()
    up = d.clip(lower=0)
    dn = -d.clip(upper=0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    rd = dn.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    if rd == 0:
        return 100.0
    return float(100 - 100 / (1 + ru / rd))


def compute(df: pd.DataFrame | None) -> dict | None:
    if df is None or len(df) < 2:
        return None
    close = df["close"]
    last = float(close.iloc[-1])
    m: dict = {
        "last": last,
        "prev": float(close.iloc[-2]),
        "last_date": close.index[-1].strftime("%Y-%m-%d"),
        "n_obs": int(len(close)),
    }
    bases: dict = {"1d": [close.index[-2].strftime("%Y-%m-%d"), float(close.iloc[-2])]}
    m["r_1d"] = _pct(last, float(close.iloc[-2]))
    for key, off in CAL_PERIODS.items():
        target = close.index[-1] - off
        before = close[close.index <= target]
        if len(before) and close.index[0] <= target:
            bases[key] = [before.index[-1].strftime("%Y-%m-%d"), float(before.iloc[-1])]
            m[f"r_{key}"] = _pct(last, float(before.iloc[-1]))
        else:
            m[f"r_{key}"] = None
    prior = close[close.index.year < close.index[-1].year]
    if len(prior):
        bases["ytd"] = [prior.index[-1].strftime("%Y-%m-%d"), float(prior.iloc[-1])]
        m["r_ytd"] = _pct(last, float(prior.iloc[-1]))
    else:
        m["r_ytd"] = None
    m["r_bases"] = bases

    tail = close.tail(252)
    hi, lo = float(tail.max()), float(tail.min())
    m["hi52"], m["lo52"] = hi, lo
    m["from_hi52"] = _pct(last, hi)
    m["from_lo52"] = _pct(last, lo)
    m["max_dd_1y"] = float(((tail / tail.cummax()) - 1).min() * 100)

    rets = close.pct_change().dropna()
    m["vol_30d"] = float(rets.tail(30).std() * math.sqrt(252) * 100) if len(rets) >= 20 else None

    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    m["sma50"] = None if sma50 is None or pd.isna(sma50) else float(sma50)
    m["sma200"] = None if sma200 is None or pd.isna(sma200) else float(sma200)
    m["vs_sma50"] = _pct(last, m["sma50"])
    m["vs_sma200"] = _pct(last, m["sma200"])
    m["rsi14"] = _rsi(close)

    vol = df["volume"]
    if len(vol) > 21 and vol.iloc[-21:-1].mean() > 0:
        m["vol_ratio"] = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
    else:
        m["vol_ratio"] = None
    m["spark"] = [round(float(x), 4) for x in close.tail(60).tolist()]
    m["sma50_over_200"] = (m["sma50"] > m["sma200"]) if m["sma50"] is not None and m["sma200"] is not None else None
    m.update(_technicals(df, last))
    return m


def _last(s: pd.Series):
    if s is None or len(s) == 0:
        return None
    v = s.iloc[-1]
    return None if pd.isna(v) else float(v)


def _technicals(df: pd.DataFrame, last: float) -> dict:
    close = df["close"]
    out: dict = {k: None for k in (
        "macd", "macd_signal", "macd_hist", "macd_hist_prev", "adx", "plus_di", "minus_di", "atr", "atr_pct",
        "stop", "stop_dist", "bb_width", "bb_width_pct", "mom_12_1")}
    if len(close) >= 35:
        line, sig, hist = indicators.macd(close)
        out.update(macd=_last(line), macd_signal=_last(sig), macd_hist=_last(hist),
                   macd_hist_prev=float(hist.iloc[-2]) if len(hist) > 1 else None)
    hl_ok = df["high"].notna().sum() > 40 and df["low"].notna().sum() > 40
    if hl_ok and len(close) >= 40:
        high = df["high"].fillna(close)
        low = df["low"].fillna(close)
        a = _last(indicators.atr(high, low, close))
        ad, pdi, mdi = indicators.adx(high, low, close)
        out.update(adx=_last(ad), plus_di=_last(pdi), minus_di=_last(mdi), atr=a)
        if a is not None:
            out["atr_pct"] = a / last * 100
            stop = float(close.tail(22).max()) - 3 * a   # "chandelier exit"
            out["stop"] = stop
            out["stop_dist"] = _pct(stop, last)
    if len(close) >= 60:
        w = indicators.bollinger_width(close).dropna()
        if len(w) >= 40:
            tail = w.tail(252)
            out["bb_width"] = float(w.iloc[-1])
            out["bb_width_pct"] = float((tail <= w.iloc[-1]).mean() * 100)
    if len(close) >= 253:
        out["mom_12_1"] = _pct(float(close.iloc[-22]), float(close.iloc[-253]))
    return out


def rs_features(df: pd.DataFrame | None, bench_df: pd.DataFrame | None) -> dict:
    """Relativ styrka mot jämförelseindex över tid (RS-linje = kurs / indexkurs)."""
    out = {"rs_6m": None, "rs_line_pct": None}
    if df is None or bench_df is None:
        return out
    ratio = (df["close"] / bench_df["close"]).dropna()
    if len(ratio) >= 60:
        out["rs_line_pct"] = _pct(float(ratio.iloc[-1]), float(ratio.rolling(50).mean().iloc[-1]))
    if len(ratio) > 126:
        out["rs_6m"] = _pct(float(ratio.iloc[-1]), float(ratio.iloc[-127]))
    return out


def aggregate_groups(rows: list[dict]) -> list[dict]:
    """Likaviktat medelvärde av avkastning per grupp (sektor/tema)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)
    out = []
    for g, members in groups.items():
        agg = {"group": g, "count": len(members), "tickers": [m["ticker"] for m in members]}
        for k in RET_KEYS:
            vals = [m[k] for m in members if m.get(k) is not None]
            agg[k] = sum(vals) / len(vals) if vals else None
        out.append(agg)
    out.sort(key=lambda a: (a["r_1m"] is None, -(a["r_1m"] or 0)))
    return out


def breadth(rows: list[dict]) -> dict:
    n50 = [r for r in rows if r.get("vs_sma50") is not None]
    n200 = [r for r in rows if r.get("vs_sma200") is not None]
    up1d = [r for r in rows if r.get("r_1d") is not None]
    return {
        "above_sma50": (100 * sum(1 for r in n50 if r["vs_sma50"] > 0) / len(n50)) if n50 else None,
        "above_sma200": (100 * sum(1 for r in n200 if r["vs_sma200"] > 0) / len(n200)) if n200 else None,
        "advancers_1d": (100 * sum(1 for r in up1d if r["r_1d"] > 0) / len(up1d)) if up1d else None,
        "n": len(rows),
    }


def series(ticker: str, range_key: str = "1y") -> dict | None:
    df = price_df(ticker)
    if df is None:
        return None
    close = df["close"]
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    if range_key == "ytd":
        cutoff = pd.Timestamp(year=close.index[-1].year, month=1, day=1)
    else:
        cutoff = close.index[-1] - timedelta(days=RANGE_DAYS.get(range_key, 366))
    mask = close.index >= cutoff
    return {
        "ticker": ticker,
        "dates": [d.strftime("%Y-%m-%d") for d in close.index[mask]],
        "close": close[mask].round(4).tolist(),
        "sma50": sma50[mask].round(4).tolist(),
        "sma200": sma200[mask].round(4).tolist(),
        "volume": df["volume"][mask].tolist(),
    }


def compare(tickers: list[str], range_key: str = "1y") -> dict:
    """Index 100 vid gemensam startpunkt, så att olika bolag och marknader
    kan jämföras. Handelsdagar som saknas fylls framåt."""
    closes = {}
    for t in tickers:
        df = price_df(t)
        if df is not None:
            closes[t] = df["close"]
    if not closes:
        return {"dates": [], "series": {}}
    last = max(s.index[-1] for s in closes.values())
    cutoff = pd.Timestamp(year=last.year, month=1, day=1) if range_key == "ytd" else last - timedelta(
        days=RANGE_DAYS.get(range_key, 366))
    frame = pd.DataFrame({t: s[s.index >= cutoff] for t, s in closes.items()}).sort_index().ffill().dropna()
    if frame.empty:
        return {"dates": [], "series": {}}
    rebased = frame / frame.iloc[0] * 100
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in rebased.index],
        "series": {t: rebased[t].round(2).tolist() for t in rebased.columns},
    }


def clean(obj):
    """Gör objekt JSON-säkra (NaN/inf -> None) och avrunda flyttal."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else round(obj, 4)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj
