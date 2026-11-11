"""Exporterar en ögonblicksbild av allt i appen som JSON och Markdown, så att
Claude (eller du) kan läsa in hela marknadsläget och göra en analys.
Filerna skrivs till data/export/ efter varje uppdatering."""
from __future__ import annotations

import json
from datetime import datetime

from . import backtest, db, digest, exercises, journal, macro, metrics, paper, portfolio, service
from .providers import get_provider

PERIOD_COLS = [("r_1d", "1d"), ("r_1w", "1v"), ("r_1m", "1m"), ("r_3m", "3m"), ("r_6m", "6m"),
               ("r_ytd", "I år"), ("r_1y", "1 år")]


def _n(v, dec=1, sign=False, suffix=""):
    if v is None:
        return "–"
    s = f"{v:+,.{dec}f}" if sign else f"{v:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",") + suffix


def _sig(t: dict) -> str:
    s = t.get("signal")
    if not s or s.get("score") is None:
        return "–"
    return f"{s['score']:+d} {s['label']}"


def signals(rows: list[dict]) -> dict:
    live = [r for r in rows if not r.get("missing")]

    def pick(cond):
        return [r["ticker"] for r in live if cond(r)]

    return {
        "overbought_rsi_70": pick(lambda r: r.get("rsi14") is not None and r["rsi14"] >= 70),
        "oversold_rsi_30": pick(lambda r: r.get("rsi14") is not None and r["rsi14"] <= 30),
        "near_52w_high_within_3pct": pick(lambda r: r.get("from_hi52") is not None and r["from_hi52"] >= -3),
        "below_sma200": pick(lambda r: r.get("vs_sma200") is not None and r["vs_sma200"] < 0),
        "big_day_move_3pct": pick(lambda r: r.get("r_1d") is not None and abs(r["r_1d"]) >= 3),
        "high_volume_2x": pick(lambda r: r.get("vol_ratio") is not None and r["vol_ratio"] >= 2),
    }


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def _macro_compact():
    m = macro.snapshot()
    for c in m["cards"] + m["derived"]:
        c.pop("spark", None)
    return m


def _portfolio_compact():
    p = portfolio.summary()
    if not p["holdings"]:
        return None
    for h in p["holdings"]:
        h.pop("suggestions", None)
    return p


def _journal_compact():
    j = journal.list_entries()
    return j if j["entries"] else None


def build() -> dict:
    lists = []
    notes = {}
    with db.connect() as con:
        for r in con.execute("SELECT ticker, text, updated_at FROM notes WHERE text != ''").fetchall():
            notes[r["ticker"]] = {"text": r["text"], "updated_at": r["updated_at"]}
    for lst in service.lists_all():
        ov = service.overview(lst["id"])
        if not ov:
            continue
        for t in ov["tickers"]:
            t.pop("spark", None)
            fund = service.fund_get(t["ticker"])
            dg = digest.build(fund, t.get("currency", ""))
            t["quarterly_digest"] = dg["headline"] if dg["has_data"] else None
            t["quarterly_flags"] = dg["flags"]
        ov["signals"] = signals(ov["tickers"])
        try:
            bt = backtest.run(lst["id"], 21)
            ov["backtest"] = None if bt.get("error") else {k: bt[k] for k in (
                "horizon", "tickers_used", "samples", "baseline", "buckets", "groups", "edge", "strategy", "caveats")}
        except Exception:  # noqa: BLE001
            ov["backtest"] = None
        lists.append(ov)
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": get_provider().name,
        "demo_data": get_provider().name == "demo",
        "notes_on_method": [
            "Avkastning i procent, i varje värdepappers egen handelsvaluta (ingen valutaomräkning).",
            "Kurser är justerade för utdelningar och splittar. Perioder räknas som kalenderperioder bakåt från senaste kursdatum (jämförelsekurs = sista stängning på eller före datumet) "
            "(1v = 7 dagar, 1m/3m/6m/1år = lika många månader/år bakåt); 'I år' räknas från sista stängningen föregående år.",
            "Gruppavkastning är likaviktat medelvärde av gruppens bolag/ETF:er.",
            "Relativ styrka (rs) = avkastning minus jämförelseindexets avkastning, i procentenheter.",
            "Kvartalssammanfattningar bygger på rapporterade nyckeltal från datakällan, inte på rapporttexten.",
            "Signalbetyg (−100…+100) är ett regelbaserat sammandrag av fem pelare (trend, momentum, relativ styrka, "
            "fundamenta, värdering; varje pelare −2…+2). Reglerna är standardregler, INTE optimerade eller backtestade, "
            "och betyget är ett beskrivande mätetal – inte en rekommendation. Värderingspelaren är relativ mot "
            "jämförelsebolag i samma lista/grupp, inte ett absolut mått.",
            "Backtesten gäller bara den tekniska delen av betyget (trend, momentum, relativ styrka), mäter vad som hände "
            "efter signalen och jämför med slumpen. Den är inte en prognos; läs förbehållen (urval av dagens bolag, överlapp, kort historik).",
            "Gratisdata kan vara fördröjd (ofta ca 15 min) och innehålla fel – kontrollera viktiga siffror.",
        ],
        "lists": lists,
        "macro": _safe(lambda: _macro_compact()),
        "portfolio": _safe(lambda: _portfolio_compact()),
        "journal": _safe(lambda: _journal_compact()),
        "paper": _safe(lambda: _paper_compact()),
        "trader": _safe(lambda: _trader_compact()),
        "pro": _safe(lambda: _pro_compact()),
        "samband": _safe(lambda: _samband_compact()),
        "upcoming_earnings_45d": service.upcoming_earnings(45),
        "notes": notes,
    }


