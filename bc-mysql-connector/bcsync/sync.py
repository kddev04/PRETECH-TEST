"""The two directions of the sync.

pull  Business Central -> MySQL: incremental on lastModifiedDateTime, idempotent upserts.
push  MySQL -> Business Central: drains bc_outbox in order; creates and ETag-guarded updates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.engine import Engine

from . import db
from .bc_client import BCClient, BCError, RetryableBCError
from .config import Settings

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)


@dataclass
class PullResult:
    entity: str
    rows: int = 0          # records read from Business Central
    changed: int = 0       # records new or different in MySQL (actually written)
    cursor: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class PushResult:
    done: int = 0
    failed: int = 0
    retry_later: int = 0
    errors: List[str] = field(default_factory=list)


def pull_entity(client: BCClient, engine: Engine, settings: Settings, entity: str,
                full: bool = False, batch_size: int = 500) -> PullResult:
    result = PullResult(entity)
    cursor = None if full else db.get_cursor(engine, entity)
    since = cursor - timedelta(seconds=settings.cursor_overlap_seconds) if cursor else None
    newest = cursor
    now = utcnow()
    batch: List[Dict] = []
    try:
        for record in client.list_changed(entity, since=since):
            row = db.to_row(entity, record, now)
            batch.append(row)
            ts = row["bc_last_modified"]
            if ts and (newest is None or ts > newest):
                newest = ts
            if len(batch) >= batch_size:
                _write(engine, entity, batch, result)
                batch = []
        _write(engine, entity, batch, result)
        result.cursor = newest
        db.save_cursor(engine, entity, newest, result.changed, None, now)
        log.info("pull %-12s read %4d, changed %4d", entity, result.rows, result.changed)
    except Exception as exc:  # keep other entities running; the cursor stays where it was
        result.error = str(exc)
        db.save_cursor(engine, entity, None, result.rows, result.error, now)
        log.error("pull %s failed: %s", entity, exc)
    return result


def _write(engine: Engine, entity: str, batch: List[Dict], result: PullResult) -> None:
    """Upsert only records that are new or whose ETag moved; re-reads in the overlap window cost nothing."""
    result.rows += len(batch)
    stored = db.existing_etags(engine, entity, [r["id"] for r in batch])
    fresh = [r for r in batch if r["id"] not in stored or stored[r["id"]] != r["etag"]]
    result.changed += db.upsert(engine, entity, fresh)


def pull_all(client: BCClient, engine: Engine, settings: Settings, full: bool = False) -> List[PullResult]:
    return [pull_entity(client, engine, settings, e, full=full) for e in settings.entities]


def _apply_returned(engine: Engine, entity: str, record: Dict) -> None:
    """Write what BC returned straight into the mirror, so MySQL has the new id and ETag at once."""
    db.upsert(engine, entity, [db.to_row(entity, record, utcnow())])


def push_outbox(client: BCClient, engine: Engine, settings: Settings) -> PushResult:
    res = PushResult()
    for item in db.pending_outbox(engine):
        entity, op, payload = item["entity"], item["operation"], item["payload"]
        attempts = item["attempts"] + 1
        try:
            if op == "create":
                record = client.create(entity, payload)
                _apply_returned(engine, entity, record)
                db.mark_outbox(engine, item["id"], utcnow(), status="done", attempts=attempts,
                               bc_id=record.get("id"), bc_number=record.get("number"), last_error=None)
            else:
                record_id = item["bc_id"]
                etag = None
                if not record_id and item["bc_number"]:
                    found = db.find_by_number(engine, entity, item["bc_number"])
                    if not found:
                        # may simply not be pulled yet: keep it pending until the next pull brings it in
                        raise RetryableBCError(404, f"{entity} number {item['bc_number']} is not in the mirror yet")
                    record_id, etag = found["id"], found["etag"]
                if not record_id:
                    raise BCError(400, "update needs bc_id or bc_number")
                etag = etag or db.etag_for(engine, entity, record_id)
                try:
                    record = client.update(entity, record_id, payload, etag)
                except BCError as exc:
                    if exc.status != 412:
                        raise
                    # someone changed the record in BC since our last pull: take their ETag, apply ours once
                    log.warning("ETag conflict on %s %s, re-reading and retrying once", entity, record_id)
                    current = client.get(entity, record_id)
                    record = client.update(entity, record_id, payload, current.get("@odata.etag"))
                _apply_returned(engine, entity, record)
                db.mark_outbox(engine, item["id"], utcnow(), status="done", attempts=attempts,
                               bc_id=record_id, last_error=None)
            res.done += 1
        except RetryableBCError as exc:
            status = "failed" if attempts >= settings.push_max_attempts else "pending"
            db.mark_outbox(engine, item["id"], utcnow(), status=status, attempts=attempts, last_error=str(exc))
            res.retry_later += status == "pending"
            res.failed += status == "failed"
            res.errors.append(f"#{item['id']}: {exc}")
        except BCError as exc:
            # validation or permission errors will not fix themselves: park the row for a person
            db.mark_outbox(engine, item["id"], utcnow(), status="failed", attempts=attempts, last_error=str(exc))
            res.failed += 1
            res.errors.append(f"#{item['id']}: {exc}")
        except Exception as exc:  # network trouble etc.: try again next round
            status = "failed" if attempts >= settings.push_max_attempts else "pending"
            db.mark_outbox(engine, item["id"], utcnow(), status=status, attempts=attempts, last_error=str(exc))
            res.retry_later += status == "pending"
            res.failed += status == "failed"
            res.errors.append(f"#{item['id']}: {exc}")
    if res.done or res.failed or res.retry_later:
        log.info("push: %d done, %d failed, %d to retry", res.done, res.failed, res.retry_later)
    return res
