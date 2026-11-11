"""Signalbetyg: ett transparent, regelbaserat sammandrag av trend, momentum,
relativ styrka, fundamenta och värdering. Varje regel ger ett poäng och en
mening i klartext, så att man alltid kan se VARFÖR betyget blev som det blev.

Viktigt: reglerna är standardregler (inte optimerade) och ännu inte
backtestade. Betyget är ett beskrivande mätetal, inte en rekommendation."""
from __future__ import annotations

from datetime import date, datetime

WEIGHTS = {"trend": 1.5, "momentum": 1.0, "rs": 1.0, "fundamentals": 1.0, "valuation": 0.5}
NAMES = {"trend": "Trend", "momentum": "Momentum", "rs": "Relativ styrka",
         "fundamentals": "Fundamenta (rapporter)", "valuation": "Värdering"}

LABELS = [  # (min_score, nyckel, etikett, lekmannatolkning)
    (50, "strong_pos", "Starkt positivt", "Lutar starkt mot köp/behåll"),
    (20, "pos", "Positivt", "Lutar mot köp/behåll"),
    (-20, "neutral", "Neutralt", "Avvakta / behåll"),
    (-50, "neg", "Negativt", "Lutar mot minska/sälj"),
    (-101, "strong_neg", "Starkt negativt", "Lutar starkt mot sälj"),
]


def _f(v, d=1):
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def _clip(x, lo=-2, hi=2):
    return max(lo, min(hi, x))


def _pillar(key, reasons):
    pts = sum(r["pts"] for r in reasons)
    return {"key": key, "name": NAMES[key], "score": _clip(pts), "reasons": reasons}


def _r(pts, text):
    return {"pts": pts, "text": text}


def _trend(r):
    out = []
    d200 = r.get("vs_sma200")
    if d200 is not None:
        up = d200 > 0
        out.append(_r(1 if up else -1,
                      f"Kursen ligger {_f(abs(d200))} % {'över' if up else 'under'} 200-dagarssnittet – långsiktig trend {'uppåt' if up else 'nedåt'}"))
    if r.get("sma50_over_200") is not None:
        up = r["sma50_over_200"]
        out.append(_r(1 if up else -1,
                      f"50-dagarssnittet ligger {'över' if up else 'under'} 200-dagarssnittet ({'golden cross-läge' if up else 'death cross-läge'})"))
    d50 = r.get("vs_sma50")
    if d50 is not None:
        out.append(_r(0, f"Kursen ligger {_f(abs(d50))} % {'över' if d50 > 0 else 'under'} 50-dagarssnittet"
                         + ("" if d50 > 0 else " – kortsiktig svaghet eller korrektion")))
    adx = r.get("adx")
    if adx is not None:
        direction = "uppåt" if (r.get("plus_di") or 0) > (r.get("minus_di") or 0) else "nedåt"
        if adx >= 25:
            out.append(_r(0, f"Trenden är stark (ADX {_f(adx, 0)}) och pekar {direction}"))
        elif adx < 20:
            out.append(_r(0, f"Svag trend/sidledes (ADX {_f(adx, 0)}) – trendsignaler är mindre pålitliga just nu"))
    return out if any(x["pts"] != 0 for x in out) else []


def _momentum(r):
    out = []
    m = r.get("mom_12_1")
    if m is not None:
        out.append(_r(1 if m > 0 else -1,
                      f"Momentum 12–1 månader är {_f(m)} % – {'vinnare på 3–12 månaders sikt tenderar att fortsätta' if m > 0 else 'förlorare på 3–12 månaders sikt tenderar att fortsätta släpa'}"))
    elif r.get("r_6m") is not None:
        out.append(_r(1 if r["r_6m"] > 0 else -1, f"Avkastning 6 månader: {_f(r['r_6m'])} %"))
    if r.get("macd") is not None and r.get("macd_signal") is not None:
        up = r["macd"] > r["macd_signal"]
        rising = (r.get("macd_hist") or 0) > (r.get("macd_hist_prev") or 0)
        out.append(_r(1 if up else -1,
                      f"MACD ligger {'över' if up else 'under'} sin signallinje – momentumet {'stärks' if up else 'försvagas'}"
                      + (" (men tappar fart)" if up and not rising else "")))
    return out


def _rs(r):
    out = []
    if r.get("rs_3m") is not None:
        out.append(_r(1 if r["rs_3m"] > 0 else -1,
                      f"Senaste 3 månaderna: {'bättre' if r['rs_3m'] > 0 else 'sämre'} än jämförelseindexet ({'+' if r['rs_3m'] > 0 else '−'}{_f(abs(r['rs_3m']))} procentenheter)"))
    if r.get("rs_line_pct") is not None:
        up = r["rs_line_pct"] > 0
        out.append(_r(1 if up else -1,
                      f"Relativa styrkan mot indexet ligger {'över' if up else 'under'} sitt 50-dagarssnitt – {'ledarskapet ökar' if up else 'eftersläpningen ökar'}"))
    return out


