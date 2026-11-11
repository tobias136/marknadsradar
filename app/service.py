"""Affärslogik: listor, översikter, aktiedetaljer och rapportsammanställningar."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db, digest, metrics, signals
from .providers import get_provider

SECTOR_SV = {
    "Technology": "Teknologi", "Healthcare": "Hälsovård", "Financial Services": "Finans",
    "Consumer Cyclical": "Sällanköp", "Consumer Defensive": "Dagligvaror", "Energy": "Energi",
    "Industrials": "Industri", "Basic Materials": "Material", "Real Estate": "Fastigheter",
    "Utilities": "Kraftbolag", "Communication Services": "Kommunikation",
}
NO_FUNDAMENTALS = {"ETF", "INDEX", "MUTUALFUND", "CURRENCY", "CRYPTOCURRENCY", "FUTURE"}
FUND_MAX_AGE_H = 24


# ---------------------------------------------------------------- fundamenta
def fund_get(ticker: str) -> dict | None:
    with db.connect() as con:
        row = con.execute("SELECT fetched_at, data FROM fundamentals WHERE ticker=?", (ticker,)).fetchone()
    if not row or not row["data"]:
        return None
    d = json.loads(row["data"])
    d["fetched_at"] = row["fetched_at"]
    return d


def fund_age_hours(ticker: str) -> float | None:
    with db.connect() as con:
        row = con.execute("SELECT fetched_at FROM fundamentals WHERE ticker=?", (ticker,)).fetchone()
    if not row or not row["fetched_at"]:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])).total_seconds() / 3600


def ensure_fundamentals(ticker: str, force: bool = False) -> tuple[dict | None, str | None]:
    """Hämtar fundamenta om de saknas eller är äldre än 24 h. Returnerar (data, fel)."""
    age = fund_age_hours(ticker)
    if not force and age is not None and age < FUND_MAX_AGE_H:
        return fund_get(ticker), None
    try:
        data = get_provider().fundamentals(ticker)
        with db.connect() as con:
            con.execute(
                "INSERT INTO fundamentals(ticker, fetched_at, data) VALUES(?,?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET fetched_at=excluded.fetched_at, data=excluded.data",
                (ticker, datetime.now(timezone.utc).isoformat(), json.dumps(data)),
            )
        return fund_get(ticker), None
    except Exception as e:  # noqa: BLE001
        return fund_get(ticker), str(e)[:200]


# -------------------------------------------------------------------- listor
def get_list(lid: int) -> dict | None:
    with db.connect() as con:
        lst = con.execute("SELECT * FROM lists WHERE id=?", (lid,)).fetchone()
        if not lst:
            return None
        items = con.execute(
            "SELECT ticker, grp, label, auto_group FROM list_items WHERE list_id=? ORDER BY position, rowid",
            (lid,),
        ).fetchall()
    d = dict(lst)
    d["items"] = [dict(i) for i in items]
    return d


def lists_all() -> list[dict]:
    with db.connect() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM lists ORDER BY position, id").fetchall()]
    return [get_list(i) for i in ids]


def all_tickers() -> list[str]:
    with db.connect() as con:
        t = {r["ticker"] for r in con.execute("SELECT DISTINCT ticker FROM list_items").fetchall()}
        t |= {r["benchmark"] for r in con.execute("SELECT benchmark FROM lists WHERE benchmark != ''").fetchall()}
    return sorted(t)


def set_auto_group_from_info(ticker: str) -> None:
    fund = fund_get(ticker)
    if not fund:
        return
    info = fund.get("info", {})
    sector = info.get("sector")
    if sector:
        grp = SECTOR_SV.get(sector, sector)
    elif info.get("quoteType") in NO_FUNDAMENTALS:
        grp = "ETF/Index"
    else:
        return
    with db.connect() as con:
        con.execute("UPDATE list_items SET grp=? WHERE ticker=? AND auto_group=1", (grp, ticker))


# ------------------------------------------------------------------ rader
def _derived(info: dict, last: float | None) -> dict:
    dy = None
    if info.get("dividendRate") and last:
        dy = info["dividendRate"] / last * 100
    return {"div_yield": dy}


def ticker_row(ticker: str, group: str = "", label: str = "", bench_df=None) -> dict:
    df = metrics.price_df(ticker)
    m = metrics.compute(df)
    fund = fund_get(ticker)
    info = (fund or {}).get("info", {})
    row = {
        "ticker": ticker,
        "group": group or "Övrigt",
        "name": label or info.get("shortName") or info.get("longName") or ticker,
        "full_name": info.get("shortName") or info.get("longName") or "",
        "currency": info.get("currency", ""),
        "quote_type": info.get("quoteType", ""),
        "missing": m is None,
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "next_earnings": (fund or {}).get("next_earnings"),
    }
    if m:
        row.update(m)
        row.update(_derived(info, m["last"]))
        row.update(metrics.rs_features(df, bench_df))
    dg = digest.build(fund)
    dm = dg["metrics"]
    row["has_q"] = dg["has_data"]
    row["rev_yoy"] = dm.get("revenue_yoy")
    om, op = dm.get("operating_margin"), dm.get("operating_margin_prev_year")
    row["opm_delta"] = om - op if om is not None and op is not None else None
    row["beats"] = dg["beats"]["beat"] if dg.get("beats") else None
    row["beats_of"] = dg["beats"]["of"] if dg.get("beats") else None
    return row


def _val_percentiles(rows: list[dict]) -> None:
    """Hur dyr är bolaget jämfört med de andra i samma grupp (eller listan)?
    val_pct = andel jämförelsebolag (exkl. sig själv) med lägre P/E."""
    def pe(r):
        v = r.get("forward_pe") or r.get("pe")
        return v if v and v > 0 and not r.get("missing") else None

    def rank(r, peers):
        mine = pe(r)
        others = [pe(p) for p in peers if p is not r and pe(p) is not None]
        return 100 * sum(1 for o in others if o < mine) / len(others), len(others)

    for r in rows:
        r["val_pct"], r["val_basis"] = None, None
        if pe(r) is None:
            continue
        grp = [p for p in rows if p["group"] == r["group"]]
        if sum(1 for p in grp if pe(p)) >= 4:
            r["val_pct"], _ = rank(r, grp)
            r["val_basis"] = f"gruppen {r['group']}"
        elif sum(1 for p in rows if pe(p)) >= 5:
            r["val_pct"], _ = rank(r, rows)
            r["val_basis"] = "listan"


def _attach_signals(rows: list[dict], bm: dict | None) -> None:
    _val_percentiles(rows)
    for r in rows:
        sig = signals.assess(r)
        r["signal"] = sig
        r["sigscore"] = sig["score"] if sig else None
        r["siglabel"] = sig["label"] if sig else None
        r["sigkey"] = sig["key"] if sig else None


def overview(lid: int) -> dict | None:
    lst = get_list(lid)
    if not lst:
        return None
    bench_df = metrics.price_df(lst["benchmark"]) if lst["benchmark"] else None
    rows = [ticker_row(i["ticker"], i["grp"], i["label"], bench_df) for i in lst["items"]]
    bench = None
    bm = None
    if lst["benchmark"]:
        bm = metrics.compute(bench_df)
        bench = {"ticker": lst["benchmark"], "missing": bm is None}
        if bm:
            bench.update({k: bm.get(k) for k in metrics.RET_KEYS + ["last", "last_date", "rsi14", "vs_sma50", "vs_sma200"]})

    def rel(a, b):
        return None if a is None or b is None else a - b

    for r in rows:
        r["rs_1m"] = rel(r.get("r_1m"), bm.get("r_1m")) if bm and not r["missing"] else None
        r["rs_3m"] = rel(r.get("r_3m"), bm.get("r_3m")) if bm and not r["missing"] else None
    _attach_signals(rows, bm)
    present = [r for r in rows if not r["missing"]]
    groups = metrics.aggregate_groups(present)
    if bm:
        for g in groups:
            g["rs_1m"] = rel(g.get("r_1m"), bm.get("r_1m"))
            g["rs_3m"] = rel(g.get("r_3m"), bm.get("r_3m"))
    updated = max((r["last_date"] for r in present), default=None)
    return metrics.clean({
        "list": {k: lst[k] for k in ("id", "name", "benchmark", "description")},
        "updated": updated, "benchmark": bench, "groups": groups, "tickers": rows,
        "breadth": metrics.breadth(present),
        "signal_summary": _signal_summary(present),
        "missing": [r["ticker"] for r in rows if r["missing"]],
    })


def _signal_summary(rows: list[dict]) -> dict:
    s = {"strong_pos": 0, "pos": 0, "neutral": 0, "neg": 0, "strong_neg": 0, "nodata": 0}
    for r in rows:
        s[r.get("sigkey") or "nodata"] += 1
    s["positive"] = s["strong_pos"] + s["pos"]
    s["negative"] = s["neg"] + s["strong_neg"]
    return s


def reports(lid: int) -> dict | None:
    lst = get_list(lid)
    if not lst:
        return None
    out = []
    for i in lst["items"]:
        t = i["ticker"]
        fund = fund_get(t)
        info = (fund or {}).get("info", {})
        dg = digest.build(fund)
        m = dg["metrics"]
        sp = dg["surprise"] or {}
        out.append({
            "ticker": t, "group": i["grp"],
            "name": i["label"] or info.get("shortName") or t,
            "currency": info.get("currency", ""), "has_data": dg["has_data"],
            "quarter": m.get("quarter"), "revenue": m.get("revenue"), "revenue_yoy": m.get("revenue_yoy"),
            "operating_margin": m.get("operating_margin"),
            "operating_margin_prev_year": m.get("operating_margin_prev_year"),
            "net_income": m.get("net_income"), "net_income_yoy": m.get("net_income_yoy"),
            "eps": m.get("eps"), "surprise_pct": sp.get("surprise_pct"),
            "next_earnings": dg["next_earnings"], "headline": dg["headline"], "flags": dg["flags"],
            "fund_missing": fund is None,
        })
    return metrics.clean({"list": {"id": lst["id"], "name": lst["name"]}, "reports": out})


def signal_for(sym: str) -> tuple[dict | None, str | None]:
    """Signalbetyget för en ticker, räknat i samband med första listan den ligger i
    (för jämförelsebolag och index). Returnerar (signal, listnamn)."""
    sig, first = None, None
    with db.connect() as con:
        r0 = con.execute("SELECT list_id FROM list_items WHERE ticker=? ORDER BY list_id LIMIT 1", (sym,)).fetchone()
    if r0:
        ov = overview(r0["list_id"])
        first = ov["list"]["name"] if ov else None
        row = next((t for t in (ov or {}).get("tickers", []) if t["ticker"] == sym), None)
        sig = row.get("signal") if row else None
    else:
        row = ticker_row(sym)
        _attach_signals([row], None)
        sig = row.get("signal")
    return sig, first


def ticker_detail(sym: str) -> dict:
    sym = sym.upper()
    m = metrics.compute(metrics.price_df(sym))
    fund, err = ensure_fundamentals(sym)
    info = (fund or {}).get("info", {})
    cur = info.get("currency", "")
    with db.connect() as con:
        note = con.execute("SELECT text, updated_at FROM notes WHERE ticker=?", (sym,)).fetchone()
        lists = [r["name"] for r in con.execute(
            "SELECT l.name FROM lists l JOIN list_items i ON i.list_id=l.id WHERE i.ticker=? ORDER BY l.position, l.id",
            (sym,)).fetchall()]
    if m:
        m = {k: v for k, v in m.items() if k != "spark"}
        m.update(_derived(info, m["last"]))
    sig, first = signal_for(sym)
    return metrics.clean({
        "signal": sig, "signal_basis": first,
        "ticker": sym, "name": info.get("shortName") or info.get("longName") or sym,
        "info": info, "currency": cur, "metrics": m,
        "quarters": (fund or {}).get("quarters", []), "earnings": (fund or {}).get("earnings", []),
        "digest": digest.build(fund, cur), "fund_error": err,
        "note": {"text": note["text"], "updated_at": note["updated_at"]} if note else {"text": "", "updated_at": None},
        "lists": lists,
    })


def upcoming_earnings(days: int = 45) -> list[dict]:
    today = datetime.now().date()
    horizon = today + timedelta(days=days)
    out = []
    for t in all_tickers():
        f = fund_get(t)
        ne = (f or {}).get("next_earnings")
        if not ne:
            continue
        try:
            d = datetime.strptime(ne, "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= d <= horizon:
            out.append({"ticker": t, "date": ne, "name": f["info"].get("shortName", t)})
    return sorted(out, key=lambda x: x["date"])
