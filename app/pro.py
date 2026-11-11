"""Proffsdelen (nivå 8–10): stresstest, handelsstatistik med osäkerhet, regeltest och Handlarprofil.

Principer:
- Resultat är aldrig ett krav för att gå upp i nivå. Det som krävs är process, dokumentation och ärlighet.
- Alla statistiska mått visas med osäkerhet (konfidensintervall). Få affärer säger väldigt lite.
- Slutnivån märks 'Visad professionell process', inte 'bevisad skicklighet'."""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import db, exercises, indicators, paper, portfolio, trader

_sv = exercises._sv


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ================================================================== ÖVNING: STRESSTEST
STRESS_NAMES = ["Nordvind", "Fjällström", "Havsbris", "Granit", "Lindholm", "Stenbro", "Solvik", "Kronvall", "Ekudden", "Älvdal"]


def _stress(seed: int) -> dict:
    rng = random.Random(seed)
    kind = rng.choice(["beta", "beta", "gap", "gap", "room"])
    n = rng.choice([4, 5, 6])
    names = rng.sample(STRESS_NAMES, n)
    cash = rng.choice([0, 10, 20, 25, 30]) if kind == "beta" else 0
    inv = 100 - cash
    w = [rng.uniform(0.6, 1.4) for _ in range(n)]
    w = [round(x / sum(w) * inv, 0) for x in w]
    w[-1] = max(1.0, inv - sum(w[:-1]))
    rows = []
    if kind == "beta":
        m = rng.choice([10, 15, 20, 25, 30])
        for i in range(n):
            rows.append({"name": names[i], "w": w[i], "beta": round(rng.uniform(0.6, 1.8), 1)})
        loss = sum(r["w"] * r["beta"] for r in rows) * m / 100
        q = f"Marknaden faller {m} % på kort tid. Varje innehav rör sig beta gånger marknaden. Kontanter förändras inte. Hur många procent av portföljen förlorar du ungefär?"
        why = (f"Räkna vikt × beta × {m} % för varje innehav och summera: det blir {_sv(loss, 1)} % av portföljen. "
               + (f"Kassan på {cash} % dämpar, men höga beta förstärker. " if cash else "Höga beta förstärker fallet. ")
               + "Tumregel: portföljbeta × investerad andel × marknadsfallet.")
        return {"kind": kind, "q": q, "rows": rows, "cash": cash, "answer": round(loss, 1), "tol": 0.6, "unit": "% av portföljen", "why": why, "decimals": 1,
                "cols": ["Innehav", "Vikt", "Beta"]}
    if kind == "gap":
        gap = rng.choice([3, 5, 8, 10])
        for i in range(n):
            rows.append({"name": names[i], "w": w[i], "stop": rng.choice([4, 5, 6, 8, 10, 12])})
        loss = sum(r["w"] * (1 - (1 - r["stop"] / 100) * (1 - gap / 100)) for r in rows)
        q = (f"Dåliga nyheter över natten: alla innehav öppnar {gap} % under sitt stopp, och du säljs där. Stoppavståndet är hur långt under dagens kurs stoppet ligger. "
             "Hur stor blir förlusten som andel av portföljen?")
        why = (f"För varje innehav blir förlusten stoppavstånd plus gap (något mindre eftersom gapet räknas från stoppet): vikt × (1 − (1 − stopp) × (1 − {gap} %)). "
               f"Summan är {_sv(loss, 1)} %. Stopp är ingen garanti: planerar du för enbart stoppavståndet underskattar du risken.")
        return {"kind": kind, "q": q, "rows": rows, "cash": 0, "answer": round(loss, 1), "tol": 0.4, "unit": "% av portföljen", "why": why, "decimals": 1,
                "cols": ["Innehav", "Vikt", "Stopp under kurs"]}
    # room: utrymme under risktaket
    limit = rng.choice([5, 6, 8, 10])
    risks = [round(rng.uniform(0.4, 1.6), 1) for _ in range(n)]
    used = sum(risks)
    while used >= limit - 0.5:
        risks = [round(x * 0.8, 1) for x in risks]
        used = sum(risks)
    for i in range(n):
        rows.append({"name": names[i], "w": w[i], "risk": risks[i]})
    room = limit - used
    q = f"Din Spelbok sätter taket för samlad öppen risk till {limit} % av portföljen (summan av vad du förlorar om alla stopp träffas). Hur många procentenheter risk har du kvar att använda?"
    why = f"Summan av öppen risk är {_sv(used, 1)} %. Taket {limit} % minus det ger {_sv(room, 1)} % kvar. Ett tak är till för att hindra att många små risker blir en stor."
    return {"kind": kind, "q": q, "rows": rows, "cash": 0, "answer": round(room, 1), "tol": 0.05, "unit": "procentenheter", "why": why, "decimals": 1,
            "cols": ["Innehav", "Vikt", "Risk vid stopp"]}


def stress_new() -> dict:
    seed = random.randint(1, 2_000_000_000)
    pr = _stress(seed)
    return {"token": exercises._tok({"s": seed}), "kind": pr["kind"], "q": pr["q"], "rows": pr["rows"], "cash": pr["cash"], "cols": pr["cols"], "unit": pr["unit"]}


def stress_answer(token: str, value: float) -> dict:
    pr = _stress(exercises._untok(token)["s"])
    ok = abs(float(value) - pr["answer"]) <= pr["tol"] + 1e-9
    exercises.log("stress", ok, pr["kind"])
    return {"correct": ok, "answer": pr["answer"], "unit": pr["unit"], "why": pr["why"], "decimals": pr["decimals"]}


