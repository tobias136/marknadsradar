"""Backtest av den TEKNISKA delen av signalbetyget (trend, momentum, relativ styrka).

Fundamenta och värdering ingår inte: kvartalsdata och P/E 'så som de såg ut då' finns inte i
gratisdatan, och att använda dagens värden på gamla datum vore fusk (framtidsläckage).

Alla indikatorer räknas en gång på hela serien. De är kausala (varje värde använder bara data
fram till och med den dagen), så varje poäng är exakt det betyget man hade sett den dagen.
Därefter mäts vad som hände efter signalen, och det jämförs med vad som hände i allmänhet."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import indicators, metrics, service, signals

WARMUP = 252           # handelsdagar som krävs för momentum 12–1
COST = 0.001           # 0,1 % per byte (köp eller sälj) – grov uppskattning
BUCKETS = [("strong_pos", "Starkt positivt (≥ +50)"), ("pos", "Positivt (+20…+49)"), ("neutral", "Neutralt (−19…+19)"),
           ("neg", "Negativt (−49…−20)"), ("strong_neg", "Starkt negativt (≤ −50)")]
_cache: dict = {}


def features(df: pd.DataFrame, bench_df: pd.DataFrame | None) -> pd.DataFrame:
    close = df["close"]
    high = df["high"].fillna(close)
    low = df["low"].fillna(close)
    f = pd.DataFrame(index=close.index)
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    f["vs_sma200"] = (close / sma200 - 1) * 100
    f["vs_sma50"] = (close / sma50 - 1) * 100
    f["sma50_over_200"] = (sma50 > sma200).where(sma200.notna())
    adx, pdi, mdi = indicators.adx(high, low, close)
    f["adx"], f["plus_di"], f["minus_di"] = adx, pdi, mdi
    f["mom_12_1"] = (close.shift(21) / close.shift(252) - 1) * 100
    f["r_6m"] = (close / close.shift(126) - 1) * 100
    line, sig, hist = indicators.macd(close)
    f["macd"], f["macd_signal"], f["macd_hist"], f["macd_hist_prev"] = line, sig, hist, hist.shift(1)
    f["rs_3m"] = np.nan
    f["rs_line_pct"] = np.nan
    if bench_df is not None and len(bench_df) > 100:
        b = bench_df["close"].reindex(close.index).ffill()
        f["rs_3m"] = (close / close.shift(63) - 1) * 100 - (b / b.shift(63) - 1) * 100
        ratio = close / b
        f["rs_line_pct"] = (ratio / ratio.rolling(50).mean() - 1) * 100
    f["close"] = close
    return f


def _rows(f: pd.DataFrame, ticker: str):
    recs = f.to_dict("records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
            elif v is not None and k == "sma50_over_200":
                r[k] = bool(v)
        r["ticker"] = ticker
        r["last"] = r.get("close")
    return recs


def _maxdd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min() * 100)


def _wilson(p: float, n: float, z: float = 1.96):
    if n <= 0:
        return None, None
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def _one(ticker: str, df: pd.DataFrame, bench_df, h: int):
    if df is None or len(df) < WARMUP + h + 60:
        return None
    f = features(df, bench_df)
    rows = _rows(f, ticker)
    close = df["close"].to_numpy()
    n = len(close)
    scores = np.full(n, np.nan)
    for i in range(WARMUP, n):
        s = signals.quick_score(rows[i])
        if s is not None:
            scores[i] = s
    fwd = np.full(n, np.nan)
    fwd[: n - h] = close[h:] / close[: n - h] - 1
    bfwd = np.full(n, np.nan)
    if bench_df is not None:
        b = bench_df["close"].reindex(df.index).ffill().to_numpy()
        bfwd[: n - h] = b[h:] / b[: n - h] - 1
    # strategi: håll aktien dagen efter en dag med poäng ≥ +20, annars kassa
    ret = pd.Series(close, index=df.index).pct_change().to_numpy()
    expo = np.zeros(n)
    expo[1:] = (scores[:-1] >= 20).astype(float)
    start = int(np.argmax(~np.isnan(scores))) if (~np.isnan(scores)).any() else None
    if start is None:
        return None
    sret = expo * np.nan_to_num(ret)
    switches = np.abs(np.diff(expo, prepend=0))
    sret = sret - switches * COST
    idx = df.index
    strat = pd.Series(sret, index=idx).iloc[start:]
    bh = pd.Series(np.nan_to_num(ret), index=idx).iloc[start:]
    years = max(len(strat) / 252, 0.1)
    eq_s, eq_b = (1 + strat).cumprod(), (1 + bh).cumprod()
    return {
        "ticker": ticker, "scores": scores, "fwd": fwd, "bfwd": bfwd, "strat": strat, "bh": bh,
        "per": {
            "ticker": ticker, "days": int(len(strat)),
            "ret_strategy": float((eq_s.iloc[-1] - 1) * 100), "ret_bh": float((eq_b.iloc[-1] - 1) * 100),
            "dd_strategy": _maxdd(eq_s), "dd_bh": _maxdd(eq_b),
            "invested": float(expo[start:].mean() * 100), "trades_per_year": float(switches[start:].sum() / 2 / years),
            "last_score": None if np.isnan(scores[-1]) else int(scores[-1]),
        },
    }


def _bucket(sc: np.ndarray, key: str):
    if key == "strong_pos":
        return sc >= 50
    if key == "pos":
        return (sc >= 20) & (sc < 50)
    if key == "neutral":
        return (sc > -20) & (sc < 20)
    if key == "neg":
        return (sc <= -20) & (sc > -50)
    return sc <= -50


def _stats(fwd: np.ndarray, bfwd: np.ndarray, h: int):
    m = ~np.isnan(fwd)
    x = fwd[m]
    n = len(x)
    if n == 0:
        return {"n": 0}
    n_eff = n / h
    hit = float((x > 0).mean())
    lo, hi = _wilson(hit, n_eff)
    bm = ~np.isnan(bfwd[m])
    beat = float((x[bm] > bfwd[m][bm]).mean() * 100) if bm.sum() >= 10 else None
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    return {"n": n, "n_eff": round(n_eff, 1), "avg": float(x.mean() * 100), "median": float(np.median(x) * 100),
            "hit": hit * 100, "hit_lo": None if lo is None else lo * 100, "hit_hi": None if hi is None else hi * 100,
            "beat": beat, "sd": sd * 100, "se": (sd / math.sqrt(max(n_eff, 1))) * 100}


def run(lid: int, h: int = 21) -> dict:
    lst = service.get_list(lid)
    if not lst:
        return {"error": "Listan finns inte"}
    h = h if h in (5, 21, 63) else 21
    bench_df = metrics.price_df(lst["benchmark"]) if lst["benchmark"] else None
    dfs = {i["ticker"]: metrics.price_df(i["ticker"]) for i in lst["items"]}
    stamp = (lid, h, tuple(sorted((t, None if d is None else (len(d), str(d.index[-1].date()))) for t, d in dfs.items())))
    if stamp in _cache:
        return _cache[stamp]

    res = [r for r in (_one(t, d, bench_df, h) for t, d in dfs.items()) if r]
    out: dict = {"list": lst["name"], "benchmark": lst["benchmark"], "horizon": h, "cost_pct": COST * 100,
                 "tickers_used": len(res), "tickers_total": len(dfs), "skipped": [t for t, d in dfs.items() if d is None or len(d) < WARMUP + h + 60]}
    if not res:
        out["error"] = f"För lite kurshistorik: backtesten kräver minst ca {WARMUP + h + 60} handelsdagar per värdepapper. Tryck Uppdatera, så hämtas 5 år."
        return out

    sc = np.concatenate([r["scores"] for r in res])
    fw = np.concatenate([r["fwd"] for r in res])
    bf = np.concatenate([r["bfwd"] for r in res])
    ok = ~np.isnan(sc) & ~np.isnan(fw)
    base = _stats(fw[ok], bf[ok], h)
    out["baseline"] = base
    out["samples"] = int(ok.sum())
    out["buckets"] = []
    for key, label in BUCKETS:
        mk = ok & _bucket(np.nan_to_num(sc, nan=0.0), key)
        st = _stats(fw[mk], bf[mk], h)
        st.update(key=key, label=label)
        st["excess"] = None if st["n"] == 0 else st["avg"] - base["avg"]
        out["buckets"].append(st)
    grp = {}
    for name, mk in (("pos", ok & (sc >= 20)), ("neutral", ok & (sc > -20) & (sc < 20)), ("neg", ok & (sc <= -20))):
        grp[name] = _stats(fw[mk], bf[mk], h)
    out["groups"] = grp
    p, q = grp["pos"], grp["neg"]
    edge = {"diff": None, "z": None, "level": "none"}
    if p.get("n", 0) and q.get("n", 0):
        diff = p["avg"] - q["avg"]
        se = math.sqrt(p["se"] ** 2 + q["se"] ** 2) or float("nan")
        z = diff / se if se and not math.isnan(se) else None
        edge.update(diff=diff, z=z)
        small = min(p["n_eff"], q["n_eff"]) < 30
        if small:
            edge["level"], edge["text"] = "few", (
                f"För få oberoende observationer (positiva ≈ {_s(p['n_eff'], 0)}, negativa ≈ {_s(q['n_eff'], 0)}) för att säga något. "
                "Lägg till fler värdepapper eller vänta på mer historik.")
        elif z is not None and z >= 2 and diff > 0:
            edge["level"], edge["text"] = "support", (
                f"I det här urvalet följdes positiva signaler av {_s(diff)} procentenheter högre avkastning per {h} handelsdagar än negativa (z ≈ {_s(z)}). "
                "Det är ett stöd, inte ett bevis. Se förbehållen nedan: överlapp, få marknadsregimer och urval av dagens bolag gör att siffran troligen är för optimistisk.")
        elif z is not None and z >= 1 and diff > 0:
            edge["level"], edge["text"] = "hint", (
                f"En antydan: positiva signaler följdes av {_s(diff)} procentenheter högre avkastning än negativa, men skillnaden är inte statistiskt säker (z ≈ {_s(z)}).")
        elif z is not None and z <= -1:
            edge["level"], edge["text"] = "reverse", (
                f"Omvänt mönster: negativa signaler följdes av bättre avkastning ({_s(diff)} procentenheter). Reglerna fungerade inte i det här urvalet, "
                "eller så dominerar återgång mot medel. Lita inte på betyget som köp/sälj-signal här.")
        else:
            edge["level"], edge["text"] = "none", (
                f"Inget tydligt samband: skillnaden mellan positiva och negativa signaler är {_s(diff)} procentenheter (z ≈ {_s(0 if z is None else z)}), vilket är inom vad slumpen kan ge.")
    out["edge"] = edge

    # strategi mot buy-and-hold (jämnt viktat över listans värdepapper)
    S = pd.concat({r["ticker"]: r["strat"] for r in res}, axis=1)
    B = pd.concat({r["ticker"]: r["bh"] for r in res}, axis=1)
    sr, br = S.mean(axis=1, skipna=True).fillna(0), B.mean(axis=1, skipna=True).fillna(0)
    eq_s, eq_b = 100 * (1 + sr).cumprod(), 100 * (1 + br).cumprod()
    step = max(1, len(eq_s) // 160)
    out["curve"] = {"dates": [d.strftime("%Y-%m-%d") for d in eq_s.index[::step]],
                    "strategy": [round(float(v), 2) for v in eq_s.iloc[::step]],
                    "buyhold": [round(float(v), 2) for v in eq_b.iloc[::step]]}
    per = [r["per"] for r in res]
    out["strategy"] = {
        "ret_strategy": float(eq_s.iloc[-1] - 100), "ret_bh": float(eq_b.iloc[-1] - 100),
        "dd_strategy": _maxdd(eq_s), "dd_bh": _maxdd(eq_b),
        "invested": float(np.mean([p["invested"] for p in per])),
        "trades_per_year": float(np.mean([p["trades_per_year"] for p in per])),
        "from": eq_s.index[0].strftime("%Y-%m-%d"), "to": eq_s.index[-1].strftime("%Y-%m-%d"),
        "wins": int(sum(1 for p in per if p["ret_strategy"] > p["ret_bh"])), "n": len(per),
    }
    out["per_ticker"] = sorted(per, key=lambda p: p["ticker"])
    out["caveats"] = [
        "Bara den tekniska delen testas (trend, momentum, relativ styrka). Fundamenta och värdering finns inte historiskt i gratisdatan och testas därför inte.",
        "Urvalet är dagens bolag i listan. Bolag som försvunnit eller gått dåligt syns inte (survivorship bias), vilket gör resultatet bättre än det borde vara.",
        "Reglerna är standardregler jag valde i förväg, men jag har inte kunnat undvika att känna till hur marknaden gick. Allt som justeras efter ett backtest riskerar att bara passa det förflutna (överanpassning).",
        f"Mätfönstren överlappar (en ny signal varje dag, men utfallet mäts {h} dagar framåt) och aktier rör sig ihop. Därför räknas bara ca 1/{h} av observationerna som oberoende, men konfidensintervallen är ändå optimistiska.",
        "Kostnad: 0,1 % per köp/sälj. Verkligt courtage, spread, skatt och valutaväxling är inte inräknade.",
        "Högst fem års historik innebär i praktiken en eller två marknadsregimer. Det som fungerat där behöver inte fungera i nästa.",
    ]
    if _is_demo():
        out["caveats"].insert(0, "DEMO-DATA: kurserna är slumpmässiga. Förvänta dig inget samband, och ett eventuellt samband är då ren slump.")
    _cache.clear()
    _cache[stamp] = out
    return out


def _s(v, d=1) -> str:
    """Svenskt talformat: decimalkomma och riktigt minustecken."""
    return f"{v:.{d}f}".replace(".", ",").replace("-", "\u2212")


def _is_demo() -> bool:
    from . import db
    return db.DEMO
