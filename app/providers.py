"""Datakällor. YahooProvider (yfinance) är standard. DemoProvider skapar
syntetisk data så att gränssnittet kan testas offline.

Alla providers har samma gränssnitt:
    history(ticker, period) -> lista av (date, open, high, low, close, volume)
    fundamentals(ticker)    -> dict med info / quarters / earnings / next_earnings

Vill du koppla in en annan källa (t.ex. Avanza om de öppnar ett API) skriver du
en ny klass med samma två metoder och returnerar den från get_provider().
"""
from __future__ import annotations

import math
import os
import zlib
from datetime import date, datetime, timedelta, timezone

from . import db

INFO_KEYS = [
    "shortName", "longName", "sector", "industry", "currency", "quoteType",
    "exchange", "country", "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "dividendRate", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "profitMargins",
    "operatingMargins", "grossMargins", "returnOnEquity", "debtToEquity",
    "revenueGrowth", "earningsGrowth", "trailingEps", "forwardEps",
]


def _f(x):
    try:
        if x is None:
            return None
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Yahoo Finance via yfinance
# --------------------------------------------------------------------------
class YahooProvider:
    name = "yahoo"

    def history(self, ticker: str, period: str = "2y"):
        import yfinance as yf

        df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True, actions=False)
        rows = []
        if df is None or df.empty:
            return rows
        for idx, r in df.iterrows():
            close = _f(r.get("Close"))
            if close is None:
                continue
            rows.append((
                idx.strftime("%Y-%m-%d"),
                _f(r.get("Open")), _f(r.get("High")), _f(r.get("Low")),
                close, _f(r.get("Volume")),
            ))
        return rows

    def fundamentals(self, ticker: str) -> dict:
        import yfinance as yf

        t = yf.Ticker(ticker)
        out: dict = {"info": {}, "quarters": [], "earnings": [], "next_earnings": None}

        try:
            info = t.info or {}
            out["info"] = {k: info.get(k) for k in INFO_KEYS if info.get(k) is not None}
        except Exception as e:  # noqa: BLE001
            out["info_error"] = str(e)[:200]

        if out["info"].get("quoteType") in ("ETF", "INDEX", "MUTUALFUND", "CURRENCY", "CRYPTOCURRENCY", "FUTURE"):
            return out  # ETF:er och index saknar kvartalsrapporter

        # Kvartalsvisa resultaträkningar (normalt de senaste 4–5 kvartalen)
        quarters: dict[str, dict] = {}
        row_map = {
            "revenue": ["Total Revenue", "Operating Revenue"],
            "gross_profit": ["Gross Profit"],
            "operating_income": ["Operating Income", "Total Operating Income As Reported"],
            "net_income": ["Net Income", "Net Income Common Stockholders"],
            "ebitda": ["EBITDA", "Normalized EBITDA"],
            "eps": ["Diluted EPS", "Basic EPS"],
        }
        try:
            inc = t.quarterly_income_stmt
            if inc is not None and not inc.empty:
                for col in inc.columns:
                    d = col.strftime("%Y-%m-%d")
                    q = quarters.setdefault(d, {"date": d})
                    for key, names in row_map.items():
                        for nm in names:
                            if nm in inc.index:
                                v = _f(inc.loc[nm, col])
                                if v is not None:
                                    q[key] = v
                                    break
        except Exception as e:  # noqa: BLE001
            out["quarters_error"] = str(e)[:200]
        try:
            cf = t.quarterly_cashflow
            if cf is not None and not cf.empty and "Free Cash Flow" in cf.index:
                for col in cf.columns:
                    d = col.strftime("%Y-%m-%d")
                    v = _f(cf.loc["Free Cash Flow", col])
                    if v is not None and d in quarters:
                        quarters[d]["fcf"] = v
        except Exception:  # noqa: BLE001
            pass
        out["quarters"] = sorted(quarters.values(), key=lambda q: q["date"], reverse=True)

        # Rapportdatum, förväntningar och överraskningar
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                now = datetime.now(timezone.utc)
                future = []
                for idx, r in ed.iterrows():
                    d = idx.strftime("%Y-%m-%d")
                    est = _f(r.get("EPS Estimate"))
                    act = _f(r.get("Reported EPS"))
                    sur = _f(r.get("Surprise(%)"))
                    when = idx.to_pydatetime()
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if act is None and when > now:
                        future.append(d)
                    elif act is not None:
                        out["earnings"].append({
                            "date": d, "eps_estimate": est, "eps_actual": act, "surprise_pct": sur,
                        })
                out["earnings"].sort(key=lambda e: e["date"], reverse=True)
                out["next_earnings"] = min(future) if future else None
        except Exception as e:  # noqa: BLE001
            out["earnings_error"] = str(e)[:200]
        return out