# ================================================================== ÖVNING: TUR ELLER SKICKLIGHET
def _binom_tail(n: int, k: int, p: float = 0.5) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _no_run(n: int, k: int, p_loss: float) -> float:
    """Sannolikhet att INGEN förlustserie på k eller fler förekommer i n affärer (DP)."""
    f = [0.0] * k
    f[0] = 1.0
    for _ in range(n):
        g = [0.0] * k
        g[0] = sum(f) * (1 - p_loss)
        for j in range(1, k):
            g[j] = f[j - 1] * p_loss
        f = g
    return sum(f)


LUCK_BUCKETS = [("a", "Under 1 %", 0.0, 0.01), ("b", "1–5 %", 0.01, 0.05), ("c", "5–20 %", 0.05, 0.20), ("d", "20–50 %", 0.20, 0.50), ("e", "Över 50 %", 0.50, 1.01)]
STREAK_BUCKETS = [("a", "4 affärer eller färre", 0, 4), ("b", "5–6 affärer", 5, 6), ("c", "7–8 affärer", 7, 8), ("d", "9 eller fler", 9, 99)]


def _luck(seed: int) -> dict:
    rng = random.Random(seed)
    if rng.random() < 0.6:
        target = rng.choice(LUCK_BUCKETS)
        cands = []
        for n in (10, 20, 30, 40, 50, 100):
            for k in range(max(2, n // 3), n):
                pr = _binom_tail(n, k)
                if target[2] <= pr < target[3]:
                    margin = min(pr - target[2], target[3] - pr) / (target[3] - target[2])
                    if margin > 0.25 or target[0] == "a" or target[0] == "e":
                        cands.append((n, k, pr))
        n, k, pr = rng.choice(cands) if cands else (20, 15, _binom_tail(20, 15))
        bk = [b for b in LUCK_BUCKETS if b[2] <= pr < b[3]][0]
        q = (f"En handlare utan någon som helst fördel, där varje affär är ett slantsinglande med 50 % chans till vinst, gör {n} affärer. "
             f"Hur stor är chansen att hen ändå vinner minst {k} av dem?")
        why = (f"Binomialfördelningen ger {_sv(pr * 100, 1)} % för minst {k} vinster av {n}. Slumpen ger ofta rader som ser ut som skicklighet, särskilt med få affärer. "
               "Därför visar Handelsstatistiken alltid ett intervall och inte bara en träffandel.")
        return {"kind": "luck", "q": q, "options": [(b[0], b[1]) for b in LUCK_BUCKETS], "answer": bk[0], "why": why}
    n = rng.choice([50, 100, 200])
    k_med = 1   # medianen: minsta m där sannolikheten att längsta serien är högst m är minst 50 %
    while _no_run(n, k_med + 1, 0.5) < 0.5:
        k_med += 1
    bk = [b for b in STREAK_BUCKETS if b[2] <= k_med <= b[3]][0]
    q = (f"Med 50 % träffandel och {n} affärer i rad: hur lång är den längsta förlustserien man typiskt ser (medianen över många sådana serier)?")
    why = (f"Medianen är ungefär {k_med} förluster i rad, trots att varje affär är 50/50. Tumregel: längsta serien är ungefär log₂(antal affärer). "
           "Förlustserier är normala och säger inte att din metod slutat fungera. Spelboken ska säga i förväg vad du gör då.")
    return {"kind": "streak", "q": q, "options": [(b[0], b[1]) for b in STREAK_BUCKETS], "answer": bk[0], "why": why}


def luck_new() -> dict:
    seed = random.randint(1, 2_000_000_000)
    pr = _luck(seed)
    return {"token": exercises._tok({"s": seed}), "kind": pr["kind"], "q": pr["q"], "options": [{"key": k, "text": t} for k, t in pr["options"]]}


def luck_answer(token: str, choice: str) -> dict:
    pr = _luck(exercises._untok(token)["s"])
    ok = choice == pr["answer"]
    exercises.log("luck", ok, pr["kind"])
    txt = dict(pr["options"])[pr["answer"]]
    return {"correct": ok, "answer": pr["answer"], "answer_text": txt, "why": pr["why"]}


# ================================================================== ÖVNING: SAMBAND ELLER SLUMP
def _max_corr_median(n: int, m: int) -> float:
    """Median av största |korrelation| bland m oberoende par med n observationer vardera."""
    from statistics import NormalDist
    p_each = 1 - 0.5 ** (1 / m)
    return NormalDist().inv_cdf(1 - p_each / 2) / math.sqrt(n)


SPUR_BUCKETS = [("a", "Under 0,10", 0.0, 0.10), ("b", "0,10–0,15", 0.10, 0.15), ("c", "0,15–0,20", 0.15, 0.20), ("d", "0,20–0,30", 0.20, 0.30), ("e", "Över 0,30", 0.30, 9.0)]


def _spur(seed: int) -> dict:
    rng = random.Random(seed)
    if rng.random() < 0.55:
        for _ in range(300):
            n = rng.choice([60, 120, 250, 500, 750])
            m = rng.choice([10, 50, 200, 1000, 5000, 20000])
            c = _max_corr_median(n, m)
            bk = [b for b in SPUR_BUCKETS if b[2] <= c < b[3]][0]
            width = min(bk[3], 0.6) - bk[2]
            if min(c - bk[2], bk[3] - c) > 0.15 * width:
                break
        q = (f"Du letar efter bolagspar där X:s rörelse idag förutsäger Y:s rörelse imorgon. Du testar {m} par, och alla bolag är helt oberoende av varandra "
             f"(ren slump), med {n} dagars kursdata per par. Hur stor blir den största korrelationen du hittar, typiskt?")
        why = (f"Med {m} försök och {n} dagar är den största korrelationen av ren slump typiskt omkring {_sv(c, 2)}. "
               "Ett 'bästa par' bland många är nästan alltid starkare än något slumpen ger för ett enda par. Därför korrigerar Samband-sidan för antal tester.")
        return {"kind": "spur", "q": q, "options": [(b[0], b[1]) for b in SPUR_BUCKETS], "answer": bk[0], "why": why}
    m = rng.choice([40, 100, 600, 2000, 10000])
    right = round(0.05 * m)
    opts = {right, max(0, round(0.005 * m)), round(0.2 * m), round(0.5 * m)}
    opts = sorted(opts)
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    opts = sorted(set(opts))
    letters = "abcd"
    options = [(letters[i], f"Ungefär {v}") for i, v in enumerate(opts)]
    ans = [l for (l, t), v in zip(options, opts) if v == right][0]
    q = (f"Du testar {m} bolagspar för samband och använder gränsen p < 0,05 för 'signifikant'. Alla par är i verkligheten helt oberoende. "
         "Ungefär hur många par får du ändå markerade som signifikanta?")
    why = (f"Gränsen p < 0,05 betyder att 5 % av oberoende par ser 'signifikanta' ut av slump: ungefär {right} av {m}. "
           "Därför räknar appen om p-värdena (Benjamini–Hochberg) och visar förväntat antal falska fynd.")
    return {"kind": "spur", "q": q, "options": options, "answer": ans, "why": why}


def spur_new() -> dict:
    seed = random.randint(1, 2_000_000_000)
    pr = _spur(seed)
    return {"token": exercises._tok({"s": seed}), "kind": "spur", "q": pr["q"], "options": [{"key": k, "text": t} for k, t in pr["options"]]}


def spur_answer(token: str, choice: str) -> dict:
    pr = _spur(exercises._untok(token)["s"])
    ok = choice == pr["answer"]
    exercises.log("spur", ok, "spur")
    return {"correct": ok, "answer": pr["answer"], "answer_text": dict(pr["options"])[pr["answer"]], "why": pr["why"]}


# ================================================================== HANDELSSTATISTIK
def _closed_trades(pid: int | None = None) -> list[dict]:
    paper.evaluate()
    with db.connect() as con:
        if pid is None:
            rows = con.execute("SELECT * FROM paper_trades WHERE status='closed' ORDER BY exit_date, id").fetchall()
        else:
            rows = con.execute("SELECT * FROM paper_trades WHERE status='closed' AND pid=? ORDER BY exit_date, id", (pid,)).fetchall()
    return [dict(r) for r in rows]


def _r(t: dict) -> float | None:
    risk1 = t["entry_price"] - (t["stop0"] or t["stop"])
    return (t["exit_price"] - t["entry_price"]) / risk1 if risk1 > 0 else None


def _net_pct(t: dict) -> float:
    return ((t["exit_price"] * t["exit_fx"] * (1 - paper.COST)) / (t["entry_price"] * t["entry_fx"] * (1 + paper.COST)) - 1) * 100


def _wilson(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h) * 100, min(1.0, c + h) * 100


def _boot_mean(x: np.ndarray, reps: int = 4000, seed: int = 7):
    if len(x) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), size=(reps, len(x)))].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def _longest_losing(flags: list[bool]) -> int:
    best = cur = 0
    for w in flags:
        cur = 0 if w else cur + 1
        best = max(best, cur)
    return best


