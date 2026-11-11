"""Hämtning av data (kurser + fundamenta) och bakgrundsloop som uppdaterar
med det intervall du ställer in i gränssnittet."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from . import db, service
from .providers import get_provider


def fetch_prices(ticker: str, force_full: bool = False) -> int:
    prov = get_provider()
    today = date.today().isoformat()
    with db.connect() as con:
        meta = con.execute("SELECT last_full FROM price_meta WHERE ticker=?", (ticker,)).fetchone()
        n = con.execute("SELECT COUNT(*) c FROM prices WHERE ticker=?", (ticker,)).fetchone()["c"]
    full = force_full or n < 100 or not meta or meta["last_full"] != today
    try:
        rows = prov.history(ticker, "5y" if full else "5d")
        if not rows:
            raise ValueError("Ingen kursdata returnerades")
        if full and n > 100 and len(rows) < n * 0.5:
            raise ValueError("Misstänkt ofullständig kursdata – behåller gammal historik")
    except Exception as e:  # noqa: BLE001
        with db.connect() as con:
            con.execute(
                "INSERT INTO price_meta(ticker, last_error) VALUES(?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET last_error=excluded.last_error",
                (ticker, str(e)[:200]),
            )
        raise
    with db.connect() as con:
        if full:
            con.execute("DELETE FROM prices WHERE ticker=?", (ticker,))
        con.executemany(
            "INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
            [(ticker,) + tuple(r) for r in rows],
        )
        con.execute(
            "INSERT INTO price_meta(ticker, last_full, last_fetch, last_error) VALUES(?,?,?,NULL) "
            "ON CONFLICT(ticker) DO UPDATE SET last_full=COALESCE(?, price_meta.last_full), "
            "last_fetch=excluded.last_fetch, last_error=NULL",
            (ticker, today if full else None, datetime.now(timezone.utc).isoformat(), today if full else None),
        )
    return len(rows)


class Refresher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.running = False
        self.phase = ""
        self.done = 0
        self.total = 0
        self.errors: dict[str, str] = {}

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        return {
            "running": self.running, "phase": self.phase, "done": self.done, "total": self.total,
            "errors": dict(self.errors), "last_refresh": db.get_setting("last_refresh"),
            "interval_minutes": int(db.get_setting("interval_minutes", "60") or 60),
            "provider": get_provider().name,
        }

    # ------------------------------------------------------------------ jobb
    def start(self, tickers: list[str] | None = None, force_full: bool = False,
              with_fundamentals: bool = True) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, args=(tickers, force_full, with_fundamentals), daemon=True).start()
        return True

    def _tick(self) -> None:
        with self._lock:
            self.done += 1

    def _run(self, tickers, force_full, with_fundamentals) -> None:
        try:
            list_tickers = tickers or service.all_tickers()
            from . import macro, paper, portfolio
            aux = [t for t in (macro.aux_tickers() + portfolio.aux_tickers() + paper.aux_tickers()) if t not in list_tickers] if not tickers else []
            tickers = list_tickers + aux
            self.errors = {}
            self.done, self.total, self.phase = 0, len(tickers), "Hämtar kurser"

            def price_job(t):
                try:
                    fetch_prices(t, force_full)
                except Exception as e:  # noqa: BLE001
                    self.errors[t] = str(e)[:160]
                finally:
                    self._tick()

            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(price_job, tickers))

            if with_fundamentals:
                need = [t for t in list_tickers if t not in self.errors and (
                    (service.fund_age_hours(t) is None) or service.fund_age_hours(t) >= service.FUND_MAX_AGE_H)]
                self.done, self.total, self.phase = 0, len(need), "Hämtar bolagsdata och rapporter"

                def fund_job(t):
                    try:
                        _, err = service.ensure_fundamentals(t, force=True)
                        if err:
                            self.errors[t] = "Bolagsdata: " + err
                        service.set_auto_group_from_info(t)
                    finally:
                        self._tick()

                with ThreadPoolExecutor(max_workers=3) as ex:
                    list(ex.map(fund_job, need))

            self.phase = "Skapar export"
            from . import snapshot
            snapshot.write_exports()
            db.set_setting("last_refresh", datetime.now(timezone.utc).isoformat())
        finally:
            self.phase = ""
            self.running = False

    def post_add(self, ticker: str) -> None:
        """Körs i bakgrunden när ett nytt bolag lagts till i en lista."""
        service.ensure_fundamentals(ticker, force=True)
        service.set_auto_group_from_info(ticker)

    # ------------------------------------------------------------ bakgrundsloop
    def loop(self) -> None:
        while not self._stop.is_set():
            try:
                interval = int(db.get_setting("interval_minutes", "60") or 60)
                if interval > 0 and not self.running:
                    last = db.get_setting("last_refresh")
                    due = last is None or (
                        datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() >= interval * 60
                    if due:
                        self.start()
            except Exception:  # noqa: BLE001
                pass
            if self._stop.wait(15):
                break

    def start_loop(self) -> None:
        threading.Thread(target=self.loop, daemon=True, name="refresh-loop").start()

    def stop(self) -> None:
        self._stop.set()


refresher = Refresher()
