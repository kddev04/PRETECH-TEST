# bcsync: Business Central ⇄ MySQL connector (prototype)

Pushes and pulls data between **Microsoft Dynamics 365 Business Central** and **MySQL** through
Business Central's standard API v2.0. Open source libraries only; no licence or subscription cost.

> **Demo data.** The mock Business Central uses Pretech Automation's public catalogue and client names
> from pretech.co.in. Every price, balance, quantity and order in it is **sample data** for
> demonstration, not a real transaction.

Status: working prototype with a browser console. Tested end to end (11 tests) against a mock of
the Business Central API and a real MySQL 8.4. Not yet run against a real Business Central tenant.

## How it works

```
 Business Central (API v2.0)                         MySQL
 ───────────────────────────                         ─────
 customers, vendors,     ── pull (incremental) ──▶   bc_customers, bc_vendors,
 items, salesOrders         lastModifiedDateTime      bc_items, bc_sales_orders   (mirror, + raw JSON)
                                                      bc_sync_state               (cursor per entity)
                         ◀── push ───────────────    bc_outbox                    (changes from Pretech apps)
                             create / update,
                             ETag-guarded
```

- **Pull:** reads only records changed since the last run (`$filter=lastModifiedDateTime gt …`),
  follows `@odata.nextLink` paging and upserts by Business Central's `systemId`. It re-reads a
  2-second overlap so equal timestamps are never missed; upserts make that harmless.
- **Push:** other systems never call Business Central directly. They write a row to `bc_outbox`
  (see `sql/outbox_examples.sql`). The connector sends it, records the BC id and number, and
  writes the returned record into the mirror.
  - **Updates** carry the stored ETag (`If-Match`). If someone changed the record in BC meanwhile
    (HTTP 412), it re-reads the record once and applies the change on top.
  - **Validation and permission errors** park the row as `failed`, with BC's message.
  - **Throttling and outages** stay `pending` and retry.
- **Throttling:** HTTP 429 and 5xx responses are retried with exponential backoff, honouring `Retry-After`.
- **Near real time (optional):** `bcsync/webhook.py` receives Business Central webhook
  notifications and pulls the changed entity at once. BC subscriptions expire after three days, so
  run `bcsync subscribe` on a schedule to renew them. Without webhooks, `bcsync run` polls every
  `SYNC_INTERVAL_SECONDS`.

## Quick start (no Business Central needed)

Windows, with Python 3.9+ and Docker Desktop running:

1. Double-click **`setup.bat`**. It creates `.venv`, installs `requirements.txt` and writes `.env`
   with fresh local passwords.
2. Double-click **`start-demo.bat`**. It starts MySQL 8.4 in Docker (container `pretech-mysql`), the
   mock Business Central and the **Pretech Connect console**, then opens http://127.0.0.1:8000.
   Without Docker it falls back to a local SQLite file.

The presentation script, laptop and office-machine setup, and going live are in **[PRESENTATION.md](PRESENTATION.md)**.

Other entry points:
```powershell
.venv\Scripts\python demo.py               # console-free round trip, prints the result
.venv\Scripts\python -m pytest -q          # 11 end-to-end tests (needs the MySQL container)
.venv\Scripts\python tools\package.py      # dist\pretech-connect.zip for another machine
```

## The console (Pretech Connect)

`console/` is a FastAPI app with a single-page dashboard:
- **Both sides at a glance:** connection status, and record counts in Business Central and in MySQL, per entity.
- **Every record** with its sync state: *In sync*, *Changed in BC*, *Waiting to push*, *New in BC*.
  Click a row to compare it field by field and see the raw BC JSON.
- **Sync now, full pull and auto sync** (every 10 s).
- **A guided demonstration:** edit in BC, change from MySQL, create a customer, an ETag conflict,
  throttling, and reset.
- **The outbox, the activity feed** (also stored in MySQL as `bc_sync_log`) and a **read-only SQL panel**.

With `BC_AUTH_MODE=entra` the console runs against the real tenant and hides the demo-only actions.

## Connect to the real Business Central

1. **Microsoft Entra admin center → App registrations → New registration.** Note the tenant id and
   client id, then create a client secret.
2. **API permissions → Add → Dynamics 365 Business Central → Application permissions →
   `API.ReadWrite.All`**, then **Grant admin consent**.
