"""Övningsportfölj (pappershandel): virtuella pengar, riktiga kurser, krav på plan innan varje köp.

Syftet är att öva PROCESS: tes, stopp, positionsstorlek och granskning. Poäng räknas på processen,
inte på vinsten. Köp sker till senaste stängningskurs. Stopp tillämpas automatiskt när kurserna
uppdateras (utlöses på dagens lägsta kurs, vid gap fylls du till öppningskursen).
Courtage antas vara 0,1 % per affär. Pappershandel saknar känslorna, och det är det svåra med riktiga pengar."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import db, exercises, indicators, metrics, portfolio, service

COST = 0.001
MAX_RISK_OK = 2.0     # % av portföljen per affär
MAX_POS_OK = 25.0     # % av portföljen per position
REASONS = {"target": "Målet nåddes", "thesis": "Tesen höll inte", "time": "Tiden gick ut", "other": "Annat skäl"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------- valuta och kurs
def _fx_now(cur: str) -> float:
    v = portfolio._fx(cur)
    return 1.0 if v is None else v


def _fx_on(cur: str, d: str) -> float:
    if not cur or cur == "SEK":
        return 1.0
    base = "GBP" if cur == "GBp" else cur
    df = metrics.price_df(f"{base}SEK=X")
    if df is None or df.empty:
        return _fx_now(cur)
    s = df["close"][df.index <= pd.Timestamp(d)]
    v = float(s.iloc[-1]) if len(s) else float(df["close"].iloc[0])
    return v / 100 if cur == "GBp" else v


def _cur(t: str) -> str:
    return portfolio._price_cur({"ticker": t})


def quote(ticker: str) -> dict:
    t = ticker.strip().upper()
    df = exercises.load(t)
    if df is None or len(df) < 2:
        raise ValueError(f"Kursdata saknas för {t}. Lägg in tickern i en lista och tryck Uppdatera först.")
    cur = _cur(t)
    atr = float(indicators.atr(df["high"], df["low"], df["close"]).iloc[-1])
    last = float(df["close"].iloc[-1])
    sig = None
    try:
        s, _ = service.signal_for(t)
        sig = {"score": s.get("score"), "label": s.get("label")} if s else None
    except Exception:  # noqa: BLE001
        sig = None
    return {"ticker": t, "name": exercises._name(t), "price": last, "currency": cur, "fx": _fx_now(cur),
            "last_date": df.index[-1].strftime("%Y-%m-%d"), "atr": atr, "atr_pct": atr / last * 100, "signal": sig}


def aux_tickers() -> list[str]:
    out, cur = [], set()
    with db.connect() as con:
        rows = con.execute("SELECT DISTINCT ticker FROM paper_trades WHERE status='open'").fetchall()
    for r in rows:
        out.append(r["ticker"])
        c = _cur(r["ticker"])
        if c and c != "SEK":
            cur.add("GBP" if c == "GBp" else c)
    out += [f"{c}SEK=X" for c in sorted(cur)]
    return out


# --------------------------------------------------------------- portföljer
def create_portfolio(name: str, strategy: str, cash0: float) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Ge portföljen ett namn")
    if cash0 < 1000:
        raise ValueError("Startkapitalet måste vara minst 1 000 kr")
    try:
        with db.connect() as con:
            cur = con.execute("INSERT INTO paper_portfolios(name, strategy, cash0, created) VALUES(?,?,?,?)",
                              (name, strategy.strip(), float(cash0), date.today().isoformat()))
            return cur.lastrowid
    except Exception as e:  # noqa: BLE001
        raise ValueError("Det finns redan en övningsportfölj med det namnet") from e


def delete_portfolio(pid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM paper_trades WHERE pid=?", (pid,))
        con.execute("DELETE FROM paper_portfolios WHERE id=?", (pid,))


def _trades(pid: int) -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM paper_trades WHERE pid=? ORDER BY id", (pid,)).fetchall()]


def _port(pid: int) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM paper_portfolios WHERE id=?", (pid,)).fetchone()
    if not r:
        raise LookupError("Portföljen finns inte")
    return dict(r)


def _cash(p: dict, trades: list[dict]) -> float:
    c = p["cash0"]
    for t in trades:
        c -= t["qty"] * t["entry_price"] * t["entry_fx"] * (1 + COST)
        if t["status"] == "closed":
            c += t["qty"] * t["exit_price"] * t["exit_fx"] * (1 - COST)
    return c


def _last_price(t: str) -> float | None:
    df = metrics.price_df(t)
    return None if df is None or df.empty else float(df["close"].iloc[-1])


def _equity(p: dict, trades: list[dict]) -> tuple[float, float, float]:
    cash = _cash(p, trades)
    inv = 0.0
    for t in trades:
        if t["status"] == "open":
            lp = _last_price(t["ticker"]) or t["entry_price"]
            inv += t["qty"] * lp * _fx_now(t["currency"])
    return cash + inv, cash, inv


# --------------------------------------------------------------- automatiska stopp
def evaluate() -> int:
    """Stänger positioner vars stopp har brutits sedan senaste kontroll. Idempotent."""
    n = 0
    with db.connect() as con:
        open_ = [dict(r) for r in con.execute("SELECT * FROM paper_trades WHERE status='open'").fetchall()]
    for t in open_:
        df = exercises.load(t["ticker"])
        if df is None:
            continue
        bars = df[df.index > pd.Timestamp(t["stop_from"] or t["entry_date"])]
        for idx, row in bars.iterrows():
            hit, fp, gap = exercises._fill(float(row["open"]), float(row["low"]), t["stop"])
            if hit:
                d = idx.strftime("%Y-%m-%d")
                with db.connect() as con:
                    con.execute("UPDATE paper_trades SET status='closed', exit_date=?, exit_price=?, exit_fx=?, exit_reason=? WHERE id=?",
                                (d, fp, _fx_on(t["currency"], d), "stop_gap" if gap else "stop", t["id"]))
                n += 1
                break
    return n


# --------------------------------------------------------------- affärer
def buy(pid: int, ticker: str, qty: float, stop: float, target: float | None, thesis: str, invalidation: str, horizon_days: int) -> int:
    p = _port(pid)
    q = quote(ticker)
    thesis, invalidation = thesis.strip(), invalidation.strip()
    if len(thesis) < 30:
        raise ValueError("Skriv en tes på minst 30 tecken: varför köper du?")
    if len(invalidation) < 10:
        raise ValueError("Skriv vad som skulle visa att du har fel (minst 10 tecken)")
    if qty is None or qty <= 0:
        raise ValueError("Antal måste vara större än 0")
    price = q["price"]
    if not stop or stop <= 0 or stop >= price * 0.995:
        raise ValueError("Stoppkursen måste vara under köpkursen")
    if target is not None and target <= price:
        raise ValueError("Målkursen måste vara över köpkursen")
    horizon_days = max(14, min(730, int(horizon_days or 90)))
    trades = _trades(pid)
    if any(t["status"] == "open" and t["ticker"] == q["ticker"] for t in trades):
        raise ValueError(f"Du har redan en öppen position i {q['ticker']} i den här portföljen")
    equity, cash, _ = _equity(p, trades)
    cost = qty * price * q["fx"] * (1 + COST)
    if cost > cash + 1e-6:
        raise ValueError(f"Det räcker inte med kontanter. Kostnad {cost:,.0f} kr, tillgängligt {cash:,.0f} kr.".replace(",", " "))
    risk_pct = qty * (price - stop) * q["fx"] / equity * 100
    pos_pct = qty * price * q["fx"] / equity * 100
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO paper_trades(pid,ticker,currency,qty,entry_date,entry_price,entry_fx,stop,stop0,stop_from,target,thesis,invalidation,"
            "horizon_days,review_on,risk_pct,pos_pct,signal_score) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, q["ticker"], q["currency"], qty, q["last_date"], price, q["fx"], stop, stop, q["last_date"], target, thesis, invalidation,
             horizon_days, (date.today() + timedelta(days=horizon_days)).isoformat(), risk_pct, pos_pct,
             (q["signal"] or {}).get("score")))
        return cur.lastrowid


def _get_trade(pid: int, tid: int) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM paper_trades WHERE id=? AND pid=?", (tid, pid)).fetchone()
    if not r:
        raise LookupError("Affären finns inte")
    return dict(r)


def close(pid: int, tid: int, reason: str) -> None:
    t = _get_trade(pid, tid)
    if t["status"] != "open":
        raise ValueError("Positionen är redan stängd")
    if reason not in REASONS:
        raise ValueError("Välj ett skäl till att du stänger")
    df = exercises.load(t["ticker"])
    price = float(df["close"].iloc[-1])
    with db.connect() as con:
        con.execute("UPDATE paper_trades SET status='closed', exit_date=?, exit_price=?, exit_fx=?, exit_reason=? WHERE id=?",
                    (df.index[-1].strftime("%Y-%m-%d"), price, _fx_now(t["currency"]), reason, tid))


def raise_stop(pid: int, tid: int, stop: float) -> None:
    t = _get_trade(pid, tid)
    if t["status"] != "open":
        raise ValueError("Positionen är stängd")
    last = _last_price(t["ticker"]) or 0
    if stop <= t["stop"]:
        raise ValueError("Ett stopp får bara flyttas uppåt (mot kursen), aldrig neråt. Annars försvinner poängen med det.")
    if stop >= last:
        raise ValueError("Stoppet måste ligga under senaste kurs")
    df = exercises.load(t["ticker"])
    with db.connect() as con:
        con.execute("UPDATE paper_trades SET stop=?, stop_from=?, stop_moves=stop_moves+1 WHERE id=?", (stop, df.index[-1].strftime("%Y-%m-%d"), tid))


def review(pid: int, tid: int, lesson: str) -> None:
    t = _get_trade(pid, tid)
    if t["status"] != "closed":
        raise ValueError("Du kan bara granska en stängd affär")
    if len(lesson.strip()) < 20:
        raise ValueError("Skriv en lärdom på minst 20 tecken: vad gjorde du bra, vad skulle du göra annorlunda?")
    with db.connect() as con:
        con.execute("UPDATE paper_trades SET lesson=? WHERE id=?", (lesson.strip(), tid))


# --------------------------------------------------------------- poäng och vyer
def points(t: dict) -> dict:
    plan = len(t["thesis"].strip()) >= 30 and len(t["invalidation"].strip()) >= 10 and t["stop"] > 0
    parts = {"plan": 20 if plan else 0, "risk": 30 if (t["risk_pct"] or 99) <= MAX_RISK_OK else 0,
             "size": 20 if (t["pos_pct"] or 99) <= MAX_POS_OK else 0, "review": 30 if len(t["lesson"].strip()) >= 20 else 0}
    return {"total": sum(parts.values()), "parts": parts}


def _trade_view(t: dict) -> dict:
    v = dict(t)
    v["points"] = points(t)
    v["name"] = exercises._name(t["ticker"])
    risk1 = t["entry_price"] - (t["stop0"] or t["stop"])
    if t["status"] == "open":
        lp = _last_price(t["ticker"]) or t["entry_price"]
        fx = _fx_now(t["currency"])
        v.update(price=lp, value=t["qty"] * lp * fx, pnl=t["qty"] * (lp * fx - t["entry_price"] * t["entry_fx"]),
                 pnl_pct=(lp * fx / (t["entry_price"] * t["entry_fx"]) - 1) * 100, r=(lp - t["entry_price"]) / risk1 if risk1 else None,
                 due=bool(t["review_on"] and t["review_on"] <= date.today().isoformat()), stop_dist=(lp - t["stop"]) / lp * 100)
    else:
        v.update(pnl=t["qty"] * (t["exit_price"] * t["exit_fx"] * (1 - COST) - t["entry_price"] * t["entry_fx"] * (1 + COST)),
                 pnl_pct=(t["exit_price"] * t["exit_fx"] * (1 - COST) / (t["entry_price"] * t["entry_fx"] * (1 + COST)) - 1) * 100,
                 r=(t["exit_price"] - t["entry_price"]) / risk1 if risk1 else None)
    return v


def _curve(p: dict, trades: list[dict]) -> list[list]:
    created = p["created"]
    if not trades:
        return [[created, p["cash0"]]]
    closes, fxs = {}, {}
    for t in {x["ticker"] for x in trades}:
        df = exercises.load(t)
        closes[t] = df["close"] if df is not None else pd.Series(dtype=float)
    for c in {x["currency"] for x in trades}:
        if c and c != "SEK":
            base = "GBP" if c == "GBp" else c
            df = metrics.price_df(f"{base}SEK=X")
            if df is not None:
                fxs[c] = df["close"] / (100 if c == "GBp" else 1)
    idx = sorted(set().union(*[set(s.index) for s in closes.values()]))
    idx = [d for d in idx if d >= pd.Timestamp(created)]
    if not idx:
        return [[created, p["cash0"]]]
    ix = pd.DatetimeIndex(idx)
    cl = {t: s.reindex(ix, method="ffill") for t, s in closes.items()}
    fx = {c: s.reindex(ix, method="ffill").bfill() for c, s in fxs.items()}
    out = []
    for k, d in enumerate(ix):
        ds = d.strftime("%Y-%m-%d")
        cash, val = p["cash0"], 0.0
        for t in trades:
            if t["entry_date"] > ds:
                continue
            cash -= t["qty"] * t["entry_price"] * t["entry_fx"] * (1 + COST)
            if t["status"] == "closed" and t["exit_date"] <= ds:
                cash += t["qty"] * t["exit_price"] * t["exit_fx"] * (1 - COST)
            else:
                px = cl[t["ticker"]].iloc[k]
                f = 1.0 if (not t["currency"] or t["currency"] == "SEK") else float(fx[t["currency"]].iloc[k]) if t["currency"] in fx else t["entry_fx"]
                if not np.isnan(px):
                    val += t["qty"] * float(px) * f
        out.append([ds, round(cash + val, 2)])
    return out


def _bench_ret(created: str) -> float | None:
    for t in portfolio.DEFAULT_BENCH:
        df = metrics.price_df(t)
        if df is not None and len(df) > 50:
            base = df["close"][df.index <= pd.Timestamp(created)]
            if not len(base):
                return None
            return (float(df["close"].iloc[-1]) / float(base.iloc[-1]) - 1) * 100
    return None


def _summary(p: dict) -> dict:
    trades = _trades(p["id"])
    equity, cash, inv = _equity(p, trades)
    opens = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed"]
    risk_open = 0.0
    for t in opens:
        lp = _last_price(t["ticker"]) or t["entry_price"]
        risk_open += max(0.0, lp - t["stop"]) * t["qty"] * _fx_now(t["currency"])
    curve = _curve(p, trades)
    vals = np.array([v for _, v in curve], float)
    dd = float(((vals / np.maximum.accumulate(vals)) - 1).min() * 100) if len(vals) > 1 else 0.0
    pts = [points(t)["total"] for t in closed]
    bench = _bench_ret(p["created"])
    ret = (equity / p["cash0"] - 1) * 100
    wins = sum(1 for t in closed if (t["exit_price"] * t["exit_fx"]) > (t["entry_price"] * t["entry_fx"]))
    return {"id": p["id"], "name": p["name"], "strategy": p["strategy"], "created": p["created"], "cash0": p["cash0"],
            "equity": equity, "cash": cash, "invested": inv, "ret": ret, "bench": bench, "excess": None if bench is None else ret - bench,
            "open_n": len(opens), "closed_n": len(closed), "risk_open_pct": risk_open / equity * 100 if equity else None, "max_dd": dd,
            "process_avg": float(np.mean(pts)) if pts else None, "reviewed_n": sum(1 for t in closed if len(t["lesson"].strip()) >= 20),
            "to_review": sum(1 for t in closed if len(t["lesson"].strip()) < 20), "win_rate": (wins / len(closed) * 100) if closed else None,
            "curve": curve, "due_n": sum(1 for t in opens if t["review_on"] and t["review_on"] <= date.today().isoformat())}


def list_portfolios() -> dict:
    evaluate()
    with db.connect() as con:
        ps = [dict(r) for r in con.execute("SELECT * FROM paper_portfolios ORDER BY id").fetchall()]
    out = []
    for p in ps:
        s = _summary(p)
        out.append(s)
    return {"portfolios": out, "rules": {"cost_pct": COST * 100, "max_risk_pct": MAX_RISK_OK, "max_pos_pct": MAX_POS_OK}}


def detail(pid: int) -> dict:
    evaluate()
    p = _port(pid)
    s = _summary(p)
    trades = [_trade_view(t) for t in _trades(pid)]
    return {"summary": s, "open": [t for t in trades if t["status"] == "open"], "closed": [t for t in reversed(trades) if t["status"] == "closed"],
            "rules": {"cost_pct": COST * 100, "max_risk_pct": MAX_RISK_OK, "max_pos_pct": MAX_POS_OK}, "reasons": REASONS}


def game_flags() -> dict:
    with db.connect() as con:
        ps = con.execute("SELECT COUNT(*) n FROM paper_portfolios").fetchone()["n"]
        rows = [dict(r) for r in con.execute("SELECT * FROM paper_trades").fetchall()]
    good = sum(1 for t in rows if (t["risk_pct"] or 99) <= MAX_RISK_OK and (t["pos_pct"] or 99) <= MAX_POS_OK)
    closed = [t for t in rows if t["status"] == "closed"]
    rev = sum(1 for t in closed if len(t["lesson"].strip()) >= 20)
    pts = [points(t)["total"] for t in closed]
    return {"portfolios": ps, "good_entries": good, "closed": len(closed), "reviewed": rev,
            "process_avg": float(np.mean(pts)) if pts else None}