def _fund(r):
    if not r.get("has_q"):
        return []
    out = []
    g = r.get("rev_yoy")
    if g is not None:
        if g >= 5:
            out.append(_r(1, f"Omsättningen växer {_f(g)} % mot samma kvartal året innan"))
        elif g < 0:
            out.append(_r(-1, f"Omsättningen minskade {_f(abs(g))} % mot samma kvartal året innan"))
        else:
            out.append(_r(0, f"Omsättningen växer svagt ({_f(g)} % på årsbasis)"))
    d = r.get("opm_delta")
    if d is not None:
        if d >= 1:
            out.append(_r(1, f"Rörelsemarginalen har ökat {_f(d)} procentenheter på ett år – mer vinst per krona omsatt"))
        elif d <= -1:
            out.append(_r(-1, f"Rörelsemarginalen har minskat {_f(abs(d))} procentenheter på ett år"))
        else:
            out.append(_r(0, "Rörelsemarginalen är i stort sett oförändrad mot förra året"))
    b, of = r.get("beats"), r.get("beats_of")
    if b is not None and of and of >= 3:
        if b >= 3:
            out.append(_r(1, f"Slog förväntningarna (EPS) i {b} av de {of} senaste rapporterna"))
        elif b <= 1:
            out.append(_r(-1, f"Slog bara förväntningarna i {b} av de {of} senaste rapporterna"))
        else:
            out.append(_r(0, f"Slog förväntningarna i {b} av {of} rapporter"))
    return out


def _val(r):
    p = r.get("val_pct")
    if p is None:
        return []
    pe = r.get("forward_pe") or r.get("pe")
    basis = r.get("val_basis", "listan")
    kind = "förväntat P/E" if r.get("forward_pe") else "P/E"
    if p >= 75:
        pts = -2 if p >= 90 else -1
        txt = f"Värderingen ({kind} {_f(pe)}) är högre än hos {_f(p, 0)} % av jämförelsebolagen i {basis} – relativt dyr"
    elif p <= 25:
        pts = 2 if p <= 10 else 1
        txt = f"Värderingen ({kind} {_f(pe)}) är lägre än hos {_f(100 - p, 0)} % av jämförelsebolagen i {basis} – relativt billig"
    else:
        pts, txt = 0, f"Värderingen ({kind} {_f(pe)}) ligger mitt i fältet bland jämförelsebolagen i {basis}"
    return [_r(pts, txt)]


def _label(score):
    for lo, key, name, lay in LABELS:
        if score >= lo:
            return key, name, lay
    return LABELS[-1][1:]


def _combine(pillars: list[dict]) -> int:
    """Viktat medelvärde av pelarnas poäng (−2…+2) skalat till −100…+100."""
    wsum = sum(WEIGHTS[p["key"]] for p in pillars)
    return round(sum(WEIGHTS[p["key"]] * p["score"] / 2 for p in pillars) / wsum * 100)


def quick_score(r: dict, keys=("trend", "momentum", "rs")) -> int | None:
    """Samma regler och vikter som assess(), men bara de pelare man anger och utan
    text. Används av backtesten, där fundamenta/värdering inte finns 'vid den tidpunkten'."""
    fns = {"trend": _trend, "momentum": _momentum, "rs": _rs, "fundamentals": _fund, "valuation": _val}
    pillars = []
    for k in keys:
        reasons = fns[k](r)
        if reasons:
            pillars.append(_pillar(k, reasons))
    if "trend" not in {p["key"] for p in pillars} or len(pillars) < 2:
        return None
    return _combine(pillars)


def label_key(score: int) -> str:
    return _label(score)[0]


def assess(r: dict) -> dict | None:
    if r.get("missing") or r.get("last") is None:
        return None
    builders = {"trend": _trend, "momentum": _momentum, "rs": _rs, "fundamentals": _fund, "valuation": _val}
    pillars = []
    for key, fn in builders.items():
        reasons = fn(r)
        if reasons:
            pillars.append(_pillar(key, reasons))
    have = {p["key"] for p in pillars}
    if "trend" not in have or len(pillars) < 2:
        return {"score": None, "key": "nodata", "label": "Otillräcklig data", "lay": "För lite kurshistorik",
                "confidence": None, "pillars": pillars, "warnings": [], "invalidation": None,
                "summary": "För lite kurshistorik för ett betyg (kräver cirka 200 handelsdagar).",
                "n_pillars": len(pillars)}

    score = _combine(pillars)
    key, label, lay = _label(score)

    nz = [p for p in pillars if p["score"] != 0]
    sign = 1 if score > 0 else -1 if score < 0 else 0
    agree = sum(1 for p in nz if (p["score"] > 0) == (sign > 0)) if sign else 0
    if sign == 0 or not nz:
        conf = "Låg"
    else:
        share = agree / len(nz)
        conf = "Hög" if (len(nz) >= 3 and share >= 0.8) else "Medel" if share >= 0.6 else "Låg"

    warnings = _warnings(r, score)
    invalid = _invalidation(r, score)
    return {"score": score, "key": key, "label": label, "lay": lay, "confidence": conf, "pillars": pillars,
            "warnings": warnings, "invalidation": invalid, "n_pillars": len(pillars),
            "summary": _summary(r, score, label, conf, pillars, warnings, invalid)}


