"""Starta Marknadsradar:  python run.py            (riktig data via Yahoo Finance)
                         python run.py --demo     (syntetisk data, fungerar offline)
Öppna sedan http://127.0.0.1:8000 i webbläsaren."""
import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

ap = argparse.ArgumentParser()
ap.add_argument("--demo", action="store_true", help="använd syntetisk demo-data (inget nätverk behövs)")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--no-browser", action="store_true")
ap.add_argument("--lan", action="store_true", help="gör appen nåbar från andra enheter på ditt nätverk (t.ex. mobilen). Kräver åtkomstnyckel.")
ap.add_argument("--key", default="", help="åtkomstnyckel för nätverksläge (skapas automatiskt om den saknas)")
args = ap.parse_args()

if args.demo:
    os.environ["MARKNADSRADAR_PROVIDER"] = "demo"

if args.lan or args.host not in ("127.0.0.1", "localhost"):
    import secrets
    import socket
    args.host = "0.0.0.0"
    key = args.key or os.environ.get("MARKNADSRADAR_KEY") or secrets.token_urlsafe(9)
    os.environ["MARKNADSRADAR_KEY"] = key
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            ip = sk.getsockname()[0]
    except Exception:
        ip = "<datorns IP-adress>"
    print(f"\n  Nätverksläge. Öppna på mobilen (samma wifi):  http://{ip}:{args.port}/?key={key}\n  Skydda nyckeln: den ger full åtkomst till din journal och dina portföljer.\n", flush=True)

import uvicorn  # noqa: E402

if not args.no_browser and not os.environ.get("MARKNADSRADAR_KEY"):
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")
