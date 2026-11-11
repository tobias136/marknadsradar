"""SQLite-lagring. Demo-läget använder en separat databasfil så att
syntetisk data aldrig hamnar i din riktiga databas."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MARKNADSRADAR_DATA", BASE_DIR / "data"))
DEMO = os.environ.get("MARKNADSRADAR_PROVIDER", "yahoo").lower() == "demo"
DB_PATH = DATA_DIR / ("marknadsradar_demo.db" if DEMO else "marknadsradar.db")
EXPORT_DIR = DATA_DIR / ("export_demo" if DEMO else "export")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    benchmark TEXT DEFAULT '',
    description TEXT DEFAULT '',
    position INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS list_items (
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    grp TEXT DEFAULT 'Övrigt',
    label TEXT DEFAULT '',
    auto_group INTEGER DEFAULT 0,
    position INTEGER DEFAULT 0,
    PRIMARY KEY (list_id, ticker)
);
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS price_meta (
    ticker TEXT PRIMARY KEY,
    last_full TEXT,
    last_fetch TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT PRIMARY KEY,
    fetched_at TEXT,
    data TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    ticker TEXT PRIMARY KEY,
    text TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    created TEXT NOT NULL,
    action TEXT NOT NULL,
    price REAL,
    currency TEXT DEFAULT '',
    signal_score INTEGER,
    signal_label TEXT DEFAULT '',
    thesis TEXT DEFAULT '',
    invalidation TEXT DEFAULT '',
    horizon_days INTEGER DEFAULT 90,
    review_on TEXT,
    status TEXT DEFAULT 'open',
    outcome TEXT DEFAULT '',
    lesson TEXT DEFAULT '',
    closed_price REAL,
    closed_on TEXT,
    closed_signal INTEGER
);
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT DEFAULT '',
    name TEXT DEFAULT '',
    isin TEXT DEFAULT '',
    qty REAL NOT NULL,
    avg_cost REAL,
    currency TEXT DEFAULT '',
    account TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS progress (
    event TEXT NOT NULL,
    key TEXT NOT NULL,
    ts TEXT,
    PRIMARY KEY (event, key)
);
CREATE TABLE IF NOT EXISTS practice_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ts TEXT,
    correct INTEGER,
    detail TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cards (
    key TEXT PRIMARY KEY,
    box INTEGER DEFAULT 1,
    due TEXT,
    added TEXT,
    reviews INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS paper_portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    strategy TEXT DEFAULT '',
    cash0 REAL NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER NOT NULL REFERENCES paper_portfolios(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    currency TEXT DEFAULT '',
    qty REAL NOT NULL,
    entry_date TEXT,
    entry_price REAL,
    entry_fx REAL DEFAULT 1,
    stop REAL NOT NULL,
    stop0 REAL,
    stop_from TEXT,
    stop_moves INTEGER DEFAULT 0,
    target REAL,
    thesis TEXT DEFAULT '',
    invalidation TEXT DEFAULT '',
    horizon_days INTEGER DEFAULT 90,
    review_on TEXT,
    risk_pct REAL,
    pos_pct REAL,
    signal_score INTEGER,
    status TEXT DEFAULT 'open',
    exit_date TEXT,
    exit_price REAL,
    exit_fx REAL,
    exit_reason TEXT DEFAULT '',
    lesson TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS playbook (
    key TEXT PRIMARY KEY,
    text TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a TEXT NOT NULL,
    b TEXT NOT NULL,
    rtype TEXT NOT NULL,
    strength TEXT DEFAULT 'mentioned',
    share_pct REAL,
    amount TEXT DEFAULT '',
    source_url TEXT NOT NULL,
    source_title TEXT DEFAULT '',
    as_of TEXT DEFAULT '',
    confidence TEXT DEFAULT 'primär',
    note TEXT DEFAULT '',
    created TEXT
);
CREATE TABLE IF NOT EXISTS rel_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a TEXT NOT NULL, b TEXT NOT NULL, rtype TEXT NOT NULL,
    source_url TEXT NOT NULL, source_title TEXT DEFAULT '', as_of TEXT DEFAULT '',
    confidence TEXT DEFAULT 'sekundär', origin TEXT DEFAULT 'wikidata', note TEXT DEFAULT '',
    status TEXT DEFAULT 'pending', created TEXT, decided TEXT,
    UNIQUE(a, b, rtype, source_url)
);
CREATE TABLE IF NOT EXISTS rel_qid (
    ticker TEXT PRIMARY KEY, qid TEXT, status TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS rel_health (
    eid INTEGER PRIMARY KEY, checked TEXT, ok INTEGER, fails INTEGER DEFAULT 0, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rel_reviewed (
    ticker TEXT PRIMARY KEY,
    ts TEXT
);
CREATE TABLE IF NOT EXISTS rule_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    hypothesis TEXT,
    rule TEXT,
    result TEXT
);
CREATE TABLE IF NOT EXISTS trader_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    decision TEXT,
    reflection TEXT,
    verdict TEXT,
    n INTEGER
);
CREATE TABLE IF NOT EXISTS monthly_reviews (
    month TEXT PRIMARY KEY,
    good TEXT,
    bad TEXT,
    change TEXT,
    stats TEXT,
    created TEXT
);
CREATE TABLE IF NOT EXISTS quiz_results (
    qid TEXT PRIMARY KEY,
    correct INTEGER,
    ts TEXT
);
"""


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)


def get_setting(key: str, default: str | None = None) -> str | None:
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
