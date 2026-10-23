"""Async Zoho CRM client built on a shared httpx.AsyncClient."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ZohoError(RuntimeError):
    """Raised when a Zoho CRM API request fails after retries."""

    def __init__(self, status: int, code: str | None, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ZohoClient:
    """Handle Zoho CRM authentication and REST requests with retry support."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def __aenter__(self) -> "ZohoClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._client.aclose()

    async def get_access_token(self) -> str:
        """Fetch or refresh the current Zoho access token, caching it safely."""
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        if self._token_lock.locked():
            async with self._token_lock:
                if self._access_token and now < self._token_expires_at:
                    return self._access_token
        else:
            async with self._token_lock:
                now = time.monotonic()
                if self._access_token and now < self._token_expires_at:
                    return self._access_token

                missing = [
                    self.settings.zoho_client_id,
                    self.settings.zoho_client_secret,
                    self.settings.zoho_refresh_token,
                ]
                if not all(missing):
                    raise ValueError(
                        "ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN must be configured."
                    )

                response = await self._client.post(
                    f"{self.settings.zoho_accounts_url.rstrip('/')}/oauth/v2/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.settings.zoho_client_id,
                        "client_secret": self.settings.zoho_client_secret,
                        "refresh_token": self.settings.zoho_refresh_token,
                    },
                )

                payload = response.json()
                if response.status_code != 200 or "access_token" not in payload:
                    error_message = payload.get("error_description") or payload.get("error") or "Zoho token refresh failed."
                    raise RuntimeError(error_message)

                self._access_token = payload["access_token"]
                expires_in = int(payload.get("expires_in", 3600))
                self._token_expires_at = time.monotonic() + max(expires_in - 300, 60)
                return self._access_token

        return self._access_token or ""

    async def request(
        self,
        method: str,
        path: str,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        return_meta: bool = False,
    ) -> dict[str, Any] | list[Any] | None:
        """Send a request to the Zoho CRM REST API with retry support."""
        token = await self.get_access_token()
        base_url = self.settings.zoho_api_url.rstrip("/") + "/crm/v6"
        request_url = f"{base_url}{path}"
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, 4):
            response = await self._client.request(
                method=method,
                url=request_url,
                headers=headers,
                json=json,
                params=params,
            )

            if response.status_code == 204:
                logger.warning(
                    "zoho_request method=%s url=%s params=%s status=%s body=%s",
                    method,
                    request_url,
                    params,
                    response.status_code,
                    None,
                )
                if return_meta:
                    return {
                        "payload": None,
                        "status": response.status_code,
                        "url": request_url,
                        "params": params,
                    }
                return None

            try:
                payload = response.json()
            except ValueError:
                payload = {"message": response.text}

            if response.status_code == 401:
                logger.warning(
                    "zoho_request method=%s url=%s params=%s status=%s body=%s",
                    method,
                    request_url,
                    params,
                    response.status_code,
                    payload,
                )
                if attempt == 1:
                    self._access_token = None
                    self._token_expires_at = 0.0
                    token = await self.get_access_token()
                    headers["Authorization"] = f"Zoho-oauthtoken {token}"
                    continue
                raise ZohoError(
                    status=response.status_code,
                    code=payload.get("code"),
                    message=payload.get("message") or payload.get("error") or "Unauthorized",
                )

            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                logger.warning(
                    "zoho_request method=%s url=%s params=%s status=%s body=%s",
                    method,
                    request_url,
                    params,
                    response.status_code,
                    payload,
                )
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code >= 400:
                logger.warning(
                    "zoho_request method=%s url=%s params=%s status=%s body=%s",
                    method,
                    request_url,
                    params,
                    response.status_code,
                    payload,
                )
                raise ZohoError(
                    status=response.status_code,
                    code=payload.get("code"),
                    message=payload.get("message") or payload.get("error") or "Zoho CRM request failed.",
                )

            logger.warning(
                "zoho_request method=%s url=%s params=%s status=%s body=%s",
                method,
                request_url,
                params,
                response.status_code,
                payload,
            )
            if return_meta:
                return {
                    "payload": payload,
                    "status": response.status_code,
                    "url": request_url,
                    "params": params,
                }
            return payload

        raise ZohoError(
            status=response.status_code,
            code=payload.get("code"),
            message=payload.get("message") or payload.get("error") or "Zoho CRM request failed.",
        )

    async def get_records(self, module_name: str, criteria: str | None = None, page: int = 1, per_page: int = 10) -> dict[str, Any]:
        """Return CRM records for a given module."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if criteria:
            params["criteria"] = criteria
        return await self.request("GET", f"/{module_name}", params=params)

    async def create_record(self, module_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a record in a Zoho CRM module."""
        return await self.request("POST", f"/{module_name}", json={"data": [payload]})


# Backward-compatibility alias for older tool modules and scripts.
ZohoCRMClient = ZohoClient
