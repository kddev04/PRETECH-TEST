"""Start Pretech Connect: the console (and, in mock mode, the mock Business Central) in one process.

    python run_demo.py              # MySQL from .env
    python run_demo.py --sqlite     # no MySQL available: use a local SQLite file instead
    python run_demo.py --no-browser

Stops cleanly with Ctrl+C or by closing the window. Nothing keeps running afterwards.
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bcsync import db  # noqa: E402
from bcsync.config import load_settings  # noqa: E402

MOCK_PORT = 8765


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_port(port: int, seconds: float = 15) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if not port_free(port):
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Start Pretech Connect")
    ap.add_argument("--sqlite", action="store_true", help="use a local SQLite file instead of MySQL")
    ap.add_argument("--port", type=int, default=8000, help="console port (default 8000)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = load_settings(str(ROOT / ".env"))
    if args.sqlite:
        settings.database_url = f"sqlite:///{(ROOT / 'pretech_connect.db').as_posix()}"

    # 1. database reachable?
    engine = db.make_engine(settings.sqlalchemy_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print("\n  Cannot reach the database:", str(getattr(exc, "orig", exc)).splitlines()[0])
        print("  Start MySQL (start-demo.bat does this with Docker) or run:  python run_demo.py --sqlite\n")
        return 2
    engine.dispose()

    # 2. mock Business Central, unless a live tenant is configured
    servers = []
    mock_url = None
    if settings.auth_mode == "mock":
        if not port_free(MOCK_PORT):
            print(f"\n  Port {MOCK_PORT} is already in use. Close the other Pretech Connect window and try again.\n")
            return 3
        from mock_bc.app import app as mock_app
        mock = uvicorn.Server(uvicorn.Config(mock_app, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
        threading.Thread(target=mock.run, daemon=True).start()
        if not wait_port(MOCK_PORT):
            print("  The mock Business Central did not start.")
            return 4
        servers.append(mock)
        mock_url = f"http://127.0.0.1:{MOCK_PORT}"
        settings.base_url = mock_url

    # 3. console
    if not port_free(args.port):
        print(f"\n  Port {args.port} is already in use. Try:  python run_demo.py --port 8010\n")
        return 3
    from console.app import app as console_app, configure
    configure(settings, mock_url)
    console = uvicorn.Server(uvicorn.Config(console_app, host="127.0.0.1", port=args.port, log_level="warning"))
    threading.Thread(target=console.run, daemon=True).start()
    if not wait_port(args.port):
        print("  The console did not start.")
        return 4
    servers.append(console)

    url = f"http://127.0.0.1:{args.port}"
    where = "mock Business Central (Pretech sample company)" if mock_url else f"Business Central tenant {settings.tenant_id}/{settings.environment}"
    dbname = "SQLite file pretech_connect.db" if args.sqlite else f"MySQL {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}"
    print("\n  ===========================================================")
    print("   Pretech Connect is running")
    print(f"   Console:          {url}")
    print(f"   Business Central: {where}")
    print(f"   Database:         {dbname}")
    print("   Stop:             press Ctrl+C or close this window")
    print("  ===========================================================\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  Stopping…")
    finally:
        for s in servers:
            s.should_exit = True
        time.sleep(0.8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
