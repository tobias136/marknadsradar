"""Makropanel: marknadens 'väder'. Räntor, oro (VIX), dollar, råvaror och en enkel regelbaserad
regimtext. Beskrivande, inte en prognos."""
from __future__ import annotations

import pandas as pd

from . import metrics

# key, ticker, namn, enhet, ordlistenyckel, typ ('level' = nivå, förändring i enheter; 'price' = pris, förändring i %)
INDICATORS = [
    ("vix", "^VIX", "VIX – oroindex", "", "vix", "level"),
    ("y10", "^TNX", "USA 10-årsränta", "%", "yieldcurve", "level"),
    ("y3m", "^IRX", "USA 3-månadersränta", "%", "yieldcurve", "level"),
    ("y5", "^FVX", "USA 5-årsränta", "%", "yieldcurve", "level"),
    ("usd", "DX-Y.NYB", "Dollarindex", "", "usd", "price"),
    ("usdsek", "USDSEK=X", "USD/SEK", "kr", "fx", "price"),
    ("eursek", "EURSEK=X", "EUR/SEK", "kr", "fx", "price"),
    ("oil", "CL=F", "Olja (WTI)", "USD", "regime", "price"),
    ("gold", "GC=F", "Guld", "USD", "regime", "price"),
    ("copper", "HG=F", "Koppar", "USD", "regime", "price"),
    ("spx", "^GSPC", "S&P 500", "", "trend", "price"),
    ("omx", "^OMX", "OMXS30", "", "trend", "price"),
]
EXTRA = ["HYG", "LQD"]


def aux_tickers() -> list[str]:
    return [i[1] for i in INDICATORS] + EXTRA


def _series(ticker: str, yield_like: bool = False) -> pd.Series | None:
    df = metrics.price_df(ticker)
    if df is None or len(df) < 30:
        return None
    s = df["close"].astype(float)
    if yield_like and s.iloc[-1] > 20:   # äldre Yahoo-format: ränta ×10
        s = s / 10
    return s


def _s(v, d=1) -> str:
    return f"{v:.{d}f}".replace(".", ",").replace("-", "\u2212")


def _pctile(s: pd.Series, n: int = 252) -> float:
    t = s.tail(n)
    return float((t <= t.iloc[-1]).mean() * 100)


def _text(key: str, last: float, ch1m: float | None, extra: dict) -> str:
    if key == "vix":
        if last < 15:
            return "Lugnt: investerare räknar inte med stora svängningar. Mycket lugn kan också betyda självbelåtenhet."
        if last < 20:
            return "Normalt läge."
        if last < 30:
            return "Förhöjd oro: marknaden räknar med större svängningar än vanligt."
        return "Hög rädsla: stora svängningar förväntas. Ofta en period där kurser faller snabbt, men höga nivåer har också historiskt kommit nära vändningar."
    if key in ("y10", "y5"):
        t = "Stigande räntor tynger ofta värderingen av bolag vars vinster ligger långt fram i tiden." if (ch1m or 0) > 0.15 else \
            "Fallande räntor brukar ge medvind för lånefinansierade och tillväxtbolag." if (ch1m or 0) < -0.15 else "Räntan är i stort sett stabil den senaste månaden."
        return t
    if key == "y3m":
        return "Styrräntenära ränta: det är vad kortsiktiga placeringar ger. Hög kort ränta gör aktier relativt mindre lockande."
    if key == "usd":
        return "Starkare dollar tynger ofta råvaror och tillväxtmarknader." if (ch1m or 0) > 1.5 else \
               "Svagare dollar brukar gynna råvaror och tillväxtmarknader." if (ch1m or 0) < -1.5 else "Dollarn är relativt stabil."
    if key in ("usdsek", "eursek"):
        return "Kronan har försvagats den senaste månaden: dina utländska innehav är värda mer i kronor." if (ch1m or 0) > 1.5 else \
               "Kronan har stärkts den senaste månaden: dina utländska innehav är värda mindre i kronor, även om kursen i dollar är oförändrad." if (ch1m or 0) < -1.5 else "Växelkursen är relativt stabil."
    if key == "oil":
        return "Dyrare olja ger vinstlyft för oljebolag men kostnader för transport och industri." if (ch1m or 0) > 5 else \
               "Billigare olja gynnar konsumenter och transportbolag men pressar energisektorn." if (ch1m or 0) < -5 else "Oljepriset är relativt stabilt."
    if key == "gold":
        return "Guld söks ofta när oron ökar eller när realräntorna faller." if (ch1m or 0) > 3 else \
               "Guld har tappat: ofta ett tecken på lugnare marknad eller stigande realräntor." if (ch1m or 0) < -3 else "Guldpriset är relativt stabilt."
    if key == "copper":
        return "Koppar kallas ibland 'Dr Copper' eftersom efterfrågan följer industrikonjunkturen: stigande pris tolkas som optimism om konjunkturen." if (ch1m or 0) > 4 else \
               "Fallande kopparpris tolkas ofta som oro för industrikonjunkturen." if (ch1m or 0) < -4 else "Kopparpriset är relativt stabilt."
    if key in ("spx", "omx"):
        v = extra.get("vs200")
        return "" if v is None else f"Ligger {_s(abs(v))} % {'över' if v > 0 else 'under'} 200-dagarssnittet."
    return ""


