"""Egen Yahoo Finance-klient utan yfinance. Används på Android, där yfinance (curl_cffi) inte går att installera.

Själva HTTP-anropen görs av en utbytbar 'transport':
- AndroidTransport: telefonens egen nätverksstack via Kotlin-klassen YahooHttp (Chaquopy).
- UrllibTransport: Pythons urllib, för test och som reserv på dator.
Resten (cookie, crumb, EU-samtycke, tolkning av svar) är samma kod oavsett transport och följer
hur yfinance gör: https://github.com/ranaroussi/yfinance (data.py, scrapers/).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser

from .providers import INFO_KEYS, _f

Q1 = "https://query1.finance.yahoo.com"
Q2 = "https://query2.finance.yahoo.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class YahooError(RuntimeError):
    pass


class Resp:
    def __init__(self, status: int, text: str, url: str = ""):
        self.status, self.text, self.url = status, text, url

    def json(self):
        return json.loads(self.text)


# ----------------------------------------------------------------------------- transporter
class UrllibTransport:
    def __init__(self) -> None:
        import http.cookiejar
        import urllib.request
        self._jar = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))

    def request(self, method: str, url: str, form: dict | None = None, headers: dict | None = None) -> Resp:
        import urllib.error
        import urllib.request
        h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.5"}
        h.update(headers or {})
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form, doseq=True).encode()
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with self._op.open(req, timeout=30) as r:
                return Resp(r.status, r.read().decode("utf-8", "replace"), r.geturl())
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read().decode("utf-8", "replace"), url)

    def clear_cookies(self) -> None:
        self._jar.clear()


class AndroidTransport:
    """Anropar Kotlin-objektet com.marknadsradar.app.YahooHttp (HttpURLConnection + CookieManager)."""

    def __init__(self) -> None:
        from java import jclass  # finns bara under Chaquopy
        self._k = jclass("com.marknadsradar.app.YahooHttp")

    def request(self, method: str, url: str, form: dict | None = None, headers: dict | None = None) -> Resp:
        body = urllib.parse.urlencode(form, doseq=True) if form is not None else ""
        try:
            out = self._k.request(method, url, body, json.dumps(headers or {}))
        except Exception as e:  # noqa: BLE001  (Java-undantag: timeout, ingen anslutning, ...)
            raise YahooError(f"Nätverksfel mot Yahoo: {str(e)[:120]}") from e
        return Resp(int(out[0]), str(out[2]), str(out[1]))

    def clear_cookies(self) -> None:
        self._k.clearCookies()


# ----------------------------------------------------------------------------- klient
class YahooClient:
    def __init__(self, transport) -> None:
        self.t = transport
        self._crumb: str | None = None
        self._lock = threading.RLock()
        self._last = 0.0

    def _throttle(self) -> None:
        with self._lock:
            wait = 0.25 - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    def _req(self, method, url, params=None, form=None, headers=None) -> Resp:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        self._throttle()
        return self.t.request(method, url, form=form, headers=headers)

    # ---- cookie och crumb
    def _crumb_basic(self) -> str | None:
        try:
            self._req("GET", "https://fc.yahoo.com")  # sätter cookie; fel här är inte kritiska
        except Exception:  # noqa: BLE001
            pass
        r = self._req("GET", Q1 + "/v1/test/getcrumb", headers={"Accept": "*/*"})
        if r.status == 429 or "Too Many Requests" in r.text:
            raise YahooError("Yahoo begränsar antalet anrop (429). Vänta en stund och försök igen.")
        txt = (r.text or "").strip()
        if r.status != 200 or not txt or "<html" in txt.lower() or " " in txt:
            return None
        return txt

    def _crumb_consent(self) -> str | None:
        """EU-samtycke: samma flöde som yfinance 'csrf'-strategin."""
        r = self._req("GET", "https://guce.yahoo.com/consent")
        tok = re.search(r'name="csrfToken"[^>]*value="([^"]+)"', r.text) or re.search(r'value="([^"]+)"[^>]*name="csrfToken"', r.text)
        sid = re.search(r'name="sessionId"[^>]*value="([^"]+)"', r.text) or re.search(r'value="([^"]+)"[^>]*name="sessionId"', r.text)
        if not tok or not sid:
            return None
        data = {"agree": ["agree", "agree"], "consentUUID": "default", "sessionId": sid.group(1), "csrfToken": tok.group(1),
                "originalDoneUrl": "https://finance.yahoo.com/", "namespace": "yahoo"}
        try:
            self._req("POST", f"https://consent.yahoo.com/v2/collectConsent?sessionId={sid.group(1)}", form=data)
            self._req("GET", f"https://guce.yahoo.com/copyConsent?sessionId={sid.group(1)}")
        except Exception:  # noqa: BLE001
            pass
        r = self._req("GET", Q2 + "/v1/test/getcrumb", headers={"Accept": "*/*"})
        if r.status == 429:
            raise YahooError("Yahoo begränsar antalet anrop (429). Vänta en stund och försök igen.")
        txt = (r.text or "").strip()
        if r.status != 200 or not txt or "<html" in txt.lower() or " " in txt:
            return None
        return txt

    def crumb(self) -> str:
        with self._lock:
            if self._crumb:
                return self._crumb
            c = self._crumb_basic()
            if c is None:
                self.t.clear_cookies()
                c = self._crumb_consent()
            if c is None:
                raise YahooError("Kunde inte få åtkomst till Yahoo (ingen crumb). Kontrollera nätverket, eller försök igen senare.")
            self._crumb = c
            return c

    def reset(self) -> None:
        with self._lock:
            self._crumb = None
            self.t.clear_cookies()

    # ---- anrop
    def get(self, url: str, params: dict | None = None, crumb: bool = False, accept_json: bool = True) -> Resp:
        for attempt in (1, 2):
            p = dict(params or {})
            if crumb:
                p["crumb"] = self.crumb()
            r = self._req("GET", url, params=p, headers={"Accept": "application/json,text/plain,*/*"} if accept_json else None)
            if r.status == 429:
                raise YahooError("Yahoo begränsar antalet anrop (429). Vänta en stund och försök igen.")
            if r.status in (401, 403) and attempt == 1:
                self.reset()
                continue
            return r
        return r

    def get_json(self, url: str, params: dict | None = None, crumb: bool = False) -> dict:
        r = self.get(url, params, crumb)
        if r.status >= 400:
            raise YahooError(f"Yahoo svarade {r.status} för {url.split('?')[0].rsplit('/', 1)[-1]}")
        try:
            return r.json()
        except Exception as e:  # noqa: BLE001
            raise YahooError("Ogiltigt svar från Yahoo (inte JSON)") from e


# ----------------------------------------------------------------------------- tolkning
def parse_chart(data: dict) -> list[tuple]:
    """Chart-API -> [(datum, open, high, low, close, volume)], justerat för utdelning och split (som yfinance auto_adjust)."""
    chart = data.get("chart") or {}
    if chart.get("error"):
        raise YahooError(str(chart["error"].get("description") or chart["error"])[:160])
    res = (chart.get("result") or [None])[0]
    if not res:
        return []
    ts = res.get("timestamp") or []
    ind = res.get("indicators") or {}
    q = (ind.get("quote") or [{}])[0]
    adj = ((ind.get("adjclose") or [{}])[0]).get("adjclose")
    off = int((res.get("meta") or {}).get("gmtoffset") or 0)
    rows = []
    for i, t in enumerate(ts):
        def g(k):
            v = q.get(k)
            return _f(v[i]) if v and i < len(v) else None
        close, o, h, l, vol = g("close"), g("open"), g("high"), g("low"), g("volume")
        if close is None:
            continue
        if adj and i < len(adj) and _f(adj[i]) is not None and close:
            k = adj[i] / close
            close = adj[i]
            o, h, l = (x * k if x is not None else None for x in (o, h, l))
        d = datetime.fromtimestamp(int(t) + off, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, o, h, l, close, vol))
    # Yahoo kan returnera två rader för samma dag (pågående dag): behåll den sista
    out: dict[str, tuple] = {}
    for r in rows:
        out[r[0]] = r
    return [out[k] for k in sorted(out)]


def _raw(v):
    if isinstance(v, dict) and "raw" in v:
        return v["raw"]
    return v


def parse_info(summary: dict, quote: dict | None, symbol: str) -> dict:
    """quoteSummary + v7/quote -> plattad dict, filtrerad på INFO_KEYS."""
    merged: dict = {}
    for src in ((summary.get("quoteSummary") or {}).get("result") or [None])[:1]:
        if src:
            for k, v in src.items():
                if isinstance(v, dict):
                    for k1, v1 in v.items():
                        if v1 is not None:
                            merged[k1] = _raw(v1)
    for src in ((quote or {}).get("quoteResponse", {}).get("result") or []):
        if src.get("symbol") == symbol:
            for k, v in src.items():
                if v is not None and k not in merged:
                    merged[k] = _raw(v)
            # v7/quote har currency/exchange även när quoteSummary saknar dem
            for k in ("currency", "exchange", "quoteType", "shortName", "longName"):
                if src.get(k) is not None:
                    merged.setdefault(k, src[k])
    return {k: merged[k] for k in INFO_KEYS if merged.get(k) is not None}


Q_KEYS = {
    "revenue": ["TotalRevenue", "OperatingRevenue"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncome", "TotalOperatingIncomeAsReported"],
    "net_income": ["NetIncome", "NetIncomeCommonStockholders"],
    "ebitda": ["EBITDA", "NormalizedEBITDA"],
    "eps": ["DilutedEPS", "BasicEPS"],
    "fcf": ["FreeCashFlow"],
}


def parse_timeseries(data: dict) -> list[dict]:
    """fundamentals-timeseries -> kvartal (nyast först), samma nycklar som YahooProvider."""
    series: dict[str, dict[str, float]] = {}
    for item in ((data.get("timeseries") or {}).get("result") or []):
        typ = (item.get("meta") or {}).get("type") or []
        for t in typ:
            vals = item.get(t)
            if not vals:
                continue
            name = t[len("quarterly"):] if t.startswith("quarterly") else t
            d: dict[str, float] = {}
            for v in vals:
                if not v:
                    continue
                x = _f(_raw(v.get("reportedValue")))
                if x is not None and v.get("asOfDate"):
                    d[v["asOfDate"]] = x
            series[name] = d
    quarters: dict[str, dict] = {}
    for key, names in Q_KEYS.items():
        for nm in names:
            if nm in series and series[nm]:
                for date, x in series[nm].items():
                    quarters.setdefault(date, {"date": date})[key] = x
                break
    return sorted(quarters.values(), key=lambda q: q["date"], reverse=True)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._t = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._t is not None:
            if self._row:
                self._t.append(self._row)
            self._row = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


_MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def parse_earnings_html(html: str) -> list[dict]:
    """Yahoos rapportkalender (HTML-tabell) -> [{date, eps_estimate, eps_actual, surprise_pct, future}]."""
    p = _TableParser()
    p.feed(html)
    if not p.tables:
        return []
    rows = p.tables[0]
    head = [h.lower() for h in rows[0]]

    def col(*names):
        for i, h in enumerate(head):
            if any(n in h for n in names):
                return i
        return None

    ci, ce, ca, cs = col("earnings date"), col("eps estimate"), col("reported eps"), col("surprise")
    if ci is None:
        return []
    out = []
    for r in rows[1:]:
        if len(r) <= ci:
            continue
        m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", r[ci])
        if not m or m.group(1) not in _MONTHS:
            continue
        d = f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"

        def num(i):
            if i is None or i >= len(r):
                return None
            s = r[i].replace(",", "").replace("%", "").replace("+", "").strip()
            return None if s in ("", "-", "—") else _f(s)

        out.append({"date": d, "eps_estimate": num(ce), "eps_actual": num(ca), "surprise_pct": num(cs)})
    return out


# ----------------------------------------------------------------------------- provider
class YahooHttpProvider:
    name = "yahoo"

    def __init__(self, transport=None) -> None:
        if transport is None:
            mode = os.environ.get("MARKNADSRADAR_HTTP", "")
            transport = AndroidTransport() if mode == "android" else UrllibTransport()
        self.c = YahooClient(transport)

    def history(self, ticker: str, period: str = "2y"):
        sym = urllib.parse.quote(ticker, safe="")
        data = self.c.get_json(f"{Q2}/v8/finance/chart/{sym}", {"range": period, "interval": "1d", "includeAdjustedClose": "true", "events": "div,splits"})
        return parse_chart(data)

    def fundamentals(self, ticker: str) -> dict:
        sym = urllib.parse.quote(ticker, safe="")
        out: dict = {"info": {}, "quarters": [], "earnings": [], "next_earnings": None}
        try:
            summ = self.c.get_json(f"{Q2}/v10/finance/quoteSummary/{sym}", {
                "modules": "financialData,quoteType,defaultKeyStatistics,assetProfile,summaryDetail", "corsDomain": "finance.yahoo.com", "formatted": "false", "symbol": ticker}, crumb=True)
            try:
                quote = self.c.get_json(f"{Q1}/v7/finance/quote", {"symbols": ticker, "formatted": "false"}, crumb=True)
            except YahooError:
                quote = None
            out["info"] = parse_info(summ, quote, ticker)
        except Exception as e:  # noqa: BLE001
            out["info_error"] = str(e)[:200]
        if out["info"].get("quoteType") in ("ETF", "INDEX", "MUTUALFUND", "CURRENCY", "CRYPTOCURRENCY", "FUTURE"):
            return out
        try:
            types = ",".join("quarterly" + n for names in Q_KEYS.values() for n in names)
            now = int(time.time())
            ts = self.c.get_json(f"{Q2}/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}", {
                "symbol": ticker, "type": types, "period1": int(datetime(2016, 12, 31).timestamp()), "period2": now + 86400})
            out["quarters"] = parse_timeseries(ts)
        except Exception as e:  # noqa: BLE001
            out["quarters_error"] = str(e)[:200]
        try:
            r = self.c.get(f"https://finance.yahoo.com/calendar/earnings?symbol={sym}&offset=0&size=100", accept_json=False)
            if r.status >= 400:
                raise YahooError(f"Rapportkalendern svarade {r.status}")
            rows = parse_earnings_html(r.text)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            future = [x["date"] for x in rows if x["eps_actual"] is None and x["date"] >= today]
            out["earnings"] = sorted(({k: x[k] for k in ("date", "eps_estimate", "eps_actual", "surprise_pct")} for x in rows if x["eps_actual"] is not None),
                                     key=lambda e: e["date"], reverse=True)
            out["next_earnings"] = min(future) if future else None
        except Exception as e:  # noqa: BLE001
            out["earnings_error"] = str(e)[:200]
        return out
