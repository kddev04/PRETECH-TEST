"""MySQL schema and helpers: one mirror table per entity, a sync cursor table, and an outbox.

Tables
  bc_<entity>     mirror of Business Central records, keyed by the BC systemId (GUID)
  bc_sync_state   per-entity cursor: the newest lastModifiedDateTime already pulled
  bc_outbox       changes written by Pretech's own systems, waiting to be pushed to BC
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    func,
    select,
    update,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine

from .entities import ENTITIES, table_name

metadata = MetaData()

# microsecond precision on MySQL, plain DateTime elsewhere
TS = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")

_KIND = {
    "text": lambda c: Text(),
    "decimal": lambda c: Numeric(18, 4),
    "bool": lambda c: Boolean(),
    "date": lambda c: Date(),
    "datetime": lambda c: TS,
    "int": lambda c: Integer(),
    "str": lambda c: String(c.length or 255),
}

mirror_tables: Dict[str, Table] = {}
for _entity, _cols in ENTITIES.items():
    mirror_tables[_entity] = Table(
        table_name(_entity),
        metadata,
        Column("id", String(36), primary_key=True, comment="Business Central systemId"),
        *[Column(c.column, _KIND[c.kind](c), nullable=True, index=(c.column == "number")) for c in _cols],
        Column("bc_last_modified", TS, nullable=True, index=True),
        Column("etag", String(120), nullable=True),
        Column("raw", JSON, nullable=False),
        Column("synced_at", TS, nullable=False),
        mysql_charset="utf8mb4",
    )

sync_state = Table(
    "bc_sync_state",
    metadata,
    Column("entity", String(64), primary_key=True),
    Column("cursor_ts", TS, nullable=True, comment="newest lastModifiedDateTime pulled"),
    Column("last_run_at", TS, nullable=True),
    Column("last_rows", Integer, nullable=False, default=0),
    Column("last_error", Text, nullable=True),
    mysql_charset="utf8mb4",
)

outbox = Table(
    "bc_outbox",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity", String(64), nullable=False),
    Column("operation", Enum("create", "update", name="bc_outbox_op"), nullable=False),
    Column("bc_id", String(36), nullable=True, comment="target record for updates; filled in after a create"),
    Column("bc_number", String(20), nullable=True, comment="alternative key for updates, e.g. customer number"),
    Column("payload", JSON, nullable=False),
    Column("status", Enum("pending", "done", "failed", name="bc_outbox_status"), nullable=False,
           default="pending", index=True),
    Column("attempts", Integer, nullable=False, default=0),
    Column("last_error", Text, nullable=True),
    Column("created_at", TS, nullable=False, server_default=func.now()),
    Column("updated_at", TS, nullable=True),
    mysql_charset="utf8mb4",
)


sync_log = Table(
    "bc_sync_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("at", TS, nullable=False),
    Column("kind", String(20), nullable=False, comment="pull, push, edit, error, info"),
    Column("message", Text, nullable=False),
    mysql_charset="utf8mb4",
)


def log_event(engine: Engine, kind: str, message: str) -> None:
    """Audit trail of what the connector did, kept in MySQL next to the data."""
    with engine.begin() as conn:
        conn.execute(sync_log.insert().values(at=datetime.utcnow(), kind=kind, message=message[:2000]))


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


# ---------- value conversion ----------
def parse_bc_datetime(value: Optional[str]) -> Optional[datetime]:
    """'2026-11-22T10:20:30.1234567Z' -> naive UTC datetime with microseconds."""
    if not value:
        return None
    v = value.rstrip("Z")
    if "+" in v[10:]:
        v = v[: 10 + v[10:].index("+")]
    if "." in v:
        head, frac = v.split(".", 1)
        v = f"{head}.{(frac + '000000')[:6]}"
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%f")
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")


def _convert(kind: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if kind == "decimal":
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if kind == "bool":
        return bool(value)
    if kind == "date":
        if value.startswith("0001-01-01"):
            return None  # BC's empty date
        return date.fromisoformat(value[:10])
    if kind == "datetime":
        return parse_bc_datetime(value)
    if kind == "int":
        return int(value)
    if kind == "str":
        return str(value)
    return value


def to_row(entity: str, record: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": record["id"]}
    for c in ENTITIES[entity]:
        row[c.column] = _convert(c.kind, record.get(c.bc_field))
    row["bc_last_modified"] = parse_bc_datetime(record.get("lastModifiedDateTime"))
    row["etag"] = record.get("@odata.etag")
    row["raw"] = record
    row["synced_at"] = now
    return row


# ---------- writes ----------
def upsert(engine: Engine, entity: str, rows: List[Dict[str, Any]]) -> int:
    """Insert or update by id. Idempotent, so re-reading the overlap window is harmless."""
    if not rows:
        return 0
    table = mirror_tables[entity]
    cols = [c.name for c in table.columns if c.name != "id"]
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "mysql":
            stmt = mysql.insert(table).values(rows)
            stmt = stmt.on_duplicate_key_update({c: stmt.inserted[c] for c in cols})
        elif dialect == "sqlite":
            from sqlalchemy.dialects import sqlite
            stmt = sqlite.insert(table).values(rows)
            stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={c: stmt.excluded[c] for c in cols})
        else:
            raise RuntimeError(f"Upsert not implemented for {dialect}")
        conn.execute(stmt)
    return len(rows)


def existing_etags(engine: Engine, entity: str, ids: List[str]) -> Dict[str, Optional[str]]:
    """ETags already stored for these ids, so unchanged records are not rewritten."""
    if not ids:
        return {}
    table = mirror_tables[entity]
    with engine.connect() as conn:
        return {r.id: r.etag for r in conn.execute(select(table.c.id, table.c.etag).where(table.c.id.in_(ids)))}


def get_cursor(engine: Engine, entity: str) -> Optional[datetime]:
    with engine.connect() as conn:
        return conn.execute(select(sync_state.c.cursor_ts).where(sync_state.c.entity == entity)).scalar()


def save_cursor(engine: Engine, entity: str, cursor_ts: Optional[datetime], rows: int,
                error: Optional[str], now: datetime) -> None:
    values = {"cursor_ts": cursor_ts, "last_run_at": now, "last_rows": rows, "last_error": error}
    with engine.begin() as conn:
        exists = conn.execute(select(sync_state.c.entity).where(sync_state.c.entity == entity)).first()
        if exists:
            if cursor_ts is None:
                values.pop("cursor_ts")  # a failed run never moves the cursor backwards
            conn.execute(update(sync_state).where(sync_state.c.entity == entity).values(**values))
        else:
            conn.execute(sync_state.insert().values(entity=entity, **values))


def find_by_number(engine: Engine, entity: str, number: str) -> Optional[Dict[str, Any]]:
    table = mirror_tables[entity]
    if "number" not in table.c:
        return None
    with engine.connect() as conn:
        row = conn.execute(select(table.c.id, table.c.etag).where(table.c.number == number)
                           .order_by(table.c.synced_at.desc())).mappings().first()
    return dict(row) if row else None


def etag_for(engine: Engine, entity: str, record_id: str) -> Optional[str]:
    table = mirror_tables[entity]
    with engine.connect() as conn:
        return conn.execute(select(table.c.etag).where(table.c.id == record_id)).scalar()


def pending_outbox(engine: Engine, limit: int = 200) -> Iterable[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(outbox).where(outbox.c.status == "pending").order_by(outbox.c.id).limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]


def mark_outbox(engine: Engine, row_id: int, now: datetime, **values: Any) -> None:
    with engine.begin() as conn:
        conn.execute(update(outbox).where(outbox.c.id == row_id).values(updated_at=now, **values))


def enqueue(engine: Engine, entity: str, operation: str, payload: Dict[str, Any],
            bc_id: Optional[str] = None, bc_number: Optional[str] = None) -> int:
    """What Pretech's own applications do (in SQL or code) to send a change to Business Central."""
    if entity not in ENTITIES:
        raise ValueError(f"Unknown entity {entity}")
    with engine.begin() as conn:
        res = conn.execute(outbox.insert().values(
            entity=entity, operation=operation, payload=payload, bc_id=bc_id, bc_number=bc_number,
            status="pending", attempts=0,
        ))
        return int(res.inserted_primary_key[0])
