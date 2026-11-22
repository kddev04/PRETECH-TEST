"""Command line: python -m bcsync <command>

  init-db                 create the MySQL tables
  check                   test the Business Central login and list companies
  pull [--full] [-e X]    copy changed BC records into MySQL (all configured entities, or one)
  push                    send pending bc_outbox rows to BC
  run [--once]            pull then push, every SYNC_INTERVAL_SECONDS
  status                  cursor and outbox summary
  subscribe --url URL     create or renew BC webhook subscriptions (optional)
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time

from sqlalchemy import func, select

from . import db
from .bc_client import BCClient
from .config import load_settings
from .sync import pull_all, pull_entity, push_outbox


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bcsync", description="Business Central <-> MySQL connector")
    p.add_argument("--env", default=".env", help="path to the .env file")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("check")
    pp = sub.add_parser("pull")
    pp.add_argument("--full", action="store_true", help="ignore the cursor and re-read everything")
    pp.add_argument("-e", "--entity")
    sub.add_parser("push")
    pr = sub.add_parser("run")
    pr.add_argument("--once", action="store_true")
    sub.add_parser("status")
    ps = sub.add_parser("subscribe")
    ps.add_argument("--url", required=True, help="public HTTPS URL of /bc/notify")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    settings = load_settings(args.env)
    engine = db.make_engine(settings.sqlalchemy_url)

    if args.cmd == "init-db":
        db.init_db(engine)
        print("tables ready:", ", ".join(sorted(db.metadata.tables)))
        return 0

    client = BCClient(settings)
    try:
        if args.cmd == "check":
            for c in client.companies():
                print(f"{c['id']}  {c.get('name')}  ({c.get('displayName', '')})")
            return 0
        if args.cmd == "pull":
            results = ([pull_entity(client, engine, settings, args.entity, full=args.full)]
                       if args.entity else pull_all(client, engine, settings, full=args.full))
            print(json.dumps([{"entity": r.entity, "read": r.rows, "changed": r.changed, "error": r.error} for r in results], indent=2))
            return 1 if any(r.error for r in results) else 0
        if args.cmd == "push":
            r = push_outbox(client, engine, settings)
            print(json.dumps({"done": r.done, "failed": r.failed, "retry_later": r.retry_later, "errors": r.errors}, indent=2))
            return 1 if r.failed else 0
        if args.cmd == "status":
            with engine.connect() as conn:
                for row in conn.execute(select(db.sync_state)).mappings():
                    print(f"{row['entity']:<14} cursor={row['cursor_ts']}  last_run={row['last_run_at']}  "
                          f"rows={row['last_rows']}  error={row['last_error'] or '-'}")
                counts = conn.execute(select(db.outbox.c.status, func.count()).group_by(db.outbox.c.status)).all()
            print("outbox:", dict(counts) or "empty")
            return 0
        if args.cmd == "subscribe":
            from .webhook import subscribe
            state = settings.webhook_client_state or "set-BC_WEBHOOK_CLIENT_STATE"
            for s in subscribe(client, args.url, settings.entities, state):
                print(s.get("resource"), "expires", s.get("expirationDateTime"))
            return 0
        if args.cmd == "run":
            stop = {"flag": False}
            signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
            while True:
                pull_all(client, engine, settings)   # pull first, so updates by number find their record
                push_outbox(client, engine, settings)
                if args.once or stop["flag"]:
                    return 0
                for _ in range(settings.sync_interval_seconds):
                    if stop["flag"]:
                        return 0
                    time.sleep(1)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
