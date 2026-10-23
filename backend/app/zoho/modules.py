"""Helpers for common Zoho CRM lead, contact, deal, and service ticket workflows."""

from __future__ import annotations

import re
from typing import Any
import logging

from app.config import get_settings
from app.zoho.client import ZohoClient

logger = logging.getLogger(__name__)


def normalize_phone(phone: str | None) -> str:
    """Normalize a phone number to a 10-digit Indian mobile number."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    digits = digits.replace("+91", "", 1)
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) > 10:
        digits = digits[-10:]
    return digits[:10]


def _phone_candidates(phone: str | None) -> list[str]:
    """Return phone formats to try against Zoho search endpoints."""
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    spaced = f"{normalized[:5]} {normalized[5:]}"
    candidates = [
        normalized,
        f"+91{normalized}",
        spaced,
        f"+91 {spaced}",
    ]
    # Preserve order while removing accidental duplicates.
    return list(dict.fromkeys(candidates))


async def create_lead(
    full_name: str,
    phone: str,
    email: str | None,
    city: str | None,
    vehicle_model: str | None,
    client: ZohoClient | None = None,
) -> dict[str, Any]:
    """Create a Zoho lead with the required AI-agent metadata."""
    crm_client = client or ZohoClient()
    first_name, last_name = (full_name.split(maxsplit=1) + [""])[:2]
    payload = {
        "First_Name": first_name,
        "Last_Name": last_name,
        "Phone": normalize_phone(phone),
        "Email": email,
        "City": city,
        "Vehicle_Model": vehicle_model,
        "Lead_Source": "AI Chat Agent",
    }
    response = await crm_client.create_record("Leads", payload)
    if isinstance(response, dict):
        return response
    return {"data": response}


async def find_lead_by_phone(phone: str, client: ZohoClient | None = None) -> dict[str, Any] | None:
    """Find a lead by normalized phone number."""
    crm_client = client or ZohoClient()
    for candidate in _phone_candidates(phone):
        criteria = f"((Phone:equals:{candidate})or(Mobile:equals:{candidate}))"
        response = await crm_client.request(
            "GET",
            "/Leads/search",
            params={"criteria": criteria},
            return_meta=True,
        )
        logger.warning(
            "find_lead_by_phone url=%s params=%s status=%s body=%s",
            response.get("url") if isinstance(response, dict) else None,
            response.get("params") if isinstance(response, dict) else None,
            response.get("status") if isinstance(response, dict) else None,
            response.get("payload") if isinstance(response, dict) else None,
        )
        payload = response.get("payload") if isinstance(response, dict) else None
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if items:
            return items[0]
    return None


async def find_contact_by_phone(phone: str, client: ZohoClient | None = None) -> dict[str, Any] | None:
    """Find a contact by normalized phone number."""
    crm_client = client or ZohoClient()
    for candidate in _phone_candidates(phone):
        criteria = f"((Phone:equals:{candidate})or(Mobile:equals:{candidate}))"
        by_criteria = await crm_client.request(
            "GET",
            "/Contacts/search",
            params={"criteria": criteria},
            return_meta=True,
        )
        logger.warning(
            "find_contact_by_phone url=%s params=%s status=%s body=%s",
            by_criteria.get("url"),
            by_criteria.get("params"),
            by_criteria.get("status"),
            by_criteria.get("payload"),
        )
        payload = by_criteria.get("payload") if isinstance(by_criteria, dict) else None
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if items:
            return items[0]

    return None


async def search_deals(
    phone: str | None = None,
    deal_id: str | None = None,
    booking_id: str | None = None,
    client: ZohoClient | None = None,
) -> list[dict[str, Any]]:
    """Search deals by phone, deal ID, or booking ID."""
    crm_client = client or ZohoClient()
    if deal_id:
        response = await crm_client.request("GET", f"/Deals/{deal_id}")
        if isinstance(response, dict):
            return [response]
        return []

    if booking_id:
        response = await crm_client.request(
            "GET",
            "/Deals/search",
            params={"criteria": f"(Booking_ID:equals:{booking_id})"},
        )
        items = response.get("data", []) if isinstance(response, dict) else []
        return items

    if not phone:
        return []

    contact = await find_contact_by_phone(phone, client=crm_client)
    if not contact:
        return []

    contact_id = contact.get("id")
    if not contact_id:
        return []

    response = await crm_client.request(
        "GET",
        "/Deals/search",
        params={"criteria": f"(Contact_Name:equals:{contact_id})"},
        return_meta=True,
    )
    logger.warning(
        "search_deals url=%s params=%s status=%s body=%s",
        response.get("url") if isinstance(response, dict) else None,
        response.get("params") if isinstance(response, dict) else None,
        response.get("status") if isinstance(response, dict) else None,
        response.get("payload") if isinstance(response, dict) else None,
    )
    payload = response.get("payload") if isinstance(response, dict) else None
    items = payload.get("data", []) if isinstance(payload, dict) else []
    if items:
        return items

    fallback = await crm_client.request(
        "GET",
        f"/Contacts/{contact_id}/Deals",
        return_meta=True,
    )
    logger.warning(
        "search_deals url=%s params=%s status=%s body=%s",
        fallback.get("url") if isinstance(fallback, dict) else None,
        fallback.get("params") if isinstance(fallback, dict) else None,
        fallback.get("status") if isinstance(fallback, dict) else None,
        fallback.get("payload") if isinstance(fallback, dict) else None,
    )

    fallback_payload = fallback.get("payload") if isinstance(fallback, dict) else None
    items = fallback_payload.get("data", []) if isinstance(fallback_payload, dict) else []
    return items


async def update_deal(deal_id: str, fields: dict[str, Any], client: ZohoClient | None = None) -> dict[str, Any]:
    """Update an existing deal record."""
    crm_client = client or ZohoClient()
    payload = {"data": [{"id": deal_id, **fields}]}
    return await crm_client.request("PUT", "/Deals", json=payload)


async def create_service_ticket(
    contact_id: str,
    reg_no: str,
    odometer: str,
    issue: str,
    service_center: str,
    client: ZohoClient | None = None,
) -> dict[str, Any]:
    """Create a service ticket for a contact using the configured service module name."""
    crm_client = client or ZohoClient()
    settings = get_settings()
    payload = {
        "Contact_Name": contact_id,
        "Registration_Number": reg_no,
        "Odometer": odometer,
        "Issue": issue,
        "Service_Center": service_center,
    }
    response = await crm_client.request("POST", f"/{settings.service_module_api_name}", json={"data": [payload]})
    if isinstance(response, dict):
        return response
    return {"data": response}