def _streak_typical(n: int, p_loss: float) -> tuple[int, int]:
    """(median, 95:e percentilen) för längsta förlustserie vid n affärer med given förlustandel."""
    if n < 2 or not 0 < p_loss < 1:
        return 0, 0
    med = p95 = None
    for k in range(1, n + 2):
        pr_ge = 1 - _no_run(n, k, p_loss) if k > 1 else 1.0
        if med is None and pr_ge < 0.5:
            med = k - 1
        if p95 is None and pr_ge < 0.05:
            p95 = k - 1
        if med is not None and p95 is not None:
            break
    return med or 0, p95 or 0


def _stats_of(trades: list[dict]) -> dict:
    rs = [(t, _r(t)) for t in trades]
    rs = [(t, r) for t, r in rs if r is not None]
    n = len(rs)
    out = {"n": n}
    if n == 0:
        return out
    r = np.array([x for _, x in rs], float)
    pct = np.array([_net_pct(t) for t, _ in rs], float)
    wins = int((r > 0).sum())
    lo, hi = _boot_mean(r)
    wl, wh = _wilson(wins, n)
    avg_w = float(r[r > 0].mean()) if (r > 0).any() else 0.0
    avg_l = float(r[r <= 0].mean()) if (r <= 0).any() else 0.0
    payoff = avg_w / abs(avg_l) if avg_l else None
    gross_w, gross_l = float(r[r > 0].sum()), float(-r[r <= 0].sum())
    flags = [bool(x > 0) for x in r]
    cum = np.cumsum(r)
    dd_r = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    med, p95 = _streak_typical(n, 1 - wins / n)
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    mean = float(r.mean())
    need = int(math.ceil((1.96 * sd / 0.25) ** 2)) if sd > 0 else None
    out.update({
        "wins": wins, "win_rate": wins / n * 100, "win_lo": wl, "win_hi": wh,
        "mean_r": mean, "median_r": float(np.median(r)), "r_lo": lo, "r_hi": hi, "sd_r": sd,
        "avg_win_r": avg_w, "avg_loss_r": avg_l, "payoff": payoff,
        "breakeven_win": (100 / (1 + payoff)) if payoff else None,
        "profit_factor": (gross_w / gross_l) if gross_l > 0 else None,
        "mean_pct": float(pct.mean()), "median_pct": float(np.median(pct)),
        "longest_losing": _longest_losing(flags), "typical_losing": med, "p95_losing": p95,
        "max_dd_r": dd_r, "need_n": need,
        "best_r": float(r.max()), "worst_r": float(r.min()),
        "gap_stops": sum(1 for t, _ in rs if t["exit_reason"] == "stop_gap"),
        "curve_r": [round(float(x), 3) for x in cum],
    })
    return out