def snapshot() -> dict:
    cards = []
    data: dict[str, pd.Series] = {}
    for key, tk, name, unit, gk, kind in INDICATORS:
        s = _series(tk, yield_like=key in ("y10", "y3m", "y5"))
        if s is None:
            cards.append({"key": key, "ticker": tk, "name": name, "unit": unit, "gloss": gk, "missing": True})
            continue
        data[key] = s
        last = float(s.iloc[-1])
        ch1 = float(s.iloc[-1] - s.iloc[-2]) if kind == "level" else float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
        ch1m = (float(s.iloc[-1] - s.iloc[-22]) if kind == "level" else float((s.iloc[-1] / s.iloc[-22] - 1) * 100)) if len(s) > 22 else None
        vs200 = float((s.iloc[-1] / s.tail(200).mean() - 1) * 100) if len(s) >= 200 else None
        cards.append({"key": key, "ticker": tk, "name": name, "unit": unit, "gloss": gk, "kind": kind, "missing": False,
                      "last": last, "ch1d": ch1, "ch1m": ch1m, "pctile": _pctile(s), "vs200": vs200, "date": s.index[-1].strftime("%Y-%m-%d"),
                      "spark": [round(float(x), 4) for x in s.tail(120)],
                      "text": _text(key, last, ch1m, {"vs200": vs200})})

    derived = []
    if "y10" in data and "y3m" in data:
        c = (data["y10"] - data["y3m"]).dropna()
        if len(c) > 30:
            v = float(c.iloc[-1])
            derived.append({"key": "curve", "name": "Räntekurva (10 år minus 3 mån)", "unit": "p.e.", "gloss": "yieldcurve", "last": v,
                            "ch1m": float(c.iloc[-1] - c.iloc[-22]) if len(c) > 22 else None, "pctile": _pctile(c),
                            "spark": [round(float(x), 4) for x in c.tail(120)],
                            "text": ("Inverterad: korta räntor över långa. Historiskt ett varningstecken för lågkonjunktur, men med lång och osäker fördröjning och flera falska alarm." if v < 0 else
                                     "Nästan platt kurva: marknaden räknar inte med högre tillväxt framöver." if v < 0.5 else
                                     "Normalt lutande: långa räntor över korta.")})
    hy, ig = _series("HYG"), _series("LQD")
    credit_state = None
    if hy is not None and ig is not None:
        ratio = (hy / ig).dropna()
        if len(ratio) > 60:
            vs50 = float((ratio.iloc[-1] / ratio.tail(50).mean() - 1) * 100)
            credit_state = vs50
            derived.append({"key": "credit", "name": "Kreditoro (HYG/LQD)", "unit": "", "gloss": "spreads", "last": float(ratio.iloc[-1]),
                            "ch1m": float((ratio.iloc[-1] / ratio.iloc[-22] - 1) * 100) if len(ratio) > 22 else None,
                            "pctile": _pctile(ratio), "spark": [round(float(x), 5) for x in ratio.tail(120)],
                            "text": ("Kvoten faller under sitt snitt: investerare lämnar riskfyllda företagsobligationer, ofta ett tidigt tecken på oro." if vs50 < -0.5 else
                                     "Kvoten ligger över sitt snitt: riskfyllda obligationer går bra, ett tecken på låg kreditoro." if vs50 > 0.5 else
                                     "Kreditmarknaden är lugn.")})
    return {"cards": cards, "derived": derived, "regime": _regime(cards, derived, credit_state)}


def _regime(cards, derived, credit_state) -> dict | None:
    by = {c["key"]: c for c in cards if not c.get("missing")}
    pts, reasons = 0.0, []

    def add(p, t):
        nonlocal pts
        pts += p
        reasons.append({"pts": p, "text": t})

    v = by.get("vix")
    if v:
        add(1 if v["last"] < 20 else -1 if v["last"] > 30 else 0,
            f"VIX {_s(v['last'])}: " + ("lågt – lugn marknad" if v["last"] < 20 else "högt – oro" if v["last"] > 30 else "förhöjt men inte extremt"))
    s = by.get("spx")
    if s and s.get("vs200") is not None:
        add(1 if s["vs200"] > 0 else -1, f"S&P 500 ligger {_s(abs(s['vs200']))} % {'över' if s['vs200'] > 0 else 'under'} 200-dagarssnittet")
    cv = next((d for d in derived if d["key"] == "curve"), None)
    if cv:
        add(0.5 if cv["last"] > 0 else -0.5, f"Räntekurvan är {'normalt lutande' if cv['last'] > 0 else 'inverterad'} ({_s(cv['last'], 2)} p.e.)")
    if credit_state is not None:
        add(0.5 if credit_state > 0 else -0.5, "Kreditmarknaden är " + ("lugn (HYG/LQD över snittet)" if credit_state > 0 else "orolig (HYG/LQD under snittet)"))
    if not reasons:
        return None
    label, key = ("Risk-on", "on") if pts >= 1.5 else ("Risk-off", "off") if pts <= -1.5 else ("Blandat", "mixed")
    lay = {"on": "Marknaden är beredd att ta risk. Medvind för aktier, särskilt cykliska och tillväxtbolag, men trendbrott kan komma snabbt.",
           "off": "Marknaden drar sig undan risk. Försiktighet är vanligt: svagare aktier, starkare räntor/guld/dollar. Ingen garanti för fortsatt nedgång.",
           "mixed": "Blandade signaler. Ingen tydlig riktning från omvärlden just nu."}[key]
    return {"key": key, "label": label, "score": pts, "lay": lay, "reasons": reasons,
            "disclaimer": "Regelbaserad beskrivning av nuläget, inte en prognos. Fyra enkla indikatorer ger en grov bild."}
