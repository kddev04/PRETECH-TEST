"""Optional near-real-time trigger: a receiver for Business Central webhook notifications.

Business Central POSTs to the notification URL with ?validationToken=... when a subscription is
created; we echo it back. Later notifications carry the changed resource, and we pull that entity.
Subscriptions expire after three days, so `bcsync subscribe` should be re-run (or scheduled) to renew.
The URL must be reachable from the internet over HTTPS (e.g. a reverse proxy or a free tunnel).

Run:  uvicorn bcsync.webhook:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, Request, Response

from . import db
from .bc_client import BCClient
from .config import load_settings
from .sync import pull_entity

log = logging.getLogger(__name__)
app = FastAPI(title="bcsync webhook receiver")

_ENTITY_RE = re.compile(r"/companies\([^)]*\)/([A-Za-z]+)")
_state: Dict[str, Any] = {}


def _deps():
    if not _state:
        settings = load_settings()
        _state["settings"] = settings
        _state["engine"] = db.make_engine(settings.sqlalchemy_url)
        _state["client"] = BCClient(settings)
    return _state["settings"], _state["engine"], _state["client"]


def entity_from_resource(resource: str) -> Optional[str]:
    m = _ENTITY_RE.search(resource or "")
    return m.group(1) if m else None


@app.post("/bc/notify")
async def notify(request: Request, background: BackgroundTasks, validationToken: Optional[str] = None):
    if validationToken is not None:  # subscription handshake
        return Response(content=validationToken, media_type="text/plain", status_code=200)
    settings, engine, client = _deps()
    body = await request.json()
    entities: List[str] = []
    for n in body.get("value", []):
        if settings.webhook_client_state and n.get("clientState") != settings.webhook_client_state:
            log.warning("ignoring notification with unexpected clientState")
            continue
        entity = entity_from_resource(n.get("resource", ""))
        if entity in settings.entities and entity not in entities:
            entities.append(entity)
    for entity in entities:
        background.add_task(pull_entity, client, engine, settings, entity)
    return Response(status_code=202)


def subscribe(client: BCClient, notification_url: str, entities: List[str], client_state: str) -> List[Dict[str, Any]]:
    """Create (or renew) one subscription per entity."""
    out = []
    existing = client._request("GET", f"{client.settings.api_root}/subscriptions").json().get("value", [])
    for entity in entities:
        resource = f"/api/v2.0/companies({client.company_id})/{entity}"
        match = next((s for s in existing if s.get("resource") == resource
                      and s.get("notificationUrl") == notification_url), None)
        if match:
            url = f"{client.settings.api_root}/subscriptions('{match['subscriptionId']}')"
            out.append(client._request("PATCH", url, json={"notificationUrl": notification_url},
                                       headers={"If-Match": match.get("@odata.etag", "*")}).json())
        else:
            out.append(client._request("POST", f"{client.settings.api_root}/subscriptions", json={
                "notificationUrl": notification_url, "resource": resource, "clientState": client_state,
            }).json())
    return out