def _verdict(s: dict) -> dict:
    n = s.get("n", 0)
    if n < 30:
        return {"key": "early", "title": "För tidigt att säga",
                "text": f"Du har {n} stängda affärer. Under ungefär 30 går det inte att skilja skicklighet från tur, och för att säga något om en fördel behövs betydligt fler. Fortsätt följa din Spelbok och dokumentera."}
    lo, hi = s["r_lo"], s["r_hi"]
    if lo is not None and lo > 0:
        return {"key": "positive", "title": "Siffrorna är förenliga med en fördel",
                "text": f"Ditt snitt är {_sv(s['mean_r'], 2)} R och osäkerhetsintervallet ({_sv(lo, 2)} till {_sv(hi, 2)}) ligger helt över noll. Det talar för att något fungerar, men det är ingen garanti: marknader ändras, urvalet kan vara fördelaktigt, och med riktiga pengar tillkommer känslor, skatt och sämre fyllning."}
    if hi is not None and hi < 0:
        return {"key": "negative", "title": "Siffrorna talar emot din nuvarande strategi",
                "text": f"Ditt snitt är {_sv(s['mean_r'], 2)} R och hela intervallet ({_sv(lo, 2)} till {_sv(hi, 2)}) ligger under noll. Det är värdefull information: ändra strategin, inte storleken, och testa den nya på samma sätt."}
    if s.get("need_n") and s["need_n"] > n:
        need = f" Med din spridning behövs ungefär {s['need_n']} affärer för att komma ner i ±0,25 R."
    elif s.get("need_n"):
        need = " Intervallet är redan smalt: ditt snitt ligger helt enkelt nära noll, så fler affärer ger främst en säkrare bild av att fördelen är liten eller saknas."
    else:
        need = ""
    return {"key": "unclear", "title": "Ingen påvisbar fördel än",
            "text": f"Ditt snitt är {_sv(s['mean_r'], 2)} R, men osäkerhetsintervallet ({_sv(lo, 2)} till {_sv(hi, 2)}) innehåller noll. Du kan alltså inte skilja ditt resultat från slump ännu.{need}"}


def trade_stats() -> dict:
    ports = {}
    with db.connect() as con:
        for r in con.execute("SELECT id, name, strategy FROM paper_portfolios ORDER BY id").fetchall():
            ports[r["id"]] = dict(r)
    allc = _closed_trades()
    total = _stats_of(allc)
    per = []
    for pid, p in ports.items():
        s = _stats_of([t for t in allc if t["pid"] == pid])
        s.update(pid=pid, name=p["name"], strategy=p["strategy"])
        per.append(s)
    return {"total": total, "verdict": _verdict(total), "portfolios": per,
            "note": "R-multipel = resultat delat med den risk du tog vid köp (köpkurs minus ursprungligt stopp). Intervallen är 95 % (bootstrap för snitt-R, Wilson för träffandel). Avgifter ingår inte i R men i procentsiffrorna."}


def compare(a: int, b: int) -> dict:
    if a == b:
        raise ValueError("Välj två olika portföljer")
    ta, tb = _closed_trades(a), _closed_trades(b)
    ra = np.array([x for x in (_r(t) for t in ta) if x is not None], float)
    rb = np.array([x for x in (_r(t) for t in tb) if x is not None], float)
    if len(ra) < 3 or len(rb) < 3:
        raise ValueError("Båda portföljerna behöver minst tre stängda affärer för att kunna jämföras")
    rng = np.random.default_rng(11)
    reps = 5000
    ma = ra[rng.integers(0, len(ra), size=(reps, len(ra)))].mean(axis=1)
    mb = rb[rng.integers(0, len(rb), size=(reps, len(rb)))].mean(axis=1)
    d = ma - mb
    lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
    diff = float(ra.mean() - rb.mean())
    p_a = float((d > 0).mean())
    with db.connect() as con:
        na = con.execute("SELECT name FROM paper_portfolios WHERE id=?", (a,)).fetchone()
        nb = con.execute("SELECT name FROM paper_portfolios WHERE id=?", (b,)).fetchone()
    if not na or not nb:
        raise LookupError("Portföljen finns inte")
    if lo > 0 or hi < 0:
        better = na["name"] if diff > 0 else nb["name"]
        text = f"Skillnaden i snitt-R ({_sv(diff, 2)}) är större än vad slumpen rimligen ger med så här många affärer: {better} verkar ha gått bättre. Det gäller bara den här perioden och de här bolagen."
    else:
        text = f"Skillnaden i snitt-R ({_sv(diff, 2)}) ryms inom slumpens spelrum (intervall {_sv(lo, 2)} till {_sv(hi, 2)}). Du kan inte säga att den ena strategin är bättre än den andra, och det är det vanligaste utfallet med få affärer."
    exercises.log("compare", None, f"{a}:{b}:{len(ra)}:{len(rb)}")
    return {"a": {"pid": a, "name": na["name"], **_stats_of(ta)}, "b": {"pid": b, "name": nb["name"], **_stats_of(tb)},
            "diff": diff, "lo": lo, "hi": hi, "prob_a_better": p_a * 100, "text": text,
            "distinguishable": bool(lo > 0 or hi < 0)}