3. **In Business Central**, open **Microsoft Entra Applications**, add the client id, set the state
   to Enabled, and assign permission sets that cover the tables being synced. Test with broad sets
   first, then narrow them down.
4. In `.env`, set `BC_AUTH_MODE=entra`, `BC_BASE_URL=https://api.businesscentral.dynamics.com`,
   `BC_TENANT_ID`, `BC_ENVIRONMENT` (e.g. `Production` or a sandbox name), `BC_CLIENT_ID` and
   `BC_CLIENT_SECRET`. Leave `BC_COMPANY_ID` empty to use the first company, or pin one.
5. Run:
   ```powershell
   .venv\Scripts\python -m bcsync check        # lists companies if the login works
   .venv\Scripts\python -m bcsync init-db
   .venv\Scripts\python -m bcsync pull --full
   .venv\Scripts\python -m bcsync run          # pull + push every SYNC_INTERVAL_SECONDS
   ```
   Try it against a **sandbox environment** first.

## Commands

| Command | What it does |
| --- | --- |
| `python -m bcsync init-db` | Create the MySQL tables |
| `python -m bcsync check` | Test the BC login, list companies |
| `python -m bcsync pull [--full] [-e items]` | Pull changes (or everything) into MySQL |
| `python -m bcsync push` | Send pending `bc_outbox` rows to BC |
| `python -m bcsync run [--once]` | Pull, then push, on a loop |
| `python -m bcsync status` | Cursors, last errors, outbox counts |
| `python -m bcsync subscribe --url https://…/bc/notify` | Create or renew webhook subscriptions |

## Adding entities or fields

Add the API entity name and the columns you want to `bcsync/entities.py`, then add it to
`BC_ENTITIES`. Everything else is generic. Fields you don't map are still stored in the `raw` JSON
column. Fields or tables that Business Central's standard API doesn't expose need a custom API
page written in AL; see the repos below.

## Open source repos this builds on

| Repo | Role here |
| --- | --- |
| [AzureAD/microsoft-authentication-library-for-python](https://github.com/AzureAD/microsoft-authentication-library-for-python) (MSAL) | Entra client-credentials sign-in to BC |
| [encode/httpx](https://github.com/encode/httpx) | HTTP client for the BC API |
| [sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) + [PyMySQL/PyMySQL](https://github.com/PyMySQL/PyMySQL) | MySQL schema and upserts |
| [jd/tenacity](https://github.com/jd/tenacity) | Retries and backoff on 429 / 5xx |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) + [encode/uvicorn](https://github.com/encode/uvicorn) | Webhook receiver and the mock BC API |
| [microsoft/AL](https://github.com/microsoft/AL) | AL language samples, for custom API pages when standard entities aren't enough |
| [microsoft/navcontainerhelper](https://github.com/microsoft/navcontainerhelper) (BcContainerHelper) | Run a real Business Central sandbox in Docker. Needs ~6 GB RAM, ~15 GB disk **and Windows containers (Windows Pro/Enterprise, not Home)** |

Alternatives considered:
- **[dlt-hub/dlt](https://github.com/dlt-hub/dlt):** good for pull-only pipelines into MySQL. It has no outbox push.
- **[n8n-io/n8n](https://github.com/n8n-io/n8n):** a visual, self-hosted alternative.
- **[tap-dynamics-bc](https://hub.meltano.com/extractors/tap-dynamics-bc) (hotglue, Singer):** an existing Business Central extractor for Meltano.

## About the APIWORK folder

`APIWORK/` holds source snapshots of AL, httpx, MSAL, BcContainerHelper, SQLAlchemy and tenacity.
They are development branches: SQLAlchemy `main` (2.1) needs Python 3.11+, and httpx `master` is the
1.0 pre-release, which needs Python 3.10+ and changes its API. The connector therefore runs on the
pinned, released versions of the same projects in `requirements.txt`, and APIWORK stays as a
reference: AL samples for custom API pages, and BcContainerHelper for a real BC sandbox.
It is excluded from git and from the package.

## Limits of this prototype

- **Real tenant:** not yet tested against one. Field names follow Microsoft's API v2.0 reference; check them on the customer's environment.
- **Sales order lines:** synced as headers only. Lines (`salesOrderLines`) can be added the same way.
- **Deletes:** not pushed, and BC deletes are only seen through webhooks.
- **Companies:** one company per connector instance.
- **API limits:** Microsoft's operational limits page sets the request limits. Check them for the expected data volume.
