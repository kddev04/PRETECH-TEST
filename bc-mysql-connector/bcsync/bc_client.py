"""A small client for the Business Central standard API v2.0.

Handles paging (@odata.nextLink), incremental reads on lastModifiedDateTime, ETag-guarded
updates, and retries with backoff on throttling (HTTP 429) and transient server errors.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .auth import TokenProvider
from .config import Settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class BCError(Exception):
    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.body = body


class RetryableBCError(BCError):
    """Throttled or transient: worth retrying."""


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (RetryableBCError, httpx.TransportError))


def odata_datetime(dt: datetime) -> str:
    """DateTimeOffset literal for $filter, UTC with a Z, keeping microseconds.

    Cutting to milliseconds would make `gt cursor` re-match every record stamped in the same
    millisecond as the cursor. The overlap window in sync.py covers equal timestamps instead.
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class BCClient:
    def __init__(self, settings: Settings, tokens: Optional[TokenProvider] = None,
                 http: Optional[httpx.Client] = None):
        self.settings = settings
        self.tokens = tokens or TokenProvider(settings)
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))
        self._company_id = settings.company_id or None

    # ---------- low level ----------
    @retry(retry=retry_if_exception(_is_retryable), stop=stop_after_attempt(6),
           wait=wait_exponential(multiplier=1, min=1, max=60), reraise=True)
    def _request(self, method: str, url: str, *, params: Optional[Dict[str, str]] = None,
                 json: Any = None, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        h = {"Authorization": f"Bearer {self.tokens.token()}", "Accept": "application/json"}
        if headers:
            h.update(headers)
        resp = self.http.request(method, url, params=params, json=json, headers=h)
        if resp.status_code in RETRYABLE_STATUS:
            wait_hint = resp.headers.get("Retry-After")
            log.warning("BC %s %s -> %s (Retry-After %s), retrying", method, url, resp.status_code, wait_hint)
            if wait_hint and wait_hint.isdigit():
                import time
                time.sleep(min(int(wait_hint), 60))
            raise RetryableBCError(resp.status_code, resp.reason_phrase, _safe_json(resp))
        if resp.status_code >= 400:
            body = _safe_json(resp)
            msg = (body or {}).get("error", {}).get("message") if isinstance(body, dict) else None
            raise BCError(resp.status_code, msg or resp.text[:300], body)
        return resp

    # ---------- companies ----------
    def companies(self) -> List[Dict[str, Any]]:
        resp = self._request("GET", f"{self.settings.api_root}/companies")
        return resp.json().get("value", [])

    @property
    def company_id(self) -> str:
        if not self._company_id:
            companies = self.companies()
            if not companies:
                raise RuntimeError("No companies visible to this app in Business Central")
            self._company_id = companies[0]["id"]
            log.info("Using company %s (%s); set BC_COMPANY_ID to pin one", companies[0].get("name"), self._company_id)
        return self._company_id

    def entity_url(self, entity: str, record_id: Optional[str] = None) -> str:
        url = f"{self.settings.api_root}/companies({self.company_id})/{entity}"
        return f"{url}({record_id})" if record_id else url

    # ---------- reads ----------
    def list_changed(self, entity: str, since: Optional[datetime] = None) -> Iterator[Dict[str, Any]]:
        """All records of an entity, or only those modified after `since`, following every page."""
        params: Optional[Dict[str, str]] = {"$top": str(self.settings.page_size)}
        if since is not None:
            params["$filter"] = f"lastModifiedDateTime gt {odata_datetime(since)}"
        url: Optional[str] = self.entity_url(entity)
        while url:
            resp = self._request("GET", url, params=params)
            data = resp.json()
            for row in data.get("value", []):
                yield row
            url = data.get("@odata.nextLink")
            params = None  # the next link already carries the query

    def get(self, entity: str, record_id: str) -> Dict[str, Any]:
        return self._request("GET", self.entity_url(entity, record_id)).json()

    # ---------- writes ----------
    def create(self, entity: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", self.entity_url(entity), json=payload,
                             headers={"Content-Type": "application/json"}).json()

    def update(self, entity: str, record_id: str, payload: Dict[str, Any], etag: Optional[str]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json", "If-Match": etag or "*"}
        return self._request("PATCH", self.entity_url(entity, record_id), json=payload, headers=headers).json()

    def close(self) -> None:
        self.http.close()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None
