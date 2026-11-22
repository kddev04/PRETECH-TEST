"""A local stand-in for the Business Central API v2.0, for development and demos without a tenant.

It copies the behaviour the connector depends on:
  - URL shape  /v2.0/{tenant}/{environment}/api/v2.0/companies({id})/{entity}({id})
  - bearer token required (any value), 401 otherwise
  - $filter=lastModifiedDateTime gt <timestamp>, $top, server-side paging with @odata.nextLink
  - @odata.etag on every record, If-Match on PATCH, 412 when the ETag is stale
  - 429 with Retry-After when throttling is switched on
  - BC-style error bodies {"error": {"code": ..., "message": ...}}

The company and its catalogue follow Pretech Automation's public website (pretech.co.in): panel
types, process systems, client names and the Pune works address. All prices, balances, quantities
and orders are SAMPLE DATA for demonstration, not real transactions.

Test and demo helpers live under /_mock: reset, touch (simulate a user editing a record in BC),
config (paging, throttling) and records (read the store directly).

Run:  uvicorn mock_bc.app:app --port 8765
"""
from __future__ import annotations

import base64
import copy
import itertools
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Business Central API v2.0 (Pretech sample company)")

COMPANY_ID = "6a1c4a2e-0b7d-4f3e-9b1a-2f6c8d9e0a11"
COMPANY = {
    "id": COMPANY_ID,
    "systemVersion": "26.0",
    "name": "PRETECH",
    "displayName": "Pretech Automation Pvt. Ltd.",
    "businessProfileId": "",
}
COMPANY_ADDRESS = "Plot 78 + 79, Tiny Industrial Estate, Kondhwa Bk., Pisoli Road, Pune 411048, Maharashtra, India"

ENTITIES = ("customers", "vendors", "items", "salesOrders")
NUMBER_PREFIX = {"customers": "C", "vendors": "V", "items": "ITM-", "salesOrders": "SO-"}
REQUIRED = {"customers": ["displayName"], "vendors": ["displayName"], "items": ["displayName"],
            "salesOrders": ["customerNumber"]}
SEED_NAMESPACE = uuid.UUID("2f0e6c7a-1d5b-4c8e-9a3f-5b7d1e0c4a22")
READ_ONLY = {"id", "number", "lastModifiedDateTime", "@odata.etag", "balanceDue", "balance", "inventory",
             "customerName", "customerId", "totalAmountIncludingTax"}

_lock = threading.RLock()
_store: Dict[str, Dict[str, Dict[str, Any]]] = {}
_versions: Dict[str, int] = {}
_counters: Dict[str, itertools.count] = {}
_cfg = {"page_size": int(os.environ.get("MOCK_PAGE_SIZE", "5")), "throttle_every": 0, "requests": 0}
_last_ts = datetime(2000, 1, 1)


# ---------- helpers ----------
def _now() -> datetime:
    """Strictly increasing UTC timestamps, like a real database clock under load."""
    global _last_ts
    t = datetime.utcnow()
    if t <= _last_ts:
        t = _last_ts + timedelta(microseconds=1)
    _last_ts = t
    return t


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"  # 7 fractional digits, as .NET writes them


def _parse(ts: str) -> datetime:
    v = ts.rstrip("Z")
    if "." in v:
        head, frac = v.split(".", 1)
        return datetime.strptime(f"{head}.{(frac + '000000')[:6]}", "%Y-%m-%dT%H:%M:%S.%f")
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")


def _etag(record_id: str) -> str:
    raw = f"{_versions[record_id]};{record_id[:8]}".encode()
    return 'W/"' + base64.b64encode(raw).decode() + '"'


def _stamp(record: Dict[str, Any]) -> Dict[str, Any]:
    _versions[record["id"]] = _versions.get(record["id"], 0) + 1
    record["lastModifiedDateTime"] = _fmt(_now())
    return record


def _out(record: Dict[str, Any]) -> Dict[str, Any]:
    r = copy.deepcopy(record)
    r["@odata.etag"] = _etag(record["id"])
    return r


