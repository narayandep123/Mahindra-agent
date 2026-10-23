"""Seed initial Zoho CRM records for demo scenarios."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.config import validate_settings
from app.zoho.client import ZohoClient
from app.zoho.modules import find_contact_by_phone, find_lead_by_phone, search_deals


def _extract_record_id(payload: dict[str, Any]) -> str | None:
    """Extract the Zoho record ID from either flat or nested API responses."""
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            details = first.get("details")
            if isinstance(details, dict):
                return details.get("id") or first.get("id")
            return first.get("id")
    return payload.get("id")


async def _ensure_lead(client: ZohoClient) -> str:
    """Ensure the Rajesh Sharma lead exists in Zoho CRM."""
    phone = "9876500001"
    lead = await find_lead_by_phone(phone, client)
    if lead:
        lead_id = str(lead.get("id") or lead.get("details", {}).get("id") or "")
        print(f"Existing Lead ID: {lead_id}")
        return lead_id

    payload = {
        "First_Name": "Rajesh",
        "Last_Name": "Sharma",
        "Phone": phone,
        "Email": "rajesh.sharma@example.com",
        "City": "Pune",
        "Vehicle_Model": "Thar",
        "Lead_Source": "AI Chat Agent",
    }
    response = await client.create_record("Leads", payload)
    lead_id = _extract_record_id(response) or ""
    print(f"Created Lead ID: {lead_id}")
    return lead_id


async def _ensure_contact_and_deal(client: ZohoClient) -> tuple[str, str]:
    """Ensure the Priya Patel contact and XUV700 test-drive deal exist."""
    phone = "9876500002"
    contact = await find_contact_by_phone(phone, client)
    contact_id = ""

    if contact:
        contact_id = str(contact.get("id") or contact.get("details", {}).get("id") or "")
        print(f"Existing Contact ID: {contact_id}")
    else:
        contact_payload = {
            "Full_Name": "Priya Patel",
            "Mobile": phone,
            "Phone": phone,
            "Email": "priya.patel@example.com",
        }
        response = await client.create_record("Contacts", contact_payload)
        contact_id = _extract_record_id(response) or ""
        print(f"Created Contact ID: {contact_id}")

    deals = await search_deals(phone=phone, client=client)
    existing_deal_id = ""
    if deals:
        existing_deal_id = str(deals[0].get("id") or deals[0].get("details", {}).get("id") or "")
        print(f"Existing Deal ID: {existing_deal_id}")
        return contact_id, existing_deal_id

    test_drive_date = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
    deal_payload = {
        "Deal_Name": "XUV700 Test Drive",
        "Stage": "Qualification",
        "Description": (
            f"Test drive scheduled: {test_drive_date}, 11:00 AM, Dealer: ABC Motors Mumbai"
        ),
        "Contact_Name": contact_id,
        "Vehicle_Model": "XUV700",
    }
    response = await client.create_record("Deals", deal_payload)
    deal_id = _extract_record_id(response) or ""
    print(f"Created Deal ID: {deal_id}")
    return contact_id, deal_id


async def _ensure_booking_deal(client: ZohoClient) -> tuple[str, str]:
    """Ensure the Amit Verma contact and booking deal exist."""
    phone = "9876500003"
    contact = await find_contact_by_phone(phone, client)
    contact_id = ""

    if contact:
        contact_id = str(contact.get("id") or contact.get("details", {}).get("id") or "")
        print(f"Existing Contact ID: {contact_id}")
    else:
        contact_payload = {
            "Full_Name": "Amit Verma",
            "Mobile": phone,
            "Phone": phone,
            "Email": "amit.verma@example.com",
        }
        response = await client.create_record("Contacts", contact_payload)
        contact_id = _extract_record_id(response) or ""
        print(f"Created Contact ID: {contact_id}")

    existing_deals = await search_deals(booking_id="MAH-9921", client=client)
    if existing_deals:
        deal_id = str(existing_deals[0].get("id") or existing_deals[0].get("details", {}).get("id") or "")
        print(f"Existing Deal ID: {deal_id}")
        return contact_id, deal_id

    deal_payload = {
        "Deal_Name": "Scorpio-N Z8L Booking",
        "Contact_Name": contact_id,
        "Stage": "Closed Won - Booking Done",
        "Booking_ID": "MAH-9921",
        "Vehicle_Model": "Scorpio-N Z8L",
        "Allocation_Stage": "Dispatch Pending",
    }
    response = await client.create_record("Deals", deal_payload)
    deal_id = _extract_record_id(response) or ""
    print(f"Created Deal ID: {deal_id}")
    return contact_id, deal_id


async def main() -> None:
    """Create the standard demo lead/contact/deal records if they do not already exist."""
    validate_settings()
    client = ZohoClient()

    lead_id = await _ensure_lead(client)
    contact_id, deal_id = await _ensure_contact_and_deal(client)
    booking_contact_id, booking_deal_id = await _ensure_booking_deal(client)

    print("Seed summary:")
    print(f"Lead: {lead_id}")
    print(f"Priya Contact: {contact_id}")
    print(f"Priya Deal: {deal_id}")
    print(f"Amit Contact: {booking_contact_id}")
    print(f"Amit Deal: {booking_deal_id}")


if __name__ == "__main__":
    asyncio.run(main())
