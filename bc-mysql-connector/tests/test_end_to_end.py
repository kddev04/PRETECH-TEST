"""End to end: the real connector and console against the mock Business Central and a real MySQL.

Needs MySQL from .env (the docker container started by start-demo.bat). Starts the mock BC on 8765.
"""
from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from bcsync import db
from bcsync.bc_client import BCClient
from bcsync.config import load_settings
from bcsync.sync import pull_all, pull_entity, push_outbox
from bcsync.webhook import app as webhook_app, entity_from_resource

MOCK = "http://127.0.0.1:8765"
SEED = {"customers": 8, "vendors": 3, "items": 18, "salesOrders": 5}


@pytest.fixture(scope="session")
def mock_server():
    from mock_bc.app import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", 8765), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield MOCK
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def env(mock_server):
    settings = load_settings(".env")
    settings.auth_mode = "mock"
    settings.base_url = mock_server
    engine = db.make_engine(settings.sqlalchemy_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"MySQL not reachable: {exc}")
    db.metadata.drop_all(engine)
    db.init_db(engine)
    httpx.post(f"{mock_server}/_mock/reset")
    client = BCClient(settings)
    yield settings, engine, client
    client.close()
    db.metadata.drop_all(engine)  # leave MySQL clean for real runs
    engine.dispose()


def count(engine, entity):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {db.mirror_tables[entity].name}")).scalar()


def outbox_row(engine, row_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(db.outbox).where(db.outbox.c.id == row_id)).mappings().one())


def mock_record(entity, number):
    return next(r for r in httpx.get(f"{MOCK}/_mock/records/{entity}").json() if r["number"] == number)


# ---------- connector ----------
def test_full_pull_pages_and_types(env):
    settings, engine, client = env
    results = pull_all(client, engine, settings)
    assert [r.error for r in results] == [None] * 4
    assert {r.entity: r.rows for r in results} == SEED   # mock pages 5 at a time: 18 items = 4 pages
    with engine.connect() as conn:
        item = conn.execute(text(
            "SELECT display_name, unit_price, item_category_code, etag, raw, bc_last_modified "
            "FROM bc_items WHERE number='FP-PLC'")).mappings().one()
        so = conn.execute(text(
            "SELECT customer_name, external_document_number, total_incl_tax, requested_delivery_date "
            "FROM bc_sales_orders WHERE number='SO-0001'")).mappings().one()
    assert item["display_name"] == "Flameproof PLC panel"
    assert float(item["unit_price"]) == 485000.0 and item["item_category_code"] == "FLAMEPROOF"
    assert item["etag"].startswith('W/"') and item["bc_last_modified"] is not None
    assert so["customer_name"] == "Emcure Pharmaceuticals Ltd." and so["external_document_number"] == "EMC/PO/26/0412"
    assert float(so["total_incl_tax"]) == round(485000 * 2 * 1.18, 2) and so["requested_delivery_date"] is not None


def test_incremental_pull_reads_only_changes(env):
    settings, engine, client = env
    pull_all(client, engine, settings)
    httpx.post(f"{MOCK}/_mock/touch/customers/C0002", json={"city": "Thane"})
    settings.cursor_overlap_seconds = 0
    r = pull_entity(client, engine, settings, "customers")
    assert r.rows == 1 and r.changed == 1 and r.error is None
    with engine.connect() as conn:
        assert conn.execute(text("SELECT city FROM bc_customers WHERE number='C0002'")).scalar() == "Thane"
    settings.cursor_overlap_seconds = 2          # the default overlap re-reads, but writes nothing
    again = pull_entity(client, engine, settings, "customers")
    assert again.changed == 0
    assert count(engine, "customers") == SEED["customers"]


def test_push_create_then_update_by_number(env):
    settings, engine, client = env
    pull_all(client, engine, settings)
    new_id = db.enqueue(engine, "customers", "create", {
        "displayName": "Bhima Biotech LLP", "city": "Pune", "country": "IN", "currencyCode": "INR"})
    upd_id = db.enqueue(engine, "customers", "update", {"phoneNumber": "+91 20 4000 9999"}, bc_number="C0001")
    r = push_outbox(client, engine, settings)
    assert (r.done, r.failed) == (2, 0), r.errors
    created = outbox_row(engine, new_id)
    assert created["status"] == "done" and created["bc_id"] and created["bc_number"] == "C0009"
    assert mock_record("customers", "C0009")["displayName"] == "Bhima Biotech LLP"
    assert count(engine, "customers") == SEED["customers"] + 1
    assert mock_record("customers", "C0001")["phoneNumber"] == "+91 20 4000 9999"
    assert outbox_row(engine, upd_id)["status"] == "done"


def test_stale_etag_is_refreshed_once(env):
    settings, engine, client = env
    pull_all(client, engine, settings)
    httpx.post(f"{MOCK}/_mock/touch/customers/C0003", json={"city": "Surat"})
    row_id = db.enqueue(engine, "customers", "update", {"creditLimit": 7000000}, bc_number="C0003")
    r = push_outbox(client, engine, settings)
    assert r.done == 1, r.errors
    rec = mock_record("customers", "C0003")
    assert rec["city"] == "Surat" and rec["creditLimit"] == 7000000      # both changes survive
    assert outbox_row(engine, row_id)["attempts"] == 1


def test_validation_error_parks_the_row(env):
    settings, engine, client = env
    row_id = db.enqueue(engine, "customers", "create", {"city": "Pune"})  # no displayName
    r = push_outbox(client, engine, settings)
    assert r.failed == 1
    row = outbox_row(engine, row_id)
    assert row["status"] == "failed" and "displayName" in row["last_error"]


