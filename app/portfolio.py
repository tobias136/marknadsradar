"""Portfölj: innehav (manuellt eller via CSV-import), värde i kronor, vikter, koncentration,
korrelation, risk och varningar. Allt är beskrivande: inga köp- eller säljråd."""
from __future__ import annotations

import csv
import io
import math
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import db, metrics, service

SUFFIX_CUR = {".ST": "SEK", ".OL": "NOK", ".CO": "DKK", ".HE": "EUR", ".DE": "EUR", ".PA": "EUR", ".AS": "EUR", ".L": "GBp"}
DEFAULT_BENCH = ("^GSPC", "SPY")


# ----------------------------------------------------------------- lagring
def list_holdings() -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM holdings ORDER BY id").fetchall()]


def _price_cur(h: dict) -> str:
    t = h.get("ticker") or ""
    info = ((service.fund_get(t) or {}).get("info") or {}) if t else {}
    cur = info.get("currency") or ""
    if not cur:
        for suf, c in SUFFIX_CUR.items():
            if t.upper().endswith(suf):
                cur = c
                break
    return cur or h.get("currency") or ("USD" if t else "")


def aux_tickers() -> list[str]:
    """Tickers som måste hämtas för portföljen: innehaven själva och valutakurser mot SEK."""
    out: list[str] = []
    cur: set[str] = {"USD", "EUR"}
    for h in list_holdings():
        if h["ticker"]:
            out.append(h["ticker"])
            cur.add(_price_cur(h))
        if h["currency"]:
            cur.add(h["currency"])
    for c in sorted(cur):
        c = "GBP" if c == "GBp" else c
        if c and c != "SEK":
            out.append(f"{c}SEK=X")
    return list(dict.fromkeys(out))


def add_holding(ticker: str, qty: float, avg_cost: float | None, currency: str = "", name: str = "", account: str = "") -> int:
    if qty is None or qty <= 0:
        raise ValueError("Antal måste vara större än 0")
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO holdings(ticker,name,qty,avg_cost,currency,account,source,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (ticker.strip().upper(), name.strip(), qty, avg_cost, currency.strip(), account.strip(), "manual",
             datetime.now(timezone.utc).isoformat()))
        return cur.lastrowid


