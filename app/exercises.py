"""Övningar: uppgifter som genereras på appens egen kursdata (eller demo-data) och rättas på servern.

Principer:
- Rätt svar skickas aldrig i förväg. Varje uppgift har en 'token' som bara innehåller vad som behövs för
  att räkna om svaret när du svarar.
- Poäng i spelläget ges för att öva och för att svara rätt på uppgifter med objektivt facit,
  aldrig för vinst eller förlust på en enskild kursrörelse.
- Allt är utbildning. Inget här är ett köp- eller säljråd."""
from __future__ import annotations

import base64
import json
import math
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import biasdata, db, indicators, portfolio, service

LOG_KINDS = ("chart", "risk", "flaw", "stopex", "stopsim", "card", "bias", "stress", "luck", "spur")


# ----------------------------------------------------------------- hjälpare
def _tok(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


def _untok(t: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(t.encode()).decode())
    except Exception as e:  # noqa: BLE001
        raise ValueError("Ogiltig uppgift") from e


def load(ticker: str) -> pd.DataFrame | None:
    with db.connect() as con:
        rows = con.execute(
            "SELECT date, open, high, low, close FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date",
            (ticker,)).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([tuple(r) for r in rows], columns=["date", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["high"] = df["high"].fillna(df["close"])
    df["low"] = df["low"].fillna(df["close"])
    df["open"] = df["open"].fillna(df["close"])
    return df


def pool(min_rows: int = 420) -> list[str]:
    with db.connect() as con:
        ticks = [r["ticker"] for r in con.execute("SELECT DISTINCT ticker FROM list_items ORDER BY ticker").fetchall()]
        counts = {r["ticker"]: r["n"] for r in con.execute("SELECT ticker, COUNT(*) n FROM prices GROUP BY ticker").fetchall()}
    return [t for t in ticks if counts.get(t, 0) >= min_rows]


def _name(t: str) -> str:
    info = ((service.fund_get(t) or {}).get("info") or {})
    return info.get("shortName") or info.get("longName") or t


def _rsi_series(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    ru = indicators.wilder(d.clip(lower=0), n)
    rd = indicators.wilder(-d.clip(upper=0), n)
    return (100 - 100 / (1 + ru / rd.replace(0, np.nan))).fillna(100)


def _sv(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace(".", ",").replace("-", "−")


def _datesv(ts) -> str:
    m = ["jan", "feb", "mars", "apr", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec"]
    return f"{ts.day} {m[ts.month - 1]} {ts.year}"


def log(kind: str, correct: bool | None, detail: str = "") -> None:
    with db.connect() as con:
        con.execute("INSERT INTO practice_log(kind, ts, correct, detail) VALUES(?,?,?,?)",
                    (kind, datetime.now(timezone.utc).isoformat(), None if correct is None else int(bool(correct)), detail[:200]))


def stats() -> dict:
    out = {}
    with db.connect() as con:
        for k in LOG_KINDS:
            r = con.execute("SELECT COUNT(*) n, SUM(COALESCE(correct,0)) c FROM practice_log WHERE kind=?", (k,)).fetchone()
            last = con.execute("SELECT correct FROM practice_log WHERE kind=? AND correct IS NOT NULL ORDER BY id DESC LIMIT 20", (k,)).fetchall()
            out[k] = {"n": r["n"] or 0, "correct": int(r["c"] or 0),
                      "recent_n": len(last), "recent_correct": sum(1 for x in last if x["correct"])}
    return out


# ============================================================ LÄS DIAGRAMMET
CHART_KINDS = ["sma_cross", "drawdown", "rsi", "volatility", "breakout", "rs"]


def _bench_close() -> pd.Series | None:
    for t in portfolio.DEFAULT_BENCH:
        df = load(t)
        if df is not None and len(df) > 300:
            return df["close"]
    return None


def _series(name: str, y, cls: str, dash: bool = False) -> dict:
    return {"name": name, "cls": cls, "dash": dash, "y": [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 4) for v in y]}


def _rebase(s: pd.Series) -> pd.Series:
    return s / s.iloc[0] * 100


def _sol_chart(p: dict) -> dict:
    """Bygger diagram, fråga och facit för en uppgift (p = token-innehåll)."""
    kind, t = p["k"], p["t"]
    df = load(t)
    if df is None:
        raise ValueError("Kursdata saknas")
    cut = pd.Timestamp(p["d"])
    df = df[df.index <= cut]
    c = df["close"]
    reveal = {"ticker": t, "name": _name(t), "date": _datesv(c.index[-1])}
    if kind == "sma_cross":
        s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
        n = 250
        a, b = float(c.iloc[-1] > s200.iloc[-1]), float(s50.iloc[-1] > s200.iloc[-1])
        correct = {(1, 1): 0, (1, 0): 1, (0, 1): 2, (0, 0): 3}[(int(a), int(b))]
        why = (f"Kursen låg {_sv(abs((c.iloc[-1] / s200.iloc[-1] - 1) * 100))} % {'över' if a else 'under'} SMA200, och SMA50 låg "
               f"{_sv(abs((s50.iloc[-1] / s200.iloc[-1] - 1) * 100))} % {'över' if b else 'under'} SMA200. "
               "Kursen mot SMA200 säger något om den långa trenden. SMA50 mot SMA200 är det som kallas guldkors (uppåt) eller dödskors (nedåt).")
        return {"title": "Läs medelvärdeslinjerna", "q": "Vilket påstående stämmer på sista dagen i diagrammet?",
                "options": ["Kursen är över SMA200 och SMA50 är över SMA200", "Kursen är över SMA200, men SMA50 är under SMA200",
                            "Kursen är under SMA200, men SMA50 är över SMA200", "Kursen är under SMA200 och SMA50 är under SMA200"],
                "correct": correct, "why": why, "reveal": reveal,
                "chart": {"panels": [{"series": [_series("Kurs", c.tail(n), "price"), _series("SMA50", s50.tail(n), "sma50"), _series("SMA200", s200.tail(n), "sma200")]}]}}
    if kind == "drawdown":
        w = c.tail(250)
        dd = float(((w / w.cummax()) - 1).min() * 100)
        v = abs(dd)
        correct = 0 if v < 10 else 1 if v < 20 else 2 if v < 35 else 3
        return {"title": "Största nedgången", "q": "Ungefär hur stor var den största nedgången från en topp (max drawdown) i diagrammet?",
                "options": ["Under 10 %", "10–20 %", "20–35 %", "Över 35 %"], "correct": correct, "reveal": reveal,
                "why": f"Största nedgången från en topp var {_sv(v)} %. Mät från toppen till den lägsta punkten efter den, inte från start till slut. Det är den siffran som visar hur ont det kunde göra att äga aktien.",
                "chart": {"panels": [{"series": [_series("Kurs (index 100 vid start)", _rebase(w), "price")]}]}}
    if kind == "rsi":
        r = _rsi_series(c)
        last = float(r.iloc[-1])
        correct = 0 if last > 70 else 2 if last < 30 else 1
        why = (f"RSI var {_sv(last, 0)}. Över 70 kallas överköpt, under 30 översåld. Det betyder att rörelsen varit snabb, inte att kursen måste vända: "
               "i en stark trend kan RSI ligga över 70 länge.")
        w = 120
        return {"title": "Läs RSI", "q": "I vilken zon ligger RSI på sista dagen?",
                "options": ["Överköpt (över 70)", "Neutral (30–70)", "Översåld (under 30)"], "correct": correct, "why": why, "reveal": reveal,
                "chart": {"panels": [{"series": [_series("Kurs", c.tail(w), "price")]},
                                     {"title": "RSI (14)", "series": [_series("RSI", r.tail(w), "sma50")], "hlines": [{"y": 70, "label": "70"}, {"y": 30, "label": "30"}], "ymin": 0, "ymax": 100, "small": True}]}}
    if kind == "volatility":
        df2 = load(p["t2"])
        df2 = df2[df2.index <= cut]
        c2 = df2["close"]
        w = 120
        idx = c.tail(w).index.intersection(c2.tail(w + 30).index)
        a, b = c.reindex(idx), c2.reindex(idx)
        va = float(a.pct_change().std() * math.sqrt(252) * 100)
        vb = float(b.pct_change().std() * math.sqrt(252) * 100)
        correct = 0 if va > vb else 1
        return {"title": "Vilken svänger mest?", "q": "Vilken av de två aktierna svängde mest dag för dag (högst volatilitet)?",
                "options": ["Aktie A", "Aktie B"], "correct": correct, "reveal": {**reveal, "ticker": f"A: {t}, B: {p['t2']}", "name": f"A: {_name(t)}, B: {_name(p['t2'])}"},
                "why": f"Volatiliteten (årsbasis) var {_sv(va, 0)} % för A och {_sv(vb, 0)} % för B. Volatilitet handlar om hur mycket kursen hoppar från dag till dag, inte om hur mycket den totalt steg eller föll. Titta på ”taggigheten”.",
                "chart": {"panels": [{"title": "Aktie A", "series": [_series("A", _rebase(a), "price")], "shared": "vol"}, {"title": "Aktie B", "series": [_series("B", _rebase(b), "sma50")], "shared": "vol"}]}}
    if kind == "breakout":
        w = c.tail(253)
        prior_max = float(w.iloc[:-1].max())
        last = float(w.iloc[-1])
        if last > prior_max:
            correct = 0
        elif last >= prior_max * 0.95:
            correct = 1
        else:
            correct = 2
        gap = (last / prior_max - 1) * 100
        return {"title": "Nära toppen?", "q": "Hur ligger kursen på sista dagen jämfört med årets högsta kurs?",
                "options": ["Ny 52-veckorshögsta (högre än alla föregående dagar)", "Inte ny topp, men inom 5 % från den", "Mer än 5 % under toppen"],
                "correct": correct, "reveal": reveal,
                "why": f"Kursen låg {_sv(abs(gap))} % {'över' if gap > 0 else 'under'} den tidigare toppen. Aktier som bryter upp genom en gammal topp kallas breakouts. Många trendföljare tittar efter just det, men falska utbrott är vanliga.",
                "chart": {"panels": [{"series": [_series("Kurs", w, "price")], "hlines": [{"y": round(prior_max, 4), "label": "tidigare topp"}]}]}}
    if kind == "rs":
        b = _bench_close()
        b = b[b.index <= cut]
        idx = c.tail(126).index.intersection(b.index)
        a, bb = _rebase(c.reindex(idx)), _rebase(b.reindex(idx))
        diff = float(a.iloc[-1] - bb.iloc[-1])
        return {"title": "Slog den indexet?", "q": "Presterade aktien bättre eller sämre än jämförelseindexet under perioden?",
                "options": ["Bättre än indexet", "Sämre än indexet"], "correct": 0 if diff > 0 else 1, "reveal": reveal,
                "why": f"Aktien slutade på {_sv(a.iloc[-1], 0)} och indexet på {_sv(bb.iloc[-1], 0)} (båda började på 100). Att stiga är inte samma sak som att slå marknaden. Relativ styrka handlar om skillnaden mellan linjerna.",
                "chart": {"panels": [{"series": [_series("Aktien", a, "price"), _series("Index", bb, "bench")]}]}}
    raise ValueError("Okänd övningstyp")


def _random_cut(rng: random.Random, t: str, lo: int = 300, tail_free: int = 0):
    df = load(t)
    if df is None or len(df) < lo + tail_free + 5:
        return None
    i = rng.randint(lo, len(df) - 1 - tail_free)
    return df.index[i]


def chart_new(kind: str | None = None, seed: int | None = None) -> dict:
    rng = random.Random(seed)
    tk = pool()
    if not tk:
        raise ValueError("För lite kursdata: behöver bolag med minst ett och ett halvt års historik. Tryck Uppdatera först.")
    kinds = [kind] if kind else CHART_KINDS[:]
    rng.shuffle(kinds)
    for k in kinds:
        if k == "rs" and _bench_close() is None:
            continue
        # sök efter en uppgift som inte är en nära gräns och (för sällsynta svar) balanserad
        want = rng.randrange(3) if k in ("rsi", "breakout") else None
        for attempt in range(90):
            t = rng.choice(tk)
            d = _random_cut(rng, t)
            if d is None:
                continue
            p = {"k": k, "t": t, "d": d.strftime("%Y-%m-%d")}
            if k == "volatility":
                t2 = rng.choice([x for x in tk if x != t]) if len(tk) > 1 else None
                if not t2:
                    continue
                p["t2"] = t2
            try:
                sol = _sol_chart(p)
            except Exception:  # noqa: BLE001
                continue
            if not _unambiguous(k, p, sol):
                continue
            if want is not None and sol["correct"] != want and attempt < 70:
                continue
            return {"token": _tok(p), "kind": k, "title": sol["title"], "q": sol["q"],
                    "options": [{"i": i, "text": o} for i, o in enumerate(sol["options"])], "chart": sol["chart"]}
    raise ValueError("Kunde inte skapa en uppgift av den data som finns. Uppdatera kurserna först.")


def _unambiguous(k: str, p: dict, sol: dict) -> bool:
    """Undvik uppgifter där svaret ligger precis på en gräns."""
    df = load(p["t"])
    c = df[df.index <= pd.Timestamp(p["d"])]["close"]
    if k == "sma_cross":
        s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
        return abs(c.iloc[-1] / s200.iloc[-1] - 1) > 0.02 and abs(s50.iloc[-1] / s200.iloc[-1] - 1) > 0.015
    if k == "drawdown":
        w = c.tail(250)
        v = abs(float(((w / w.cummax()) - 1).min() * 100))
        return all(abs(v - b) > 2 for b in (10, 20, 35))
    if k == "rsi":
        v = float(_rsi_series(c).iloc[-1])
        return abs(v - 70) > 3 and abs(v - 30) > 3
    if k == "volatility":
        c2 = load(p["t2"])
        c2 = c2[c2.index <= pd.Timestamp(p["d"])]["close"]
        idx = c.tail(120).index.intersection(c2.tail(150).index)
        if len(idx) < 100:
            return False
        va, vb = c.reindex(idx).pct_change().std(), c2.reindex(idx).pct_change().std()
        return max(va, vb) / max(min(va, vb), 1e-9) > 1.35
    if k == "breakout":
        w = c.tail(253)
        pm = float(w.iloc[:-1].max())
        r = float(w.iloc[-1]) / pm
        return abs(r - 0.95) > 0.012 and abs(r - 1) > 0.004
    if k == "rs":
        b = _bench_close()
        b = b[b.index <= pd.Timestamp(p["d"])]
        idx = c.tail(126).index.intersection(b.index)
        if len(idx) < 100:
            return False
        a, bb = _rebase(c.reindex(idx)), _rebase(b.reindex(idx))
        return abs(float(a.iloc[-1] - bb.iloc[-1])) > 4
    return True


def chart_answer(token: str, choice: int) -> dict:
    p = _untok(token)
    sol = _sol_chart(p)
    ok = int(choice) == sol["correct"]
    log("chart", ok, p["k"])
    return {"correct": ok, "answer": sol["correct"], "why": sol["why"], "reveal": sol["reveal"]}


# ============================================================ RISKRÄKNAREN
RISK_KINDS = ["shares", "position", "recover", "rmult", "cap", "expect"]


def _kr(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ") + " kr"


def _risk(seed: int, kind: str | None = None) -> dict:
    rng = random.Random(seed)
    k = kind or rng.choice(RISK_KINDS)
    cap = rng.choice([50_000, 75_000, 100_000, 150_000, 200_000, 300_000, 500_000])
    r = rng.choice([0.5, 1.0, 1.5, 2.0])
    price = round(rng.choice([24, 38, 52, 75, 96, 128, 185, 240, 315, 420, 640]) * rng.uniform(0.9, 1.1), 2)
    if k == "shares":
        s = rng.choice([4, 5, 6, 8, 10, 12, 15])
        stop = round(price * (1 - s / 100), 2)
        risk_kr = cap * r / 100
        ans = math.floor(risk_kr / (price - stop))
        return {"kind": k, "unit": "aktier", "tol": 0, "answer": ans, "decimals": 0,
                "q": f"Din portfölj är värd {_kr(cap)}. Du vill köpa en aktie för {_sv(price, 2)} kr med stoppkurs {_sv(stop, 2)} kr, och du vill högst riskera {_sv(r)} % av portföljen om stoppet träffas. Hur många aktier köper du?",
                "why": f"Högsta förlust: {_sv(r)} % av {_kr(cap)} = {_kr(risk_kr)}. Förlust per aktie om stoppet träffas: {_sv(price, 2)} − {_sv(stop, 2)} = {_sv(price - stop, 2)} kr. Antal = {_kr(risk_kr)} ÷ {_sv(price - stop, 2)} = {_sv(risk_kr / (price - stop), 1)}, avrundat nedåt till {ans} aktier. Rätt storlek styrs av hur mycket du får förlora, inte av hur mycket du vill köpa för."}
    if k == "position":
        n = max(1, int(cap * rng.choice([0.04, 0.08, 0.12, 0.2, 0.3]) / price))
        val = n * price
        ans = val / cap * 100
        return {"kind": k, "unit": "%", "tol": 0.6, "answer": round(ans, 1), "decimals": 1,
                "q": f"Du köper {n} aktier för {_sv(price, 2)} kr styck. Portföljen är värd {_kr(cap)}. Hur stor andel av portföljen utgör positionen (i %)?",
                "why": f"Positionens värde: {n} × {_sv(price, 2)} = {_kr(val)}. Andel = {_kr(val)} ÷ {_kr(cap)} = {_sv(ans, 1)} %. Många sätter en gräns på 10–25 % per position, så att ett enskilt misstag inte avgör hela portföljen."}
    if k == "recover":
        x = rng.choice([10, 20, 25, 30, 40, 50, 60, 75])
        ans = (1 / (1 - x / 100) - 1) * 100
        return {"kind": k, "unit": "%", "tol": 1.0, "answer": round(ans, 1), "decimals": 1,
                "q": f"En aktie har fallit {x} %. Hur många procent måste den stiga från den nya, lägre kursen för att komma tillbaka dit den var?",
                "why": f"Börjar du på 100 och faller {x} % hamnar du på {100 - x}. För att komma tillbaka till 100 krävs 100 ÷ {100 - x} − 1 = {_sv(ans, 1)} %. Förluster är ”tyngre” än vinster: ju större nedgång, desto mer krävs för att ta igen den."}
    if k == "rmult":
        s = rng.choice([5, 6, 8, 10])
        stop = round(price * (1 - s / 100), 2)
        exitp = round(price * rng.choice([0.92, 0.96, 1.05, 1.1, 1.15, 1.2, 1.3]), 2)
        ans = (exitp - price) / (price - stop)
        return {"kind": k, "unit": "R", "tol": 0.15, "answer": round(ans, 2), "decimals": 1,
                "q": f"Du köpte för {_sv(price, 2)} kr med stoppkurs {_sv(stop, 2)} kr. Du säljer för {_sv(exitp, 2)} kr. Hur många R blev affären? (1 R = det du riskerade från början.)",
                "why": f"Riskerat per aktie (1 R): {_sv(price, 2)} − {_sv(stop, 2)} = {_sv(price - stop, 2)} kr. Resultat per aktie: {_sv(exitp, 2)} − {_sv(price, 2)} = {_sv(exitp - price, 2)} kr. R-multipel = {_sv(exitp - price, 2)} ÷ {_sv(price - stop, 2)} = {_sv(ans, 2)} R. Med R-mått kan du jämföra affärer oavsett storlek."}
    if k == "cap":
        s = rng.choice([3, 4, 5])
        stop = round(price * (1 - s / 100), 2)
        r = rng.choice([1.0, 1.5, 2.0])
        maxpos = rng.choice([10, 15, 20])
        by_risk = math.floor(cap * r / 100 / (price - stop))
        by_cap = math.floor(cap * maxpos / 100 / price)
        ans = min(by_risk, by_cap)
        return {"kind": k, "unit": "aktier", "tol": 0, "answer": ans, "decimals": 0,
                "q": f"Portfölj {_kr(cap)}. Aktie {_sv(price, 2)} kr, stoppkurs {_sv(stop, 2)} kr. Du får högst riskera {_sv(r)} % av portföljen, och ingen position får vara större än {maxpos} % av portföljen. Hur många aktier får du köpa?",
                "why": f"Enligt risken: {_kr(cap * r / 100)} ÷ {_sv(price - stop, 2)} = {by_risk} aktier. Enligt positionsgränsen: {maxpos} % av {_kr(cap)} = {_kr(cap * maxpos / 100)} ÷ {_sv(price, 2)} = {by_cap} aktier. Båda reglerna måste hållas, så du tar det lägsta: {ans} aktier. Ett tätt stopp ger stor position för samma risk, och det är då gränsen sätter stopp."}
    # expect
    hit = rng.choice([30, 35, 40, 45, 50, 55])
    win = rng.choice([1.5, 2.0, 2.5, 3.0])
    ev = hit / 100 * win - (1 - hit / 100) * 1.0
    return {"kind": "expect", "unit": "R", "tol": 0.06, "answer": round(ev, 2), "decimals": 2,
            "q": f"En metod vinner i {hit} % av affärerna. En vinnare ger i snitt {_sv(win)} R och en förlorare förlorar 1 R. Vad är förväntat resultat per affär i R?",
            "why": f"{hit} % × {_sv(win)} − {100 - hit} % × 1 = {_sv(ev, 2)} R per affär. {'Positivt: metoden har ett försprång, förutsatt att siffrorna är riktiga och urvalet stort.' if ev > 0 else 'Negativt: metoden förlorar pengar i längden, hur bra den än känns.'} Träffsäkerhet säger ingenting ensam, det är kombinationen med vinst- och förlust-storlek som räknas."}


def risk_new(kind: str | None = None) -> dict:
    seed = random.randint(1, 2_000_000_000)
    pr = _risk(seed, kind)
    return {"token": _tok({"s": seed, "k": kind}), "kind": pr["kind"], "q": pr["q"], "unit": pr["unit"]}


def risk_answer(token: str, value: float) -> dict:
    p = _untok(token)
    pr = _risk(p["s"], p.get("k"))
    ok = abs(float(value) - pr["answer"]) <= pr["tol"] + 1e-9
    log("risk", ok, pr["kind"])
    return {"correct": ok, "answer": pr["answer"], "unit": pr["unit"], "why": pr["why"], "decimals": pr["decimals"]}


# ============================================================ HITTA FELET
FLAW_OPTIONS = [("conc", "En enda position är för stor"), ("sector", "För mycket i samma bransch"),
                ("currency", "Nästan allt i samma utländska valuta"), ("overlap", "Innehaven är i praktiken samma sak"),
                ("over", "För många små innehav"), ("ok", "Inget allvarligt fel")]
_NAMES = ["Nordvind", "Fjällström", "Havsbris", "Granit", "Lindholm", "Stenbro", "Solvik", "Kronvall", "Ekudden", "Älvdal", "Bergmark",
          "Vågbrytaren", "Tallbacken", "Isfors", "Rosenlund", "Klippan", "Silverhamn", "Ljusnan", "Brandt", "Mosseby"]
_SECT = ["Teknik", "Hälsovård", "Industri", "Konsument", "Energi", "Finans", "Material", "Kraft & vatten"]


def _flaw(seed: int) -> dict:
    rng = random.Random(seed)
    kind = rng.choice(["conc", "sector", "currency", "overlap", "over", "ok"])
    names = rng.sample(_NAMES, 12)
    cur = ["SEK", "USD", "EUR"]
    rows: list[dict] = []
    note = ""

    def mk(n, sector, c, w, extra=""):
        rows.append({"name": n, "sector": sector, "cur": c, "w": round(w, 1), "extra": extra})

    if kind == "conc":
        big = rng.uniform(38, 55)
        rest = [rng.uniform(0.8, 1.2) for _ in range(7)]
        sc = (100 - big) / sum(rest)
        mk(names[0], rng.choice(_SECT), rng.choice(cur), big)
        for i, x in enumerate(rest):
            mk(names[i + 1], _SECT[(i + 1) % len(_SECT)], cur[i % 3], x * sc)
        why = f"{names[0]} utgör {_sv(big, 0)} % av portföljen. Går det dåligt för just det bolaget påverkar det hela portföljen kraftigt. Bolagen är i övrigt rimligt spridda, så det som sticker ut är storleken på en position."
    elif kind == "sector":
        sec = rng.choice(_SECT)
        w = [rng.uniform(10, 16) for _ in range(6)]
        tot = sum(w)
        rest = 100 - tot
        for i, x in enumerate(w):
            mk(names[i], sec, cur[i % 3], x)
        mk(names[6], "Finans", "SEK", rest * 0.55)
        mk(names[7], "Konsument", "SEK", rest * 0.45)
        why = f"Sex av åtta innehav ligger i samma bransch ({sec}) och står för {_sv(tot, 0)} % av portföljen. Det ser spritt ut på antalet bolag, men de påverkas av samma nyheter och konjunktur och rör sig ofta ihop."
    elif kind == "currency":
        c = rng.choice(["USD", "USD", "EUR"])
        w = [rng.uniform(0.8, 1.2) for _ in range(8)]
        sc = 100 / sum(w)
        for i, x in enumerate(w):
            mk(names[i], _SECT[i % len(_SECT)], c if i != 7 else "SEK", x * sc)
        usd = sum(r["w"] for r in rows if r["cur"] == c)
        why = f"{_sv(usd, 0)} % av portföljen står i {c}. Branscherna är spridda, men du är svensk och har utgifter i kronor, så en kronstärkning mot {c} slår mot hela portföljen samtidigt. Det är inte automatiskt fel, men det ska vara ett medvetet val."
    elif kind == "overlap":
        w = [rng.uniform(18, 30) for _ in range(4)]
        sc = 90 / sum(w)
        top = "Nvidia, Microsoft, Apple, Amazon, Alphabet"
        labels = ["USA Index Fond", "Nasdaq 100 ETF", "Storbolag Tillväxt USA", "Mega Cap Teknik ETF"]
        for i, x in enumerate(w):
            mk(labels[i], "Fond (bred)", "USD" if i else "SEK", x * sc, f"Största innehav: {top}")
        mk(names[0], "Konsument", "SEK", 10)
        why = "Fyra fonder med olika namn men nästan samma största innehav. Du har betalat flera gånger för att äga samma handfull bolag. Antalet innehav säger inget om spridning, det gör vad de innehåller."
    elif kind == "over":
        n = rng.choice([22, 25, 28])
        rows_all = []
        for i in range(n):
            rows_all.append({"name": f"{rng.choice(_NAMES)} {chr(65 + i % 26)}", "sector": _SECT[i % len(_SECT)], "cur": cur[i % 3], "w": round(100 / n, 1), "extra": ""})
        rows = rows_all[:9]
        note = f"… och {n - 9} innehav till, alla runt {_sv(100 / n, 1)} %"
        why = f"{n} innehav på ungefär {_sv(100 / n, 1)} % vardera. Risken är väl spridd, men det är svårt att följa upp så många bolag, och en bra idé får knappt någon betydelse. Ofta blir resultatet ungefär som en indexfond, fast dyrare och mer jobb."
    else:
        w = [rng.uniform(10, 16) for _ in range(8)]
        sc = 100 / sum(w)
        sectors = rng.sample(_SECT, 6) + rng.sample(_SECT, 2)
        cs = ["SEK", "SEK", "SEK", "USD", "USD", "EUR", "SEK", "USD"]
        for i, x in enumerate(w):
            mk(names[i], sectors[i], cs[i], x * sc)
        why = "Åtta innehav på ungefär 10–16 % vardera, olika branscher och en blandning av kronor, dollar och euro. Ingen enskild sak sticker ut. Det är lika viktigt att kunna se när något är tillräckligt bra som att hitta fel. Att hitta på ett problem som inte finns leder till onödiga affärer."
    return {"kind": kind, "rows": rows, "note": note, "why": why}


def flaw_new() -> dict:
    seed = random.randint(1, 2_000_000_000)
    f = _flaw(seed)
    return {"token": _tok({"s": seed}), "rows": f["rows"], "note": f["note"], "options": [{"key": k, "text": t} for k, t in FLAW_OPTIONS],
            "q": "Du är svensk privatsparare och får se den här portföljen. Vilket är det största problemet?"}


def flaw_answer(token: str, choice: str) -> dict:
    p = _untok(token)
    f = _flaw(p["s"])
    ok = choice == f["kind"]
    log("flaw", ok, f["kind"])
    return {"correct": ok, "answer": f["kind"], "answer_text": dict(FLAW_OPTIONS)[f["kind"]], "why": f["why"]}


# ============================================================ BETEENDEFÄLLOR
def bias_new() -> dict:
    seed = random.randint(1, 2_000_000_000)
    rng = random.Random(seed)
    idx = rng.randrange(len(biasdata.SCENARIOS))
    text, key, _, _ = biasdata.SCENARIOS[idx]
    others = [k for k in biasdata.BIASES if k != key]
    opts = [key] + rng.sample(others, 3)
    rng.shuffle(opts)
    return {"token": _tok({"i": idx}), "q": text,
            "options": [{"key": k, "text": biasdata.BIASES[k][0], "hint": biasdata.BIASES[k][1]} for k in opts]}


def bias_answer(token: str, choice: str) -> dict:
    i = _untok(token)["i"]
    text, key, why, antidote = biasdata.SCENARIOS[i]
    ok = choice == key
    log("bias", ok, key)
    return {"correct": ok, "answer": key, "answer_text": biasdata.BIASES[key][0], "answer_hint": biasdata.BIASES[key][1], "why": why, "antidote": antidote}


# ============================================================ STOPPÖVNING + SIMULATOR
def stopex_new(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    tk = pool(420)
    if not tk:
        raise ValueError("För lite kursdata. Tryck Uppdatera först.")
    for _ in range(40):
        t = rng.choice(tk)
        df = load(t)
        if df is None or len(df) < 420:
            continue
        i = rng.randint(250, len(df) - 66)
        d = df.index[i]
        c = df["close"].iloc[: i + 1]
        atr = float(indicators.atr(df["high"].iloc[: i + 1], df["low"].iloc[: i + 1], c).iloc[-1])
        return {"token": _tok({"t": t, "d": d.strftime("%Y-%m-%d")}), "entry": round(float(c.iloc[-1]), 4),
                "atr": round(atr, 4), "atr_pct": round(atr / float(c.iloc[-1]) * 100, 2),
                "chart": {"panels": [{"series": [_series("Kurs", c.tail(120), "price")]}]},
                "horizon": 60}
    raise ValueError("Kunde inte skapa uppgiften.")


def _fill(open_: float, low: float, stop: float) -> tuple[bool, float, bool]:
    """Returnerar (utlöst, fyllnadskurs, gap). Gap = öppnade under stoppet, då fylls du till öppningskursen."""
    if low > stop:
        return False, 0.0, False
    if open_ < stop:
        return True, open_, True
    return True, stop, False


def stopex_answer(token: str, stop_pct: float) -> dict:
    p = _untok(token)
    df = load(p["t"])
    if df is None:
        raise ValueError("Kursdata saknas")
    cut = pd.Timestamp(p["d"])
    pos = df.index.get_loc(cut)
    hist, fut = df.iloc[: pos + 1], df.iloc[pos + 1: pos + 61]
    entry = float(hist["close"].iloc[-1])
    atr = float(indicators.atr(hist["high"], hist["low"], hist["close"]).iloc[-1])
    sp = max(0.5, min(40.0, float(stop_pct)))
    stop = entry * (1 - sp / 100)
    mult = (entry - stop) / atr if atr else 0
    exit_i, exit_p, gap = None, float(fut["close"].iloc[-1]), False
    for k, (idx, row) in enumerate(fut.iterrows()):
        hit, fp, g = _fill(float(row["open"]), float(row["low"]), stop)
        if hit:
            exit_i, exit_p, gap = k, fp, g
            break
    res = (exit_p / entry - 1) * 100
    after = fut["high"].iloc[exit_i + 1:].max() if exit_i is not None and exit_i + 1 < len(fut) else None
    whip = exit_i is not None and after is not None and float(after) > entry
    mae = float(fut["low"].min() / entry - 1) * 100
    verdict = ("inside" if mult < 1.5 else "ok" if mult <= 4 else "far")
    vtext = {"inside": f"Ditt stopp låg bara {_sv(mult, 1)} ATR från ingången, inom det vanliga dagsbruset. Stopp så tätt löses ofta ut av vanliga svängningar, inte av att din idé var fel.",
             "ok": f"Ditt stopp låg {_sv(mult, 1)} ATR från ingången. Det är utanför det vanliga dagsbruset men inte så långt bort att förlusten blir stor. Ett vanligt spann är ungefär 1,5–4 ATR.",
             "far": f"Ditt stopp låg {_sv(mult, 1)} ATR från ingången, långt bort. Då blir förlusten per aktie stor, och för att hålla risken nere måste positionen göras mindre."}[verdict]
    atr_stop = entry - 3 * atr
    atr_hit = next((k for k, (_, r) in enumerate(fut.iterrows()) if float(r["low"]) <= atr_stop), None)
    log("stopex", verdict == "ok", verdict)
    return {"verdict": verdict, "verdict_text": vtext, "atr_mult": round(mult, 2), "stop": round(stop, 4), "entry": round(entry, 4),
            "stopped": exit_i is not None, "exit_day": None if exit_i is None else exit_i + 1, "exit_price": round(exit_p, 4), "gap": gap,
            "result_pct": round(res, 2), "whipsaw": bool(whip), "mae_pct": round(mae, 2),
            "atr_stop_hit": atr_hit is not None, "atr_stop": round(atr_stop, 4),
            "reveal": {"ticker": p["t"], "name": _name(p["t"]), "date": _datesv(cut)},
            "future": {"series": [_series("Efteråt", fut["close"], "price")], "low": [round(float(x), 4) for x in fut["low"]]},
            "disclaimer": "Det här är ett enda utfall. Ett stopp ska bedömas på många affärer, inte på en. Använd stoppsimulatorn för det."}


STOP_RULES = [("none", "Inget stopp (håll hela tiden)"), ("fixed8", "Fast stopp −8 %"), ("fixed15", "Fast stopp −15 %"),
              ("trail10", "Släpande stopp 10 % under högsta kurs"), ("trail20", "Släpande stopp 20 % under högsta kurs"),
              ("atr3", "ATR-stopp (3 × ATR, släpande)"), ("time", "Tidsstopp (ut efter 40 dagar om under +5 %)")]


def _simulate(rule: str, o, h, l, c, i: int, horizon: int, atr: float):
    """En affär med ingång på stängningen dag i. Returnerar (avkastning %, dagar, stoppad, gap)."""
    entry = c[i]
    hi_close = entry
    n = min(horizon, len(c) - 1 - i)
    if n < horizon:
        return None
    stop = None
    if rule == "fixed8":
        stop = entry * 0.92
    elif rule == "fixed15":
        stop = entry * 0.85
    elif rule == "trail10":
        stop = entry * 0.90
    elif rule == "trail20":
        stop = entry * 0.80
    elif rule == "atr3":
        stop = entry - 3 * atr
    for k in range(1, n + 1):
        j = i + k
        if stop is not None:
            hit, fp, gap = _fill(o[j], l[j], stop)
            if hit:
                return ((fp / entry - 1) * 100, k, True, gap)
            if rule in ("trail10", "trail20", "atr3"):
                hi_close = max(hi_close, c[j])
                new = hi_close * (0.90 if rule == "trail10" else 0.80) if rule != "atr3" else hi_close - 3 * atr
                stop = max(stop, new)
        if rule == "time" and k == 40 and c[j] / entry - 1 < 0.05:
            return ((c[j] / entry - 1) * 100, k, True, False)
    return ((c[i + n] / entry - 1) * 100, n, False, False)


def stopsim(ticker: str, horizon: int = 120) -> dict:
    df = load(ticker.upper())
    if df is None or len(df) < horizon + 200:
        raise ValueError("För lite kurshistorik för den tickern. Välj en med minst ett par års data.")
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atrs = indicators.atr(df["high"], df["low"], df["close"]).to_numpy(float)
    entries = list(range(30, len(df) - horizon - 1, 5))
    out = []
    final = {}
    for rule, label in STOP_RULES:
        trades = [t for t in (_simulate(rule, o, h, l, c, i, horizon, atrs[i]) for i in entries) if t is not None]
        # slutkurs vid tidshorisonten (för att bedöma om stoppet var onödigt)
        rets = np.array([t[0] for t in trades])
        stopped = [(t, i) for t, i in zip(trades, entries) if t[2]]
        whip = sum(1 for t, i in stopped if (c[i + horizon] / c[i] - 1) * 100 > t[0] + 0.0001)
        saved = sum(1 for t, i in stopped if (c[i + horizon] / c[i] - 1) * 100 < t[0] - 0.0001)
        tail = np.sort(rets)[: max(1, len(rets) // 10)]
        out.append({"rule": rule, "label": label, "n": len(trades), "mean": float(rets.mean()), "median": float(np.median(rets)),
                    "win": float((rets > 0).mean() * 100), "stopped": float(len(stopped) / len(trades) * 100),
                    "avg_stopped": float(np.mean([t[0] for t, _ in stopped])) if stopped else None,
                    "whipsaw": float(whip / len(stopped) * 100) if stopped else None, "saved": float(saved / len(stopped) * 100) if stopped else None,
                    "gaps": int(sum(1 for t, _ in stopped if t[3])), "tail10": float(tail.mean()), "worst": float(rets.min())})
    base = out[0]
    notes = []
    best_tail = min(out[1:], key=lambda x: -x["tail10"])
    notes.append(f"De sämsta 10 % av affärerna gav i snitt {_sv(base['tail10'])} % utan stopp. Med ”{best_tail['label']}” blev det {_sv(best_tail['tail10'])} %.")
    tight = next(x for x in out if x["rule"] == "fixed8")
    if tight["whipsaw"] is not None:
        notes.append(f"Det tätaste fasta stoppet löstes ut i {_sv(tight['stopped'], 0)} % av affärerna, och i {_sv(tight['whipsaw'], 0)} % av de utlösningarna hade aktien ändå slutat högre efter {horizon} dagar än där du sålde. Så ser stopp-jakt ut: du blir utskakad och går miste om uppgången.")
    means = [x["mean"] for x in out]
    notes.append(f"Snittavkastningen låg mellan {_sv(min(means))} % och {_sv(max(means))} % beroende på regel (utan stopp: {_sv(base['mean'])} %). Stopp styr främst hur stor förlusten kan bli och hur ojämnt det går, inte hur mycket du tjänar i snitt.")
    return {"ticker": ticker.upper(), "name": _name(ticker.upper()), "horizon": horizon, "rules": out, "notes": notes,
            "n_eff": round(len(entries) * 5 / horizon, 1), "from": df.index[0].strftime("%Y-%m-%d"), "to": df.index[-1].strftime("%Y-%m-%d"),
            "caveats": ["Affärerna överlappar varandra (ny ingång var femte dag), så urvalet är mindre än det ser ut: räkna med ungefär " + f"{len(entries) * 5 / horizon:.0f}" + " oberoende affärer.",
                        "Bara en aktie och dess egen historia. Det som gällde här gäller inte automatiskt för andra aktier eller framåt.",
                        "Utlösning sker på dagens lägsta kurs. Öppnar aktien under stoppet fylls du till öppningskursen (gap), annars till stoppkursen. Courtage och skatt ingår inte.",
                        "Kurserna är justerade för utdelningar och splittar."]}


# ============================================================ REPETITIONSKORT
INTERVALS = [1, 3, 7, 16, 35, 90]
NEW_PER_DAY = 8


def cards_due(keys: list[str]) -> dict:
    today = date.today().isoformat()
    keys = list(dict.fromkeys(keys))
    with db.connect() as con:
        rows = {r["key"]: dict(r) for r in con.execute("SELECT * FROM cards").fetchall()}
    due = [k for k in keys if k in rows and rows[k]["due"] <= today]
    due.sort(key=lambda k: (rows[k]["due"], rows[k]["box"]))
    new_today = sum(1 for r in rows.values() if r["added"] == today)
    unseen = [k for k in keys if k not in rows]
    new = unseen[: max(0, NEW_PER_DAY - new_today)]
    known = [rows[k] for k in keys if k in rows]
    return {"due": due, "new": new, "stats": {"known": len(known), "mastered": sum(1 for r in known if r["box"] >= 4),
                                               "unseen": len(unseen), "due": len(due), "total": len(keys)}}


def cards_answer(key: str, grade: str) -> dict:
    if grade not in ("again", "hard", "good"):
        raise ValueError("Ogiltigt betyg")
    today = date.today()
    with db.connect() as con:
        r = con.execute("SELECT * FROM cards WHERE key=?", (key,)).fetchone()
        box = r["box"] if r else 0
        if grade == "again":
            nbox, days = 1, 0
        elif grade == "hard":
            nbox, days = max(1, box), 1
        else:
            nbox = min(len(INTERVALS), box + 1)
            days = INTERVALS[nbox - 1]
        due = (today + timedelta(days=days)).isoformat()
        con.execute("INSERT INTO cards(key, box, due, added, reviews) VALUES(?,?,?,?,1) "
                    "ON CONFLICT(key) DO UPDATE SET box=?, due=?, reviews=reviews+1",
                    (key, nbox, due, today.isoformat(), nbox, due))
    log("card", grade == "good", key)
    return {"box": nbox, "next_days": days}