# ================================================================== RISKPANEL (stresstest av egen portfölj + risk över tid)
def _beta(ticker: str, bench: pd.Series | None) -> float:
    df = exercises.load(ticker)
    if df is None or bench is None:
        return 1.0
    r = pd.concat([df["close"].pct_change(), bench.pct_change()], axis=1, keys=["a", "b"]).dropna().tail(252)
    if len(r) < 60 or r["b"].var() == 0:
        return 1.0
    return float(r["a"].cov(r["b"]) / r["b"].var())


def stress_portfolio(pid: int) -> dict:
    paper.evaluate()
    p = paper._port(pid)
    trades = paper._trades(pid)
    equity, cash, inv = paper._equity(p, trades)
    opens = [t for t in trades if t["status"] == "open"]
    bench = exercises._bench_close()
    pos, risk_tot, gap5 = [], 0.0, 0.0
    for t in opens:
        lp = paper._last_price(t["ticker"]) or t["entry_price"]
        fx = paper._fx_now(t["currency"])
        val = t["qty"] * lp * fx
        beta = _beta(t["ticker"], bench)
        r_stop = max(0.0, lp - t["stop"]) * t["qty"] * fx
        risk_tot += r_stop
        gap5 += (lp - t["stop"] * 0.95) * t["qty"] * fx if lp > t["stop"] else lp * 0.05 * t["qty"] * fx
        pos.append({"ticker": t["ticker"], "name": exercises._name(t["ticker"]), "w": val / equity * 100 if equity else 0, "beta": beta,
                    "risk_pct": r_stop / equity * 100 if equity else 0, "stop_dist": (lp - t["stop"]) / lp * 100})
    lim = trader.playbook_get()["limits"]
    sc = []
    for m in (10, 20, 30):
        loss = sum(x["w"] * x["beta"] for x in pos) * m / 100
        sc.append({"key": f"mkt{m}", "label": f"Marknaden faller {m} %", "loss_pct": loss, "over": loss > lim["max_dd"]["value"]})
    sc.append({"key": "stops", "label": "Alla stopp träffas till stoppkursen", "loss_pct": risk_tot / equity * 100 if equity else 0,
               "over": (risk_tot / equity * 100 if equity else 0) > lim["max_open_risk"]["value"]})
    g = gap5 / equity * 100 if equity else 0
    sc.append({"key": "gap5", "label": "Alla stopp träffas, men med 5 % gap under stoppet", "loss_pct": g, "over": g > lim["max_dd"]["value"]})
    if pos:
        big = max(pos, key=lambda x: x["w"])
        sc.append({"key": "big", "label": f"Största positionen ({big['ticker']}) tappar 30 % över natten", "loss_pct": big["w"] * 0.30,
                   "over": big["w"] * 0.30 > lim["max_dd"]["value"]})
    beta_p = sum(x["w"] * x["beta"] for x in pos) / 100
    exercises.log("stressrun", None, f"{pid}:{len(pos)}")
    return {"pid": pid, "name": p["name"], "equity": equity, "cash_pct": cash / equity * 100 if equity else 100, "positions": pos,
            "portfolio_beta": beta_p, "scenarios": sc, "limits": {k: v["value"] for k, v in lim.items()}, "n_open": len(pos)}


def risk_history() -> dict:
    """För varje portfölj: hölls öppen risk och nedgång inom egna gränser de senaste 60 handelsdagarna?"""
    paper.evaluate()
    lim = {k: v["value"] for k, v in trader.playbook_get()["limits"].items()}
    with db.connect() as con:
        ps = [dict(r) for r in con.execute("SELECT * FROM paper_portfolios ORDER BY id").fetchall()]
    out = []
    for p in ps:
        trades = paper._trades(p["id"])
        row = {"pid": p["id"], "name": p["name"], "days": 0, "window_days": 0, "invested_days": 0, "max_risk": None, "dd": None, "ok": False,
               "why": "Inga affärer ännu."}
        if trades:
            curve = paper._curve(p, trades)
            first = min(t["entry_date"] for t in trades)
            curve = [c for c in curve if c[0] >= first]
            row["days"] = len(curve)
            if len(curve) < 60:
                row["why"] = f"{len(curve)} av 60 handelsdagar sedan första affären."
            else:
                win = curve[-60:]
                closes = {t["ticker"]: exercises.load(t["ticker"]) for t in trades}
                max_risk, invested = 0.0, 0
                for ds, eq in win:
                    rsum, any_open = 0.0, False
                    for t in trades:
                        if t["entry_date"] > ds or (t["status"] == "closed" and t["exit_date"] <= ds):
                            continue
                        any_open = True
                        df = closes[t["ticker"]]
                        s = df["close"][df.index <= pd.Timestamp(ds)] if df is not None else None
                        px = float(s.iloc[-1]) if s is not None and len(s) else t["entry_price"]
                        stop = t["stop0"] if ds < (t["stop_from"] or t["entry_date"]) else t["stop"]
                        rsum += max(0.0, px - stop) * t["qty"] * t["entry_fx"]
                    invested += any_open
                    if eq:
                        max_risk = max(max_risk, rsum / eq * 100)
                vals = np.array([v for _, v in win], float)
                dd = float((vals / np.maximum.accumulate(vals) - 1).min() * 100)
                row.update(window_days=60, invested_days=invested, max_risk=max_risk, dd=dd)
                bad = []
                if invested < 30:
                    bad.append(f"du hade positioner på {invested} av 60 dagar (minst 30 krävs)")
                if max_risk > lim["max_open_risk"]:
                    bad.append(f"högsta öppna risk {_sv(max_risk, 1)} % > ditt tak {_sv(lim['max_open_risk'], 1)} %")
                if -dd > lim["max_dd"]:
                    bad.append(f"nedgång {_sv(-dd, 1)} % > din gräns {_sv(lim['max_dd'], 1)} %")
                row["ok"] = not bad
                row["why"] = "Inom dina gränser hela perioden." if not bad else "Inte godkänt: " + "; ".join(bad) + "."
        out.append(row)
    return {"portfolios": out, "limits": lim, "ok": any(r["ok"] for r in out)}


