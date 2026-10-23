"""Tests for Zoho client token caching and retry behavior."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.config import Settings
from app.zoho.client import ZohoClient


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set required Zoho settings for tests."""
    monkeypatch.setenv("ZOHO_CLIENT_ID", "client-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    monkeypatch.setenv("ZOHO_API_URL", "https://www.zohoapis.in")
    return Settings()


@pytest.mark.asyncio
async def test_token_is_cached(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """A fresh token should be fetched once and reused for subsequent calls."""
    token_route = respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
    )
    crm_route = respx_mock.get("https://www.zohoapis.in/crm/v6/Contacts").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1", "Full_Name": "Aman"}]})
    )

    client = ZohoClient(settings=settings)

    assert await client.get_access_token() == "token-1"
    await client.request("GET", "/Contacts")
    assert await client.get_access_token() == "token-1"

    assert token_route.call_count == 1
    assert crm_route.call_count == 1


@pytest.mark.asyncio
async def test_concurrent_refresh_only_happens_once(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """Concurrent callers should share a single refresh token operation."""
    token_route = respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
    )

    client = ZohoClient(settings=settings)

    await asyncio.gather(*(client.get_access_token() for _ in range(5)))

    assert token_route.call_count == 1


@pytest.mark.asyncio
async def test_401_refreshes_once_and_retries(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """A 401 should trigger a token refresh and a single retry of the request."""
    token_route = respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "token-1", "expires_in": 300}),
            httpx.Response(200, json={"access_token": "token-2", "expires_in": 300}),
        ]
    )
    crm_route = respx_mock.get("https://www.zohoapis.in/crm/v6/Contacts").mock(
        side_effect=[
            httpx.Response(401, json={"code": "INVALID_TOKEN", "message": "expired token"}),
            httpx.Response(200, json={"data": [{"id": "2", "Full_Name": "Rohit"}]}),
        ]
    )

    client = ZohoClient(settings=settings)

    response = await client.request("GET", "/Contacts")

    assert response == {"data": [{"id": "2", "Full_Name": "Rohit"}]}
    assert token_route.call_count == 2
    assert crm_route.call_count == 2
