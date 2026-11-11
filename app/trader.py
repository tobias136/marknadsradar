"""Handlarens verktyg: Spelbok (dina skriftliga regler) och månadsgranskning.

Spelboken är det som skiljer en handlare från någon som bara köper och säljer: regler skrivna i förväg,
i lugn och ro, som man följer när det stormar. Månadsgranskningen är vanan att titta tillbaka på processen."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import numpy as np

from . import db, exercises, paper

MIN_LEN = 40
SECTIONS = [
    ("setups", "Vad letar jag efter?", "Beskriv de lägen du handlar. T.ex.: ”Aktier i stigande trend (över SMA200) som dragit sig tillbaka mot SMA50 och är starka mot indexet.”"),
    ("entry", "När köper jag?", "Vilka villkor ska vara uppfyllda? T.ex.: ”Signalbetyg över +20, RSI under 70, inte mindre än 5 dagar till rapport.”"),
    ("exit", "När säljer jag?", "Stopp, mål och tid. T.ex.: ”Stopp 3 ATR under, höjer det efter 2 R. Ut om tesen bryts eller efter 90 dagar utan framsteg.”"),
    ("size", "Hur stor får jag vara?", "T.ex.: ”Högst 1 % risk per affär, högst 15 % i en position, högst 6 positioner.”"),
    ("nogo", "När handlar jag inte?", "T.ex.: ”Inte dagen före rapport, inte efter en nyhetschock, inte när jag är trött eller arg, inte om jag inte kan skriva tesen.”"),
    ("losing", "Vad gör jag efter tre förluster i rad?", "T.ex.: ”Halverar storleken, granskar de tre affärerna mot spelboken, tar en vecka utan nya affärer.”"),
]
LIMITS = {"max_open_risk": (6.0, 1.0, 20.0, "Högsta samlade öppna risk (% av portföljen om alla stopp träffas)"),
          "max_dd": (10.0, 3.0, 30.0, "Största nedgång jag accepterar i en portfölj (%)")}
MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ spelbok
def playbook_get() -> dict:
    with db.connect() as con:
        rows = {r["key"]: r["text"] for r in con.execute("SELECT key, text FROM playbook").fetchall()}
        upd = con.execute("SELECT MAX(updated) u FROM playbook").fetchone()["u"]
    secs = [{"key": k, "title": t, "hint": h, "text": rows.get(k, ""), "ok": len(rows.get(k, "").strip()) >= MIN_LEN} for k, t, h in SECTIONS]
    limits = {}
    for k, (d, lo, hi, label) in LIMITS.items():
        try:
            v = float(rows.get("limit_" + k, d))
        except ValueError:
            v = d
        limits[k] = {"value": v, "min": lo, "max": hi, "label": label}
    return {"sections": secs, "limits": limits, "complete": all(s["ok"] for s in secs), "min_len": MIN_LEN, "updated": upd}


def playbook_save(sections: dict, limits: dict) -> dict:
    valid = {k for k, _, _ in SECTIONS}
    with db.connect() as con:
        for k, text in (sections or {}).items():
            if k in valid:
                con.execute("INSERT INTO playbook(key,text,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET text=excluded.text, updated=excluded.updated",
                            (k, str(text).strip()[:2000], _now()))
        for k, v in (limits or {}).items():
            if k not in LIMITS:
                continue
            d, lo, hi, _ = LIMITS[k]
            v = float(v)
            if not (lo <= v <= hi):
                raise ValueError(f"Gränsen måste ligga mellan {lo:g} och {hi:g} %")
            con.execute("INSERT INTO playbook(key,text,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET text=excluded.text, updated=excluded.updated",
                        ("limit_" + k, str(v), _now()))
    return playbook_get()


# ------------------------------------------------------------------ månadsgranskning
def _recent_months(n: int = 4) -> list[str]:
    d = date.today().replace(day=1)
    out = []
    y, m = d.year, d.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _label(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS_SV[int(m) - 1]} {y}"


def month_stats(month: str) -> dict:
    with db.connect() as con:
        trades = [dict(r) for r in con.execute("SELECT * FROM paper_trades WHERE status='closed' AND substr(exit_date,1,7)=?", (month,)).fetchall()]
        jn = con.execute("SELECT COUNT(*) n FROM journal WHERE substr(created,1,7)=?", (month,)).fetchone()["n"]
        pr = con.execute("SELECT COUNT(*) n FROM practice_log WHERE substr(ts,1,7)=?", (month,)).fetchone()["n"]
    rs, pts, pnl, wins = [], [], [], 0
    for t in trades:
        risk1 = t["entry_price"] - (t["stop0"] or t["stop"])
        if risk1:
            rs.append((t["exit_price"] - t["entry_price"]) / risk1)
        pts.append(paper.points(t)["total"])
        p = (t["exit_price"] * t["exit_fx"] * (1 - paper.COST)) / (t["entry_price"] * t["entry_fx"] * (1 + paper.COST)) - 1
        pnl.append(p * 100)
        wins += p > 0
    n = len(trades)
    return {"closed_n": n, "hit_rate": wins / n * 100 if n else None, "avg_r": float(np.mean(rs)) if rs else None,
            "avg_pnl_pct": float(np.mean(pnl)) if pnl else None, "process_avg": float(np.mean(pts)) if pts else None,
            "journal_n": jn, "practice_n": pr}


def monthly_list() -> dict:
    with db.connect() as con:
        done = {r["month"]: dict(r) for r in con.execute("SELECT * FROM monthly_reviews").fetchall()}
    out = []
    for m in _recent_months():
        st = month_stats(m)
        r = done.get(m)
        out.append({"month": m, "label": _label(m), "stats": st, "eligible": st["closed_n"] >= 3, "done": bool(r),
                    "review": {"good": r["good"], "bad": r["bad"], "change": r["change"]} if r else None})
    older = [{"month": m, "label": _label(m), "review": {"good": r["good"], "bad": r["bad"], "change": r["change"]}}
             for m, r in sorted(done.items(), reverse=True) if m not in {x["month"] for x in out}]
    return {"months": out, "older": older, "need": 3}


def monthly_save(month: str, good: str, bad: str, change: str) -> None:
    if month not in _recent_months():
        raise ValueError("Du kan granska den här månaden och de tre föregående")
    if month_stats(month)["closed_n"] < 3:
        raise ValueError("Det krävs minst tre stängda övningsaffärer under månaden för att det ska finnas något att granska")
    for name, v in (("Vad som gick bra", good), ("Vad som gick sämre", bad), ("Vad jag ändrar", change)):
        if len((v or "").strip()) < 30:
            raise ValueError(f"{name}: skriv minst 30 tecken")
    with db.connect() as con:
        con.execute("INSERT INTO monthly_reviews(month,good,bad,change,stats,created) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(month) DO UPDATE SET good=excluded.good, bad=excluded.bad, change=excluded.change, stats=excluded.stats",
                    (month, good.strip(), bad.strip(), change.strip(), json.dumps(month_stats(month)), _now()))


def game_flags() -> dict:
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) n FROM monthly_reviews").fetchone()["n"]
    return {"playbook": playbook_get()["complete"], "monthly": n}
