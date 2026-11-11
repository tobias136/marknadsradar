"""Automatisk underhåll av relationslistan.

Principer:
- Inget hamnar direkt i listan. Fynd läggs i en inkorg (förslag) och blir relationer först när du godkänner dem.
- Bara strukturerade källor används (Wikidata: ägande, dotterbolag, moderbolag) och bara mellan bolag som redan finns i dina listor.
- Leverantörs- och kundrelationer går inte att läsa ut strukturerat. De läggs in manuellt eller via import.
- Befintliga relationer kontrolleras: är källlänken nåbar, och är uppgiften äldre än 18 månader?
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db, relations

UA = "Marknadsradar/1.0 (personligt lokalt verktyg)"
STALE_DAYS = 540
INTERVAL_DAYS = 7
QID_MAX_AGE_DAYS = 30
PROPS = {  # Wikidata-egenskap -> (riktning, text). 'fwd': a→b investerar, 'rev': b→a
    "P127": "rev",   # a ägs av b
    "P355": "fwd",   # a har dotterbolag b
    "P749": "rev",   # a har moderbolag b
    "P1830": "fwd",  # a äger b
}
_WD = "http://www.wikidata.org/entity/"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sparql(query: str) -> list[dict]:
    """Standardhämtning mot Wikidata. Byts ut i test."""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)["results"]["bindings"]


def head(url: str) -> tuple[bool, str]:
    """Kontrollerar att en källänk svarar. Många sajter blockerar robotar, så ett fel är en varning och inget bevis."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                return (r.status < 400, f"HTTP {r.status}")
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return (False, f"HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            if method == "GET":
                return (False, str(e)[:80])
    return (False, "okänt fel")


_fetch = {"sparql": sparql, "head": head}  # injicerbara för test


def _symbols(tickers: list[str]) -> dict[str, list[str]]:
    """Yahoo-ticker -> möjliga börssymboler (utan landsuffix; bindestreck och mellanslag provas)."""
    out = {}
    for t in tickers:
        base = t.split(".")[0]
        out[t] = list(dict.fromkeys([base, base.replace("-", " "), base.replace("-", "")]))
    return out


def resolve_qids(tickers: list[str]) -> dict:
    """Matchar tickers mot Wikidata-bolag. Tvetydiga eller okända träffar hoppas över (precision före täckning)."""
    now = datetime.now(timezone.utc)
    with db.connect() as con:
        cached = {r["ticker"]: dict(r) for r in con.execute("SELECT * FROM rel_qid").fetchall()}
    need = [t for t in tickers if t not in cached or (now - datetime.fromisoformat(cached[t]["ts"])).days >= QID_MAX_AGE_DAYS]
    if need:
        sym = _symbols(need)
        allsyms = sorted({s for v in sym.values() for s in v})
        vals = " ".join(json.dumps(s) for s in allsyms)
        q = f"SELECT ?sym ?c WHERE {{ VALUES ?sym {{ {vals} }} ?c p:P414 ?st . ?st pq:P249 ?sym . }}"
        rows = _fetch["sparql"](q)
        hit: dict[str, set] = {}
        for r in rows:
            hit.setdefault(r["sym"]["value"], set()).add(r["c"]["value"].replace(_WD, ""))
        with db.connect() as con:
            for t in need:
                cands = set().union(*[hit.get(s, set()) for s in sym[t]])
                if len(cands) == 1:
                    qid, st = next(iter(cands)), "ok"
                elif not cands:
                    qid, st = None, "okänd"
                else:
                    qid, st = None, "tvetydig"
                con.execute("INSERT OR REPLACE INTO rel_qid(ticker, qid, status, ts) VALUES(?,?,?,?)", (t, qid, st, _now()))
                cached[t] = {"ticker": t, "qid": qid, "status": st, "ts": _now()}
    return {t: cached[t] for t in tickers if t in cached}


def discover(tickers: list[str] | None = None) -> dict:
    """Letar ägar- och dotterbolagsrelationer mellan bolag i dina listor och lägger dem som förslag."""
    with db.connect() as con:
        tk = tickers or [r["ticker"] for r in con.execute("SELECT DISTINCT ticker FROM list_items").fetchall()]
    res = {"tickers": len(tk), "matched": 0, "ambiguous": 0, "unknown": 0, "new": 0, "seen": 0}
    if len(tk) < 2:
        return res
    q = resolve_qids(tk)
    byq = {v["qid"]: t for t, v in q.items() if v["qid"]}
    res["matched"] = len(byq)
    res["ambiguous"] = sum(1 for v in q.values() if v["status"] == "tvetydig")
    res["unknown"] = sum(1 for v in q.values() if v["status"] == "okänd")
    if len(byq) < 2:
        return res
    ids = " ".join(f"wd:{x}" for x in byq)
    props = " ".join(f"wdt:{p}" for p in PROPS)
    rows = _fetch["sparql"](f"SELECT ?a ?p ?b WHERE {{ VALUES ?a {{ {ids} }} VALUES ?b {{ {ids} }} VALUES ?p {{ {props} }} ?a ?p ?b . FILTER(?a != ?b) }}")
    seen = set()
    with db.connect() as con:
        for r in rows:
            qa, qb = r["a"]["value"].replace(_WD, ""), r["b"]["value"].replace(_WD, "")
            prop = r["p"]["value"].rsplit("/", 1)[-1]
            if prop not in PROPS or qa not in byq or qb not in byq:
                continue
            a, b = (byq[qa], byq[qb]) if PROPS[prop] == "fwd" else (byq[qb], byq[qa])
            src_q = qa
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            url = f"https://www.wikidata.org/wiki/{src_q}"
            if con.execute("SELECT 1 FROM relations WHERE a=? AND b=? AND rtype='invests'", (a, b)).fetchone():
                res["seen"] += 1
                continue
            try:
                cur = con.execute("INSERT INTO rel_candidates(a,b,rtype,source_url,source_title,confidence,origin,note,created) VALUES(?,?,?,?,?,?,?,?,?)",
                                  (a, b, "invests", url, f"Wikidata ({prop})", "sekundär", "wikidata", "Hämtad automatiskt. Kontrollera mot bolagets egna dokument innan du godkänner.", _now()))
                res["new"] += 1
            except Exception:  # redan föreslagen (UNIQUE), godkänd eller avvisad
                res["seen"] += 1
    return res


def check_edges() -> dict:
    """Källkontroll och åldersflagga för befintliga relationer."""
    with db.connect() as con:
        edges = [dict(r) for r in con.execute("SELECT id, source_url FROM relations").fetchall()]
        health = {r["eid"]: dict(r) for r in con.execute("SELECT * FROM rel_health").fetchall()}
        con.execute("DELETE FROM rel_health WHERE eid NOT IN (SELECT id FROM relations)")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    n, bad = 0, 0
    done: dict[str, tuple] = {}
    for e in edges:
        h = health.get(e["id"])
        if h and h["checked"] > cutoff:
            continue
        if e["source_url"] not in done:
            done[e["source_url"]] = _fetch["head"](e["source_url"])
            time.sleep(0.3)
        ok, note = done[e["source_url"]]
        fails = 0 if ok else (h["fails"] if h else 0) + 1
        bad += 0 if ok else 1
        n += 1
        with db.connect() as con:
            con.execute("INSERT OR REPLACE INTO rel_health(eid, checked, ok, fails, note) VALUES(?,?,?,?,?)", (e["id"], _now(), 1 if ok else 0, fails, note))
    return {"checked": n, "unreachable": bad}


def stale(as_of: str, created: str) -> bool:
    ref = (as_of or "")[:10] or (created or "")[:10]
    try:
        return (datetime.now(timezone.utc).date() - datetime.fromisoformat(ref).date()).days > STALE_DAYS
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------ inkorg
def candidates(status: str = "pending") -> list[dict]:
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM rel_candidates WHERE status=? ORDER BY id DESC LIMIT 200", (status,)).fetchall()]
    for r in rows:
        r["a_name"], r["b_name"] = relations._name(r["a"]), relations._name(r["b"])
        r["verb"] = relations.TYPES[r["rtype"]]
    return rows


def decide(cid: int, accept: bool, strength: str = "mentioned") -> dict:
    with db.connect() as con:
        c = con.execute("SELECT * FROM rel_candidates WHERE id=? AND status='pending'", (cid,)).fetchone()
    if not c:
        raise ValueError("Förslaget finns inte eller är redan hanterat")
    if accept:
        try:
            relations.add_edge({"a": c["a"], "b": c["b"], "rtype": c["rtype"], "strength": strength, "source_url": c["source_url"],
                                "source_title": c["source_title"], "as_of": (c["created"] or "")[:10], "confidence": c["confidence"],
                                "note": "Godkänt från automatiskt förslag."})
        except ValueError as e:
            if "finns redan" not in str(e):
                raise
    with db.connect() as con:
        con.execute("UPDATE rel_candidates SET status=?, decided=? WHERE id=?", ("accepted" if accept else "rejected", _now(), cid))
    return {"ok": True}


# ------------------------------------------------------------ körning och status
class Runner:
    def __init__(self) -> None:
        self.running = False
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def enabled(self) -> bool:
        return (db.get_setting("rel_auto", "1") or "1") == "1"

    def status(self) -> dict:
        last = db.get_setting("rel_auto_last")
        with db.connect() as con:
            pend = con.execute("SELECT COUNT(*) n FROM rel_candidates WHERE status='pending'").fetchone()["n"]
            unreach = con.execute("SELECT COUNT(*) n FROM rel_health WHERE ok=0 AND fails>=2").fetchone()["n"]
            rows = con.execute("SELECT as_of, created FROM relations").fetchall()
        return {"enabled": self.enabled(), "running": self.running, "last": last, "result": json.loads(db.get_setting("rel_auto_result", "{}") or "{}"),
                "error": db.get_setting("rel_auto_error", ""), "pending": pend, "unreachable": unreach, "n_stale": sum(1 for r in rows if stale(r["as_of"], r["created"])),
                "interval_days": INTERVAL_DAYS}

    def run(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._job, daemon=True, name="rel-auto").start()
        return True

    def _job(self) -> None:
        try:
            out, err = {}, []
            try:
                out["discover"] = discover()
            except Exception as e:  # noqa: BLE001
                err.append(f"Sökning efter ägarrelationer: {str(e)[:120]}")
            try:
                out["links"] = check_edges()
            except Exception as e:  # noqa: BLE001
                err.append(f"Källkontroll: {str(e)[:120]}")
            db.set_setting("rel_auto_result", json.dumps(out))
            db.set_setting("rel_auto_error", " | ".join(err))
            db.set_setting("rel_auto_last", _now())
        finally:
            self.running = False

    def _loop(self) -> None:
        while not self._stop.wait(900):
            try:
                if not self.enabled() or self.running:
                    continue
                from .providers import get_provider
                if get_provider().name == "demo":
                    continue
                last = db.get_setting("rel_auto_last")
                if last is None or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days >= INTERVAL_DAYS:
                    self.run()
            except Exception:  # noqa: BLE001
                pass

    def start_loop(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="rel-auto-loop").start()

    def stop(self) -> None:
        self._stop.set()


runner = Runner()