def to_markdown(snap: dict) -> str:
    L: list[str] = []
    L.append("# Marknadsradar – ögonblicksbild")
    L.append(f"Genererad: {snap['generated_at']} · Datakälla: {snap['provider']}")
    if snap.get("demo_data"):
        L.append("\n> **OBS: DEMO-DATA.** Siffrorna är påhittade och får inte användas för analys.")
    L.append("\n## Så ska siffrorna läsas")
    L += [f"- {x}" for x in snap["notes_on_method"]]

    for ov in snap["lists"]:
        lst = ov["list"]
        L.append(f"\n## {lst['name']}" + (f" (jämförelseindex: {lst['benchmark']})" if lst["benchmark"] else ""))
        if lst.get("description"):
            L.append(f"_{lst['description']}_")
        L.append(f"Senaste kursdatum: {ov['updated'] or '–'}")
        b = ov["breadth"]
        if b["n"]:
            L.append(f"Marknadsbredd ({b['n']} värdepapper): {_n(b['above_sma50'], 0)} % över 50-dagars medelvärde, "
                     f"{_n(b['above_sma200'], 0)} % över 200-dagars, {_n(b['advancers_1d'], 0)} % steg senaste dagen.")
        bm = ov.get("benchmark")
        if bm and not bm.get("missing"):
            L.append(f"Jämförelseindex {bm['ticker']}: " + ", ".join(
                f"{lab} {_n(bm.get(k), 1, True, ' %')}" for k, lab in PERIOD_COLS))
        if ov["missing"]:
            L.append(f"Saknar kursdata: {', '.join(ov['missing'])}")

        L.append("\n### Grupper (likaviktat, avkastning i %)")
        L.append("| Grupp | Antal | " + " | ".join(lab for _, lab in PERIOD_COLS) + " | Rel. 1m | Rel. 3m |")
        L.append("|---|---|" + "---|" * (len(PERIOD_COLS) + 2))
        for g in ov["groups"]:
            L.append(f"| {g['group']} | {g['count']} | " + " | ".join(_n(g.get(k), 1, True) for k, _ in PERIOD_COLS)
                     + f" | {_n(g.get('rs_1m'), 1, True)} | {_n(g.get('rs_3m'), 1, True)} |")

        live = [t for t in ov["tickers"] if not t.get("missing") and t.get("r_1m") is not None]
        if len(live) >= 4:
            srt = sorted(live, key=lambda t: t["r_1m"], reverse=True)
            L.append("\n**Starkast senaste månaden:** " + ", ".join(
                f"{t['ticker']} ({_n(t['r_1m'], 1, True, ' %')})" for t in srt[:3]))
            L.append("**Svagast senaste månaden:** " + ", ".join(
                f"{t['ticker']} ({_n(t['r_1m'], 1, True, ' %')})" for t in srt[-3:][::-1]))

        sg = ov["signals"]
        labels = {
            "overbought_rsi_70": "RSI ≥ 70 (överköpt)", "oversold_rsi_30": "RSI ≤ 30 (översåld)",
            "near_52w_high_within_3pct": "Inom 3 % från 52-veckorshögsta", "below_sma200": "Under 200-dagars medelvärde",
            "big_day_move_3pct": "Dagsrörelse ≥ 3 %", "high_volume_2x": "Volym ≥ 2× normalt",
        }
        sig_lines = [f"- {labels[k]}: {', '.join(v)}" for k, v in sg.items() if v]
        if sig_lines:
            L.append("\n### Signaler")
            L += sig_lines

        scored = [t for t in ov["tickers"] if (t.get("signal") or {}).get("score") is not None]
        if scored:
            ss = ov.get("signal_summary", {})
            L.append("\n### Signalbetyg (regelbaserat, ej backtestat)")
            L.append(f"Fördelning: {ss.get('positive', 0)} positiva, {ss.get('neutral', 0)} neutrala, {ss.get('negative', 0)} negativa.")
            L.append("| Ticker | Poäng | Läge | Samstämmighet | Trend | Momentum | Rel. styrka | Fundamenta | Värdering | Invalidering |")
            L.append("|---|---|---|---|---|---|---|---|---|---|")
            for t in sorted(scored, key=lambda x: -x["signal"]["score"]):
                sg = t["signal"]
                ps = {p["key"]: p["score"] for p in sg["pillars"]}
                cell = lambda k: (f"{ps[k]:+d}" if k in ps else "–")
                L.append(f"| {t['ticker']} | {sg['score']:+d} | {sg['label']} | {sg['confidence']} | {cell('trend')} | {cell('momentum')} | "
                         f"{cell('rs')} | {cell('fundamentals')} | {cell('valuation')} | {sg.get('invalidation') or '–'} |")
            warns = [(t["ticker"], w) for t in scored for w in t["signal"]["warnings"]]
            if warns:
                L.append("\nVarningar/observationer:")
                L += [f"- {tk}: {w}" for tk, w in warns]

        bt = ov.get("backtest")
        if bt:
            L.append(f"\n### Backtest av teknisk signal ({bt['horizon']} handelsdagar framåt, {bt['tickers_used']} värdepapper, {bt['samples']} observationer)")
            L.append("| Signalklass | Observationer | Snitt-avkastning % | Träffsäkerhet % (andel positiva) |")
            L.append("|---|---|---|---|")
            b0 = bt["baseline"]
            L.append(f"| Alla dagar (jämförelse) | {b0.get('n', 0)} | {_n(b0.get('avg'), 2, True)} | {_n(b0.get('hit'), 0)} |")
            for b in bt["buckets"]:
                L.append(f"| {b['label']} | {b.get('n', 0)} | {_n(b.get('avg'), 2, True)} | {_n(b.get('hit'), 0)} |")
            L.append(f"Slutsats: {bt['edge'].get('text', '–')}")
            st = bt["strategy"]
            L.append(f"Enkel strategi (äg vid poäng ≥ +20, annars kassa; 0,1 % kostnad per byte) mot att bara äga, jämnt viktat {st['from']}–{st['to']}: "
                     f"{_n(st['ret_strategy'], 0, True, ' %')} mot {_n(st['ret_bh'], 0, True, ' %')}; största nedgång {_n(st['dd_strategy'], 0, False, ' %')} mot {_n(st['dd_bh'], 0, False, ' %')}.")

        L.append("\n### Alla värdepapper")
        L.append("| Ticker | Namn | Grupp | Kurs | Valuta | 1d | 1m | 3m | I år | RSI | mot SMA200 | från 52v-topp | P/E | Signal | Nästa rapport |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for t in ov["tickers"]:
            if t.get("missing"):
                L.append(f"| {t['ticker']} | {t['name']} | {t['group']} | saknar data ||||||||||||")
                continue
            L.append(f"| {t['ticker']} | {t['name']} | {t['group']} | {_n(t['last'], 2)} | {t.get('currency') or ''} | "
                     f"{_n(t.get('r_1d'), 1, True)} | {_n(t.get('r_1m'), 1, True)} | {_n(t.get('r_3m'), 1, True)} | "
                     f"{_n(t.get('r_ytd'), 1, True)} | {_n(t.get('rsi14'), 0)} | {_n(t.get('vs_sma200'), 1, True)} | "
                     f"{_n(t.get('from_hi52'), 1, True)} | {_n(t.get('pe'), 1)} | {_sig(t)} | {t.get('next_earnings') or '–'} |")

        digs = [t for t in ov["tickers"] if t.get("quarterly_digest")]
        if digs:
            L.append("\n### Senaste kvartalsrapporter (från rapporterade nyckeltal)")
            for t in digs:
                L.append(f"- **{t['ticker']}** ({t['name']}): {t['quarterly_digest']}")
                for f in t["quarterly_flags"]:
                    L.append(f"  - ⚑ {f}")

    mc = snap.get("macro")
    if mc:
        L.append("\n## Makro (marknadens 'väder')")
        rg = mc.get("regime")
        if rg:
            L.append(f"**Regim: {rg['label']}** ({rg['score']:+.1f}). {rg['lay']}")
            L += [f"- {r['text']}" for r in rg["reasons"]]
        L.append("| Mått | Nivå | Förändring 1d | Förändring 1m | Percentil 1 år | Tolkning |")
        L.append("|---|---|---|---|---|---|")
        for c in mc["cards"] + mc["derived"]:
            if c.get("missing"):
                continue
            L.append(f"| {c['name']} | {_n(c['last'], 2)} {c.get('unit', '')} | {_n(c.get('ch1d'), 2, True)} | {_n(c.get('ch1m'), 2, True)} | {_n(c.get('pctile'), 0)} | {c.get('text', '')} |")
    pf = snap.get("portfolio")
    if pf:
        t = pf["totals"]
        L.append("\n## Min portfölj")
        L.append(f"Värde (de {t['n_valued']} innehav som har kurs): {_n(t['value_sek'], 0)} kr. {t['n_unmapped']} innehav saknar ticker och är inte med i beräkningarna.")
        L.append("| Ticker | Namn | Antal | Värde (kr) | Vikt % | Vinst/förlust % | Signal | Sektor |")
        L.append("|---|---|---|---|---|---|---|---|")
        for h in pf["holdings"]:
            sg = h.get("signal") or {}
            L.append(f"| {h['ticker'] or '(saknar ticker)'} | {h.get('name') or ''} | {_n(h['qty'], 2)} | {_n(h.get('value_sek'), 0)} | {_n(h.get('weight'), 1)} | "
                     f"{_n(h.get('pl_pct'), 1, True)} | {('%+d %s' % (sg['score'], sg['label'])) if sg.get('score') is not None else '–'} | {h.get('sector') or '–'} |")
        c = pf.get("concentration")
        if c:
            L.append(f"Koncentration: största innehav {_n(c['top1'], 0)} %, tre största {_n(c['top3'], 0)} %, effektivt antal innehav {_n(c['effective_n'], 1)}.")
        rk = pf.get("risk")
        if rk:
            L.append(f"Risk (konstanta vikter, lokala valutor): volatilitet {_n(rk['vol'], 1)} % per år, största nedgång 1 år {_n(rk['max_dd_1y'], 1)} %, beta mot S&P 500 {_n(rk.get('beta'), 2)}, spridningsvinst {_n(rk.get('diversification'), 2)}×.")
        L += [f"- ({w['level']}) {w['text']}" for w in pf["warnings"]]
    jn = snap.get("journal")
    if jn:
        st = jn["stats"]
        L.append("\n## Beslutsjournal")
        L.append(f"{st['total']} beslut, {st['open']} öppna, {st['reviewed']} granskade, {st['due']} som är dags att granska."
                 + (f" Träffsäkerhet bland granskade köp/sälj: {_n(st['hit_rate'], 0)} % (snitt {_n(st['avg_dir_return'], 1, True)} %), preliminärt tills ≥ 20 beslut." if st["hit_rate"] is not None else ""))
        for e in jn["entries"][:30]:
            L.append(f"- {e['created'][:10]} {e['action']} **{e['ticker']}** @ {_n(e['price'], 2)} (signal då: {e['signal_score'] if e['signal_score'] is not None else '–'}), "
                     f"{e['status']}{', ' + _n(e['dir_return'], 1, True, ' %') + ' i beslutets riktning' if e.get('dir_return') is not None else ''}. "
                     f"Tes: {e['thesis'] or '–'} | Ändrar åsikt om: {e['invalidation'] or '–'}" + (f" | Lärdom: {e['lesson']}" if e["lesson"] else ""))

    pp = snap.get("paper")
    if pp:
        L.append("\n## Övningsportföljer (virtuella pengar)")
        L.append("Pappershandel för att öva process. Poäng räknas på process (plan, risk ≤ 2 %, position ≤ 25 %, granskning), inte på vinst. Courtage 0,1 % ingår.")
        for s in pp:
            L.append(f"\n### {s['name']}" + (f" – {s['strategy']}" if s["strategy"] else ""))
            L.append(f"Start {_n(s['start_capital'], 0)} kr, värde nu {_n(s['equity'], 0)} kr ({_n(s['return_pct'], 1, True)} %), index sedan start {_n(s['index_return_pct'], 1, True)} %, "
                     f"största nedgång {_n(s['max_drawdown_pct'], 1, True)} %, processpoäng {_n(s['process_avg'], 0)} (snitt över stängda affärer).")
            for t in s["open"]:
                L.append(f"- Öppen **{t['ticker']}**: {_n(t['qty'], 0)} st @ {_n(t['entry'], 2)}, stopp {_n(t['stop'], 2)}, {_n(t['pnl_pct'], 1, True)} % ({_n(t['r'], 1, True)} R), risk vid köp {_n(t['risk_pct'], 1)} %. Tes: {t['thesis']} | Fel om: {t['invalidation']}")
            for t in s["closed"][:15]:
                L.append(f"- Stängd **{t['ticker']}** ({t['reason']}): {_n(t['pnl_pct'], 1, True)} % ({_n(t['r'], 1, True)} R), processpoäng {t['process_points']}. Tes: {t['thesis']}" + (f" | Lärdom: {t['lesson']}" if t["lesson"] else ""))

    tr = snap.get("trader")
    if tr and (tr["playbook"] or tr["reviews"]):
        L.append("\n## Spelbok och månadsgranskningar")
        if tr["playbook"]:
            L.append("Mina egna handelsregler (skrivna av mig):")
            for t, x in tr["playbook"].items():
                L.append(f"- **{t}:** {x}")
            L.append("Gränser: " + ", ".join(f"{k} {_n(v, 1)} %" for k, v in tr["limits"].items()))
        for r in tr["reviews"]:
            L.append(f"- Månadsgranskning {r['month']}: bra: {r['good']} | sämre: {r['bad']} | ändrar: {r['change']}")

    pr = snap.get("pro")
    if pr and pr["n"]:
        L.append("\n## Handelsstatistik (övningsportföljer)")
        L.append(f"{pr['n']} stängda affärer. Snitt {_n(pr['mean_r'], 2, True)} R (95 % intervall {_n(pr['r_lo'], 2, True)} till {_n(pr['r_hi'], 2, True)}), träffandel {_n(pr['win_rate'], 0)} %, "
                 f"längsta förlustserie {pr['longest_losing']}, processsnitt senaste 30: {_n(pr['proc'], 0) if pr['proc'] is not None else '–'}.")
        L.append(f"Ärligt utlåtande: {pr['verdict']} {pr['verdict_text']}")
        if pr["decision"]:
            L.append(f"Mitt beslut ({pr['decision']['ts']}): {pr['decision']['label']}. Motivering: {pr['decision']['reflection']}")

    sb = snap.get("samband")
    if sb and (sb["edges"] or sb["sig"]):
        L.append("\n## Samband mellan bolag")
        if sb["tests"]:
            L.append(f"Lead-lag (rensat från marknaden, {sb['tests']} tester, FDR-korrigerat): {len(sb['sig'])} samband klarar korrigeringen, ungefär {_n(sb['exp_false'], 1)} väntas vara falska. Behandla dem som hypoteser.")
        for x in sb["sig"]:
            L.append(f"- {x['a']} → {x['b']}, {x['lag']} d, r={_n(x['r'], 2, True)}, {'stabil' if x['stable'] else 'ej stabil'}")
        if sb["edges"]:
            L.append(f"Relationer jag lagt in ({sb['n_reviewed']} av {sb['n_tickers']} bolag genomgångna; saknade relationer betyder inte att de inte finns):")
            for e in sb["edges"]:
                L.append(f"- {e['a']} {e['verb']} {e['b']}" + (f" ({_n(e['share_pct'], 0)} % av omsättningen)" if e["share_pct"] is not None else "") + f" [{e['confidence']}, {e['as_of'] or 'datum saknas'}] källa: {e['source_url']}")

    if snap["upcoming_earnings_45d"]:
        L.append("\n## Kommande rapporter (45 dagar)")
        for e in snap["upcoming_earnings_45d"]:
            L.append(f"- {e['date']}: {e['ticker']} ({e['name']})")
    if snap["notes"]:
        L.append("\n## Mina anteckningar")
        for t, n in snap["notes"].items():
            L.append(f"### {t}\n{n['text']}")
    return "\n".join(L) + "\n"


def _trader_compact() -> dict:
    from . import trader
    pb = trader.playbook_get()
    mo = trader.monthly_list()
    revs = [{"month": m["month"], **m["review"]} for m in mo["months"] if m["done"]] + [{"month": m["month"], **m["review"]} for m in mo["older"]]
    return {"playbook": {x["title"]: x["text"] for x in pb["sections"] if x["text"].strip()},
            "limits": {v["label"]: v["value"] for v in pb["limits"].values()} if any(x["text"].strip() for x in pb["sections"]) else {},
            "reviews": sorted(revs, key=lambda r: r["month"], reverse=True)[:6]}


def _samband_compact() -> dict:
    from . import relations
    cov = relations.coverage()
    with db.connect() as con:
        edges = [dict(r) for r in con.execute("SELECT * FROM relations ORDER BY id DESC LIMIT 60").fetchall()]
    for e in edges:
        e["verb"] = relations.TYPES.get(e["rtype"], e["rtype"])
    try:
        ll = relations.leadlag_top(12)
    except Exception:  # noqa: BLE001
        ll = {"sig": [], "n_tests": 0, "expected_false_sig": 0}
    return {"edges": edges, "n_reviewed": cov["n_reviewed"], "n_tickers": cov["n_tickers"], "sig": ll["sig"], "tests": ll.get("n_tests", 0), "exp_false": ll.get("expected_false_sig", 0)}


def _pro_compact() -> dict:
    from . import pro
    p = pro.profile()
    st = p["stats"]
    if not st.get("n"):
        return {"n": 0}
    return {"n": st["n"], "mean_r": st["mean_r"], "r_lo": st["r_lo"], "r_hi": st["r_hi"], "win_rate": st["win_rate"], "longest_losing": st["longest_losing"],
            "proc": p["process_last30"], "verdict": p["verdict"]["title"] + ".", "verdict_text": p["verdict"]["text"], "decision": p["decision"]}


def _paper_compact() -> list[dict]:
    out = []
    for s in paper.list_portfolios()["portfolios"]:
        d = paper.detail(s["id"])
        out.append({"name": s["name"], "strategy": s["strategy"], "created": s["created"], "start_capital": s["cash0"], "equity": s["equity"],
                    "return_pct": s["ret"], "index_return_pct": s["bench"], "max_drawdown_pct": s["max_dd"], "open_risk_pct": s["risk_open_pct"],
                    "process_avg": s["process_avg"],
                    "open": [{"ticker": t["ticker"], "qty": t["qty"], "entry": t["entry_price"], "stop": t["stop"], "pnl_pct": t["pnl_pct"], "r": t["r"],
                              "risk_pct": t["risk_pct"], "thesis": t["thesis"], "invalidation": t["invalidation"]} for t in d["open"]],
                    "closed": [{"ticker": t["ticker"], "pnl_pct": t["pnl_pct"], "r": t["r"], "reason": t["exit_reason"], "process_points": t["points"]["total"],
                                "thesis": t["thesis"], "lesson": t["lesson"]} for t in d["closed"][:30]]})
    return out


def write_exports() -> dict:
    snap = metrics.clean(build())
    db.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    (db.EXPORT_DIR / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    (db.EXPORT_DIR / "snapshot.md").write_text(to_markdown(snap), encoding="utf-8")
    return snap
