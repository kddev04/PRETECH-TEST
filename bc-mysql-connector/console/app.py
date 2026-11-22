"""Pretech Connect console: a browser dashboard over the bcsync connector.

Shows both sides (Business Central and MySQL), runs syncs, queues changes through bc_outbox,
keeps an audit log in MySQL and offers a read-only SQL panel. In mock mode it adds demo actions
that edit records "inside Business Central" so the round trip can be shown live.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text

from bcsync import db
from bcsync.bc_client import BCClient
from bcsync.config import Settings
from bcsync.entities import ENTITIES, table_name
from bcsync.sync import pull_all, push_outbox

STATIC = Path(__file__).parent / "static"
LABELS = {"customers": "Customers", "vendors": "Vendors", "items": "Items", "salesOrders": "Sales orders"}


class ConsoleState:
    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.engine = None
        self.client: Optional[BCClient] = None
        self.mock_url: Optional[str] = None
        self.lock = threading.Lock()
        self.auto_sync = False
        self.auto_interval = 10
        self.events: Deque[Dict[str, Any]] = deque(maxlen=300)
        self.company: Optional[Dict[str, Any]] = None

    @property
    def is_mock(self) -> bool:
        return bool(self.settings and self.settings.auth_mode == "mock")


state = ConsoleState()
app = FastAPI(title="Pretech Connect")


# ---------- event log: in memory for the screen, in MySQL for the record ----------
class _EventHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("bcsync"):
            kind = "error" if record.levelno >= logging.ERROR else ("warn" if record.levelno >= logging.WARNING else "info")
            state.events.appendleft({"at": datetime.now().strftime("%H:%M:%S"), "kind": kind,
                                     "message": record.getMessage()})


def event(kind: str, message: str) -> None:
    state.events.appendleft({"at": datetime.now().strftime("%H:%M:%S"), "kind": kind, "message": message})
    try:
        db.log_event(state.engine, kind, message)
    except Exception:  # the audit log must never break the demo
        pass


def configure(settings: Settings, mock_url: Optional[str]) -> None:
    state.settings = settings
    state.mock_url = mock_url
    state.engine = db.make_engine(settings.sqlalchemy_url)
    db.init_db(state.engine)
    state.client = BCClient(settings)
    handler = _EventHandler(level=logging.INFO)
    logging.getLogger("bcsync").addHandler(handler)
    logging.getLogger("bcsync").setLevel(logging.INFO)
    threading.Thread(target=_auto_loop, daemon=True).start()


# ---------- helpers ----------
def jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def require_entity(entity: str) -> None:
    if entity not in ENTITIES:
        raise HTTPException(404, f"Unknown entity {entity}")


def require_mock() -> str:
    if not state.is_mock or not state.mock_url:
        raise HTTPException(400, "This demo action only exists with the mock Business Central")
    return state.mock_url


def bc_records(entity: str) -> Optional[List[Dict[str, Any]]]:
    """What Business Central holds right now (mock only; a live tenant is read through the sync)."""
    if not state.is_mock:
        return None
    return httpx.get(f"{state.mock_url}/_mock/records/{entity}", timeout=10).json()


def run_sync(full: bool = False, reason: str = "manual") -> Dict[str, Any]:
    with state.lock:
        t0 = time.perf_counter()
        pulls = pull_all(state.client, state.engine, state.settings, full=full)
        push = push_outbox(state.client, state.engine, state.settings)
        ms = int((time.perf_counter() - t0) * 1000)
    pulled = sum(p.changed for p in pulls)
    read = sum(p.rows for p in pulls)
    errors = [f"{p.entity}: {p.error}" for p in pulls if p.error] + push.errors
    summary = (f"Sync ({reason}{', full' if full else ''}): {pulled} changed record(s) pulled (read {read}), "
               f"pushed {push.done}, failed {push.failed}, waiting {push.retry_later} · {ms} ms")
    event("error" if errors else "sync", summary)
    return {"pulled": {p.entity: p.changed for p in pulls}, "read": read, "pushed": push.done, "failed": push.failed,
            "retry_later": push.retry_later, "errors": errors, "ms": ms}


def _auto_loop() -> None:
    while True:
        time.sleep(1)
        if not state.auto_sync:
            continue
        try:
            run_sync(reason="auto")
        except Exception as exc:
            event("error", f"Auto sync failed: {exc}")
        for _ in range(state.auto_interval):
            if not state.auto_sync:
                break
            time.sleep(1)


# ---------- API ----------
@app.get("/api/overview")
def overview() -> Dict[str, Any]:
    s, engine = state.settings, state.engine
    if state.company is None:
        try:
            comps = state.client.companies()
            state.company = next((c for c in comps if c["id"] == state.client.company_id), comps[0] if comps else {})
        except Exception as exc:
            state.company = {"displayName": f"not reachable: {exc}"}
    url = engine.url
    dbinfo = {"dialect": engine.dialect.name, "host": url.host or "local file", "port": url.port,
              "database": url.database, "ok": True, "version": None}
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "mysql":
                dbinfo["version"] = conn.execute(text("SELECT VERSION()")).scalar()
            else:
                dbinfo["version"] = conn.execute(text("SELECT sqlite_version()")).scalar()
    except Exception as exc:
        dbinfo.update(ok=False, error=str(exc))

    entities = []
    with engine.connect() as conn:
        states = {r["entity"]: r for r in conn.execute(select(db.sync_state)).mappings()}
        pending_by_entity = dict(conn.execute(
            select(db.outbox.c.entity, func.count()).where(db.outbox.c.status == "pending").group_by(db.outbox.c.entity)
        ).all())
        for e in s.entities:
            rows = conn.execute(select(func.count()).select_from(db.mirror_tables[e])).scalar()
            bc = bc_records(e)
            st = states.get(e) or {}
            entities.append({
                "entity": e, "label": LABELS.get(e, e), "mysql_rows": rows,
                "bc_rows": len(bc) if bc is not None else None,
                "cursor": st.get("cursor_ts"), "last_run": st.get("last_run_at"),
                "last_error": st.get("last_error"), "pending": pending_by_entity.get(e, 0),
            })
        outbox_counts = dict(conn.execute(select(db.outbox.c.status, func.count()).group_by(db.outbox.c.status)).all())
    return jsonable({
        "mode": s.auth_mode, "environment": s.environment, "api_root": s.api_root,
        "company": state.company, "db": dbinfo, "entities": entities, "outbox": outbox_counts,
        "auto_sync": state.auto_sync, "auto_interval": state.auto_interval,
    })


@app.get("/api/records/{entity}")
def records(entity: str) -> Dict[str, Any]:
    require_entity(entity)
    table = db.mirror_tables[entity]
    cols = [c.column for c in ENTITIES[entity]]
    with state.engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            select(*[table.c[c] for c in ["id", *cols, "etag", "bc_last_modified", "synced_at"]])
            .order_by(table.c.number)).mappings()]
        pending = {r["bc_number"] or r["bc_id"] for r in conn.execute(
            select(db.outbox.c.bc_number, db.outbox.c.bc_id)
            .where(db.outbox.c.entity == entity, db.outbox.c.status == "pending")).mappings()}
    bc = bc_records(entity)
    bc_by_id = {r["id"]: r for r in bc} if bc is not None else None
    for r in rows:
        if r["number"] in pending or r["id"] in pending:
            r["sync_status"] = "pending"
        elif bc_by_id is None:
            r["sync_status"] = "synced"
        elif r["id"] not in bc_by_id:
            r["sync_status"] = "only-mysql"
        elif bc_by_id[r["id"]].get("@odata.etag") != r["etag"]:
            r["sync_status"] = "changed-in-bc"
        else:
            r["sync_status"] = "synced"
    new_in_bc = []
    if bc_by_id is not None:
        known = {r["id"] for r in rows}
        new_in_bc = [{"id": b["id"], "number": b.get("number"), "name": b.get("displayName") or b.get("customerName"),
                      "sync_status": "new-in-bc"} for b in bc if b["id"] not in known]
    fields = [{"bc": c.bc_field, "col": c.column, "kind": c.kind} for c in ENTITIES[entity]]
    return jsonable({"entity": entity, "columns": cols, "fields": fields, "rows": rows,
                     "new_in_bc": new_in_bc, "bc": bc_by_id})


class SyncRequest(BaseModel):
    full: bool = False


@app.post("/api/sync")
def sync(req: SyncRequest) -> Dict[str, Any]:
    return run_sync(full=req.full)


class AutoRequest(BaseModel):
    on: bool
    interval: int = 10


@app.post("/api/auto-sync")
def auto_sync(req: AutoRequest) -> Dict[str, Any]:
    state.auto_sync = req.on
    state.auto_interval = max(5, min(req.interval, 300))
    event("info", f"Auto sync {'on, every ' + str(state.auto_interval) + ' s' if req.on else 'off'}")
    return {"auto_sync": state.auto_sync, "interval": state.auto_interval}


class OutboxRequest(BaseModel):
    entity: str
    operation: str
    payload: Dict[str, Any]
    bc_number: Optional[str] = None
    bc_id: Optional[str] = None


@app.post("/api/outbox")
def add_outbox(req: OutboxRequest) -> Dict[str, Any]:
    require_entity(req.entity)
    if req.operation not in ("create", "update"):
        raise HTTPException(400, "operation must be create or update")
    if req.operation == "update" and not (req.bc_number or req.bc_id):
        raise HTTPException(400, "an update needs bc_number or bc_id")
    row_id = db.enqueue(state.engine, req.entity, req.operation, req.payload, bc_id=req.bc_id, bc_number=req.bc_number)
    target = req.bc_number or req.bc_id or "new record"
    event("queue", f"MySQL queued {req.operation} of {LABELS[req.entity].lower()} {target} in bc_outbox "
                   f"(#{row_id}): {', '.join(f'{k}={v}' for k, v in req.payload.items())}")
    return {"id": row_id}


@app.get("/api/outbox")
def list_outbox() -> List[Dict[str, Any]]:
    with state.engine.connect() as conn:
        rows = conn.execute(select(db.outbox).order_by(desc(db.outbox.c.id)).limit(50)).mappings().all()
    return jsonable([dict(r) for r in rows])


@app.post("/api/outbox/{row_id}/retry")
def retry_outbox(row_id: int) -> Dict[str, Any]:
    db.mark_outbox(state.engine, row_id, datetime.utcnow(), status="pending", attempts=0, last_error=None)
    event("queue", f"Outbox #{row_id} set back to pending")
    return {"ok": True}


class EditRequest(BaseModel):
    entity: str
    number: str
    fields: Dict[str, Any]


@app.post("/api/demo/bc-edit")
def demo_bc_edit(req: EditRequest) -> Dict[str, Any]:
    url = require_mock()
    require_entity(req.entity)
    resp = httpx.post(f"{url}/_mock/touch/{req.entity}/{req.number}", json=req.fields, timeout=10)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.json().get("error", {}).get("message", resp.text))
    event("bc-edit", f"Business Central user changed {LABELS[req.entity].lower()} {req.number}: "
                     f"{', '.join(f'{k}={v}' for k, v in req.fields.items())}")
    return jsonable(resp.json())


class ThrottleRequest(BaseModel):
    on: bool


@app.post("/api/demo/throttle")
def demo_throttle(req: ThrottleRequest) -> Dict[str, Any]:
    url = require_mock()
    httpx.post(f"{url}/_mock/config", json={"throttle_every": 3 if req.on else 0}, timeout=10)
    event("info", "Business Central throttling simulation " + ("on: every 3rd call gets HTTP 429" if req.on else "off"))
    return {"throttle": req.on}


@app.post("/api/demo/reset")
def demo_reset() -> Dict[str, Any]:
    url = require_mock()
    with state.lock:
        state.auto_sync = False
        httpx.post(f"{url}/_mock/reset", timeout=10)
        db.metadata.drop_all(state.engine)
        db.init_db(state.engine)
        state.events.clear()
        state.company = None
    event("info", "Demo reset: Business Central sample company restored, MySQL tables recreated empty")
    return {"ok": True}


@app.get("/api/events")
def events() -> List[Dict[str, Any]]:
    return list(state.events)


_SQL_OK = re.compile(r"^\s*(select|with|show|describe|desc|explain)\b", re.I)
_SQL_BAD = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|replace|call|load|"
                      r"set|lock|unlock|rename|handler|do|into|outfile|dumpfile|sleep|benchmark)\b", re.I)


class SqlRequest(BaseModel):
    query: str


@app.post("/api/sql")
def run_sql(req: SqlRequest) -> Dict[str, Any]:
    q = req.query.strip().rstrip(";").strip()
    if not q or ";" in q or not _SQL_OK.match(q) or _SQL_BAD.search(q):
        raise HTTPException(400, "Read-only panel: one SELECT, SHOW, DESCRIBE or EXPLAIN statement only")
    with state.engine.connect() as conn:
        if state.engine.dialect.name == "mysql":
            conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
        try:
            res = conn.execute(text(q))
            cols = list(res.keys())
            rows = [list(r) for r in res.fetchmany(200)]
        except Exception as exc:
            raise HTTPException(400, str(getattr(exc, "orig", exc)))
        finally:
            conn.rollback()
            if state.engine.dialect.name == "mysql":
                conn.execute(text("SET SESSION TRANSACTION READ WRITE"))
    return jsonable({"columns": cols, "rows": rows, "truncated": len(rows) == 200})


@app.get("/api/meta")
def meta() -> Dict[str, Any]:
    out = {}
    with state.engine.connect() as conn:
        for e in ("customers", "items"):
            t = db.mirror_tables[e]
            out[e] = [dict(r) for r in conn.execute(select(t.c.number, t.c.display_name).order_by(t.c.number)).mappings()]
    out["tables"] = sorted(db.metadata.tables)
    out["mirror_tables"] = {e: table_name(e) for e in ENTITIES}
    return out


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))