def test_update_waits_for_record_not_yet_pulled(env):
    settings, engine, client = env
    row_id = db.enqueue(engine, "items", "update", {"unitPrice": 39900}, bc_number="FP-LCP")
    push_outbox(client, engine, settings)                      # mirror empty: stays pending
    assert outbox_row(engine, row_id)["status"] == "pending"
    pull_all(client, engine, settings)
    push_outbox(client, engine, settings)
    assert outbox_row(engine, row_id)["status"] == "done"
    assert mock_record("items", "FP-LCP")["unitPrice"] == 39900


def test_throttling_is_retried(env):
    settings, engine, client = env
    httpx.post(f"{MOCK}/_mock/config", json={"throttle_every": 2})
    try:
        r = pull_entity(client, engine, settings, "items", full=True)
    finally:
        httpx.post(f"{MOCK}/_mock/config", json={"throttle_every": 0})
    assert r.error is None and r.rows == SEED["items"]


def test_webhook_handshake_and_resource_parsing():
    tc = TestClient(webhook_app)
    resp = tc.post("/bc/notify?validationToken=abc123")
    assert resp.status_code == 200 and resp.text == "abc123"
    assert entity_from_resource("api/v2.0/companies(6a1c)/salesOrders(1234)") == "salesOrders"
    assert entity_from_resource("nothing here") is None


# ---------- console ----------
@pytest.fixture()
def console(env):
    settings, engine, _ = env
    from console.app import app, configure, state
    configure(settings, MOCK)
    state.events.clear()
    state.company = None
    return TestClient(app)


def statuses(tc, entity):
    return {r["number"]: r["sync_status"] for r in tc.get(f"/api/records/{entity}").json()["rows"]}


def test_console_round_trip(console):
    tc = console
    ov = tc.get("/api/overview").json()
    assert ov["mode"] == "mock" and ov["company"]["displayName"] == "Pretech Automation Pvt. Ltd."
    assert ov["db"]["ok"] and ov["db"]["dialect"] == "mysql"
    assert {e["entity"]: e["bc_rows"] for e in ov["entities"]} == SEED
    assert all(e["mysql_rows"] == 0 for e in ov["entities"])

    r = tc.post("/api/sync", json={"full": True}).json()
    assert r["pulled"] == SEED and not r["errors"]
    assert set(statuses(tc, "items").values()) == {"synced"}

    # step 2: an edit inside Business Central shows up as "changed in BC", then syncs
    tc.post("/api/demo/bc-edit", json={"entity": "items", "number": "FP-PLC", "fields": {"unitPrice": 499000}})
    assert statuses(tc, "items")["FP-PLC"] == "changed-in-bc"
    step2 = tc.post("/api/sync", json={"full": False}).json()
    assert sum(step2["pulled"].values()) == 1, step2
    rows = {r["number"]: r for r in tc.get("/api/records/items").json()["rows"]}
    assert rows["FP-PLC"]["sync_status"] == "synced" and rows["FP-PLC"]["unit_price"] == 499000

    # step 3: a change from MySQL is "waiting to push", then lands in BC
    assert tc.post("/api/outbox", json={"entity": "items", "operation": "update", "bc_number": "EP-MCC",
                                        "payload": {"unitPrice": 949000}}).status_code == 200
    assert statuses(tc, "items")["EP-MCC"] == "pending"
    r = tc.post("/api/sync", json={"full": False}).json()
    assert r["pushed"] == 1 and r["failed"] == 0
    assert mock_record("items", "EP-MCC")["unitPrice"] == 949000
    assert statuses(tc, "items")["EP-MCC"] == "synced"

    # step 4: a new customer gets its number from BC
    tc.post("/api/outbox", json={"entity": "customers", "operation": "create",
                                 "payload": {"displayName": "Bhima Biotech LLP", "city": "Pune"}})
    tc.post("/api/sync", json={"full": False})
    assert "C0009" in statuses(tc, "customers")

    # audit trail kept in MySQL, and the activity feed has the story
    sql = tc.post("/api/sql", json={"query": "SELECT kind, message FROM bc_sync_log ORDER BY id"}).json()
    kinds = [row[0] for row in sql["rows"]]
    assert "bc-edit" in kinds and "queue" in kinds and "sync" in kinds
    assert any("FP-PLC" in e["message"] for e in tc.get("/api/events").json())


def test_console_sql_panel_is_read_only(console):
    tc = console
    ok = tc.post("/api/sql", json={"query": "SELECT COUNT(*) AS n FROM bc_items"})
    assert ok.status_code == 200 and ok.json()["columns"] == ["n"]
    for bad in ("DELETE FROM bc_items", "DROP TABLE bc_items", "SELECT 1; DELETE FROM bc_items",
                "UPDATE bc_items SET unit_price = 0", "SELECT * INTO OUTFILE '/tmp/x' FROM bc_items",
                "WITH x AS (SELECT 1) DELETE FROM bc_items"):
        assert tc.post("/api/sql", json={"query": bad}).status_code == 400, bad


def test_console_reset(console):
    tc = console
    tc.post("/api/sync", json={"full": True})
    tc.post("/api/demo/bc-edit", json={"entity": "items", "number": "FP-PLC", "fields": {"unitPrice": 1}})
    assert tc.post("/api/demo/reset").status_code == 200
    ov = tc.get("/api/overview").json()
    assert all(e["mysql_rows"] == 0 for e in ov["entities"])
    assert mock_record("items", "FP-PLC")["unitPrice"] == 485000
