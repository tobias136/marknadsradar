"""Startpunkt för Android (anropas från MainActivity via Chaquopy). Startar samma FastAPI-app som på datorn."""
import os
import threading
import traceback


def start(data_dir, static_dir, port, key):
    os.environ["MARKNADSRADAR_DATA"] = str(data_dir)
    os.environ["MARKNADSRADAR_STATIC"] = str(static_dir)
    os.environ["MARKNADSRADAR_HTTP"] = "android"   # Yahoo via telefonens egna nätverk (se app/yahoo_http.py)
    os.environ["MARKNADSRADAR_KEY"] = str(key)     # bara appens egen WebView känner nyckeln
    log = os.path.join(str(data_dir), "server.log")
    os.makedirs(str(data_dir), exist_ok=True)

    def run():
        try:
            import uvicorn
            cfg = uvicorn.Config("app.main:app", host="127.0.0.1", port=int(port), log_level="warning", loop="asyncio", http="h11", lifespan="on")
            uvicorn.Server(cfg).run()
        except BaseException:  # noqa: BLE001
            with open(log, "a") as f:
                f.write(traceback.format_exc())

    threading.Thread(target=run, daemon=True, name="marknadsradar-server").start()


def last_log(data_dir, n=15):
    try:
        with open(os.path.join(str(data_dir), "server.log")) as f:
            return "".join(f.readlines()[-n:])
    except Exception:  # noqa: BLE001
        return ""
