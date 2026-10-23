"""Tests for Zoho CRM helper functions."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.zoho.client import ZohoClient
from app.zoho.modules import (
    create_lead,
    create_service_ticket,
    find_contact_by_phone,
    find_lead_by_phone,
    normalize_phone,
    search_deals,
    update_deal,
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Populate minimum settings for module helper tests."""
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    monkeypatch.setenv("ZOHO_CLIENT_ID", "client-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    monkeypatch.setenv("ZOHO_API_URL", "https://www.zohoapis.in")
    monkeypatch.setenv("SERVICE_MODULE_API_NAME", "Cases")
    return Settings()


def test_normalize_phone() -> None:
    """Phone numbers should normalize to a 10-digit format."""
    assert normalize_phone("+91 98765-43210") == "9876543210"
    assert normalize_phone("0987654321") == "987654321"
    assert normalize_phone("(981) 234-5678") == "9812345678"


@pytest.mark.asyncio
async def test_create_lead_and_find_by_phone(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """Lead creation and lookup should use the normalized phone and AI source metadata."""
    respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-123", "expires_in": 3600})
    )
    respx_mock.post("https://www.zohoapis.in/crm/v6/Leads").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "L1"}]})
    )
    respx_mock.get("https://www.zohoapis.in/crm/v6/Leads/search").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "L1", "Phone": "9876543210"}]})
    )

    client = ZohoClient(settings=settings)
    created = await create_lead("Aman Gupta", "+91 98765-43210", "aman@example.com", "Delhi", "Scorpio", client)
    found = await find_lead_by_phone("9876543210", client)

    assert created["data"][0]["id"] == "L1"
    assert found["Phone"] == "9876543210"


@pytest.mark.asyncio
async def test_find_lead_by_phone_checks_mobile_and_plus91(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """Lead lookup should try normalized and +91 criteria across Phone and Mobile fields."""
    respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-lead", "expires_in": 3600})
    )

    leads_search = respx_mock.get("https://www.zohoapis.in/crm/v6/Leads/search").mock(
        side_effect=[
            httpx.Response(204),
            httpx.Response(200, json={"data": [{"id": "L9", "Mobile": "+919876500002", "Vehicle_Model": "XUV700"}]}),
        ]
    )

    client = ZohoClient(settings=settings)
    lead = await find_lead_by_phone("9876500002", client=client)

    assert leads_search.called
    assert lead is not None
    assert lead["id"] == "L9"


@pytest.mark.asyncio
async def test_search_deals_and_update(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """Search deals by contact and update a deal payload."""
    respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-abc", "expires_in": 3600})
    )
    respx_mock.get("https://www.zohoapis.in/crm/v6/Contacts/search").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "C1", "Full_Name": "Rohit Sharma"}]})
    )
    respx_mock.get("https://www.zohoapis.in/crm/v6/Deals/search").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "D1", "Contact_Name": "Rohit Sharma"}]})
    )
    respx_mock.put("https://www.zohoapis.in/crm/v6/Deals").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "D1", "Stage": "Closed Won"}]})
    )

    client = ZohoClient(settings=settings)
    rows = await search_deals(phone="9812345678", client=client)
    updated = await update_deal("D1", {"Stage": "Closed Won"}, client=client)

    assert rows[0]["id"] == "D1"
    assert updated["data"][0]["Stage"] == "Closed Won"


@pytest.mark.asyncio
async def test_search_deals_uses_phone_and_criteria_and_related_list_fallback(
    settings: Settings, respx_mock: respx.MockRouter
) -> None:
    """Deal search should use contact phone lookups and fall back to contact related-list deals."""
    respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-fallback", "expires_in": 3600})
    )

    contacts_search = respx_mock.get("https://www.zohoapis.in/crm/v6/Contacts/search").mock(
        side_effect=[
            httpx.Response(204),
            httpx.Response(200, json={"data": [{"id": "C55", "Phone": "+919876500002"}]}),
        ]
    )

    deals_search = respx_mock.get("https://www.zohoapis.in/crm/v6/Deals/search").mock(
        return_value=httpx.Response(204)
    )
    related_deals = respx_mock.get("https://www.zohoapis.in/crm/v6/Contacts/C55/Deals").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "D55", "Stage": "Follow Up"}]})
    )

    client = ZohoClient(settings=settings)
    rows = await search_deals(phone="9876500002", client=client)

    assert contacts_search.called
    assert deals_search.called
    assert related_deals.called
    assert rows[0]["id"] == "D55"


@pytest.mark.asyncio
async def test_create_service_ticket(settings: Settings, respx_mock: respx.MockRouter) -> None:
    """Service module ticket creation should issue a POST with the configured module name."""
    respx_mock.post("https://accounts.zoho.in/oauth/v2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token-xyz", "expires_in": 3600})
    )
    respx_mock.post("https://www.zohoapis.in/crm/v6/Cases").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "T1"}]})
    )

    client = ZohoClient(settings=settings)
    created = await create_service_ticket("C1", "DL01AB1234", "12000", "Brake noise", "Bengaluru", client)

    assert created["data"][0]["id"] == "T1"
