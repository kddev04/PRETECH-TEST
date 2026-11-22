"""One-command demo: mock Business Central + your MySQL, a full round trip, then a summary.

    python demo.py

Starts the mock BC API in a background thread (port 8765), creates the tables, pulls everything,
writes a price change into bc_outbox the way another application would, pushes it, and shows
that BC and MySQL now agree. Uses the MySQL settings from .env.
"""
from __future__ import annotations

import logging
import socket
import threading
import time

import httpx
import uvicorn
from sqlalchemy import text

from bcsync import db
from bcsync.bc_client import BCClient
from bcsync.config import load_settings
from bcsync.sync import pull_all, push_outbox

MOCK = "http://127.0.0.1:8765"


def start_mock() -> uvicorn.Server:
    from mock_bc.app import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", 8765), timeout=0.2).close()
            return server
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("mock BC did not start")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    server = start_mock()
    settings = load_settings(".env")
    settings.auth_mode, settings.base_url = "mock", MOCK
    engine = db.make_engine(settings.sqlalchemy_url)
    db.init_db(engine)
    client = BCClient(settings)
    try:
        print("\n1. Pull Business Central -> MySQL")
        for r in pull_all(client, engine, settings):
            print(f"   {r.entity:<12} {r.rows} rows")

        print("\n2. Another app asks for a price change by writing to bc_outbox")
        db.enqueue(engine, "items", "update", {"unitPrice": 949000}, bc_number="EP-MCC")

        print("\n3. Push MySQL -> Business Central")
        res = push_outbox(client, engine, settings)
        print(f"   done={res.done} failed={res.failed} errors={res.errors}")

        bc_price = next(r["unitPrice"] for r in httpx.get(f"{MOCK}/_mock/records/items").json()
                        if r["number"] == "EP-MCC")
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT number, display_name, unit_price FROM bc_items "
                "WHERE item_category_code IN ('LV-ELECTRICAL','FLAMEPROOF') ORDER BY number")).all()
            totals = conn.execute(text("SELECT COUNT(*), COUNT(DISTINCT number) FROM bc_items")).one()
        print(f"\n4. Result: BC price for EP-MCC = {bc_price:,.0f}")
        for number, name, price in rows:
            print(f"   {number:<9} {name:<56} {float(price):>12,.0f}")
        print(f"   bc_items rows={totals[0]} distinct numbers={totals[1]}")
    finally:
        client.close()
        server.should_exit = True


if __name__ == "__main__":
    main()
