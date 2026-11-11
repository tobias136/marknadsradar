"""Samband mellan bolag.

Tre delar:
1. Lead-lag: följer Y efter X? Mäts på kursdata, rensat från marknadsrörelser, med korrigering för att
   många par testas samtidigt (Benjamini–Hochberg).
2. Händelsestudie: hur rör sig Y runt X:s rapporter och kraftiga rörelser?
3. Relationer: handinmatade eller importerade kund-/leverantörs-/partnerkopplingar med obligatorisk källa.
   De behandlas som hypoteser och jämförs mot de statistiska sambanden.

Statistiken är beskrivande. Samband i historiken är ingen garanti framåt, och med många par blir en del
signifikanta av ren slump. Därför visas alltid antal tester och förväntat antal falska fynd."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import db, exercises, service

MIN_ROWS = 300
LAGS = (1, 2, 3, 4, 5)
FDR_Q = 0.10
MIN_EVENTS = 8
GOOD_EVENTS = 20
TYPES = {"supplies": "levererar till", "invests": "äger eller investerar i", "partner": "samarbetar med", "competitor": "konkurrerar med"}
STRENGTHS = {"major": "avgörande (t.ex. över 10 % av omsättningen eller uttalat kritisk)", "mentioned": "nämnd i bolagets egna dokument", "minor": "mindre"}
CONFIDENCE = ("primär", "sekundär")

_ND = NormalDist()
_cache: dict = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ================================================================== DATA
def _bench_tickers() -> list[str]:
    with db.connect() as con:
        rows = con.execute("SELECT DISTINCT benchmark FROM lists WHERE benchmark IS NOT NULL AND benchmark<>''").fetchall()
    out = []
    for r in rows:
        df = exercises.load(r["benchmark"])
        if df is not None and len(df) >= MIN_ROWS:
            out.append(r["benchmark"])
    return out[:3]


def _frame() -> dict:
    """Marknadsrensade dagliga avkastningar (residualer) för alla tickers i listorna."""
    bens = _bench_tickers()
    tk = [t for t in exercises.pool(MIN_ROWS) if t not in bens]
    dfs = {t: exercises.load(t) for t in tk}
    key = tuple((t, len(d), str(d.index[-1])) for t, d in dfs.items() if d is not None) + tuple(bens)
    if _cache.get("frame_key") == key:
        return _cache["frame"]
    px = pd.DataFrame({t: d["close"] for t, d in dfs.items() if d is not None}).sort_index()
    ret = np.log(px).diff()
    ret = ret.iloc[1:]
    if bens:
        bpx = pd.DataFrame({b: exercises.load(b)["close"] for b in bens}).reindex(px.index)
        bret = np.log(bpx).diff()
        fac = pd.concat([bret, bret.shift(1).add_suffix("_l1")], axis=1).iloc[1:]
        fac = fac.reindex(ret.index)
    else:
        fac = pd.DataFrame(index=ret.index)
    res = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    for t in ret.columns:
        y = ret[t]
        if len(fac.columns):
            ok = y.notna() & fac.notna().all(axis=1)
            if ok.sum() < 200:
                continue
            X = np.column_stack([np.ones(ok.sum()), fac[ok].to_numpy()])
            beta, *_ = np.linalg.lstsq(X, y[ok].to_numpy(), rcond=None)
            res.loc[ok, t] = y[ok].to_numpy() - X @ beta
        else:
            res[t] = y - y.mean()
    res = res.dropna(axis=1, thresh=200)
    out = {"res": res, "bens": bens}
    _cache["frame_key"], _cache["frame"] = key, out
    _cache.pop("leadlag", None)
    return out


def _name(t: str) -> str:
    try:
        return exercises._name(t)
    except Exception:  # noqa: BLE001
        return t


def _p_norm(t: np.ndarray) -> np.ndarray:
    return np.array([math.erfc(abs(x) / math.sqrt(2)) for x in np.ravel(t)]).reshape(np.shape(t))


def _bh(p: np.ndarray, q: float = FDR_Q) -> tuple[np.ndarray, np.ndarray]:
    """Benjamini–Hochberg: (justerade p-värden, signifikant-flagga)."""
    m = len(p)
    if m == 0:
        return p, np.zeros(0, bool)
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(m) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out, out <= q


# ================================================================== LEAD-LAG
def leadlag() -> dict:
    fr = _frame()
    res: pd.DataFrame = fr["res"]
    if "leadlag" in _cache:
        return _cache["leadlag"]
    cols = list(res.columns)
    n = len(cols)
    out = {"n_tickers": n, "n_tests": 0, "n_obs": len(res), "start": str(res.index[0].date()) if len(res) else None,
           "end": str(res.index[-1].date()) if len(res) else None, "benchmarks": fr["bens"], "fdr_q": FDR_Q, "sig": [], "best_uncorrected": None}
    if n < 3 or len(res) < 200:
        _cache["leadlag"] = out
        return out
    A = res.to_numpy()
    V = (~np.isnan(A)).astype(float)
    sd = np.nanstd(A, axis=0)
    Z = np.where(np.isnan(A), 0.0, (A - np.nanmean(A, axis=0)) / sd)
    tests = []   # (i, j, k, r, t, cnt)
    for k in LAGS:
        num = Z[:-k].T @ Z[k:]
        cnt = V[:-k].T @ V[k:]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = num / cnt
        r = np.clip(np.nan_to_num(r), -0.999, 0.999)
        mask = (cnt >= 200) & ~np.eye(n, dtype=bool)
        ii, jj = np.where(mask)
        tt = r[ii, jj] * np.sqrt((cnt[ii, jj] - 2) / (1 - r[ii, jj] ** 2))
        tests += list(zip(ii, jj, [k] * len(ii), r[ii, jj], tt, cnt[ii, jj]))
    if not tests:
        _cache["leadlag"] = out
        return out
    t_arr = np.array([x[4] for x in tests])
    p = _p_norm(t_arr)
    q, sig = _bh(p)
    out["n_tests"] = len(tests)
    out["expected_false_p05"] = 0.05 * len(tests)
    best = int(np.argmax(np.abs(t_arr)))
    bi, bj, bk, br, bt, bc = tests[best]
    out["best_uncorrected"] = {"a": cols[bi], "b": cols[bj], "lag": int(bk), "r": float(br), "p": float(p[best])}
    half = len(res) // 2
    rows = []
    for idx in np.where(sig)[0]:
        i, j, k, r, t, c = tests[idx]
        x, y = res[cols[i]], res[cols[j]]
        halves = []
        for part in (slice(0, half), slice(half, None)):
            xs, ys = x.iloc[part], y.iloc[part]
            d = pd.concat([xs.shift(k), ys], axis=1).dropna()
            halves.append(float(d.iloc[:, 0].corr(d.iloc[:, 1])) if len(d) > 60 else None)
        stable = bool(halves[0] is not None and halves[1] is not None and np.sign(halves[0]) == np.sign(halves[1]) == np.sign(r))
        rows.append({"a": cols[i], "b": cols[j], "lag": int(k), "r": float(r), "t": float(t), "p": float(p[idx]), "q": float(q[idx]), "n": int(c),
                     "slope": float(r * sd[j] / sd[i]), "r1": halves[0], "r2": halves[1], "stable": stable})
    rows.sort(key=lambda x: -abs(x["t"]))
    out["sig"] = rows
    out["n_sig"] = len(rows)
    out["n_stable"] = sum(1 for x in rows if x["stable"])
    out["expected_false_sig"] = FDR_Q * len(rows)
    _cache["leadlag"] = out
    return out


def leadlag_for(ticker: str) -> dict:
    ll = leadlag()
    t = ticker.strip().upper()
    in_u = t in set(_frame()["res"].columns)
    mine = {"ticker": t, "in_universe": in_u, "n_tickers": ll["n_tickers"], "n_tests": ll["n_tests"], "n_obs": ll["n_obs"], "start": ll["start"], "end": ll["end"],
            "fdr_q": ll["fdr_q"], "expected_false_p05": ll.get("expected_false_p05", 0), "best_uncorrected": ll["best_uncorrected"], "n_sig_total": ll.get("n_sig", 0),
            "expected_false_sig_total": ll.get("expected_false_sig", 0), "benchmarks": ll["benchmarks"]}
    def dec(x, other):
        return {**x, "other": x[other], "other_name": _name(x[other])}
    mine["leads"] = [dec(x, "b") for x in ll["sig"] if x["a"] == t][:15]
    mine["led_by"] = [dec(x, "a") for x in ll["sig"] if x["b"] == t][:15]
    return mine


def leadlag_top(n: int = 20) -> dict:
    ll = leadlag()
    return {**{k: v for k, v in ll.items() if k != "sig"}, "sig": [{**x, "a_name": _name(x["a"]), "b_name": _name(x["b"])} for x in ll["sig"][:n]]}


# ================================================================== HÄNDELSESTUDIE
def _events(t: str, res: pd.DataFrame, kind: str, thr: float) -> list[tuple[int, float]]:
    """[(index för dag 0, X:s reaktion i log-%)]. Dag 0 för rapporter är första handelsdagen på/efter rapportdatum."""
    x = res[t]
    ev = []
    if kind == "earnings":
        fund = service.fund_get(t) or {}
        for e in fund.get("earnings") or []:
            try:
                d = pd.Timestamp(e["date"])
            except Exception:  # noqa: BLE001
                continue
            pos = int(res.index.searchsorted(d))
            if pos + 8 >= len(res) or pos < 5:
                continue
            react = float(x.iloc[pos:pos + 2].sum(skipna=True))
            ev.append((pos, react))
    else:
        sd = float(x.std())
        big = np.where(np.abs(x.to_numpy()) >= thr * sd)[0]
        for pos in big:
            if pos + 8 >= len(res) or pos < 5:
                continue
            ev.append((int(pos), float(x.iloc[pos])))
    ev.sort()
    out, last = [], -99
    for pos, r in ev:
        if pos - last >= 6:
            out.append((pos, r))
            last = pos
    return out


def _slope(xv: np.ndarray, yv: np.ndarray, reps: int = 2000, seed: int = 3):
    """Lutning av Y:s rörelse mot X:s reaktion. Intervall via bootstrap, p-värde via permutation (tål få händelser)."""
    n = len(xv)
    if n < MIN_EVENTS or np.ptp(xv) == 0:
        return None
    xc = xv - xv.mean()
    den = float((xc ** 2).sum())
    b = float((xc * (yv - yv.mean())).sum() / den)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(reps, n))
    bx, by = xv[idx], yv[idx]
    bxc = bx - bx.mean(axis=1, keepdims=True)
    bden = (bxc ** 2).sum(axis=1)
    bs = np.where(bden > 0, (bxc * (by - by.mean(axis=1, keepdims=True))).sum(axis=1) / np.where(bden > 0, bden, 1), 0.0)
    perm = np.array([rng.permutation(yv) for _ in range(reps)])
    pb = ((perm - perm.mean(axis=1, keepdims=True)) * xc).sum(axis=1) / den
    p = float((1 + (np.abs(pb) >= abs(b) - 1e-15).sum()) / (1 + reps))
    return {"slope": b, "lo": float(np.percentile(bs, 2.5)), "hi": float(np.percentile(bs, 97.5)), "p": p}


def event_study(ticker: str, kind: str = "move", thr: float = 2.5) -> dict:
    fr = _frame()
    res: pd.DataFrame = fr["res"]
    t = ticker.strip().upper()
    thr = float(max(1.5, min(5.0, thr)))
    if t not in res.columns:
        raise ValueError(f"{t} har för lite kursdata (minst {MIN_ROWS} dagar krävs) eller finns inte i någon lista.")
    ev = _events(t, res, "earnings" if kind == "earnings" else "move", thr)
    out = {"ticker": t, "name": _name(t), "kind": kind, "threshold": thr, "n_events": len(ev), "rows": [], "n_tests": 0, "notes": []}
    ups = sum(1 for _, r in ev if r > 0)
    out["n_up"], out["n_down"] = ups, len(ev) - ups
    if len(ev) < MIN_EVENTS:
        out["notes"].append(f"Bara {len(ev)} händelser. Minst {MIN_EVENTS} krävs för att räkna, och minst {GOOD_EVENTS} för att resultatet ska säga något."
                            + (" Välj 'kraftiga rörelser' eller sänk tröskeln för fler händelser." if kind == "earnings" else " Sänk tröskeln för fler händelser."))
        return out
    pos = np.array([p for p, _ in ev])
    xr = np.array([r for _, r in ev])
    rows = []
    A = res.to_numpy()
    cols = list(res.columns)
    for j, y in enumerate(cols):
        if y == t:
            continue
        co, after, xs_co, xs_af = [], [], [], []
        for p, r in zip(pos, xr):
            w = A[p:p + 6, j]
            if np.isnan(w).sum() > 1:
                continue
            w = np.nan_to_num(w)
            co.append(w[0:2].sum())
            after.append(w[2:6].sum())
            xs_co.append(r)
        if len(co) < MIN_EVENTS:
            continue
        xs = np.array(xs_co)
        s_co = _slope(xs, np.array(co))
        s_af = _slope(xs, np.array(after))
        if not s_co or not s_af:
            continue
        rows.append({"ticker": y, "name": _name(y), "n": len(co), "co": s_co, "after": s_af,
                     "mean_co": float(np.mean(co) * 100), "mean_after": float(np.mean(after) * 100)})
    if not rows:
        out["notes"].append("Inga andra bolag hade tillräckligt med data runt händelserna.")
        return out
    for key in ("co", "after"):
        pv = np.array([r[key]["p"] for r in rows])
        qv, sg = _bh(pv)
        for r, qq, ss in zip(rows, qv, sg):
            r[key]["q"] = float(qq)
            r[key]["sig"] = bool(ss)
    rows.sort(key=lambda r: min(r["co"]["q"], r["after"]["q"]))
    out["rows"] = rows
    out["n_tests"] = len(rows) * 2
    out["n_sig"] = sum(1 for r in rows if r["co"]["sig"] or r["after"]["sig"])
    out["expected_false_p05"] = 0.05 * out["n_tests"]
    if len(ev) < GOOD_EVENTS:
        out["notes"].append(f"{len(ev)} händelser är få. Intervallen är breda och resultatet ska läsas som en fingervisning.")
    if kind == "earnings":
        out["notes"].append("Rapportdatum anges utan klockslag. Därför mäts samrörelsen över dag 0 och 1, och 'efterföljande rörelse' över dag 2 till 5.")
    out["notes"].append(f"{out['n_tests']} tester görs på en gång, så ungefär {out['expected_false_p05']:.0f} skulle bli 'signifikanta' (p<0,05) av ren slump. Därför korrigeras för det (FDR {int(FDR_Q * 100)} %).")
    out["notes"].append("Alla rörelser är rensade från marknaden (index). Bolag på olika börser stänger vid olika tider, så effekter mellan USA och Sverige kan hamna en dag fel.")
    return out


# ================================================================== RELATIONER (källbelagda hypoteser)
def _clean(t: str) -> str:
    return (t or "").strip().upper()


def _check_edge(e: dict) -> dict:
    a, b = _clean(e.get("a")), _clean(e.get("b"))
    if not a or not b or a == b:
        raise ValueError("Ange två olika tickers")
    if e.get("rtype") not in TYPES:
        raise ValueError("Okänd relationstyp")
    url = (e.get("source_url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Källa krävs: ange en länk (https://…) till bolagets dokument eller pressmeddelande")
    st = e.get("strength") or "mentioned"
    if st not in STRENGTHS:
        raise ValueError("Okänd styrka")
    cf = e.get("confidence") or "primär"
    if cf not in CONFIDENCE:
        raise ValueError("Okänd säkerhetsnivå")
    sp = e.get("share_pct")
    if sp in ("", None):
        sp = None
    else:
        sp = float(sp)
        if not 0 <= sp <= 100:
            raise ValueError("Andel måste vara mellan 0 och 100 %")
    return {"a": a, "b": b, "rtype": e["rtype"], "strength": st, "share_pct": sp, "amount": (e.get("amount") or "").strip()[:120],
            "source_url": url[:500], "source_title": (e.get("source_title") or "").strip()[:200], "as_of": (e.get("as_of") or "").strip()[:10],
            "confidence": cf, "note": (e.get("note") or "").strip()[:500]}


def add_edge(e: dict) -> int:
    c = _check_edge(e)
    with db.connect() as con:
        dup = con.execute("SELECT id FROM relations WHERE a=? AND b=? AND rtype=? AND source_url=?", (c["a"], c["b"], c["rtype"], c["source_url"])).fetchone()
        if dup:
            raise ValueError("Samma relation med samma källa finns redan")
        cur = con.execute("INSERT INTO relations(a,b,rtype,strength,share_pct,amount,source_url,source_title,as_of,confidence,note,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                          (c["a"], c["b"], c["rtype"], c["strength"], c["share_pct"], c["amount"], c["source_url"], c["source_title"], c["as_of"], c["confidence"], c["note"], _now()))
        return cur.lastrowid


def delete_edge(eid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM relations WHERE id=?", (eid,))


def import_edges(items: list[dict]) -> dict:
    ok, skipped = 0, []
    for i, e in enumerate(items):
        try:
            add_edge(e)
            ok += 1
        except ValueError as ex:
            skipped.append(f"#{i + 1}: {ex}")
    return {"added": ok, "skipped": skipped}


def mark_reviewed(ticker: str, on: bool = True) -> None:
    t = _clean(ticker)
    with db.connect() as con:
        if on:
            con.execute("INSERT OR REPLACE INTO rel_reviewed(ticker, ts) VALUES(?,?)", (t, _now()))
        else:
            con.execute("DELETE FROM rel_reviewed WHERE ticker=?", (t,))


def coverage() -> dict:
    with db.connect() as con:
        tk = [r["ticker"] for r in con.execute("SELECT DISTINCT ticker FROM list_items ORDER BY ticker").fetchall()]
        rev = {r["ticker"]: r["ts"][:10] for r in con.execute("SELECT * FROM rel_reviewed").fetchall()}
        cnt: dict = {}
        for r in con.execute("SELECT a, b FROM relations").fetchall():
            cnt[r["a"]] = cnt.get(r["a"], 0) + 1
            cnt[r["b"]] = cnt.get(r["b"], 0) + 1
        n_edges = con.execute("SELECT COUNT(*) n FROM relations").fetchone()["n"]
    rows = [{"ticker": t, "name": _name(t), "reviewed": rev.get(t), "edges": cnt.get(t, 0)} for t in tk]
    return {"n_tickers": len(tk), "n_reviewed": sum(1 for r in rows if r["reviewed"]), "n_edges": n_edges, "n_with_edges": sum(1 for r in rows if r["edges"]), "rows": rows}


def edges_for(ticker: str) -> dict:
    t = _clean(ticker)
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM relations WHERE a=? OR b=? ORDER BY CASE strength WHEN 'major' THEN 0 WHEN 'mentioned' THEN 1 ELSE 2 END, id", (t, t)).fetchall()]
        rv = con.execute("SELECT ts FROM rel_reviewed WHERE ticker=?", (t,)).fetchone()
    ll = leadlag()
    sig = {(x["a"], x["b"]): x for x in ll["sig"]}
    for r in rows:
        r["other"] = r["b"] if r["a"] == t else r["a"]
        r["other_name"] = _name(r["other"])
        r["dir"] = "out" if r["a"] == t else "in"
        r["verb"] = TYPES[r["rtype"]]
        r["strength_text"] = STRENGTHS[r["strength"]]
        s1, s2 = sig.get((r["a"], r["b"])), sig.get((r["b"], r["a"]))
        r["stat"] = None
        if s1 or s2:
            s = s1 or s2
            r["stat"] = {"a": s["a"], "b": s["b"], "lag": s["lag"], "r": s["r"], "stable": s["stable"]}
    from . import relauto
    with db.connect() as con:
        hl = {r["eid"]: dict(r) for r in con.execute("SELECT * FROM rel_health").fetchall()}
    for r in rows:
        h = hl.get(r["id"])
        r["stale"] = relauto.stale(r["as_of"], r["created"])
        r["link_state"] = "okänd" if not h else ("ok" if h["ok"] else ("varning" if h["fails"] >= 2 else "okänd"))
        r["link_note"] = h["note"] if h else ""
    return {"ticker": t, "name": _name(t), "reviewed": rv["ts"][:10] if rv else None, "edges": rows, "types": TYPES, "strengths": STRENGTHS}


def linked_holdings(ticker: str, held: list[str]) -> list[dict]:
    """Kopplingar mellan ticker och bolag man redan äger: relationer och statistiska samband."""
    t = _clean(ticker)
    held = [h for h in {_clean(x) for x in held} if h and h != t]
    out = []
    if not held:
        return out
    with db.connect() as con:
        q = ",".join("?" * len(held))
        rows = con.execute(f"SELECT * FROM relations WHERE (a=? AND b IN ({q})) OR (b=? AND a IN ({q}))", [t, *held, t, *held]).fetchall()
    for r in rows:
        other = r["b"] if r["a"] == t else r["a"]
        verb = TYPES[r["rtype"]]
        out.append({"ticker": other, "name": _name(other), "kind": "relation",
                    "text": f"{r['a']} {verb} {r['b']}" + (f" ({r['share_pct']:g} % av omsättningen)" if r["share_pct"] is not None else "")})
    if len(_frame()["res"].columns) >= 3:
        for x in leadlag()["sig"]:
            other = x["b"] if x["a"] == t else x["a"] if x["b"] == t else None
            if other in held and x["stable"]:
                out.append({"ticker": other, "name": _name(other), "kind": "stat", "text": f"statistiskt lead-lag ({x['a']} → {x['b']}, {x['lag']} dag{'ar' if x['lag'] > 1 else ''}, r={x['r']:.2f})"})
    return out
