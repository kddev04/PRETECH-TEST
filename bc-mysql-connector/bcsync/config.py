"""Settings, read from environment variables (and a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    # Business Central
    auth_mode: str = "mock"            # "mock" or "entra"
    base_url: str = "https://api.businesscentral.dynamics.com"
    tenant_id: str = ""
    environment: str = "Production"
    client_id: str = ""
    client_secret: str = ""
    company_id: str = ""
    entities: List[str] = field(default_factory=lambda: ["customers", "vendors", "items", "salesOrders"])

    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_db: str = "bc_sync"
    mysql_user: str = "bcsync"
    mysql_password: str = ""
    database_url: str = ""             # optional override, e.g. sqlite:///local.db for experiments

    # Sync behaviour
    sync_interval_seconds: int = 300
    push_max_attempts: int = 5
    cursor_overlap_seconds: int = 2    # re-read a small window so equal timestamps are never missed
    page_size: int = 500
    webhook_client_state: str = ""

    @property
    def api_root(self) -> str:
        """Root of the standard API v2.0 for this tenant and environment."""
        tenant = self.tenant_id or "mock"
        return f"{self.base_url.rstrip('/')}/v2.0/{tenant}/{self.environment}/api/v2.0"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        from urllib.parse import quote_plus
        return (
            f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


def load_settings(env_file: str = ".env") -> Settings:
    load_dotenv(env_file, override=False)
    entities = [e.strip() for e in _env("BC_ENTITIES", "customers,vendors,items,salesOrders").split(",") if e.strip()]
    s = Settings(
        auth_mode=_env("BC_AUTH_MODE", "mock").lower(),
        base_url=_env("BC_BASE_URL", "https://api.businesscentral.dynamics.com"),
        tenant_id=_env("BC_TENANT_ID"),
        environment=_env("BC_ENVIRONMENT", "Production"),
        client_id=_env("BC_CLIENT_ID"),
        client_secret=_env("BC_CLIENT_SECRET"),
        company_id=_env("BC_COMPANY_ID"),
        entities=entities,
        mysql_host=_env("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(_env("MYSQL_PORT", "3306")),
        mysql_db=_env("MYSQL_DB", "bc_sync"),
        mysql_user=_env("MYSQL_USER", "bcsync"),
        mysql_password=_env("MYSQL_PASSWORD"),
        database_url=_env("DATABASE_URL"),
        sync_interval_seconds=int(_env("SYNC_INTERVAL_SECONDS", "300")),
        push_max_attempts=int(_env("PUSH_MAX_ATTEMPTS", "5")),
        webhook_client_state=_env("BC_WEBHOOK_CLIENT_STATE"),
    )
    if s.auth_mode not in ("mock", "entra"):
        raise ValueError("BC_AUTH_MODE must be 'mock' or 'entra'")
    if s.auth_mode == "entra":
        missing = [n for n, v in (("BC_TENANT_ID", s.tenant_id), ("BC_CLIENT_ID", s.client_id),
                                  ("BC_CLIENT_SECRET", s.client_secret)) if not v]
        if missing:
            raise ValueError("Missing settings for entra mode: " + ", ".join(missing))
    return s
