"""Beslutsjournal: skriv ner VARFÖR du köper/säljer/avvaktar medan du fortfarande inte vet
utgången, och granska sedan. Det är det enda sättet att lära sig något av sina beslut i
stället för att minnas dem i efterhand (efterklokhet)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import db, metrics, service

ACTIONS = {"buy": 1, "add": 1, "sell": -1, "trim": -1, "hold": 0, "watch": 0}
OUTCOMES = ("as_planned", "not_as_planned", "unclear")


def _last_price(sym: str):
    df = metrics.price_df(sym)
    if df is None or len(df) == 0:
        return None
    return float(df["close"].iloc[-1])


def _currency(sym: str) -> str:
    f = service.fund_get(sym) or {}
    return (f.get("info") or {}).get("currency", "") or ""


def create(ticker: str, action: str, thesis: str, invalidation: str, horizon_days: int) -> dict:
    sym = ticker.strip().upper()
    if not sym:
        raise ValueError("Ticker saknas")
    if action not in ACTIONS:
        raise ValueError("Okänd typ av beslut")
    horizon_days = max(7, min(int(horizon_days or 90), 1825))
    sig, _ = service.signal_for(sym)
    now = datetime.now().astimezone()
    review = (date.today() + timedelta(days=horizon_days)).isoformat()
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO journal(ticker, created, action, price, currency, signal_score, signal_label, thesis, invalidation, "
            "horizon_days, review_on) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (sym, now.isoformat(timespec="seconds"), action, _last_price(sym), _currency(sym),
             (sig or {}).get("score"), (sig or {}).get("label") or "", thesis.strip(), invalidation.strip(), horizon_days, review))
        new_id = cur.lastrowid
    return {"id": new_id}


def _dir_return(action: str, p0, p1):
    if not p0 or p1 is None:
        return None
    r = (p1 / p0 - 1) * 100
    d = ACTIONS.get(action, 0)
    return r * d if d else r


def _entry(row, cache: dict) -> dict:
    e = dict(row)
    sym = e["ticker"]
    if sym not in cache:
        cache[sym] = _last_price(sym)
    now_p = cache[sym]
    end_p = e["closed_price"] if e["status"] == "reviewed" else now_p
    e["price_now"] = now_p
    e["ret_since"] = None if not e["price"] or end_p is None else (end_p / e["price"] - 1) * 100
    e["dir_return"] = _dir_return(e["action"], e["price"], end_p)
    e["due"] = e["status"] == "open" and bool(e["review_on"]) and e["review_on"] <= date.today().isoformat()
    try:
        e["days_open"] = (date.today() - datetime.fromisoformat(e["created"]).date()).days
    except ValueError:
        e["days_open"] = None
    return e


def list_entries() -> dict:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM journal ORDER BY created DESC, id DESC").fetchall()
    cache: dict = {}
    entries = [_entry(r, cache) for r in rows]
    return {"entries": entries, "stats": stats(entries)}


def review(jid: int, outcome: str, lesson: str) -> None:
    if outcome not in OUTCOMES:
        raise ValueError("Okänt utfall")
    with db.connect() as con:
        row = con.execute("SELECT ticker, status FROM journal WHERE id=?", (jid,)).fetchone()
    if not row:
        raise LookupError("Beslutet finns inte")
    sym = row["ticker"]
    sig, _ = service.signal_for(sym)
    with db.connect() as con:
        con.execute(
            "UPDATE journal SET status='reviewed', outcome=?, lesson=?, closed_price=?, closed_on=?, closed_signal=? WHERE id=?",
            (outcome, lesson.strip(), _last_price(sym), date.today().isoformat(), (sig or {}).get("score"), jid))


def delete(jid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM journal WHERE id=?", (jid,))


def stats(entries: list[dict]) -> dict:
    rev = [e for e in entries if e["status"] == "reviewed"]
    acted = [e for e in rev if ACTIONS.get(e["action"], 0) != 0 and e["dir_return"] is not None]
    out = {
        "total": len(entries), "open": sum(1 for e in entries if e["status"] == "open"), "reviewed": len(rev),
        "due": sum(1 for e in entries if e["due"]),
        "with_invalidation": sum(1 for e in entries if len(e["invalidation"].strip()) >= 10),
        "with_thesis": sum(1 for e in entries if len(e["thesis"].strip()) >= 30),
        "as_planned": sum(1 for e in rev if e["outcome"] == "as_planned"),
        "n_acted": len(acted),
        "hit_rate": (100 * sum(1 for e in acted if e["dir_return"] > 0) / len(acted)) if acted else None,
        "avg_dir_return": (sum(e["dir_return"] for e in acted) / len(acted)) if acted else None,
        "enough": len(acted) >= 20,
    }
    follow = {"with": [], "against": []}
    for e in acted:
        s = e["signal_score"]
        if s is None:
            continue
        d = ACTIONS[e["action"]]
        if (d > 0 and s >= 20) or (d < 0 and s <= -20):
            follow["with"].append(e["dir_return"])
        elif (d > 0 and s <= -20) or (d < 0 and s >= 20):
            follow["against"].append(e["dir_return"])
    out["follow"] = {k: {"n": len(v), "avg": (sum(v) / len(v)) if v else None,
                         "hit": (100 * sum(1 for x in v if x > 0) / len(v)) if v else None} for k, v in follow.items()}
    return out