def update_holding(hid: int, fields: dict) -> None:
    allowed = {"ticker", "name", "qty", "avg_cost", "currency", "account"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            vals.append(v.strip().upper() if k == "ticker" else v)
    if not sets:
        return
    with db.connect() as con:
        con.execute(f"UPDATE holdings SET {', '.join(sets)}, updated_at=? WHERE id=?",
                    vals + [datetime.now(timezone.utc).isoformat(), hid])


def delete_holding(hid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM holdings WHERE id=?", (hid,))


def suggest(name: str) -> list[dict]:
    """Föreslår tickers från dina bevakningslistor vars namn liknar värdepappersnamnet. Förslag, inget facit."""
    words = [w for w in re.split(r"[^a-zåäö0-9]+", name.lower()) if len(w) >= 3 and w not in {"ab", "inc", "corp", "class", "ser"}]
    if not words:
        return []
    out = []
    with db.connect() as con:
        rows = con.execute("SELECT DISTINCT ticker, label FROM list_items").fetchall()
    for r in rows:
        f = service.fund_get(r["ticker"]) or {}
        text = f"{r['ticker']} {r['label']} {(f.get('info') or {}).get('shortName', '')} {(f.get('info') or {}).get('longName', '')}".lower()
        hits = sum(1 for w in words if w in text)
        if hits:
            out.append({"ticker": r["ticker"], "label": r["label"] or (f.get("info") or {}).get("shortName", ""), "score": hits})
    return sorted(out, key=lambda x: -x["score"])[:5]


# ---------------------------------------------------------------- CSV-import
def _num(s) -> float | None:
    if s is None:
        return None
    t = str(s).replace("−", "-").replace("\xa0", "").replace(" ", "").strip()
    if not t or t == "-":
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_csv(text: str) -> dict:
    """Tolerant parser för Avanzas transaktionsexport (semikolonseparerad, decimalkomma) och liknande filer.
    Läser Köp/Sälj och räknar fram nuvarande antal och genomsnittligt inköpspris (snittkostnadsmetoden).
    Courtage räknas inte in. Utdelningar, insättningar och uttag ignoreras."""
    text = text.lstrip("﻿")
    head = text.splitlines()[0] if text.strip() else ""
    delim = max(";,\t", key=head.count) if head else ";"
    rdr = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in rdr if any(c.strip() for c in r)]
    if len(rows) < 2:
        return {"error": "Filen verkar tom eller saknar rader.", "holdings": [], "stats": {}}
    hdr = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(hdr):
                if h == n or h.startswith(n):
                    return i
        return None

    c_date = col("datum")
    c_type = col("typ av transaktion", "transaktionstyp", "typ")
    c_name = col("värdepapper/beskrivning", "värdepapper", "beskrivning", "namn")
    c_qty = col("antal")
    c_price = col("kurs", "pris")
    c_cur = col("instrumentvaluta", "transaktionsvaluta", "valuta")
    c_isin = col("isin")
    c_acct = col("konto")
    missing = [n for n, c in (("Typ av transaktion", c_type), ("Värdepapper/beskrivning", c_name), ("Antal", c_qty), ("Kurs", c_price)) if c is None]
    if missing:
        return {"error": "Hittar inte kolumnerna: " + ", ".join(missing) + ". Kontrollera att det är en transaktionsexport med rubrikrad.",
                "holdings": [], "stats": {"columns": rows[0]}}

    def get(r, c):
        return r[c].strip() if c is not None and c < len(r) else ""

    body = rows[1:]
    if c_date is not None:
        body.sort(key=lambda r: get(r, c_date))
    pos: dict[str, dict] = {}
    seen_types: dict[str, int] = {}
    used = 0
    for r in body:
        typ = get(r, c_type).lower()
        seen_types[typ or "(tom)"] = seen_types.get(typ or "(tom)", 0) + 1
        kind = "buy" if typ.startswith("köp") else "sell" if typ.startswith("sälj") else None
        if not kind:
            continue
        q, p = _num(get(r, c_qty)), _num(get(r, c_price))
        if not q:
            continue
        q = abs(q)
        key = get(r, c_isin) or get(r, c_name)
        if not key:
            continue
        h = pos.setdefault(key, {"name": get(r, c_name), "isin": get(r, c_isin), "qty": 0.0, "avg_cost": 0.0,
                                 "currency": get(r, c_cur), "account": get(r, c_acct)})
        used += 1
        if kind == "buy":
            tot = h["qty"] + q
            h["avg_cost"] = ((h["qty"] * h["avg_cost"]) + q * (p or 0)) / tot if tot else 0.0
            h["qty"] = tot
        else:
            h["qty"] = max(0.0, h["qty"] - q)
    holdings = [dict(h, qty=round(h["qty"], 6), avg_cost=round(h["avg_cost"], 4)) for h in pos.values() if h["qty"] > 1e-9]
    for h in holdings:
        h["suggestions"] = suggest(h["name"])
    return {"holdings": holdings, "stats": {"rows": len(body), "trades_used": used, "types": seen_types,
                                            "note": "Courtage, utdelningar och valutaeffekter ingår inte i snittpriset."}}


def apply_import(text: str) -> dict:
    res = parse_csv(text)
    if res.get("error"):
        return res
    with db.connect() as con:
        old = {(r["isin"] or r["name"]): r["ticker"] for r in con.execute("SELECT isin,name,ticker FROM holdings WHERE source='import'").fetchall()}
        con.execute("DELETE FROM holdings WHERE source='import'")
        now = datetime.now(timezone.utc).isoformat()
        for h in res["holdings"]:
            tk = old.get(h["isin"] or h["name"], "")
            if not tk and h["suggestions"] and h["suggestions"][0]["score"] >= 2:
                tk = ""   # förslag används aldrig automatiskt – användaren bekräftar
            con.execute("INSERT INTO holdings(ticker,name,isin,qty,avg_cost,currency,account,source,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (tk, h["name"], h["isin"], h["qty"], h["avg_cost"], h["currency"], h["account"], "import", now))
    return {"imported": len(res["holdings"]), "stats": res["stats"]}


# ------------------------------------------------------------------- analys
def _fx(cur: str) -> float | None:
    if not cur or cur == "SEK":
        return 1.0
    if cur == "GBp":
        v = _fx("GBP")
        return None if v is None else v / 100
    df = metrics.price_df(f"{cur}SEK=X")
    return None if df is None or df.empty else float(df["close"].iloc[-1])


def _bench() -> pd.Series | None:
    for t in DEFAULT_BENCH:
        df = metrics.price_df(t)
        if df is not None and len(df) > 150:
            return df["close"].pct_change()
    return None


def summary() -> dict:
    hs = list_holdings()
    out: dict = {"holdings": [], "totals": {}, "risk": None, "warnings": [], "sectors": [], "currencies": [], "pairs": []}
    if not hs:
        return out
    rets: dict[str, pd.Series] = {}
    rows = []
    for h in hs:
        row = dict(h)
        row.update(last=None, price_cur=None, fx=None, value_sek=None, pl_pct=None, weight=None, sector=None,
                   signal=None, status="unmapped" if not h["ticker"] else "ok")
        t = h["ticker"]
        if t:
            df = metrics.price_df(t)
            if df is None or df.empty:
                row["status"] = "nodata"
            else:
                pc = _price_cur(h)
                fx = _fx(pc)
                last = float(df["close"].iloc[-1])
                row.update(last=last, price_cur=pc, fx=fx, last_date=df.index[-1].strftime("%Y-%m-%d"))
                if fx is not None:
                    row["value_sek"] = h["qty"] * last * fx
                else:
                    row["status"] = "nofx"
                if h["avg_cost"]:
                    ac = h["avg_cost"]
                    if h["currency"] and h["currency"] != pc:
                        a, b = _fx(h["currency"]), fx
                        ac = ac * a / b if a and b else None
                    row["pl_pct"] = None if not ac else (last / ac - 1) * 100
                f = service.fund_get(t) or {}
                info = f.get("info") or {}
                qt = info.get("quoteType", "")
                row["sector"] = service.SECTOR_SV.get(info.get("sector", ""), info.get("sector") or ("Fond/ETF" if qt in ("ETF", "MUTUALFUND") else "Okänd"))
                row["name"] = h["name"] or info.get("shortName") or t
                rets[t] = df["close"].pct_change()
                try:
                    r = service.ticker_row(t)
                    service._attach_signals([r], None)
                    sg = r.get("signal") or {}
                    row["signal"] = {"score": sg.get("score"), "label": sg.get("label"), "key": sg.get("key")}
                    row["stop"], row["atr_pct"] = r.get("stop"), r.get("atr_pct")
                except Exception:  # noqa: BLE001
                    pass
        rows.append(row)

    valued = [r for r in rows if r["value_sek"]]
    total = sum(r["value_sek"] for r in valued)
    for r in rows:
        r["weight"] = (r["value_sek"] / total * 100) if total and r["value_sek"] else None
    rows.sort(key=lambda r: -(r["value_sek"] or 0))
    out["holdings"] = rows
    out["totals"] = {"value_sek": total, "n": len(rows), "n_valued": len(valued),
                     "n_unmapped": sum(1 for r in rows if r["status"] == "unmapped"),
                     "n_nodata": sum(1 for r in rows if r["status"] in ("nodata", "nofx"))}
    if not valued:
        return out

    w = np.array([r["weight"] / 100 for r in valued])
    hhi = float((w ** 2).sum())
    out["concentration"] = {"top1": float(w.max() * 100), "top3": float(np.sort(w)[::-1][:3].sum() * 100),
                            "hhi": hhi, "effective_n": 1 / hhi if hhi else None}
    sec: dict[str, float] = {}
    cur: dict[str, float] = {}
    for r in valued:
        sec[r["sector"] or "Okänd"] = sec.get(r["sector"] or "Okänd", 0) + r["weight"]
        c = r["price_cur"] or "?"
        cur[c] = cur.get(c, 0) + r["weight"]
    out["sectors"] = sorted(({"name": k, "weight": v} for k, v in sec.items()), key=lambda x: -x["weight"])
    out["currencies"] = sorted(({"name": k, "weight": v} for k, v in cur.items()), key=lambda x: -x["weight"])

    # risk: dagsavkastning i respektive handelsvaluta, konstanta vikter, senaste ~120 respektive 252 dagar
    tick = [r["ticker"] for r in valued if r["ticker"] in rets]
    if len(tick) >= 1:
        R = pd.concat({t: rets[t] for t in tick}, axis=1).dropna(how="all").tail(252).fillna(0.0)
        if len(R) >= 60:
            ww = pd.Series({r["ticker"]: r["weight"] / 100 for r in valued if r["ticker"] in rets})
            ww = ww / ww.sum()
            R120 = R.tail(120)
            port = (R * ww).sum(axis=1)
            vol_p = float(((R120 * ww).sum(axis=1)).std() * math.sqrt(252) * 100)
            vols = R120.std() * math.sqrt(252) * 100
            wavg = float((vols * ww).sum())
            eq = (1 + port).cumprod()
            risk = {"vol": vol_p, "wavg_vol": wavg, "diversification": (wavg / vol_p) if vol_p else None,
                    "max_dd_1y": _dd(eq), "days": int(len(R)), "beta": None}
            b = _bench()
            if b is not None:
                j = pd.concat([port, b], axis=1, join="inner").dropna().tail(252)
                if len(j) > 60 and j.iloc[:, 1].var() > 0:
                    risk["beta"] = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var())
            out["risk"] = risk
            if len(tick) >= 2:
                C = R120.corr()
                pairs = []
                for i, a in enumerate(C.columns):
                    for bcol in C.columns[i + 1:]:
                        v = C.loc[a, bcol]
                        if not math.isnan(v):
                            pairs.append({"a": a, "b": bcol, "corr": float(v)})
                out["pairs"] = sorted(pairs, key=lambda p: -p["corr"])[:6]
                out["corr_avg"] = float(np.mean([p["corr"] for p in pairs])) if pairs else None
    out["warnings"] = _warnings(out, valued)
    return out


def _s(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace(".", ",").replace("-", "\u2212")


def _dd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min() * 100)


def _warnings(o: dict, valued: list[dict]) -> list[dict]:
    W = []

    def add(level, text, code):
        W.append({"level": level, "text": text, "code": code})

    c = o["concentration"]
    n = len(valued)
    for r in valued:
        if r["weight"] >= 25 and n >= 3:
            add("high", f"{r['ticker']} är {r['weight']:.0f} % av portföljen. Går just det bolaget fel får det stor effekt på helheten.", "pos25")
    if c["top3"] >= 65 and n >= 5:
        add("medium", f"De tre största innehaven är {c['top3']:.0f} % av portföljen.", "top3")
    if c["effective_n"] and c["effective_n"] < 4 and n >= 3:
        add("medium", f"Du har {n} innehav men fungerar som ca {_s(c['effective_n'])} lika stora (effektivt antal). Spridningen är mindre än den ser ut.", "effn")
    for s in o["sectors"]:
        if s["weight"] >= 45 and s["name"] not in ("Fond/ETF",) and len(o["sectors"]) > 1:
            add("medium", f"{s['weight']:.0f} % ligger i sektorn {s['name']}. Sektorn avgör mycket av hur portföljen mår.", "sector")
    for cc in o["currencies"]:
        if cc["name"] not in ("SEK", "?") and cc["weight"] >= 70:
            add("info", f"{cc['weight']:.0f} % i {cc['name']}. Kronans kurs påverkar värdet i kronor.", "currency")
    for p in o.get("pairs", []):
        if p["corr"] >= 0.8:
            add("medium", f"{p['a']} och {p['b']} rör sig nästan likadant (korrelation {p['corr']:.2f}). De ger mindre spridning än två separata bolag.", "corr")
            break
    for r in valued:
        s = (r.get("signal") or {}).get("score")
        if s is not None and s <= -20 and r["weight"] >= 10:
            add("info", f"{r['ticker']} ({r['weight']:.0f} %) har negativt signalbetyg ({_s(s, 0)}). Betyget är regelbaserat och ingen rådgivning, men värt att granska tesen.", "negsig")
    if not W:
        add("ok", "Inga uppenbara koncentrationsvarningar enligt de enkla reglerna.", "none")
    return W


def game_flags() -> dict:
    """Små mått som spelläget använder."""
    s = summary()
    t = s.get("totals", {})
    warn = {w["code"] for w in s.get("warnings", []) if w["level"] in ("high", "medium")}
    c = s.get("concentration") or {}
    return {"n": t.get("n_valued", 0), "top1": c.get("top1"), "effective_n": c.get("effective_n"),
            "no_big_warning": bool(t.get("n_valued", 0)) and not warn}