# ================================================================== REGELTEST
CONDS = {
    "trend_up": ("Kursen över SMA200", "Långsiktig uppåttrend."),
    "golden": ("SMA50 över SMA200", "Medellång trend över lång."),
    "pullback": ("Pullback: 0–3 % över SMA50 i uppåttrend", "Kursen har dragit sig tillbaka mot sitt 50-dagarssnitt."),
    "rsi_low": ("RSI under 30", "Översåld på kort sikt."),
    "rsi_hot": ("RSI över 70", "Övermogen på kort sikt."),
    "breakout": ("Ny 55-dagarshögsta stängning", "Utbrott över tidigare toppar."),
    "rs_pos": ("Starkare än index senaste 3 månaderna", "Positiv relativ styrka."),
    "mom": ("Positiv momentum 12−1 månader", "Aktien har stigit senaste året (exklusive sista månaden)."),
    "calm": ("Låg volatilitet (ATR under 2 % av kursen)", "Lugna aktier."),
    "drop": ("Föll mer än 8 % senaste fem dagarna", "Kraftigt kortsiktigt fall."),
}


def _cond_frame(df: pd.DataFrame, bench: pd.Series | None) -> pd.DataFrame:
    c, h, l = df["close"], df["high"], df["low"]
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    rsi = exercises._rsi_series(c)
    atr = indicators.atr(h, l, c)
    f = pd.DataFrame(index=df.index)
    f["trend_up"] = c > sma200
    f["golden"] = sma50 > sma200
    f["pullback"] = (c > sma200) & (c / sma50 - 1 >= 0) & (c / sma50 - 1 <= 0.03)
    f["rsi_low"] = rsi < 30
    f["rsi_hot"] = rsi > 70
    f["breakout"] = c >= c.shift(1).rolling(55).max()
    if bench is not None:
        b = bench.reindex(df.index).ffill()
        f["rs_pos"] = (c / c.shift(63) - 1) > (b / b.shift(63) - 1)
    else:
        f["rs_pos"] = False
    f["mom"] = (c.shift(21) / c.shift(252) - 1) > 0
    f["calm"] = atr / c < 0.02
    f["drop"] = (c / c.shift(5) - 1) < -0.08
    f["valid"] = sma200.notna() & atr.notna() & c.shift(252).notna()
    f["atr"] = atr
    return f