# --------------------------------------------------------------------------
# Demo-data (syntetisk, endast för test av gränssnittet)
# --------------------------------------------------------------------------
_DEMO_ETFS = {
    "XLK", "XLC", "XLY", "XLP", "XLV", "XLF", "XLI", "XLE", "XLB", "XLU", "XLRE",
    "URA", "URNM", "XBI", "SMH", "GDX", "COPX", "ICLN", "ITA", "SPY",
}
_DEMO_SECTOR = {
    "NVDA": "Technology", "MSFT": "Technology", "AMZN": "Consumer Cyclical", "GOOGL": "Communication Services",
    "META": "Communication Services", "ORCL": "Technology", "AVGO": "Technology", "TSM": "Technology",
    "VST": "Utilities", "CEG": "Utilities", "BKNG": "Consumer Cyclical", "VFS": "Consumer Cyclical",
}


class DemoProvider:
    name = "demo"

    @staticmethod
    def _rng(ticker: str, salt: int = 0):
        import numpy as np
        return np.random.RandomState((zlib.crc32(ticker.encode()) + salt) % (2**32 - 1))

    # Påhittade nivåer för makro-/valutatickers så att demo-panelen ser rimlig ut: (startnivå, daglig vol, drift)
    _MACRO = {
        "^VIX": (18, 0.045, 0), "^TNX": (4.2, 0.012, 0), "^IRX": (4.4, 0.004, 0), "^FVX": (4.0, 0.012, 0),
        "DX-Y.NYB": (104, 0.004, 0), "USDSEK=X": (10.4, 0.005, 0), "EURSEK=X": (11.3, 0.003, 0),
        "GBPSEK=X": (13.2, 0.004, 0), "NOKSEK=X": (0.96, 0.004, 0), "DKKSEK=X": (1.51, 0.003, 0),
        "CL=F": (74, 0.017, 0), "GC=F": (2500, 0.009, 0.0002), "HG=F": (4.3, 0.011, 0),
        "HYG": (77, 0.003, 0), "LQD": (108, 0.004, 0), "^GSPC": (5200, 0.008, 0.0004), "^OMX": (2400, 0.009, 0.0002),
    }

    def history(self, ticker: str, period: str = "5y"):
        import numpy as np

        full_n = 1300
        n = {"5d": 7, "1mo": 25, "2y": 520, "5y": full_n}.get(period, full_n)
        rng = self._rng(ticker)
        market = np.random.RandomState(2026).normal(0.0002, 0.006, full_n)  # delad marknadsfaktor
        if ticker in self._MACRO:
            start, vol, drift = self._MACRO[ticker]
            beta = 0.0
            rets = drift + rng.normal(0, vol, full_n)
            if ticker in ("^VIX", "^TNX", "^IRX", "^FVX"):   # återgår mot medelnivå i stället för att driva iväg
                lvl = np.empty(full_n)
                x = start
                k = 0.03
                for i in range(full_n):
                    x = x + k * (start - x) + start * vol * rng.normal()
                    lvl[i] = max(x, 0.1)
                prices = lvl
            else:
                prices = start * np.exp(np.cumsum(rets))
        else:
            drift = rng.normal(0.0001, 0.0002)
            vol = rng.uniform(0.004, 0.012)
            beta = rng.uniform(0.6, 1.4)
            rets = drift + beta * market + rng.normal(0, vol, full_n)
            start = rng.uniform(80, 400) if ticker.endswith(".ST") else rng.uniform(25, 450)
            prices = start * np.exp(np.cumsum(rets))
        # Datum: senaste vardagar bakåt från idag
        days, d = [], date.today()
        while len(days) < full_n:
            if d.weekday() < 5:
                days.append(d)
            d -= timedelta(days=1)
        days.reverse()
        rows = []
        for i in range(full_n - n, full_n):
            c = float(prices[i])
            o = c * (1 + rng.normal(0, 0.004))
            rows.append((days[i].isoformat(), o, max(o, c) * 1.004, min(o, c) * 0.996, c,
                         float(rng.randint(1_000_000, 9_000_000))))
        return rows

    def fundamentals(self, ticker: str) -> dict:
        rng = self._rng(ticker, 7)
        is_etf = ticker in _DEMO_ETFS or ticker.startswith("^")
        cur = "SEK" if ticker.endswith(".ST") else "USD"
        info = {
            "shortName": f"{ticker} (demo)", "currency": cur,
            "quoteType": "ETF" if is_etf else "EQUITY", "exchange": "DEMO",
        }
        if not is_etf:
            sector = _DEMO_SECTOR.get(ticker) or rng.choice(
                ["Industrials", "Financial Services", "Technology", "Consumer Defensive", "Basic Materials"])
            info.update({
                "sector": str(sector), "industry": "Demo",
                "marketCap": float(rng.uniform(5e9, 3e12)),
                "trailingPE": float(rng.uniform(9, 45)), "forwardPE": float(rng.uniform(8, 38)),
                "priceToBook": float(rng.uniform(1, 12)), "dividendRate": float(rng.uniform(0, 6)),
                "beta": float(rng.uniform(0.6, 1.5)), "profitMargins": float(rng.uniform(0.04, 0.3)),
                "operatingMargins": float(rng.uniform(0.06, 0.38)), "grossMargins": float(rng.uniform(0.2, 0.7)),
                "returnOnEquity": float(rng.uniform(0.05, 0.4)),
            })
        quarters, earnings = [], []
        next_e = None
        if not is_etf:
            rev = float(rng.uniform(2e9, 6e10))
            for i, qdate in enumerate(_quarter_ends(5)):
                growth = rng.normal(0.02, 0.03)
                opm = float(np_clip(rng.normal(0.18, 0.02), 0.03, 0.4))
                nim = opm * 0.78
                q_rev = rev * (1 - growth) ** i
                quarters.append({
                    "date": qdate.isoformat(), "revenue": q_rev, "gross_profit": q_rev * 0.45,
                    "operating_income": q_rev * opm, "net_income": q_rev * nim,
                    "ebitda": q_rev * (opm + 0.04), "eps": q_rev * nim / 1e9 * 0.4, "fcf": q_rev * nim * 0.9,
                })
            for i, q in enumerate(quarters[:4]):
                est = q["eps"] * float(rng.uniform(0.9, 1.05))
                earnings.append({
                    "date": (date.fromisoformat(q["date"]) + timedelta(days=30)).isoformat(),
                    "eps_estimate": est, "eps_actual": q["eps"],
                    "surprise_pct": (q["eps"] / est - 1) * 100,
                })
            next_e = (date.today() + timedelta(days=int(rng.randint(5, 70)))).isoformat()
        return {"info": info, "quarters": quarters, "earnings": earnings, "next_earnings": next_e}


def _quarter_ends(n: int):
    today = date.today()
    y, m = today.year, ((today.month - 1) // 3) * 3
    out = []
    for _ in range(n):
        if m == 0:
            y, m = y - 1, 12
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        out.append(nxt - timedelta(days=1))
        m -= 3
    return out


def np_clip(x, lo, hi):
    return max(lo, min(hi, x))


_provider = None


def get_provider():
    global _provider
    if _provider is None:
        if db.DEMO:
            _provider = DemoProvider()
        elif os.environ.get("MARKNADSRADAR_HTTP"):
            from .yahoo_http import YahooHttpProvider  # Android: egen klient i stället för yfinance
            _provider = YahooHttpProvider()
        else:
            _provider = YahooProvider()
    return _provider
