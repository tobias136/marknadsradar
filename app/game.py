"""Spelläge ('Karriär'): ett frivilligt tillägg som gör inlärningen till nivåer.

Designprinciper:
- Poäng och nivåer ges för att LÄRA, DOKUMENTERA och GRANSKA, aldrig för antal affärer.
- Resultatuppdrag kräver stora urval (≥ 20 granskade beslut) så att tur inte belönas.
- Allt räknas fram ur dina egna data (journal, portfölj, läsning, quiz). Inget går att 'fuska' bort
  utan att faktiskt skriva tes, invalideringsnivå och lärdom.
- Spelläget kan stängas av helt under Inställningar. Då loggas inget och fliken döljs."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import db, exercises, journal, paper, portfolio, pro, quizdata, trader

LEVELS = [
    (1, "Nybörjare", "Lär dig läsa kartan"),
    (2, "Kartläsare", "Förstå trend och relativ styrka"),
    (3, "Trendspanare", "Använd signalbetyget och testa regler"),
    (4, "Analytiker", "Skriv tes och förstå värdering"),
    (5, "Riskhanterare", "Bygg och granska en portfölj"),
    (6, "Lärling", "Skriv dina regler och bygg vanan"),
    (7, "Disciplinerad", "Visa disciplin över många affärer"),
    (8, "Riskchef", "Styr risken, även när det går fel"),
    (9, "Systematiker", "Mät dig själv ärligt"),
    (10, "Handlare", "Visa en professionell process"),
]
TABS_ALL = {"overview", "compare", "reports", "stock", "samband", "macro", "portfolio", "journal", "backtest", "claude", "glossary", "practice", "paper"}
_ctx_cache: dict = {"t": 0.0, "v": None}


def enabled() -> bool:
    return (db.get_setting("game", "1") or "1") == "1"


def set_enabled(on: bool) -> None:
    db.set_setting("game", "1" if on else "0")


def record(event: str, key: str) -> None:
    if not enabled():
        return
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO progress(event,key,ts) VALUES(?,?,?)", (event, str(key)[:80], datetime.now(timezone.utc).isoformat()))
    invalidate_light()


def invalidate() -> None:
    _ctx_cache["t"] = 0.0


def invalidate_light() -> None:
    # läsningar ändrar inte journal/portfölj; behåll cachen för de tunga delarna
    pass


def _events() -> dict[str, set[str]]:
    with db.connect() as con:
        rows = con.execute("SELECT event, key FROM progress").fetchall()
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(r["event"], set()).add(r["key"])
    return out


def _heavy() -> dict:
    now = time.time()
    if _ctx_cache["v"] is not None and now - _ctx_cache["t"] < 30:
        return _ctx_cache["v"]
    j = journal.list_entries()
    entries = j["entries"]
    reviewed = [e for e in entries if e["status"] == "reviewed"]
    v = {
        "j_thesis": sum(1 for e in entries if len(e["thesis"].strip()) >= 30),
        "j_invalid": sum(1 for e in entries if len(e["invalidation"].strip()) >= 10),
        "j_total": len(entries),
        "j_reviewed": len(reviewed),
        "j_reviewed_lesson": sum(1 for e in reviewed if len(e["lesson"].strip()) >= 20),
        "j_all_invalid": bool(entries) and all(len(e["invalidation"].strip()) >= 10 for e in entries),
        "j_stats": j["stats"],
        "pf": portfolio.game_flags(),
        "ex": exercises.stats(),
        "paper": paper.game_flags(),
        "trader": trader.game_flags(),
        "pro": pro.game_flags(),
    }
    _ctx_cache.update(t=now, v=v)
    return v


def _quiz_state() -> dict[int, dict]:
    with db.connect() as con:
        res = {r["qid"]: r["correct"] for r in con.execute("SELECT qid, correct FROM quiz_results").fetchall()}
    out = {}
    for n, _, _ in LEVELS:
        qs = [q for q in quizdata.QUIZ if q["level"] == n]
        c = sum(1 for q in qs if res.get(q["id"]))
        a = sum(1 for q in qs if q["id"] in res)
        out[n] = {"total": len(qs), "answered": a, "correct": c, "passed": c >= 4}
    return out


def _quests(ev: dict[str, set[str]], h: dict, quiz: dict) -> list[dict]:
    g = ev.get("gloss", set())
    tabs, stocks = ev.get("tab", set()), ev.get("stock", set())

    def has(*keys):
        return all(k in g for k in keys)

    def cnt(have, need):
        return f"{min(have, need)}/{need}"

    st = h["j_stats"]
    pf = h["pf"]
    ex, pp, tr, px = h["ex"], h["paper"], h["trader"], h["pro"]
    Q = []

    def q(level, qid, title, desc, done, progress, xp, where=""):
        Q.append({"level": level, "id": qid, "title": title, "desc": desc, "done": bool(done), "progress": progress, "xp": xp, "where": where})

    def acc(kind, need_n, need_pct):
        e = ex[kind]
        ok = e["n"] >= need_n and e["recent_n"] and e["recent_correct"] / e["recent_n"] * 100 >= need_pct
        return ok, (f"{e['n']}/{need_n}" if e["n"] < need_n else f"{e['recent_correct']}/{e['recent_n']} senaste")

    # nivå 1
    q(1, "q1_gloss", "Läs fem förklaringar", "Klicka på (?)-ikonerna eller öppna Ordlistan och läs minst fem olika förklaringar.", len(g) >= 5, cnt(len(g), 5), 20, "overview")
    q(1, "q1_tabs", "Besök fem flikar", "Titta runt i appen: Översikt, Jämför, Rapporter, Aktie, Makro och så vidare.", len(tabs) >= 5, cnt(len(tabs), 5), 20, "overview")
    q(1, "q1_chart", "Gör fem diagramövningar", "Fliken Öva → Läs diagrammet. Rätt eller fel spelar ingen roll här, det viktiga är att du tittar och tänker.", ex["chart"]["n"] >= 5, cnt(ex["chart"]["n"], 5), 20, "practice")
    q(1, "q1_quiz", "Klara quizet för nivå 1", "Minst 4 av 5 rätt.", quiz[1]["passed"], f"{quiz[1]['correct']}/4", 40, "game")
    # nivå 2
    q(2, "q2_list", "Skapa en egen lista", "Klicka '+ Ny lista' i sidomenyn och lägg in bolag du är nyfiken på.", bool(ev.get("list")), "1/1" if ev.get("list") else "0/1", 25, "overview")
    q(2, "q2_stocks", "Öppna tre aktiesidor", "Välj bolag på fliken Aktie eller klicka i tabellen.", len(stocks) >= 3, cnt(len(stocks), 3), 25, "stock")
    q(2, "q2_trend", "Läs om SMA, relativ styrka och RS-linje", "Öppna de tre förklaringarna i Ordlistan.", has("sma", "rel", "rsline"),
      cnt(sum(1 for k in ("sma", "rel", "rsline") if k in g), 3), 25, "glossary")
    ok, pr = acc("chart", 15, 70)
    q(2, "q2_chart", "Läs diagram: minst 70 % rätt", "Gör minst 15 diagramövningar och håll minst 70 % rätt på de senaste 20.", ok, pr, 35, "practice")
    q(2, "q2_quiz", "Klara quizet för nivå 2", "Minst 4 av 5 rätt.", quiz[2]["passed"], f"{quiz[2]['correct']}/4", 40, "game")
    # nivå 3
    q(3, "q3_sig", "Förstå signalbetyget", "Läs förklaringarna för signalbetyg, pelare, samstämmighet och invalideringsnivå.", has("signal", "pillars", "confidence", "invalid"),
      cnt(sum(1 for k in ("signal", "pillars", "confidence", "invalid") if k in g), 4), 30, "glossary")
    q(3, "q3_stocks", "Granska sex aktier", "Öppna sex olika aktiesidor och läs signalpanelen.", len(stocks) >= 6, cnt(len(stocks), 6), 30, "stock")
    q(3, "q3_backtest", "Kör en backtest", "Gå till fliken Backtest och läs resultatet, särskilt förbehållen.", bool(ev.get("backtest")), "1/1" if ev.get("backtest") else "0/1", 30, "backtest")
    q(3, "q3_skeptic", "Var skeptisk", "Läs förklaringarna för backtest, träffsäkerhet och överanpassning.", has("backtest", "hitrate", "overfit"),
      cnt(sum(1 for k in ("backtest", "hitrate", "overfit") if k in g), 3), 30, "glossary")
    q(3, "q3_stopex", "Sätt tre stopp själv", "Öva → Stoppövning. Poängen ges för att du placerar stoppet utanför dagsbruset, inte för hur det gick efteråt.", ex["stopex"]["n"] >= 3, cnt(ex["stopex"]["n"], 3), 25, "practice")
    q(3, "q3_stopsim", "Kör stoppsimulatorn", "Öva → Stoppsimulator. Jämför stopp-typer över hundratals affärer i stället för ett enda utfall.", ex["stopsim"]["n"] >= 1, cnt(ex["stopsim"]["n"], 1), 25, "practice")
    q(3, "q3_quiz", "Klara quizet för nivå 3", "Minst 4 av 5 rätt.", quiz[3]["passed"], f"{quiz[3]['correct']}/4", 40, "game")
    # nivå 4
    q(4, "q4_thesis", "Skriv tre beslut med tes", "Logga tre beslut i journalen med en tes på minst 30 tecken.", h["j_thesis"] >= 3, cnt(h["j_thesis"], 3), 40, "journal")
    q(4, "q4_invalid", "Bestäm i förväg vad som skulle ändra din åsikt", "Fyll i 'vad skulle få mig att ändra mig' (minst 10 tecken) i tre beslut.", h["j_invalid"] >= 3, cnt(h["j_invalid"], 3), 40, "journal")
    q(4, "q4_val", "Förstå värdering", "Läs förklaringarna för P/E, värderingspercentil och fritt kassaflöde.", has("pe", "valpct", "fcf"),
      cnt(sum(1 for k in ("pe", "valpct", "fcf") if k in g), 3), 20, "glossary")
    ok, pr = acc("risk", 8, 60)
    q(4, "q4_risk", "Riskräknaren: minst 60 % rätt", "Gör minst 8 uppgifter i riskräknaren och håll minst 60 % rätt på de senaste 20.", ok, pr, 40, "practice")
    q(4, "q4_cards", "Repetera 25 kort", "Öva → Repetitionskort. Korten du missar kommer tillbaka oftare.", ex["card"]["n"] >= 25, cnt(ex["card"]["n"], 25), 25, "practice")
    q(4, "q4_quiz", "Klara quizet för nivå 4", "Minst 4 av 5 rätt.", quiz[4]["passed"], f"{quiz[4]['correct']}/4", 40, "game")
    # nivå 5
    q(5, "q5_hold", "Lägg in tre innehav", "Lägg till innehav manuellt eller via CSV så att tre har kurs och värde.", pf["n"] >= 3, cnt(pf["n"], 3), 40, "portfolio")
    q(5, "q5_conc", "Ingen position över 25 %", "Med minst tre värderade innehav: inget enskilt bolag över 25 % av portföljen.", pf["n"] >= 3 and (pf["top1"] or 100) < 25,
      "ok" if pf["n"] >= 3 and (pf["top1"] or 100) < 25 else ("största " + (f"{pf['top1']:.0f} %" if pf["top1"] else "–")), 40, "portfolio")
    q(5, "q5_size", "Räkna ut en positionsstorlek", "Använd positionsstorlekskalkylatorn på portföljfliken.", bool(ev.get("possize")), "1/1" if ev.get("possize") else "0/1", 20, "portfolio")
    q(5, "q5_macro", "Läs av makroläget", "Öppna fliken Makro och läs förklaringarna för VIX och regim.", "macro" in tabs and has("vix", "regime"),
      cnt(("macro" in tabs) + sum(1 for k in ("vix", "regime") if k in g), 3), 20, "macro")
    ok, pr = acc("flaw", 6, 60)
    q(5, "q5_flaw", "Hitta felet: minst 60 % rätt", "Gör minst 6 portföljer i Hitta felet och håll minst 60 % rätt på de senaste 20.", ok, pr, 35, "practice")
    q(5, "q5_paper", "Öppna tre övningsaffärer med plan", "Skapa en övningsportfölj och öppna tre positioner med tes, stopp, risk högst 2 % och position högst 25 %.", pp["good_entries"] >= 3, cnt(pp["good_entries"], 3), 40, "paper")
    q(5, "q5_quiz", "Klara quizet för nivå 5", "Minst 4 av 5 rätt.", quiz[5]["passed"], f"{quiz[5]['correct']}/4", 40, "game")
    # nivå 6: Lärling
    q(6, "q6_playbook", "Skriv din Spelbok", "Handlarens verktyg → Spelbok. Fyll i alla sex avsnitt (minst 40 tecken vardera): vad du letar efter, när du köper och säljer, storlek, när du inte handlar och vad du gör efter förluster.", tr["playbook"], "klar" if tr["playbook"] else "ej klar", 50, "playbook")
    q(6, "q6_closed10", "Stäng tio övningsaffärer", "Tio affärer i övningsportföljen som är stängda, antingen av stoppet eller av dig.", pp["closed"] >= 10, cnt(pp["closed"], 10), 40, "paper")
    q(6, "q6_proc70", "Processsnitt över 70", "Minst tio stängda övningsaffärer och ett snitt på 70 processpoäng eller mer. Vinsten spelar ingen roll.", pp["closed"] >= 10 and (pp["process_avg"] or 0) >= 70,
      cnt(pp["closed"], 10) if pp["closed"] < 10 else f"snitt {pp['process_avg']:.0f}/70", 50, "paper")
    q(6, "q6_paperrev", "Granska tre stängda övningsaffärer", "Skriv en lärdom på minst 20 tecken för tre stängda affärer i övningsportföljen.", pp["reviewed"] >= 3, cnt(pp["reviewed"], 3), 40, "paper")
    q(6, "q6_reviews5", "Granska fem journalbeslut med lärdom", "Granska beslut på journalfliken och skriv en lärdom på minst 20 tecken.", h["j_reviewed_lesson"] >= 5, cnt(h["j_reviewed_lesson"], 5), 40, "journal")
    q(6, "q6_quiz", "Klara quizet för nivå 6", "Minst 4 av 5 rätt.", quiz[6]["passed"], f"{quiz[6]['correct']}/4", 40, "game")
    # nivå 7: Disciplinerad
    q(7, "q7_closed20", "Stäng tjugo övningsaffärer", "Tjugo stängda affärer är ett första, ändå litet, urval.", pp["closed"] >= 20, cnt(pp["closed"], 20), 60, "paper")
    q(7, "q7_proc80", "Processsnitt över 80", "Minst tjugo stängda övningsaffärer och ett snitt på 80 processpoäng eller mer: du följer planen, håller risken nere och granskar.", pp["closed"] >= 20 and (pp["process_avg"] or 0) >= 80,
      cnt(pp["closed"], 20) if pp["closed"] < 20 else f"snitt {pp['process_avg']:.0f}/80", 70, "paper")
    q(7, "q7_monthly", "Två månadsgranskningar", "Handlarens verktyg → Månadsgranskning. Det krävs minst tre stängda övningsaffärer under en månad för att kunna granska den.", tr["monthly"] >= 2, cnt(tr["monthly"], 2), 60, "monthly")
    ok, pr = acc("bias", 10, 60)
    q(7, "q7_bias", "Beteendefällor: minst 60 % rätt", "Gör minst 10 scenarier i Beteendefällor och håll minst 60 % rätt på de senaste 20.", ok, pr, 50, "practice")
    q(7, "q7_reviews10", "Granska tio journalbeslut med lärdom", "Tio granskade journalbeslut med lärdom ger en första hållbar bild av hur du beslutar.", h["j_reviewed_lesson"] >= 10, cnt(h["j_reviewed_lesson"], 10), 40, "journal")
    q(7, "q7_discipline", "Invalideringsnivå på varje journalbeslut", "Minst tio journalbeslut och varje beslut har en invalideringsnivå.", h["j_total"] >= 10 and h["j_all_invalid"], cnt(h["j_total"], 10), 40, "journal")
    q(7, "q7_port", "En väl spridd portfölj", "Minst fem i effektivt antal innehav och inga allvarliga koncentrationsvarningar.", (pf["effective_n"] or 0) >= 5 and pf["no_big_warning"],
      "ok" if (pf["effective_n"] or 0) >= 5 and pf["no_big_warning"] else f"eff. {pf['effective_n']:.1f}/5" if pf["effective_n"] else "0/5", 50, "portfolio")
    q(7, "q7_quiz", "Klara quizet för nivå 7", "Minst 4 av 5 rätt.", quiz[7]["passed"], f"{quiz[7]['correct']}/4", 40, "game")
    # nivå 8: Riskchef (tidsgrindad av design: kräver 60 handelsdagar)
    ok, pq = acc("stress", 8, 60)
    q(8, "q8_stress", "Stresstest: minst 60 % rätt", "Öva → Stresstest. Räkna ut vad en kraftig nedgång, ett gap genom stoppen eller ett risktak betyder i kronor och procent. Minst 8 uppgifter och minst 60 % rätt på de senaste 20.", ok, pq, 50, "stress")
    q(8, "q8_stressrun", "Stresstesta din egen portfölj", "Handlarens verktyg → Riskpanel. Kör stresstestet på en övningsportfölj med minst tre öppna positioner och se vad scenarierna kostar jämfört med dina gränser.", px["stress_ok"], "klar" if px["stress_ok"] else "ej klar", 50, "riskpanel")
    q(8, "q8_risk60", "Håll dina egna gränser i 60 handelsdagar", "I en övningsportfölj: öppen risk under ditt tak, nedgång under din gräns och positioner minst 30 av 60 dagar. Gränserna sätter du själv i Spelboken. Resultatet spelar ingen roll, bara att du höll dig inom ramarna.", px["risk_ok"], "klar" if px["risk_ok"] else "ej klar", 100, "riskpanel")
    q(8, "q8_monthly4", "Fyra månadsgranskningar", "Fyra månader med granskning visar att granskningen blivit en vana och inte ett engångsprojekt.", tr["monthly"] >= 4, cnt(tr["monthly"], 4), 60, "monthly")
    q(8, "q8_quiz", "Klara quizet för nivå 8", "Minst 4 av 5 rätt.", quiz[8]["passed"], f"{quiz[8]['correct']}/4", 40, "game")
    # nivå 9: Systematiker
    ok, pq = acc("luck", 8, 60)
    q(9, "q9_luck", "Tur eller skicklighet: minst 60 % rätt", "Öva → Tur eller skicklighet. Lär dig hur mycket slumpen kan ge: serier av vinster och förluster som ser ut som skicklighet. Minst 8 uppgifter och minst 60 % rätt på de senaste 20.", ok, pq, 50, "luck")
    q(9, "q9_trades30", "Trettio stängda övningsaffärer", "Det är ungefär här statistiken börjar säga något, och fortfarande bara lite.", px["closed"] >= 30, cnt(px["closed"], 30), 50, "paper")
    q(9, "q9_stats", "Läs din Handelsstatistik", "Handlarens verktyg → Handelsstatistik, med minst 20 stängda affärer: snitt i R, träffandel, längsta förlustserie, alla med osäkerhetsintervall.", "stats" in ev.get("pro", set()), "klar" if "stats" in ev.get("pro", set()) else "ej klar", 40, "stats")
    q(9, "q9_compare", "Jämför två strategier", "Jämför två övningsportföljer med minst tio stängda affärer vardera och läs om skillnaden går att skilja från slump.", px["compare_ok"], "klar" if px["compare_ok"] else "ej klar", 60, "stats")
    ok, pq = acc("spur", 8, 60)
    q(9, "q9_spur", "Samband eller slump: minst 60 % rätt", "Öva → Samband eller slump. Lär dig varför det bästa sambandet bland många par ofta är slump. Minst 8 uppgifter och minst 60 % rätt på de senaste 20.", ok, pq, 40, "spur")
    q(9, "q9_events", "Kör en händelsestudie", "Samband → Händelser. Välj ett bolag och se hur andra bolag rör sig kring dess rapporter eller kraftiga rörelser, och läs om något klarar korrigeringen för antal tester.", "events" in ev.get("pro", set()), "klar" if "events" in ev.get("pro", set()) else "ej klar", 50, "events")
    q(9, "q9_rules", "Testa tre egna regler", "Handlarens verktyg → Regeltest. Skriv din hypotes först, kör testet och läs det ärligt, inklusive om regeln håller i båda halvorna av perioden. Tre tester med olika hypoteser.", px["rule_tests"] >= 3, cnt(px["rule_tests"], 3), 60, "rules")
    q(9, "q9_quiz", "Klara quizet för nivå 9", "Minst 4 av 5 rätt.", quiz[9]["passed"], f"{quiz[9]['correct']}/4", 40, "game")
    # nivå 10: Handlare (tidsgrindad av design: minst sex månader och 50 affärer)
    q(10, "q10_trades", "Femtio stängda övningsaffärer", "Ett urval som börjar vara användbart, om än fortfarande litet.", px["closed"] >= 50, cnt(px["closed"], 50), 80, "paper")
    q(10, "q10_span", "Sex månader sedan din första affär", "Minst 180 dagar. En process som bara prövats i en marknadsfas har inte prövats.", px["span"] >= 180, f"{min(px['span'], 180)}/180 dagar", 60, "paper")
    q(10, "q10_proc", "Processsnitt över 80 på de senaste 30 affärerna", "Plan, risk, storlek och granskning, konsekvent. Vinst och förlust spelar ingen roll.", (px["proc30"] or 0) >= 80,
      f"{px['closed']} affärer" if px["proc30"] is None else f"snitt {px['proc30']:.0f}/80", 80, "paper")
    q(10, "q10_monthly6", "Sex månadsgranskningar", "Sex månader med skriftlig granskning av processen.", tr["monthly"] >= 6, cnt(tr["monthly"], 6), 60, "monthly")
    q(10, "q10_decision", "Skriv ditt ärliga beslut", "Handlarprofilen → Ditt beslut. Utifrån din egen statistik: handla på riktigt med litet belopp, öva mer eller ändra strategi. Du måste motivera och beskriva vad som skulle få dig att ändra dig. Vilket beslut du väljer spelar ingen roll, bara att det är ärligt.", px["decision"], "klar" if px["decision"] else "ej klar", 80, "profile")
    q(10, "q10_quiz", "Klara quizet för nivå 10", "Minst 4 av 5 rätt.", quiz[10]["passed"], f"{quiz[10]['correct']}/4", 40, "game")
    return Q


def _badges(ev, h) -> list[dict]:
    g, tabs = ev.get("gloss", set()), ev.get("tab", set())
    return [
        {"id": "b_bookworm", "title": "Bokmal", "desc": "Läst 30 förklaringar.", "done": len(g) >= 30},
        {"id": "b_explorer", "title": "Upptäckare", "desc": "Besökt alla flikar.", "done": TABS_ALL <= tabs},
        {"id": "b_skeptic", "title": "Skeptikern", "desc": "Kört en backtest och läst om överanpassning och träffsäkerhet.", "done": bool(ev.get("backtest")) and {"overfit", "hitrate"} <= g},
        {"id": "b_reviewer", "title": "Granskaren", "desc": "Granskat ett beslut med lärdom.", "done": h["j_reviewed_lesson"] >= 1},
        {"id": "b_playbook", "title": "Spelboksförfattare", "desc": "Skrivit alla sex avsnitten i din Spelbok.", "done": h["trader"]["playbook"]},
        {"id": "b_stress", "title": "Stresstestad", "desc": "Kört stresstestet på en egen portfölj.", "done": h["pro"]["stress_ok"]},
        {"id": "b_honest", "title": "Ärlig mätare", "desc": "Skrivit ett beslut utifrån din egen statistik.", "done": h["pro"]["decision"]},
        {"id": "b_practice", "title": "Övare", "desc": "Gjort minst 50 övningar.", "done": sum(v["n"] for v in h["ex"].values()) >= 50},
        {"id": "b_disciplined", "title": "Disciplinerad", "desc": "Minst tio beslut, alla med invalideringsnivå.", "done": h["j_total"] >= 10 and h["j_all_invalid"]},
    ]


def state() -> dict:
    if not enabled():
        return {"enabled": False}
    ev = _events()
    h = _heavy()
    quiz = _quiz_state()
    quests = _quests(ev, h, quiz)
    done_levels = 0
    levels = []
    for n, name, goal in LEVELS:
        qs = [x for x in quests if x["level"] == n]
        complete = all(x["done"] for x in qs)
        levels.append({"n": n, "name": name, "goal": goal, "quests": qs, "complete": complete, "quiz": quiz[n]})
    for lv in levels:
        if lv["complete"]:
            done_levels += 1
        else:
            break
    current = min(done_levels + 1, len(LEVELS))
    for lv in levels:
        lv["status"] = "done" if lv["n"] <= done_levels else "current" if lv["n"] == current else "next"
    xp = sum(x["xp"] for x in quests if x["done"]) + 10 * sum(v["correct"] for v in quiz.values())
    badges = _badges(ev, h)
    # nyupptäckt: spara 'done'-markeringar och rapportera det som inte setts förut
    with db.connect() as con:
        seen = {r["key"] for r in con.execute("SELECT key FROM progress WHERE event='done'").fetchall()}
        new = []
        now = datetime.now(timezone.utc).isoformat()
        for x in quests:
            if x["done"] and x["id"] not in seen:
                new.append({"type": "quest", "id": x["id"], "title": x["title"], "xp": x["xp"]})
                con.execute("INSERT OR IGNORE INTO progress(event,key,ts) VALUES('done',?,?)", (x["id"], now))
        for lv in levels:
            k = f"level{lv['n']}"
            if lv["n"] <= done_levels and k not in seen:
                new.append({"type": "level", "id": k, "title": f"Nivå {lv['n']} klar: {lv['name']}"})
                con.execute("INSERT OR IGNORE INTO progress(event,key,ts) VALUES('done',?,?)", (k, now))
        for b in badges:
            if b["done"] and b["id"] not in seen:
                new.append({"type": "badge", "id": b["id"], "title": b["title"]})
                con.execute("INSERT OR IGNORE INTO progress(event,key,ts) VALUES('done',?,?)", (b["id"], now))
    rank = LEVELS[current - 1][1] + (" ✓" if done_levels >= len(LEVELS) else "")
    total_q = len(quests)
    return {"enabled": True, "level": current, "completed_levels": done_levels, "rank": rank, "xp": xp,
            "quests_done": sum(1 for x in quests if x["done"]), "quests_total": total_q,
            "levels": levels, "badges": badges, "new": new,
            "principle": "Poäng ges för att lära, dokumentera och granska. Aldrig för antal affärer och aldrig för vinst på enskilda beslut."}


def answer(qid: str, choice: int) -> dict:
    q = quizdata.BY_ID.get(qid)
    if not q:
        raise LookupError("Okänd fråga")
    ok = int(choice) == q["answer"]
    with db.connect() as con:
        con.execute("INSERT INTO quiz_results(qid, correct, ts) VALUES(?,?,?) "
                    "ON CONFLICT(qid) DO UPDATE SET correct=MAX(correct, excluded.correct), ts=excluded.ts",
                    (qid, 1 if ok else 0, datetime.now(timezone.utc).isoformat()))
    return {"correct": ok, "answer": q["answer"], "why": q["why"]}


def reset() -> None:
    with db.connect() as con:
        con.execute("DELETE FROM progress")
        con.execute("DELETE FROM quiz_results")
    invalidate()
