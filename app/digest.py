"""Regelbaserad sammanfattning av senaste kvartalsrapport utifrån
rapporterade nyckeltal. Den sammanfattar siffror – inte ledningens
kommentarer eller framtidsutsikter (för det behövs rapporttexten)."""
from __future__ import annotations

from datetime import date


def _sv(x: float, dec: int = 1) -> str:
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def money(v, cur: str = "") -> str:
    if v is None:
        return "–"
    a = abs(v)
    if a >= 1e9:
        s = f"{_sv(v / 1e9, 2)} mdr"
    elif a >= 1e6:
        s = f"{_sv(v / 1e6, 1)} mn"
    else:
        s = _sv(v, 0)
    return f"{s} {cur}".strip()


def pct(v, dec: int = 1, sign: bool = True) -> str:
    if v is None:
        return "–"
    return f"{'+' if sign and v > 0 else ''}{_sv(v, dec)} %"


def _growth(now, base):
    if now is None or base is None or base == 0:
        return None
    if base < 0:
        return None
    return (now / base - 1) * 100


def _find_prior(quarters: list[dict], latest: dict, lo: int, hi: int):
    d0 = date.fromisoformat(latest["date"])
    for q in quarters[1:]:
        gap = (d0 - date.fromisoformat(q["date"])).days
        if lo <= gap <= hi:
            return q
    return None


def build(fund: dict | None, currency: str = "") -> dict:
    empty = {"has_data": False, "headline": "Ingen kvartalsdata tillgänglig (gäller t.ex. ETF:er och index).",
             "metrics": {}, "flags": [], "surprise": None, "next_earnings": None, "beats": None}
    if not fund:
        return empty
    quarters = fund.get("quarters") or []
    earnings = fund.get("earnings") or []
    nxt = fund.get("next_earnings")
    cur = currency or (fund.get("info") or {}).get("currency", "")
    if not quarters:
        e = dict(empty)
        e["next_earnings"] = nxt
        if nxt:
            e["headline"] += f" Nästa rapport väntas {nxt}."
        return e

    q = quarters[0]
    yoy_q = _find_prior(quarters, q, 330, 400)
    qoq_q = _find_prior(quarters, q, 60, 125)

    def margin(x, k):
        return None if not x or x.get(k) is None or not x.get("revenue") else x[k] / x["revenue"] * 100

    m = {
        "quarter": q["date"],
        "revenue": q.get("revenue"),
        "revenue_yoy": _growth(q.get("revenue"), yoy_q.get("revenue") if yoy_q else None),
        "revenue_qoq": _growth(q.get("revenue"), qoq_q.get("revenue") if qoq_q else None),
        "gross_margin": margin(q, "gross_profit"),
        "operating_margin": margin(q, "operating_income"),
        "operating_margin_prev_year": margin(yoy_q, "operating_income"),
        "net_income": q.get("net_income"),
        "net_income_yoy": _growth(q.get("net_income"), yoy_q.get("net_income") if yoy_q else None),
        "net_margin": margin(q, "net_income"),
        "ebitda": q.get("ebitda"),
        "eps": q.get("eps"),
        "eps_yoy": _growth(q.get("eps"), yoy_q.get("eps") if yoy_q else None),
        "fcf": q.get("fcf"),
    }

    parts, flags = [], []
    rev = f"omsättning {money(m['revenue'], cur)}"
    comp = []
    if m["revenue_yoy"] is not None:
        comp.append(f"{pct(m['revenue_yoy'])} mot samma kvartal året innan")
    if m["revenue_qoq"] is not None:
        comp.append(f"{pct(m['revenue_qoq'])} mot föregående kvartal")
    parts.append(rev + (f" ({', '.join(comp)})" if comp else ""))

    if m["operating_margin"] is not None:
        s = f"rörelsemarginal {pct(m['operating_margin'], sign=False)}"
        pm = m["operating_margin_prev_year"]
        if pm is not None:
            s += f" ({pct(pm, sign=False)} ett år tidigare)"
            diff = m["operating_margin"] - pm
            if diff >= 1:
                flags.append(f"Rörelsemarginalen expanderade {_sv(diff)} procentenheter på årsbasis")
            elif diff <= -1:
                flags.append(f"Rörelsemarginalen föll {_sv(-diff)} procentenheter på årsbasis")
        parts.append(s)

    ni = m["net_income"]
    if ni is not None:
        s = f"nettoresultat {money(ni, cur)}"
        if m["net_income_yoy"] is not None:
            s += f" ({pct(m['net_income_yoy'])} på årsbasis)"
        elif yoy_q and yoy_q.get("net_income") is not None and yoy_q["net_income"] <= 0 < ni:
            s += " (vände till vinst jämfört med föregående år)"
            flags.append("Vände till vinst jämfört med samma kvartal året innan")
        parts.append(s)
        if ni < 0:
            flags.append("Förlust under kvartalet")

    if m["eps"] is not None:
        parts.append(f"vinst per aktie {_sv(m['eps'], 2)} {cur}".strip())
    if m["fcf"] is not None:
        parts.append(f"fritt kassaflöde {money(m['fcf'], cur)}")

    if m["revenue_yoy"] is not None and m["revenue_yoy"] >= 15:
        flags.append("Stark omsättningstillväxt (≥ 15 % på årsbasis)")
    if m["revenue_yoy"] is not None and m["revenue_yoy"] < 0:
        flags.append("Omsättningen minskade på årsbasis")

    headline = f"Kvartal som slutade {q['date']}: " + "; ".join(parts) + "."

    surprise = None
    beats = None
    if earnings:
        e = earnings[0]
        surprise = e
        if e.get("eps_actual") is not None and e.get("eps_estimate") is not None:
            sp = e.get("surprise_pct")
            word = "över" if (sp or 0) >= 0 else "under"
            headline += (f" Vinst per aktie {_sv(e['eps_actual'], 2)} mot förväntat {_sv(e['eps_estimate'], 2)}"
                         f" ({pct(abs(sp) if sp is not None else None, sign=False)} {word} förväntan, rapport {e['date']}).")
        recent = [x for x in earnings[:4] if x.get("surprise_pct") is not None]
        if recent:
            beats = {"beat": sum(1 for x in recent if x["surprise_pct"] > 0), "of": len(recent)}
            headline += f" Slog förväntningarna i {beats['beat']} av de {beats['of']} senaste rapporterna."
    if nxt:
        headline += f" Nästa rapport väntas {nxt}."

    return {"has_data": True, "headline": headline, "metrics": m, "flags": flags,
            "surprise": surprise, "next_earnings": nxt, "beats": beats}