def _error(status: int, code: str, message: str, headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _next_number(entity: str) -> str:
    while True:
        candidate = f"{NUMBER_PREFIX[entity]}{next(_counters[entity]):04d}"
        if not any(r.get("number") == candidate for r in _store[entity].values()):
            return candidate


def _find_by_number(entity: str, number: str) -> Optional[Dict[str, Any]]:
    return next((r for r in _store[entity].values() if r.get("number") == number), None)


# ---------- seed: Pretech Automation, sample figures ----------
CUSTOMERS = [
    # name, city, state code, country, credit limit, balance due (sample)
    ("Emcure Pharmaceuticals Ltd.", "Pune", "MH", "IN", 5000000, 845000),
    ("Indoco Remedies Ltd.", "Mumbai", "MH", "IN", 3000000, 212500),
    ("Navin Fluorine International Ltd.", "Mumbai", "MH", "IN", 6000000, 1268000),
    ("Anupam Rasayan India Ltd.", "Surat", "GJ", "IN", 4500000, 0),
    ("GMM Pfaudler Ltd.", "Anand", "GJ", "IN", 4000000, 356000),
    ("Crystal Crop Protection Ltd.", "New Delhi", "DL", "IN", 2500000, 0),
    ("Borosil Ltd.", "Mumbai", "MH", "IN", 2000000, 98000),
    ("Bhabha Atomic Research Centre", "Mumbai", "MH", "IN", 7500000, 1712000),
]
VENDORS = [
    ("Schneider Electric India Pvt. Ltd.", "Gurugram", "IN", 1840000),
    ("Emerson Automation Solutions", "", "IN", 965000),
    ("Kondhwa Sheet Metal Works (sample)", "Pune", "IN", 142000),
]
ITEMS = [
    # number, description, category, unit price (sample)
    ("AP-DCS", "DCS panel", "AUTOMATION", 1450000),
    ("AP-MRS", "Marshalling panel", "AUTOMATION", 385000),
    ("AP-PLM", "PLC cum marshalling panel", "AUTOMATION", 640000),
    ("AP-PMC", "PLC cum MCC panel", "AUTOMATION", 890000),
    ("EP-MCC", "MCC panel, LV 415 V", "LV-ELECTRICAL", 925000),
    ("EP-IMC", "iMCC (smart MCC) panel, LV 415 V", "LV-ELECTRICAL", 1280000),
    ("EP-SST", "Soft starter panel", "LV-ELECTRICAL", 355000),
    ("EP-VFD", "VFD drive panel", "LV-ELECTRICAL", 410000),
    ("EP-PDB", "Power distribution board", "LV-ELECTRICAL", 268000),
    ("FP-AUT", "Flameproof automation panel", "FLAMEPROOF", 520000),
    ("FP-PLC", "Flameproof PLC panel", "FLAMEPROOF", 485000),
    ("FP-ELE", "Flameproof electrical panel", "FLAMEPROOF", 410000),
    ("FP-DRV", "Flameproof drive panel", "FLAMEPROOF", 612000),
    ("FP-LCP", "Flameproof local control panel", "FLAMEPROOF", 38500),
    ("PS-PLT", "Pilot plant skid, EPC", "PROCESS-SYSTEMS", 4800000),
    ("PS-WBS", "Weighing and batching system", "PROCESS-SYSTEMS", 2350000),
    ("PS-MMT", "Metering mobile trolley", "PROCESS-SYSTEMS", 185000),
    ("PS-HWS", "Hot water system", "PROCESS-SYSTEMS", 320000),
]
SALES_ORDERS = [
    # customer index, item number, quantity, status, customer PO (sample), days to delivery
    (0, "FP-PLC", 2, "Open", "EMC/PO/26/0412", 45),
    (2, "EP-MCC", 1, "Open", "NFIL/PO/26/1187", 60),
    (3, "FP-DRV", 2, "Draft", "ARIL/PO/26/0093", 75),
    (7, "AP-DCS", 1, "Open", "BARC/PUR/26/0551", 90),
    (4, "PS-PLT", 1, "Draft", "GMMP/PO/26/0230", 120),
]


def reset() -> None:
    global _last_ts
    with _lock:
        _store.clear(); _versions.clear()
        _last_ts = datetime(2000, 1, 1)
        for e in ENTITIES:
            _store[e] = {}
            _counters[e] = itertools.count(1)

        def add(entity: str, number: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
            number = number or _next_number(entity)
            rid = str(uuid.uuid5(SEED_NAMESPACE, f"{entity}:{number}"))  # stable across restarts, like real BC
            rec = {"id": rid, "number": number, **fields}
            _store[entity][rid] = _stamp(rec)
            return rec

        customers = [
            add("customers", displayName=name, type="Company", addressLine1="", city=city, state=state,
                country=country, postalCode="", phoneNumber="", email="", website="", taxRegistrationNumber="",
                currencyCode="INR", blocked=" ", balanceDue=float(due), creditLimit=float(limit))
            for name, city, state, country, limit, due in CUSTOMERS
        ]
        for name, city, country, balance in VENDORS:
            add("vendors", displayName=name, city=city, country=country, phoneNumber="", email="",
                taxRegistrationNumber="", currencyCode="INR", blocked=" ", balance=float(balance))
        items = {}
        for number, desc, cat, price in ITEMS:
            items[number] = add("items", number=number, displayName=desc, type="Inventory", itemCategoryCode=cat,
                                blocked=False, baseUnitOfMeasureCode="NOS", unitPrice=float(price),
                                unitCost=float(round(price * 0.74, -2)), inventory=float(2 if price > 1000000 else 4),
                                gtin="")
        today = date.today()
        for cust_i, item_no, qty, status, po, days in SALES_ORDERS:
            cust, item = customers[cust_i], items[item_no]
            excl = item["unitPrice"] * qty
            add("salesOrders", externalDocumentNumber=po, orderDate=today.isoformat(),
                requestedDeliveryDate=(today + timedelta(days=days)).isoformat(),
                customerId=cust["id"], customerNumber=cust["number"], customerName=cust["displayName"],
                currencyCode="INR", status=status, totalAmountExcludingTax=excl,
                totalAmountIncludingTax=round(excl * 1.18, 2))


reset()


# ---------- API ----------
_PATH = re.compile(r"^companies(?:\((?P<cid>[^)]+)\)(?:/(?P<entity>[A-Za-z]+)(?:\((?P<rid>[^)]+)\))?)?)?$")
_FILTER = re.compile(r"^\s*lastModifiedDateTime\s+gt\s+(\S+)\s*$")


@app.api_route("/v2.0/{tenant}/{environment}/api/v2.0/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def api(tenant: str, environment: str, rest: str, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or len(auth) < 12:
        return _error(401, "Authentication_InvalidCredentials", "The server has rejected the client credentials.")
    with _lock:
        _cfg["requests"] += 1
        n = _cfg["throttle_every"]
        if n and _cfg["requests"] % n == 0:
            return _error(429, "TooManyRequests", "Too many requests, retry later.", {"Retry-After": "1"})

    m = _PATH.match(rest)
    if not m:
        return _error(404, "BadRequest_NotFound", f"No HTTP resource was found that matches '{rest}'.")
    cid, entity, rid = m.group("cid"), m.group("entity"), m.group("rid")
    if cid is None:
        return {"value": [COMPANY]} if request.method == "GET" else _error(405, "MethodNotAllowed", "Not allowed")
    if cid != COMPANY_ID:
        return _error(404, "Internal_CompanyNotFound", "Cannot find the company.")
    if entity not in ENTITIES:
        return _error(404, "BadRequest_NotFound", f"Resource '{entity}' does not exist.")

    with _lock:
        table = _store[entity]
        if request.method == "GET" and rid is None:
            return _list(request, table)
        if request.method == "GET":
            rec = table.get(rid)
            return _out(rec) if rec else _error(404, "Internal_RecordNotFound", "The record does not exist.")
        if request.method == "POST" and rid is None:
            body = await request.json()
            missing = [f for f in REQUIRED[entity] if not body.get(f)]
            if missing:
                return _error(400, "BadRequest", f"The field {missing[0]} must have a value.")
            rec = {k: v for k, v in body.items() if k not in READ_ONLY}
            if entity == "salesOrders":
                cust = _find_by_number("customers", body["customerNumber"])
                if not cust:
                    return _error(400, "BadRequest", f"The customer {body['customerNumber']} does not exist.")
                rec.update(customerId=cust["id"], customerName=cust["displayName"])
                excl = float(rec.get("totalAmountExcludingTax") or 0)
                rec["totalAmountIncludingTax"] = round(excl * 1.18, 2)
                rec.setdefault("status", "Draft")
                rec.setdefault("orderDate", date.today().isoformat())
            new_id = str(uuid.uuid4())
            rec.update(id=new_id, number=_next_number(entity))
            table[new_id] = _stamp(rec)
            return JSONResponse(_out(rec), status_code=201)
        if request.method == "PATCH" and rid:
            rec = table.get(rid)
            if not rec:
                return _error(404, "Internal_RecordNotFound", "The record does not exist.")
            if_match = request.headers.get("if-match")
            if not if_match:
                return _error(400, "Application_MissingIfMatch", "Could not find a property named 'If-Match'.")
            if if_match != "*" and if_match != _etag(rid):
                return _error(412, "Request_EntityChanged", "Another user has already changed the record.")
            body = await request.json()
            rec.update({k: v for k, v in body.items() if k not in READ_ONLY})
            _stamp(rec)
            return _out(rec)
    return _error(405, "MethodNotAllowed", "The requested method is not supported.")


def _list(request: Request, table: Dict[str, Dict[str, Any]]):
    q = request.query_params
    rows = sorted(table.values(), key=lambda r: r["lastModifiedDateTime"])
    flt = q.get("$filter")
    if flt:
        fm = _FILTER.match(flt)
        if not fm:
            return _error(400, "BadRequest", "Only 'lastModifiedDateTime gt <timestamp>' is supported by the mock.")
        since = _parse(fm.group(1))
        rows = [r for r in rows if _parse(r["lastModifiedDateTime"]) > since]
    page = min(int(q.get("$top", _cfg["page_size"])), _cfg["page_size"])
    skip = int(q.get("$skiptoken", 0))
    chunk = rows[skip: skip + page]
    body: Dict[str, Any] = {"value": [_out(r) for r in chunk]}
    if skip + page < len(rows):
        params = {k: v for k, v in q.items() if k != "$skiptoken"}
        params["$skiptoken"] = str(skip + page)
        body["@odata.nextLink"] = f"{str(request.url).split('?')[0]}?{urlencode(params)}"
    return body


# ---------- test and demo helpers ----------
@app.post("/_mock/reset")
def mock_reset():
    reset()
    _cfg.update(throttle_every=0, requests=0)
    return {"ok": True}


@app.post("/_mock/config")
async def mock_config(request: Request):
    body = await request.json()
    _cfg.update({k: int(v) for k, v in body.items() if k in ("page_size", "throttle_every")})
    return _cfg


@app.post("/_mock/touch/{entity}/{number}")
async def mock_touch(entity: str, number: str, request: Request):
    """Simulate a user editing a record inside Business Central."""
    body = await request.json()
    with _lock:
        if entity not in _store:
            return _error(404, "BadRequest_NotFound", f"Resource '{entity}' does not exist.")
        rec = _find_by_number(entity, number)
        if not rec:
            return _error(404, "Internal_RecordNotFound", "The record does not exist.")
        rec.update({k: v for k, v in body.items() if k not in ("id", "number", "lastModifiedDateTime")})
        _stamp(rec)
        return _out(rec)


@app.get("/_mock/records/{entity}")
def mock_records(entity: str) -> List[Dict[str, Any]]:
    with _lock:
        return [_out(r) for r in _store.get(entity, {}).values()]


@app.get("/_mock/info")
def mock_info():
    return {"company": COMPANY, "address": COMPANY_ADDRESS, "config": _cfg}
