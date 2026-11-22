"""Access tokens for Business Central.

entra: OAuth 2.0 client credentials (service-to-service) through Microsoft Entra ID, using MSAL.
       Scope https://api.businesscentral.dynamics.com/.default. The app registration needs the
       Dynamics 365 Business Central application permission API.ReadWrite.All, admin consent,
       and the app must be added on the "Microsoft Entra Applications" page inside Business Central.
mock:  a fixed bearer token accepted by the local mock API.
"""
from __future__ import annotations

import logging
import threading

from .config import Settings

log = logging.getLogger(__name__)

BC_SCOPE = "https://api.businesscentral.dynamics.com/.default"


class TokenProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._app = None
        if settings.auth_mode == "entra":
            import msal  # imported lazily so mock mode needs nothing from Microsoft

            self._app = msal.ConfidentialClientApplication(
                client_id=settings.client_id,
                authority=f"https://login.microsoftonline.com/{settings.tenant_id}",
                client_credential=settings.client_secret,
            )

    def token(self) -> str:
        if self.settings.auth_mode == "mock":
            return "mock-token"
        with self._lock:
            # MSAL keeps the token in its in-memory cache and only calls Entra when it is close to expiry
            result = self._app.acquire_token_for_client(scopes=[BC_SCOPE])
        if "access_token" not in result:
            raise RuntimeError(
                "Could not get a Business Central token: "
                f"{result.get('error')}: {result.get('error_description')}"
            )
        return result["access_token"]
