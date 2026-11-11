"""Förvalda listor som skapas första gången appen startar. Allt kan ändras
eller tas bort i gränssnittet. Tickers är Yahoo Finance-symboler
(svenska aktier slutar på .ST) och kan behöva justeras om ett bolag byter symbol."""
from __future__ import annotations

from . import db

SEED = [
    {
        "name": "USA – sektorer (SPDR)", "benchmark": "SPY",
        "description": "Elva sektor-ETF:er som visar sektorrotationen på den amerikanska marknaden.",
        "items": [
            ("XLK", "Teknologi"), ("XLC", "Kommunikation"), ("XLY", "Sällanköp"), ("XLP", "Dagligvaror"),
            ("XLV", "Hälsovård"), ("XLF", "Finans"), ("XLI", "Industri"), ("XLE", "Energi"),
            ("XLB", "Material"), ("XLU", "Kraftbolag"), ("XLRE", "Fastigheter"),
        ],
        "label_is_group": True,
    },
    {
        "name": "Teman & råvaror", "benchmark": "SPY",
        "description": "Tematiska ETF:er: uran, biotech, halvledare, guld, koppar, ren energi och försvar.",
        "items": [
            ("URA", "Uran", "Uran"), ("URNM", "Uran-gruvor", "Uran"), ("XBI", "Biotech", "Biotech"),
            ("SMH", "Halvledare", "Halvledare"), ("GDX", "Guldgruvor", "Guld"), ("COPX", "Koppargruvor", "Koppar"),
            ("ICLN", "Ren energi", "Ren energi"), ("ITA", "Försvar", "Försvar"),
        ],
    },
    {
        "name": "Sverige – storbolag", "benchmark": "^OMX",
        "description": "Ett urval av de största bolagen på Stockholmsbörsen, grupperade per bransch.",
        "items": [
            ("VOLV-B.ST", "", "Industri"), ("ATCO-A.ST", "", "Industri"), ("SAND.ST", "", "Industri"),
            ("ALFA.ST", "", "Industri"), ("ASSA-B.ST", "", "Industri"),
            ("SEB-A.ST", "", "Finans"), ("SHB-A.ST", "", "Finans"), ("SWED-A.ST", "", "Finans"),
            ("INVE-B.ST", "", "Finans"),
            ("ERIC-B.ST", "", "Teknik & telekom"), ("HEXA-B.ST", "", "Teknik & telekom"),
            ("TELIA.ST", "", "Teknik & telekom"),
            ("HM-B.ST", "", "Konsument"), ("ESSITY-B.ST", "", "Konsument"),
            ("BOL.ST", "", "Material"),
        ],
    },
    {
        "name": "AI-infrastruktur", "benchmark": "SPY",
        "description": "Molnjättar, chip och kraftbolag – kedjan som påverkas av AI-investeringar.",
        "items": [
            ("MSFT", "", "Molnjättar"), ("AMZN", "", "Molnjättar"), ("GOOGL", "", "Molnjättar"),
            ("META", "", "Molnjättar"), ("ORCL", "", "Molnjättar"),
            ("NVDA", "", "Chip"), ("AVGO", "", "Chip"), ("TSM", "", "Chip"),
            ("VST", "", "Kraft"), ("CEG", "", "Kraft"),
        ],
    },
    {
        "name": "Mina bevakningar", "benchmark": "SPY",
        "description": "Egna bevakningar – ändra fritt.",
        "items": [("BKNG", "", "Resor"), ("VFS", "", "Fordon")],
    },
]


def seed_if_empty() -> None:
    with db.connect() as con:
        if con.execute("SELECT COUNT(*) c FROM lists").fetchone()["c"] > 0:
            return
        for pos, lst in enumerate(SEED):
            cur = con.execute(
                "INSERT INTO lists(name, benchmark, description, position) VALUES(?,?,?,?)",
                (lst["name"], lst["benchmark"], lst["description"], pos),
            )
            lid = cur.lastrowid
            for i, it in enumerate(lst["items"]):
                ticker, label = it[0], it[1]
                grp = label if lst.get("label_is_group") else (it[2] if len(it) > 2 else "Övrigt")
                con.execute(
                    "INSERT INTO list_items(list_id, ticker, grp, label, auto_group, position) VALUES(?,?,?,?,0,?)",
                    (lid, ticker, grp, label, i),
                )
