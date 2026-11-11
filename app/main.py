"""FastAPI-app: JSON-API under /api och det grafiska gränssnittet under /."""
from __future__ import annotations

import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import relauto, backtest, db, exercises, game, journal, macro, metrics, paper, portfolio, pro, relations, quizdata, seed, service, snapshot, trader
from .scheduler import fetch_prices, refresher

import os as _os
STATIC = Path(_os.environ.get("MARKNADSRADAR_STATIC") or Path(__file__).resolve().parent.parent / "static")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    seed.seed_if_empty()
    refresher.start_loop()
    relauto.runner.start_loop()
    yield
    refresher.stop()
    relauto.runner.stop()


app = FastAPI(title="Marknadsradar", lifespan=lifespan)

_LOGIN = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Marknadsradar</title>
<body style="font-family:system-ui;background:#0a0e14;color:#e6edf3;display:grid;place-items:center;min-height:100vh;margin:0"><form method="get" style="width:min(320px,90vw)">
<h2>Marknadsradar</h2><p style="color:#8b98a9">Ange åtkomstnyckeln som visas där programmet startades.</p>
<input name="key" type="password" autofocus style="width:100%;padding:12px;font-size:16px;border-radius:8px;border:1px solid #2a3442;background:#111826;color:inherit;box-sizing:border-box">
<button style="margin-top:10px;width:100%;padding:12px;font-size:16px;border:0;border-radius:8px;background:#5aa0ff;color:#fff">Öppna</button></form>"""


@app.middleware("http")
async def access_key(request, call_next):
    """Om MARKNADSRADAR_KEY är satt (nätverksläge) krävs nyckeln. Annars är appen öppen, vilket är rätt för localhost."""
    import hmac
    import os
    key = os.environ.get("MARKNADSRADAR_KEY", "")
    if not key:
        return await call_next(request)
    given = request.query_params.get("key", "")
    cookie = request.cookies.get("mr_key", "")
    if hmac.compare_digest(cookie.encode(), key.encode()):
        return await call_next(request)
    if given and hmac.compare_digest(given.encode(), key.encode()):
        from fastapi.responses import RedirectResponse
        resp = RedirectResponse(request.url.path or "/", status_code=303)
        resp.set_cookie("mr_key", key, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
        return resp
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Åtkomstnyckel krävs"}, status_code=401)
    return PlainTextResponse(_LOGIN, status_code=401, media_type="text/html")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _dump(m) -> dict:
    return m.model_dump() if hasattr(m, "model_dump") else m.dict()  # pydantic 2 eller 1


def J(obj) -> JSONResponse:
    return JSONResponse(metrics.clean(obj))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


# ------------------------------------------------------------------ status
@app.get("/api/status")
def status():
    return J(refresher.status())


class RefreshIn(BaseModel):
    full: bool = False


@app.post("/api/refresh")
def refresh(body: RefreshIn | None = None):
    started = refresher.start(force_full=bool(body and body.full))
    return J({"started": started, **refresher.status()})


class SettingsIn(BaseModel):
    interval_minutes: int


@app.put("/api/settings")
def settings(body: SettingsIn):
    if body.interval_minutes < 0 or body.interval_minutes > 24 * 60:
        raise HTTPException(400, "Intervallet måste vara mellan 0 (av) och 1440 minuter.")
    db.set_setting("interval_minutes", str(body.interval_minutes))
    return J(refresher.status())


# ------------------------------------------------------------------ listor
class ListIn(BaseModel):
    name: str
    benchmark: str = ""
    description: str = ""
    tickers: str = ""  # kommaseparerad / mellanslag / radbrytning


class ListPatch(BaseModel):
    name: str | None = None
    benchmark: str | None = None
    description: str | None = None


class TickersIn(BaseModel):
    tickers: str
    group: str = ""


class GroupIn(BaseModel):
    group: str


def _split(raw: str) -> list[str]:
    seen, out = set(), []
    for t in re.split(r"[\s,;]+", raw.upper()):
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _add_tickers(lid: int, raw: str, group: str, bg: BackgroundTasks | None) -> dict:
    added, failed = [], []
    for t in _split(raw):
        try:
            fetch_prices(t, force_full=True)
        except Exception as e:  # noqa: BLE001
            failed.append({"ticker": t, "error": f"Hittade ingen kursdata ({str(e)[:80]}). "
                                                 "Svenska aktier slutar på .ST, t.ex. VOLV-B.ST."})
            continue
        with db.connect() as con:
            pos = con.execute("SELECT COALESCE(MAX(position), -1) + 1 p FROM list_items WHERE list_id=?",
                              (lid,)).fetchone()["p"]
            cur = con.execute(
                "INSERT OR IGNORE INTO list_items(list_id, ticker, grp, label, auto_group, position) "
                "VALUES(?,?,?,?,?,?)",
                (lid, t, group or "Övrigt", "", 0 if group else 1, pos),
            )
        if cur.rowcount:
            added.append(t)
            if bg is not None:
                bg.add_task(refresher.post_add, t)
        else:
            failed.append({"ticker": t, "error": "Finns redan i listan."})
    return {"added": added, "failed": failed}


@app.get("/api/lists")
def get_lists():
    return J(service.lists_all())


@app.post("/api/lists")
def create_list(body: ListIn, bg: BackgroundTasks):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Listan behöver ett namn.")
    bench = body.benchmark.strip().upper()
    try:
        with db.connect() as con:
            pos = con.execute("SELECT COALESCE(MAX(position), -1) + 1 p FROM lists").fetchone()["p"]
            cur = con.execute("INSERT INTO lists(name, benchmark, description, position) VALUES(?,?,?,?)",
                              (name, bench, body.description.strip(), pos))
            lid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Det finns redan en lista med det namnet.")
    if bench:
        bg.add_task(_safe_fetch, bench)
    result = _add_tickers(lid, body.tickers, "", bg)
    game.record("list", name)
    return J({"id": lid, **result})


def _safe_fetch(ticker: str):
    try:
        fetch_prices(ticker, force_full=True)
    except Exception:  # noqa: BLE001
        pass


@app.put("/api/lists/{lid}")
def update_list(lid: int, body: ListPatch, bg: BackgroundTasks):
    lst = service.get_list(lid)
    if not lst:
        raise HTTPException(404, "Listan finns inte.")
    name = (body.name if body.name is not None else lst["name"]).strip()
    bench = (body.benchmark if body.benchmark is not None else lst["benchmark"]).strip().upper()
    desc = body.description if body.description is not None else lst["description"]
    try:
        with db.connect() as con:
            con.execute("UPDATE lists SET name=?, benchmark=?, description=? WHERE id=?", (name, bench, desc, lid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Det finns redan en lista med det namnet.")
    if bench and bench != lst["benchmark"]:
        bg.add_task(_safe_fetch, bench)
    return J({"ok": True})


@app.delete("/api/lists/{lid}")
def delete_list(lid: int):
    with db.connect() as con:
        con.execute("DELETE FROM lists WHERE id=?", (lid,))
    return J({"ok": True})


@app.post("/api/lists/{lid}/tickers")
def add_tickers(lid: int, body: TickersIn, bg: BackgroundTasks):
    if not service.get_list(lid):
        raise HTTPException(404, "Listan finns inte.")
    return J(_add_tickers(lid, body.tickers, body.group.strip(), bg))


@app.patch("/api/lists/{lid}/tickers/{ticker}")
def set_group(lid: int, ticker: str, body: GroupIn):
    with db.connect() as con:
        con.execute("UPDATE list_items SET grp=?, auto_group=0 WHERE list_id=? AND ticker=?",
                    (body.group.strip() or "Övrigt", lid, ticker.upper()))
    return J({"ok": True})


@app.delete("/api/lists/{lid}/tickers/{ticker}")
def remove_ticker(lid: int, ticker: str):
    with db.connect() as con:
        con.execute("DELETE FROM list_items WHERE list_id=? AND ticker=?", (lid, ticker.upper()))
    return J({"ok": True})


@app.get("/api/lists/{lid}/overview")
def list_overview(lid: int):
    ov = service.overview(lid)
    if ov is None:
        raise HTTPException(404, "Listan finns inte.")
    return JSONResponse(ov)


@app.get("/api/lists/{lid}/reports")
def list_reports(lid: int):
    r = service.reports(lid)
    if r is None:
        raise HTTPException(404, "Listan finns inte.")
    return JSONResponse(r)


# ------------------------------------------------------------------ aktier
@app.get("/api/ticker/{sym}")
def ticker(sym: str):
    return JSONResponse(service.ticker_detail(sym))


@app.get("/api/ticker/{sym}/series")
def ticker_series(sym: str, range: str = Query("1y")):
    s = metrics.series(sym.upper(), range)
    if s is None:
        raise HTTPException(404, "Ingen kursdata för tickern.")
    return J(s)


class NoteIn(BaseModel):
    text: str


@app.put("/api/ticker/{sym}/note")
def save_note(sym: str, body: NoteIn):
    with db.connect() as con:
        con.execute(
            "INSERT INTO notes(ticker, text, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(ticker) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at",
            (sym.upper(), body.text, datetime.now(timezone.utc).isoformat()),
        )
    return J({"ok": True})


@app.get("/api/compare")
def compare(tickers: str, range: str = Query("1y")):
    return J(metrics.compare(_split(tickers), range))


# ---------------------------------------------------------------- backtest
@app.get("/api/lists/{lid}/backtest")
def get_backtest(lid: int, h: int = Query(21)):
    res = backtest.run(lid, h)
    if res.get("error") == "Listan finns inte":
        raise HTTPException(404, "Listan finns inte.")
    if not res.get("error"):
        game.record("backtest", str(lid))
    return J(res)


# ----------------------------------------------------------------- journal
class JournalIn(BaseModel):
    ticker: str
    action: str
    thesis: str = ""
    invalidation: str = ""
    horizon_days: int = 90


class ReviewIn(BaseModel):
    outcome: str
    lesson: str = ""


@app.get("/api/journal")
def get_journal():
    return J(journal.list_entries())


@app.post("/api/journal")
def add_journal(body: JournalIn):
    try:
        r = journal.create(body.ticker, body.action, body.thesis, body.invalidation, body.horizon_days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    game.invalidate()
    return J(r)


@app.put("/api/journal/{jid}/review")
def review_journal(jid: int, body: ReviewIn):
    try:
        journal.review(jid, body.outcome, body.lesson)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    game.invalidate()
    return J({"ok": True})


@app.delete("/api/journal/{jid}")
def delete_journal(jid: int):
    journal.delete(jid)
    game.invalidate()
    return J({"ok": True})


# ----------------------------------------------------------------- portfölj
class HoldingIn(BaseModel):
    ticker: str = ""
    qty: float
    avg_cost: float | None = None
    currency: str = ""
    name: str = ""
    account: str = ""


class HoldingPatch(BaseModel):
    ticker: str | None = None
    qty: float | None = None
    avg_cost: float | None = None
    currency: str | None = None
    name: str | None = None


class ImportIn(BaseModel):
    csv: str
    apply: bool = False


def _fetch_holding(t: str):
    if not t:
        return
    _safe_fetch(t)
    try:
        service.ensure_fundamentals(t, force=True)
        for c in portfolio.aux_tickers():
            if c.endswith("SEK=X"):
                _safe_fetch(c)
    except Exception:  # noqa: BLE001
        pass


@app.get("/api/portfolio")
def get_portfolio():
    return J(portfolio.summary())


@app.post("/api/portfolio/holdings")
def add_holding(body: HoldingIn, bg: BackgroundTasks):
    try:
        hid = portfolio.add_holding(body.ticker, body.qty, body.avg_cost, body.currency, body.name, body.account)
    except ValueError as e:
        raise HTTPException(400, str(e))
    bg.add_task(_fetch_holding, body.ticker.strip().upper())
    game.invalidate()
    return J({"id": hid})


@app.patch("/api/portfolio/holdings/{hid}")
def patch_holding(hid: int, body: HoldingPatch, bg: BackgroundTasks):
    portfolio.update_holding(hid, _dump(body))
    if body.ticker:
        bg.add_task(_fetch_holding, body.ticker.strip().upper())
    game.invalidate()
    return J({"ok": True})


@app.delete("/api/portfolio/holdings/{hid}")
def remove_holding(hid: int):
    portfolio.delete_holding(hid)
    game.invalidate()
    return J({"ok": True})


@app.post("/api/portfolio/import")
def import_portfolio(body: ImportIn):
    if body.apply:
        res = portfolio.apply_import(body.csv)
        game.invalidate()
    else:
        res = portfolio.parse_csv(body.csv)
    return J(res)


@app.get("/api/portfolio/suggest")
def suggest_ticker(name: str):
    return J(portfolio.suggest(name))


# ------------------------------------------------------------------- makro
@app.get("/api/macro")
def get_macro():
    return J(macro.snapshot())


# -------------------------------------------------------------- spelläge
class TrackIn(BaseModel):
    event: str
    key: str


class AnswerIn(BaseModel):
    qid: str
    choice: int


class EnabledIn(BaseModel):
    enabled: bool


@app.get("/api/game")
def game_state():
    return J(game.state())


@app.post("/api/game/track")
def game_track(body: TrackIn):
    if body.event in ("gloss", "tab", "stock", "report", "possize"):
        game.record(body.event, body.key)
    return J(game.state())


@app.get("/api/game/quiz/{level}")
def game_quiz(level: int):
    return J({"level": level, "questions": quizdata.questions(level)})


@app.post("/api/game/quiz/answer")
def game_answer(body: AnswerIn):
    try:
        r = game.answer(body.qid, body.choice)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return J(r)


@app.put("/api/game/enabled")
def game_enable(body: EnabledIn):
    game.set_enabled(body.enabled)
    return J({"enabled": game.enabled()})


@app.post("/api/game/reset")
def game_reset():
    game.reset()
    return J({"ok": True})


# ------------------------------------------------------------------ export
@app.get("/api/snapshot")
def get_snapshot():
    return JSONResponse(metrics.clean(snapshot.build()))


@app.get("/api/snapshot.md", response_class=PlainTextResponse)
def get_snapshot_md():
    return PlainTextResponse(snapshot.to_markdown(metrics.clean(snapshot.build())),
                             media_type="text/markdown; charset=utf-8")


@app.get("/api/snapshot/download")
def download_snapshot(fmt: str = "md"):
    snap = metrics.clean(snapshot.build())
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    if fmt == "json":
        import json
        return PlainTextResponse(json.dumps(snap, ensure_ascii=False, indent=1), media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="marknadsradar_{stamp}.json"'})
    return PlainTextResponse(snapshot.to_markdown(snap), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="marknadsradar_{stamp}.md"'})


# ----------------------------------------------------------------- övningar
def _bad(e: Exception):
    raise HTTPException(400, str(e))


@app.get("/api/practice/stats")
def practice_stats():
    return J(exercises.stats())


@app.get("/api/practice/chart")
def practice_chart(kind: str | None = None):
    try:
        return J(exercises.chart_new(kind))
    except ValueError as e:
        _bad(e)


class ChartAns(BaseModel):
    token: str
    choice: int


@app.post("/api/practice/chart/answer")
def practice_chart_answer(body: ChartAns):
    try:
        r = exercises.chart_answer(body.token, body.choice)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/practice/risk")
def practice_risk(kind: str | None = None):
    return J(exercises.risk_new(kind))


class RiskAns(BaseModel):
    token: str
    value: float


@app.post("/api/practice/risk/answer")
def practice_risk_answer(body: RiskAns):
    try:
        r = exercises.risk_answer(body.token, body.value)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/practice/flaw")
def practice_flaw():
    return J(exercises.flaw_new())


class FlawAns(BaseModel):
    token: str
    choice: str


@app.post("/api/practice/flaw/answer")
def practice_flaw_answer(body: FlawAns):
    try:
        r = exercises.flaw_answer(body.token, body.choice)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/practice/stopex")
def practice_stopex():
    try:
        return J(exercises.stopex_new())
    except ValueError as e:
        _bad(e)


class StopAns(BaseModel):
    token: str
    stop_pct: float


@app.post("/api/practice/stopex/answer")
def practice_stopex_answer(body: StopAns):
    try:
        r = exercises.stopex_answer(body.token, body.stop_pct)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/practice/stopsim")
def practice_stopsim(ticker: str, horizon: int = Query(120, ge=20, le=250)):
    try:
        r = exercises.stopsim(ticker, horizon)
    except ValueError as e:
        _bad(e)
    exercises.log("stopsim", None, ticker.upper())
    game.invalidate()
    return J(r)


@app.get("/api/practice/pool")
def practice_pool():
    return J({"tickers": [{"ticker": t, "name": exercises._name(t)} for t in exercises.pool(400)]})


class CardsIn(BaseModel):
    keys: list[str]


@app.post("/api/practice/cards/due")
def practice_cards_due(body: CardsIn):
    return J(exercises.cards_due(body.keys))


class CardAns(BaseModel):
    key: str
    grade: str


@app.post("/api/practice/cards/answer")
def practice_cards_answer(body: CardAns):
    try:
        r = exercises.cards_answer(body.key, body.grade)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


# ----------------------------------------------------------- övningsportfölj
@app.get("/api/paper")
def paper_list():
    return J(paper.list_portfolios())


class PaperIn(BaseModel):
    name: str
    strategy: str = ""
    cash0: float = 100000


@app.post("/api/paper")
def paper_create(body: PaperIn):
    try:
        pid = paper.create_portfolio(body.name, body.strategy, body.cash0)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"id": pid})


@app.get("/api/paper/quote")
def paper_quote(ticker: str, pid: int | None = None):
    try:
        q = paper.quote(ticker)
    except ValueError as e:
        _bad(e)
    q["links"] = []
    if pid:
        try:
            with db.connect() as con:
                held = [r["ticker"] for r in con.execute("SELECT ticker FROM paper_trades WHERE pid=? AND status='open'", (pid,)).fetchall()]
            q["links"] = relations.linked_holdings(q["ticker"], held)
        except Exception:  # noqa: BLE001
            q["links"] = []
    return J(q)


@app.get("/api/paper/{pid}")
def paper_detail(pid: int):
    try:
        return J(paper.detail(pid))
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/paper/{pid}")
def paper_delete(pid: int):
    paper.delete_portfolio(pid)
    game.invalidate()
    return J({"ok": True})


class PaperBuy(BaseModel):
    ticker: str
    qty: float
    stop: float
    target: float | None = None
    thesis: str = ""
    invalidation: str = ""
    horizon_days: int = 90


@app.post("/api/paper/{pid}/buy")
def paper_buy(pid: int, body: PaperBuy):
    try:
        tid = paper.buy(pid, body.ticker, body.qty, body.stop, body.target, body.thesis, body.invalidation, body.horizon_days)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"id": tid})


class PaperClose(BaseModel):
    reason: str


@app.post("/api/paper/{pid}/trades/{tid}/close")
def paper_close(pid: int, tid: int, body: PaperClose):
    try:
        paper.close(pid, tid, body.reason)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"ok": True})


class PaperStop(BaseModel):
    stop: float


@app.put("/api/paper/{pid}/trades/{tid}/stop")
def paper_stop(pid: int, tid: int, body: PaperStop):
    try:
        paper.raise_stop(pid, tid, body.stop)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        _bad(e)
    return J({"ok": True})


class PaperReview(BaseModel):
    lesson: str


@app.put("/api/paper/{pid}/trades/{tid}/review")
def paper_review(pid: int, tid: int, body: PaperReview):
    try:
        paper.review(pid, tid, body.lesson)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"ok": True})


# ------------------------------------------------------- beteendefällor, spelbok, månadsgranskning
@app.get("/api/practice/bias")
def practice_bias():
    return J(exercises.bias_new())


class BiasAns(BaseModel):
    token: str
    choice: str


@app.post("/api/practice/bias/answer")
def practice_bias_answer(body: BiasAns):
    try:
        r = exercises.bias_answer(body.token, body.choice)
    except (ValueError, IndexError, KeyError) as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/trader/playbook")
def trader_playbook():
    return J(trader.playbook_get())


class PlaybookIn(BaseModel):
    sections: dict[str, str] = {}
    limits: dict[str, float] = {}


@app.put("/api/trader/playbook")
def trader_playbook_save(body: PlaybookIn):
    try:
        r = trader.playbook_save(body.sections, body.limits)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/trader/monthly")
def trader_monthly():
    return J(trader.monthly_list())


class MonthlyIn(BaseModel):
    good: str = ""
    bad: str = ""
    change: str = ""


@app.put("/api/trader/monthly/{month}")
def trader_monthly_save(month: str, body: MonthlyIn):
    try:
        trader.monthly_save(month, body.good, body.bad, body.change)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"ok": True})


# ----------------------------------------------------------------- proffsdelen (nivå 8–10)
@app.get("/api/practice/stress")
def practice_stress():
    return J(pro.stress_new())


class NumAns(BaseModel):
    token: str
    value: float


@app.post("/api/practice/stress/answer")
def practice_stress_answer(body: NumAns):
    try:
        r = pro.stress_answer(body.token, body.value)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/practice/luck")
def practice_luck():
    return J(pro.luck_new())


@app.post("/api/practice/luck/answer")
def practice_luck_answer(body: BiasAns):
    try:
        r = pro.luck_answer(body.token, body.choice)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/pro/riskpanel")
def pro_riskpanel():
    return J({"history": pro.risk_history()})


@app.get("/api/pro/stress/{pid}")
def pro_stress(pid: int):
    try:
        r = pro.stress_portfolio(pid)
    except LookupError as e:
        raise HTTPException(404, str(e))
    game.invalidate()
    return J(r)


@app.get("/api/pro/stats")
def pro_stats():
    r = pro.trade_stats()
    if r["total"].get("n", 0) >= 20:
        game.record("pro", "stats")
    return J(r)


@app.get("/api/pro/compare")
def pro_compare(a: int, b: int):
    try:
        r = pro.compare(a, b)
    except (ValueError, LookupError) as e:
        _bad(e)
    game.invalidate()
    return J(r)


class RuleIn(BaseModel):
    conds: list[str]
    stop_atr: float = 3.0
    horizon: int = 40
    hypothesis: str = ""


@app.get("/api/pro/rules")
def pro_rules():
    return J({"conds": [{"key": k, "label": v[0], "hint": v[1]} for k, v in pro.CONDS.items()], "history": pro.rule_history()})


@app.post("/api/pro/rules")
def pro_rules_run(body: RuleIn):
    try:
        r = pro.rule_test(body.conds, body.stop_atr, body.horizon, body.hypothesis)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/pro/profile")
def pro_profile():
    return J(pro.profile())


class DecisionIn(BaseModel):
    decision: str
    reflection: str


@app.put("/api/pro/decision")
def pro_decision(body: DecisionIn):
    try:
        pro.decision_save(body.decision, body.reflection)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J({"ok": True})


# ----------------------------------------------------------------- samband mellan bolag
@app.get("/api/practice/spur")
def practice_spur():
    return J(pro.spur_new())


@app.post("/api/practice/spur/answer")
def practice_spur_answer(body: BiasAns):
    try:
        r = pro.spur_answer(body.token, body.choice)
    except ValueError as e:
        _bad(e)
    game.invalidate()
    return J(r)


@app.get("/api/rel/leadlag")
def rel_leadlag(ticker: str = ""):
    try:
        return J(relations.leadlag_for(ticker) if ticker else relations.leadlag_top(25))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Kunde inte beräkna lead-lag: {e}")


@app.get("/api/rel/events")
def rel_events(ticker: str, kind: str = "move", thr: float = 2.5):
    try:
        r = relations.event_study(ticker, kind, thr)
    except ValueError as e:
        _bad(e)
    if r["n_events"] >= relations.MIN_EVENTS and r["rows"]:
        game.record("pro", "events")
        game.invalidate()
    return J(r)


@app.get("/api/rel/edges")
def rel_edges(ticker: str):
    return J(relations.edges_for(ticker))


@app.get("/api/rel/coverage")
def rel_coverage():
    return J(relations.coverage())


class EdgeIn(BaseModel):
    a: str
    b: str
    rtype: str
    strength: str = "mentioned"
    share_pct: float | None = None
    amount: str = ""
    source_url: str = ""
    source_title: str = ""
    as_of: str = ""
    confidence: str = "primär"
    note: str = ""


@app.post("/api/rel/edges")
def rel_edge_add(body: EdgeIn):
    try:
        eid = relations.add_edge(_dump(body))
    except ValueError as e:
        _bad(e)
    return J({"id": eid})


@app.delete("/api/rel/edges/{eid}")
def rel_edge_del(eid: int):
    relations.delete_edge(eid)
    return J({"ok": True})


class EdgeImport(BaseModel):
    items: list[dict]


@app.post("/api/rel/import")
def rel_import(body: EdgeImport):
    return J(relations.import_edges(body.items))


class RevIn(BaseModel):
    ticker: str
    on: bool = True


@app.get("/api/rel/auto")
def rel_auto_status():
    return J({**relauto.runner.status(), "candidates": relauto.candidates()})


@app.post("/api/rel/auto/run")
def rel_auto_run():
    return J({"started": relauto.runner.run()})


class AutoIn(BaseModel):
    on: bool


@app.put("/api/rel/auto/enabled")
def rel_auto_enabled(body: AutoIn):
    db.set_setting("rel_auto", "1" if body.on else "0")
    return J({"ok": True})


class DecideIn(BaseModel):
    accept: bool
    strength: str = "mentioned"


@app.post("/api/rel/candidates/{cid}")
def rel_candidate_decide(cid: int, body: DecideIn):
    try:
        return J(relauto.decide(cid, body.accept, body.strength))
    except ValueError as e:
        _bad(e)


@app.put("/api/rel/reviewed")
def rel_reviewed(body: RevIn):
    relations.mark_reviewed(body.ticker, body.on)
    return J({"ok": True})