def _simulate(df: pd.DataFrame, sig: np.ndarray, atr: np.ndarray, stop_atr: float, horizon: int) -> list[dict]:
    """Enter på nästa dags öppning efter signal. Stopp = ATR-multipel vid signaldagen. Ut vid stopp eller horisont. Ingen överlappning per aktie."""
    o, l, c = df["open"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    idx = df.index
    n = len(c)
    trades, i = [], 0
    while i < n - 2:
        if not sig[i]:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        stop = c[i] - stop_atr * atr[i]
        if not (entry > 0) or stop >= entry or stop <= 0:
            i += 1
            continue
        end = min(n - 1, e + horizon)
        ex_i, ex_p, why = end, c[end], "time"
        if end - e < horizon:
            i += 1   # inte tillräckligt med framtid kvar
            continue
        for j in range(e, end + 1):
            hit, fp, gap = exercises._fill(float(o[j]) if j > e else entry, float(l[j]), stop)
            if hit:
                ex_i, ex_p, why = j, fp, "stop"
                break
        risk1 = entry - stop
        trades.append({"date": idx[e], "r": (ex_p - entry) / risk1, "ret": ((ex_p * (1 - paper.COST)) / (entry * (1 + paper.COST)) - 1) * 100, "why": why})
        i = ex_i + 1
    return trades


def rule_test(conds: list[str], stop_atr: float, horizon: int, hypothesis: str) -> dict:
    hypothesis = (hypothesis or "").strip()
    if len(hypothesis) < 30:
        raise ValueError("Skriv din hypotes först (minst 30 tecken): vad tror du kommer hända, och varför?")
    conds = [c for c in conds if c in CONDS]
    if not conds:
        raise ValueError("Välj minst ett villkor för köp")
    stop_atr = max(1.0, min(6.0, float(stop_atr)))
    horizon = int(max(10, min(120, horizon)))
    tk = exercises.pool(420)
    if len(tk) < 3:
        raise ValueError("För lite kursdata. Tryck Uppdatera först.")
    bench = exercises._bench_close()
    rule_tr, base_tr = [], []
    used = 0
    for t in tk:
        df = exercises.load(t)
        if df is None or len(df) < 420:
            continue
        f = _cond_frame(df, bench)
        valid = f["valid"].to_numpy(bool)
        sig = valid.copy()
        for c in conds:
            sig &= f[c].fillna(False).to_numpy(bool)
        atr = f["atr"].to_numpy(float)
        rule_tr += [dict(x, t=t) for x in _simulate(df, sig, atr, stop_atr, horizon)]
        base_tr += [dict(x, t=t) for x in _simulate(df, valid, atr, stop_atr, horizon)]
        used += 1
    if len(rule_tr) < 8:
        raise ValueError(f"Regeln gav bara {len(rule_tr)} affärer i historiken, för få för att säga något. Lätta på villkoren eller välj fler bolag i dina listor.")
    r = np.array([x["r"] for x in rule_tr])
    rb = np.array([x["r"] for x in base_tr])
    ret = np.array([x["ret"] for x in rule_tr])
    retb = np.array([x["ret"] for x in base_tr])
    lo, hi = _boot_mean(r)
    wins = int((r > 0).sum())
    wl, wh = _wilson(wins, len(r))
    order = sorted(range(len(rule_tr)), key=lambda i: rule_tr[i]["date"])
    half = len(order) // 2
    a, b = r[order[:half]], r[order[half:]]
    split_date = rule_tr[order[half]]["date"].strftime("%Y-%m-%d")
    months = len({x["date"].strftime("%Y-%m") for x in rule_tr})
    with db.connect() as con:
        prev = con.execute("SELECT COUNT(*) n FROM rule_tests").fetchone()["n"]
    ahead = float(r.mean() - rb.mean())
    consistent = bool(a.mean() > rb.mean() and b.mean() > rb.mean()) if ahead > 0 else bool(a.mean() < rb.mean() and b.mean() < rb.mean())
    notes = []
    if len(r) < 30:
        notes.append(f"Bara {len(r)} affärer: resultatet är mycket osäkert.")
    if months < 12:
        notes.append(f"Affärerna är spridda över bara {months} månader, och bolag som rör sig ihop räknas som flera affärer.")
    if prev >= 2:
        notes.append(f"Du har redan testat {prev} regler. Testar du 20 regler hittar slumpen i snitt en som ser bra ut. Räkna inte med att den håller.")
    notes.append("Bolagen är dagens urval ur dina listor (de som överlevde och du valt att följa), vilket brukar göra historiska resultat bättre än de var på riktigt.")
    if not consistent and len(r) >= 20:
        notes.append("Regeln slår inte jämförelsen i båda halvorna av perioden. Det är ett typiskt tecken på överanpassning eller att den bara fungerade i en viss marknad.")
    result = {"n": int(len(r)), "tickers": used, "months": months, "win_rate": wins / len(r) * 100, "win_lo": wl, "win_hi": wh,
              "mean_r": float(r.mean()), "r_lo": lo, "r_hi": hi, "mean_pct": float(ret.mean()),
              "base_n": int(len(rb)), "base_r": float(rb.mean()), "base_pct": float(retb.mean()), "ahead_r": ahead,
              "first_half_r": float(a.mean()), "second_half_r": float(b.mean()), "split_date": split_date, "consistent": consistent,
              "stopped_pct": float(np.mean([x["why"] == "stop" for x in rule_tr]) * 100), "notes": notes,
              "better_than_chance": bool(lo is not None and lo > float(rb.mean()))}
    rule = {"conds": conds, "stop_atr": stop_atr, "horizon": horizon}
    with db.connect() as con:
        con.execute("INSERT INTO rule_tests(ts, hypothesis, rule, result) VALUES(?,?,?,?)", (_now(), hypothesis, json.dumps(rule), json.dumps(result)))
    return {"rule": rule, "result": result, "prev_tests": prev + 1}


def rule_history() -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM rule_tests ORDER BY id DESC LIMIT 20").fetchall()
    out = []
    for r in rows:
        rule, res = json.loads(r["rule"]), json.loads(r["result"])
        out.append({"id": r["id"], "ts": r["ts"][:10], "hypothesis": r["hypothesis"], "rule": rule, "n": res["n"], "mean_r": res["mean_r"],
                    "base_r": res["base_r"], "consistent": res["consistent"],
                    "label": " + ".join(CONDS[c][0] for c in rule["conds"]) + f" · stopp {rule['stop_atr']:g} ATR · {rule['horizon']} dagar"})
    return out


# ================================================================== HANDLARPROFIL
DECISIONS = {"live_small": "Börja handla på riktigt, med ett litet belopp jag är beredd att förlora och samma regler",
             "practice_more": "Fortsätta öva: fler affärer i övningsportföljen innan jag riskerar riktiga pengar",
             "change": "Ändra strategin: den nuvarande visar ingen fördel, och jag testar en ny"}
MIN_TRADES, MIN_DAYS, MIN_PROC, MIN_MONTHLY = 50, 180, 80, 6
MIN_REFLECT = 150


def _span_days(trades_all: list[dict]) -> int:
    if not trades_all:
        return 0
    first = min(t["entry_date"] for t in trades_all)
    return (date.today() - date.fromisoformat(first)).days


def profile() -> dict:
    paper.evaluate()
    closed = _closed_trades()
    with db.connect() as con:
        alltr = [dict(r) for r in con.execute("SELECT entry_date FROM paper_trades").fetchall()]
        dec = con.execute("SELECT * FROM trader_decisions ORDER BY id DESC LIMIT 1").fetchone()
        n_rules = con.execute("SELECT COUNT(*) n FROM rule_tests").fetchone()["n"]
    stats = _stats_of(closed)
    verdict = _verdict(stats)
    last30 = closed[-30:]
    pts = [paper.points(t)["total"] for t in last30]
    proc = float(np.mean(pts)) if len(pts) >= 30 else None
    pb = trader.playbook_get()
    mo = trader.game_flags()
    rh = risk_history()
    ex = exercises.stats()
    span = _span_days(alltr)
    months_with = len({t["exit_date"][:7] for t in closed})
    bias = ex["bias"]
    lessons = [{"ticker": t["ticker"], "date": t["exit_date"], "text": t["lesson"], "r": _r(t)} for t in reversed(closed) if len(t["lesson"].strip()) >= 20][:8]
    reqs = [
        {"id": "trades", "label": f"Minst {MIN_TRADES} stängda affärer", "have": f"{len(closed)}/{MIN_TRADES}", "ok": len(closed) >= MIN_TRADES},
        {"id": "span", "label": f"Minst {MIN_DAYS // 30} månader sedan första affären", "have": f"{min(span, MIN_DAYS) // 30}/{MIN_DAYS // 30} mån", "ok": span >= MIN_DAYS},
        {"id": "process", "label": f"Processsnitt minst {MIN_PROC} över de senaste 30 affärerna", "have": "–" if proc is None else f"{proc:.0f}/{MIN_PROC}", "ok": proc is not None and proc >= MIN_PROC},
        {"id": "playbook", "label": "Fullständig Spelbok", "have": "klar" if pb["complete"] else "ej klar", "ok": pb["complete"]},
        {"id": "monthly", "label": f"{MIN_MONTHLY} månadsgranskningar", "have": f"{min(mo['monthly'], MIN_MONTHLY)}/{MIN_MONTHLY}", "ok": mo["monthly"] >= MIN_MONTHLY},
        {"id": "risk", "label": "Egna riskgränser hållna i 60 handelsdagar", "have": "ja" if rh["ok"] else "nej", "ok": rh["ok"]},
        {"id": "decision", "label": "Skrivit ditt ärliga beslut om vad du gör härnäst", "have": "ja" if dec else "nej", "ok": bool(dec)},
    ]
    ready = all(r["ok"] for r in reqs)
    return {
        "ready": ready, "reqs": reqs, "stats": stats, "verdict": verdict, "span_days": span, "months_with_trades": months_with,
        "process_last30": proc, "playbook": {"complete": pb["complete"], "limits": {k: v["value"] for k, v in pb["limits"].items()},
                                              "sections": [{"title": s["title"], "text": s["text"]} for s in pb["sections"]]},
        "monthly_n": mo["monthly"], "risk": rh, "bias": {"n": bias["n"], "pct": (bias["recent_correct"] / bias["recent_n"] * 100) if bias["recent_n"] else None},
        "rule_tests": n_rules, "lessons": lessons, "decisions": DECISIONS, "min_reflect": MIN_REFLECT,
        "decision": None if not dec else {"ts": dec["ts"][:10], "decision": dec["decision"], "label": DECISIONS.get(dec["decision"], ""), "reflection": dec["reflection"],
                                          "verdict": dec["verdict"], "n": dec["n"]},
        "label": "Visad professionell process" if ready else "Preliminär profil",
        "disclaimer": "Profilen visar att du har byggt och följt en process. Den bevisar inte skicklighet, och den är inget investeringsråd. Pappershhandel saknar känslorna, courtaget är förenklat och fyllningarna är bättre än i verkligheten.",
    }


def decision_save(decision: str, reflection: str) -> None:
    if decision not in DECISIONS:
        raise ValueError("Välj vad du tänker göra härnäst")
    reflection = (reflection or "").strip()
    if len(reflection) < MIN_REFLECT:
        raise ValueError(f"Skriv minst {MIN_REFLECT} tecken: vad visar siffrorna, vad är du osäker på, och vad skulle få dig att ändra dig?")
    closed = _closed_trades()
    if len(closed) < 30:
        raise ValueError("Du behöver minst 30 stängda övningsaffärer innan det finns något att fatta beslut om")
    v = _verdict(_stats_of(closed))
    with db.connect() as con:
        con.execute("INSERT INTO trader_decisions(ts, decision, reflection, verdict, n) VALUES(?,?,?,?,?)", (_now(), decision, reflection, v["key"], len(closed)))


# ================================================================== SPELFLAGGOR
def game_flags() -> dict:
    closed = _closed_trades()
    with db.connect() as con:
        sr = con.execute("SELECT detail FROM practice_log WHERE kind='stressrun'").fetchall()
        cp = con.execute("SELECT detail FROM practice_log WHERE kind='compare'").fetchall()
        rt = con.execute("SELECT hypothesis FROM rule_tests").fetchall()
        alltr = [dict(r) for r in con.execute("SELECT entry_date FROM paper_trades").fetchall()]
        dec = con.execute("SELECT COUNT(*) n FROM trader_decisions").fetchone()["n"]
    stress_ok = any(int(x["detail"].split(":")[1]) >= 3 for x in sr if ":" in x["detail"])
    compare_ok = any(len(x["detail"].split(":")) == 4 and int(x["detail"].split(":")[2]) >= 10 and int(x["detail"].split(":")[3]) >= 10 for x in cp)
    last30 = closed[-30:]
    proc = float(np.mean([paper.points(t)["total"] for t in last30])) if len(last30) >= 30 else None
    return {"stress_ok": stress_ok, "compare_ok": compare_ok, "rule_tests": len({r["hypothesis"] for r in rt}), "closed": len(closed),
            "span": _span_days(alltr), "proc30": proc, "decision": dec > 0, "risk_ok": risk_history()["ok"]}
