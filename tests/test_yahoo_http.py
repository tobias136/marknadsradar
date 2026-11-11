"""Test av Yahoo-klienten mot en simulerad Yahoo. Kör: python tests/test_yahoo_http.py
Svarsformen är hämtad från hur yfinance tolkar Yahoos svar. Detta bevisar inte att Yahoo svarar så i dag."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MARKNADSRADAR_PROVIDER"] = "demo"
from app.yahoo_http import YahooHttpProvider, Resp, YahooError, parse_chart, parse_earnings_html

T0 = 1730000000  # ~2024-10-27 UTC
CHART = {"chart": {"result": [{"meta": {"gmtoffset": -14400}, "timestamp": [T0 + i * 86400 for i in range(5)],
    "indicators": {"quote": [{"open": [10, 11, None, 13, 14], "high": [11, 12, None, 14, 15], "low": [9, 10, None, 12, 13],
                              "close": [10.5, 11.5, None, 13.5, 14.5], "volume": [100, 200, None, 400, 500]}],
                   "adjclose": [{"adjclose": [10.0, 11.0, None, 13.0, 14.0]}]}}], "error": None}}
SUMMARY = {"quoteSummary": {"result": [{"summaryDetail": {"trailingPE": {"raw": 25.5, "fmt": "25.5"}, "marketCap": {"raw": 3e12}},
    "assetProfile": {"sector": "Technology", "industry": "Semis", "country": "United States"}, "quoteType": {"quoteType": "EQUITY", "shortName": "Test Corp", "exchange": "NMS"},
    "financialData": {"profitMargins": {"raw": 0.2}}, "defaultKeyStatistics": {"beta": {"raw": 1.2}}}], "error": None}}
QUOTE = {"quoteResponse": {"result": [{"symbol": "TEST", "currency": "USD", "longName": "Test Corporation", "fiftyTwoWeekHigh": 200.5}]}}
def ts(key, vals): return {"meta": {"symbol": ["TEST"], "type": [key]}, "timestamp": [1, 2], key: [{"asOfDate": d, "currencyCode": "USD", "reportedValue": {"raw": v, "fmt": str(v)}} for d, v in vals]}
TS = {"timeseries": {"result": [ts("quarterlyTotalRevenue", [("2025-03-31", 100.0), ("2025-06-30", 120.0)]), ts("quarterlyNetIncome", [("2025-06-30", 30.0)]),
      ts("quarterlyFreeCashFlow", [("2025-06-30", 25.0)]), ts("quarterlyDilutedEPS", [("2025-06-30", 1.5)])]}}
HTML = """<html><body><table><thead><tr><th>Symbol</th><th>Company</th><th>Earnings Date</th><th>EPS Estimate</th><th>Reported EPS</th><th>Surprise (%)</th></tr></thead><tbody>
<tr><td>TEST</td><td>Test Corp</td><td>January 28, 2027 at 4 PM EST</td><td>1.10</td><td>-</td><td>-</td></tr>
<tr><td>TEST</td><td>Test Corp</td><td>October 30, 2025 at 4 PM EDT</td><td>2.97</td><td>3.10</td><td>4.38</td></tr>
<tr><td>TEST</td><td>Test Corp</td><td>July 22, 2025 at 4 PM EDT</td><td>1.73</td><td>1.54</td><td>-10.88</td></tr></tbody></table></body></html>"""
CONSENT = '<form><input type="hidden" name="csrfToken" value="TOK123"><input type="hidden" name="sessionId" value="SID9"></form>'

class Fake:
    def __init__(self, eu=False, bad_crumb_once=False):
        self.eu, self.consented, self.log, self.bad_once = eu, False, [], bad_crumb_once
        self.cookies = False
    def clear_cookies(self): self.cookies = False; self.consented = self.consented  # samtycke sparas som cookie i riktig webbläsare
    def request(self, method, url, form=None, headers=None):
        self.log.append((method, url.split("?")[0]))
        if "fc.yahoo.com" in url:
            self.cookies = True; return Resp(404, "", url)
        if "getcrumb" in url:
            if self.eu and not self.consented: return Resp(403, "<html>consent</html>", url)
            if self.bad_once: self.bad_once = False; return Resp(200, "OLDCRUMB", url)
            return Resp(200, "CRUMB1", url)
        if "guce.yahoo.com/consent" in url: return Resp(200, CONSENT, url)
        if "collectConsent" in url:
            assert form["csrfToken"] == "TOK123" and form["sessionId"] == "SID9"; self.consented = True; return Resp(200, "", url)
        if "copyConsent" in url: return Resp(200, "", url)
        if "/v8/finance/chart/" in url: return Resp(200, json.dumps(CHART), url)
        if "quoteSummary" in url:
            if "crumb=CRUMB1" not in url: return Resp(401, '{"finance":{"error":{"code":"Unauthorized","description":"Invalid Crumb"}}}', url)
            return Resp(200, json.dumps(SUMMARY), url)
        if "v7/finance/quote" in url:
            return Resp(200, json.dumps(QUOTE), url) if "crumb=CRUMB1" in url else Resp(401, "{}", url)
        if "fundamentals-timeseries" in url: return Resp(200, json.dumps(TS), url)
        if "calendar/earnings" in url: return Resp(200, HTML, url)
        return Resp(404, "", url)

def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: sys.exit(1)

# 1) historik: justering, tomma rader, datum via gmtoffset
rows = parse_chart(CHART)
check("historik: 4 rader (tom hoppas över)", len(rows) == 4)
check("historik: stängning är justerad", rows[0][4] == 10.0 and abs(rows[0][1] - 10 * (10.0 / 10.5)) < 1e-9)
check("historik: datum stigande", [r[0] for r in rows] == sorted(r[0] for r in rows))
# 2) earnings-HTML
e = parse_earnings_html(HTML)
check("rapporter: 3 rader, datum rätt", [x["date"] for x in e] == ["2027-01-28", "2025-10-30", "2025-07-22"])
check("rapporter: '-' blir None, överraskning tolkas", e[0]["eps_actual"] is None and e[1]["surprise_pct"] == 4.38 and e[2]["surprise_pct"] == -10.88)
# 3) hela leverantören, vanligt flöde
p = YahooHttpProvider(Fake())
h = p.history("TEST", "5y"); check("provider.history", len(h) == 4)
f = p.fundamentals("TEST")
check("info: nycklar och plattning", f["info"].get("sector") == "Technology" and f["info"].get("trailingPE") == 25.5 and f["info"].get("marketCap") == 3e12 and f["info"].get("currency") == "USD")
check("info: shortName från quoteType", f["info"].get("shortName") == "Test Corp")
check("kvartal: sammanslagna per datum, nyast först", [q["date"] for q in f["quarters"]] == ["2025-06-30", "2025-03-31"] and f["quarters"][0]["revenue"] == 120.0 and f["quarters"][0]["net_income"] == 30.0 and f["quarters"][0]["fcf"] == 25.0 and f["quarters"][0]["eps"] == 1.5)
check("rapporter: framtida datum blir next_earnings, utfallna sorteras", f["next_earnings"] == "2027-01-28" and [x["date"] for x in f["earnings"]] == ["2025-10-30", "2025-07-22"])
check("inga fel registrerade", not any(k.endswith("_error") for k in f))
# 4) EU-samtycke
fk = Fake(eu=True); p2 = YahooHttpProvider(fk); f2 = p2.fundamentals("TEST")
check("EU: samtyckesflödet kördes och info hämtades", fk.consented and f2["info"].get("sector") == "Technology")
# 5) gammal crumb -> 401 -> ny crumb och omförsök
fk = Fake(bad_crumb_once=True); f3 = YahooHttpProvider(fk).fundamentals("TEST")
check("utgången crumb: nytt försök lyckas", f3["info"].get("sector") == "Technology")
# 6) 429 ger begriplig svensk text
class Rate(Fake):
    def request(self, method, url, form=None, headers=None):
        return Resp(429, "Too Many Requests", url)
try: YahooHttpProvider(Rate()).history("X"); check("429 ger fel", False)
except YahooError as ex: check("429 ger begripligt fel", "429" in str(ex))
# 7) ETF hoppar över kvartal
SUMMARY["quoteSummary"]["result"][0]["quoteType"]["quoteType"] = "ETF"
f4 = YahooHttpProvider(Fake()).fundamentals("TEST")
check("ETF: inga kvartal hämtas", f4["quarters"] == [] and f4["info"].get("quoteType") == "ETF")
print("\nAlla test gick igenom.")