def _warnings(r, score):
    w = []
    rsi = r.get("rsi14")
    if rsi is not None and rsi >= 70:
        w.append(f"RSI {_f(rsi, 0)}: kursen har stigit snabbt – risk för paus eller återgång, även i en uppåttrend")
    if rsi is not None and rsi <= 30:
        w.append(f"RSI {_f(rsi, 0)}: kursen har fallit snabbt – kan studsa, men det säger inget om att nedgången är över")
    if score <= -20 and rsi is not None and rsi <= 30:
        w.append("Översåld i en nedåttrend: studsar är vanliga men trenden är fortfarande nedåt")
    h = r.get("from_hi52")
    if h is not None and h >= -2 and score > 0:
        w.append("Nära 52-veckorshögsta – styrka, men också mindre marginal om tillväxten skulle missa")
    v = r.get("vol_30d")
    if v is not None and v > 45:
        w.append(f"Hög volatilitet ({_f(v, 0)} % på årsbasis) – stora kursrörelser, ta höjd för det i positionsstorlek")
    dd = r.get("max_dd_1y")
    if dd is not None and dd <= -30:
        w.append(f"Största nedgången senaste året var {_f(dd, 0)} % – räkna med att något liknande kan upprepas")
    bw = r.get("bb_width_pct")
    if bw is not None and bw <= 15:
        w.append("Volatiliteten är ihoptryckt (squeeze) – en större rörelse kan vara nära, men riktningen är oklar")
    vr = r.get("vol_ratio")
    if vr is not None and vr >= 2:
        w.append(f"Ovanligt hög volym ({_f(vr, 1)}× normalt) – något har hänt (rapport, nyhet eller stora aktörer)")
    ne = r.get("next_earnings")
    if ne:
        try:
            days = (datetime.strptime(ne, "%Y-%m-%d").date() - date.today()).days
            if 0 <= days <= 7:
                w.append(f"Rapport om {days} dagar – kursen kan röra sig kraftigt åt endera hållet")
        except ValueError:
            pass
    return w


def _invalidation(r, score):
    stop, sd, s200 = r.get("stop"), r.get("stop_dist"), r.get("sma200")
    last = r.get("last")
    if score >= -20 and stop is not None:
        t = f"Bilden försvagas om kursen stänger under {_f(stop, 2)} (ATR-stop, {_f(sd)} % från nu)"
        if s200 is not None and s200 < last:
            t += f", och tydligt om den tappar 200-dagarssnittet vid {_f(s200, 2)}"
        return t + "."
    if s200 is not None and last and s200 > last:
        return f"Bilden förbättras först om kursen tar sig över 200-dagarssnittet vid {_f(s200, 2)} ({'+' if s200 > last else ''}{_f((s200 / last - 1) * 100)} % från nu)."
    if stop is not None:
        return f"Fortsätter kursen under {_f(stop, 2)} är nedtrenden intakt."
    return None


def _summary(r, score, label, conf, pillars, warnings, invalid):
    by = {p["key"]: p for p in pillars}
    parts = [f"{r['ticker']} har ett {label.lower()} läge ({score:+d} av 100) med {conf.lower()} samstämmighet."]
    t = by.get("trend")
    if t:
        parts.append("Trenden pekar uppåt." if t["score"] >= 1 else "Trenden pekar nedåt." if t["score"] <= -1 else "Trenden är blandad.")
    m, s = by.get("momentum"), by.get("rs")
    bits = []
    if m:
        bits.append("momentumet är positivt" if m["score"] > 0 else "momentumet är negativt" if m["score"] < 0 else "momentumet är neutralt")
    if s:
        bits.append("aktien går bättre än jämförelseindexet" if s["score"] > 0 else "aktien går sämre än jämförelseindexet" if s["score"] < 0 else "aktien går ungefär som indexet")
    if bits:
        parts.append(" och ".join(bits).capitalize() + ".")
    f, v = by.get("fundamentals"), by.get("valuation")
    if f:
        parts.append("Rapporterna stöder bilden." if f["score"] > 0 else "Rapporterna talar emot bilden." if f["score"] < 0 else "Rapporterna är blandade.")
    if v and v["score"] != 0:
        parts.append("Värderingen är relativt hög." if v["score"] < 0 else "Värderingen är relativt låg.")
    if warnings:
        parts.append("Att tänka på: " + warnings[0] + ".")
    if invalid:
        parts.append(invalid)
    return " ".join(parts).replace("..", ".")
