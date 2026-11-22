"""Which Business Central API v2.0 entities are mirrored, and how their fields map to MySQL columns.

Every mirror table keeps the typed columns below for easy SQL, plus the full record as JSON in
`raw`, so fields added later in Business Central are never lost.
To add an entity, add an entry here with its API name (as in /api/v2.0/companies(..)/<name>).
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple


class Col(NamedTuple):
    bc_field: str     # field name in the BC API payload
    column: str       # MySQL column name
    kind: str         # "str", "text", "decimal", "bool", "date", "datetime", "int"
    length: int = 0   # for "str"


ENTITIES: Dict[str, List[Col]] = {
    "customers": [
        Col("number", "number", "str", 20),
        Col("displayName", "display_name", "str", 100),
        Col("type", "type", "str", 20),
        Col("addressLine1", "address_line1", "str", 100),
        Col("city", "city", "str", 30),
        Col("state", "state", "str", 30),
        Col("country", "country", "str", 10),
        Col("postalCode", "postal_code", "str", 20),
        Col("phoneNumber", "phone_number", "str", 30),
        Col("email", "email", "str", 80),
        Col("website", "website", "str", 80),
        Col("taxRegistrationNumber", "tax_registration_number", "str", 50),
        Col("currencyCode", "currency_code", "str", 10),
        Col("blocked", "blocked", "str", 20),
        Col("balanceDue", "balance_due", "decimal"),
        Col("creditLimit", "credit_limit", "decimal"),
    ],
    "vendors": [
        Col("number", "number", "str", 20),
        Col("displayName", "display_name", "str", 100),
        Col("city", "city", "str", 30),
        Col("country", "country", "str", 10),
        Col("phoneNumber", "phone_number", "str", 30),
        Col("email", "email", "str", 80),
        Col("taxRegistrationNumber", "tax_registration_number", "str", 50),
        Col("currencyCode", "currency_code", "str", 10),
        Col("blocked", "blocked", "str", 20),
        Col("balance", "balance", "decimal"),
    ],
    "items": [
        Col("number", "number", "str", 20),
        Col("displayName", "display_name", "str", 100),
        Col("type", "type", "str", 20),
        Col("itemCategoryCode", "item_category_code", "str", 20),
        Col("blocked", "blocked", "bool"),
        Col("baseUnitOfMeasureCode", "base_unit_of_measure", "str", 10),
        Col("unitPrice", "unit_price", "decimal"),
        Col("unitCost", "unit_cost", "decimal"),
        Col("inventory", "inventory", "decimal"),
        Col("gtin", "gtin", "str", 14),
    ],
    "salesOrders": [
        Col("number", "number", "str", 20),
        Col("externalDocumentNumber", "external_document_number", "str", 35),
        Col("orderDate", "order_date", "date"),
        Col("requestedDeliveryDate", "requested_delivery_date", "date"),
        Col("customerId", "customer_id", "str", 36),
        Col("customerNumber", "customer_number", "str", 20),
        Col("customerName", "customer_name", "str", 100),
        Col("currencyCode", "currency_code", "str", 10),
        Col("status", "status", "str", 20),
        Col("totalAmountExcludingTax", "total_excl_tax", "decimal"),
        Col("totalAmountIncludingTax", "total_incl_tax", "decimal"),
    ],
}


def table_name(entity: str) -> str:
    """customers -> bc_customers, salesOrders -> bc_sales_orders."""
    snake = "".join("_" + c.lower() if c.isupper() else c for c in entity)
    return "bc_" + snake
