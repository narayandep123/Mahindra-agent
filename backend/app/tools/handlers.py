"""Async handlers for automotive CRM tool calls."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

from app.config import get_settings
from app.zoho.client import ZohoClient, ZohoError
from app.zoho.modules import create_lead as create_lead_record
from app.zoho.modules import create_service_ticket as create_service_ticket_record
from app.zoho.modules import find_contact_by_phone, find_lead_by_phone, search_deals, update_deal
from app.tools.schemas import (
    BookingStatusArgs,
    CreateLeadArgs,
    CreateServiceTicketArgs,
    LookupDealArgs,
    UpdateFollowupPreferenceArgs,
    VehicleInfoArgs,
)


VEHICLES_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "vehicles.json"


def _load_vehicle_catalog() -> list[dict[str, Any]]:
    """Load the vehicle catalogue once at import time."""
    try:
        payload = json.loads(VEHICLES_CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Vehicle catalogue missing at {VEHICLES_CATALOG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Vehicle catalogue has invalid JSON at {VEHICLES_CATALOG_PATH}") from exc

    if not isinstance(payload, list):
        raise RuntimeError(f"Vehicle catalogue must be a list at {VEHICLES_CATALOG_PATH}")
    return payload


def _response(ok: bool, data: Any = None, error: str | None = None) -> dict[str, Any]:
    """Return a consistent tool result payload for the LLM."""
    return {"ok": ok, "data": data, "error": error}


VEHICLES_DATA = _load_vehicle_catalog()


def _missing_fields(model: BaseModel) -> list[str]:
    """Return required fields missing from a validated model."""
    missing: list[str] = []
    for name, field in model.model_fields.items():
        value = getattr(model, name, None)
        if field.is_required() and (value is None or value == ""):
            missing.append(name)
    return missing


def _normalize_lookup(value: str | None) -> str:
    """Normalize vehicle names for matching, ignoring case, spaces, and hyphens."""
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


async def get_vehicle_info(model: str | dict[str, Any] | None, variant: str | None = None) -> dict[str, Any]:
    """Return a vehicle's variant information and indicative pricing from the vended data file."""
    if isinstance(model, dict):
        args = model
        model_name = args.get("model")
        variant = args.get("variant") if args.get("variant") is not None else variant
        model = model_name

    try:
        if not isinstance(model, str) or not model.strip():
            return _response(False, None, "A vehicle model is required.")

        normalized_model = _normalize_lookup(model)
        for item in VEHICLES_DATA:
            model_name = item.get("model", "")
            if _normalize_lookup(model_name) != normalized_model:
                continue

            if variant is not None:
                normalized_variant = _normalize_lookup(variant)
                matches = [
                    entry for entry in item.get("variants", [])
                    if _normalize_lookup(entry.get("name", "")) == normalized_variant
                ]
                if matches:
                    return _response(
                        True,
                        {
                            "model": model_name,
                            "variant": matches[0].get("name"),
                            "indicative_ex_showroom_price": matches[0].get("indicative_ex_showroom_price"),
                            "price_note": matches[0].get("price_note", "indicative, varies by city"),
                            "key_features": matches[0].get("key_features", []),
                        },
                        None,
                    )
                return _response(False, None, f"Variant '{variant}' not found for {model_name}.")

            variants = []
            for entry in item.get("variants", []):
                variants.append(
                    {
                        "name": entry.get("name"),
                        "indicative_ex_showroom_price": entry.get("indicative_ex_showroom_price"),
                        "price_note": entry.get("price_note", "indicative, varies by city"),
                        "key_features": entry.get("key_features", []),
                    }
                )
            return _response(
                True,
                {
                    "model": model_name,
                    "variants": variants,
                    "price_note": "Indicative ex-showroom prices vary by city.",
                },
                None,
            )

        return _response(False, None, f"Vehicle model '{model}' was not found.")
    except Exception:
        logger.exception("tool get_vehicle_info failed with args model=%s variant=%s", model, variant)
        return _response(False, None, "I couldn’t complete that request right now.")


async def create_lead(
    full_name: str,
    phone: str,
    email: str,
    city: str,
    vehicle_model: str,
) -> dict[str, Any]:
    """Create a lead after validating the request and checking for duplicates."""
    payload = {
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "city": city,
        "vehicle_model": vehicle_model,
    }
    missing = [field for field, value in payload.items() if value in (None, "")]
    if missing:
        return _response(False, {"missing_fields": missing}, "Please provide the missing required fields.")

    try:
        args = CreateLeadArgs(**payload)
    except ValidationError as exc:
        logger.exception("tool create_lead failed with args %s", payload)
        return _response(False, None, exc.errors()[0]["msg"])

    client = ZohoClient()
    try:
        existing = await find_lead_by_phone(args.phone, client)
        if existing:
            return _response(True, {"lead_id": existing.get("id")}, "A lead already exists for this customer.")
        result = await create_lead_record(
            full_name=args.full_name,
            phone=args.phone,
            email=args.email,
            city=args.city,
            vehicle_model=args.vehicle_model,
            client=client,
        )
        return _response(True, result, None)
    except ZohoError as exc:
        logger.exception("tool create_lead failed with args %s", payload)
        return _response(False, None, f"Unable to create the lead right now: {exc.message}")
    except ValidationError as exc:
        logger.exception("tool create_lead failed with args %s", payload)
        return _response(False, None, exc.errors()[0]["msg"])
    except Exception:
        logger.exception("tool create_lead failed with args %s", payload)
        return _response(False, None, "I couldn’t complete that request right now.")


async def lookup_deal(phone: str | None = None, deal_id: str | None = None) -> dict[str, Any]:
    """Lookup a deal by phone or deal ID and summarize its key details for the customer."""
    try:
        args = LookupDealArgs(phone=phone, deal_id=deal_id)
    except ValidationError as exc:
        logger.exception("tool lookup_deal failed with args %s", {"phone": phone, "deal_id": deal_id})
        return _response(False, None, exc.errors()[0]["msg"])

    if not args.has_lookup_value:
        return _response(False, {"missing_fields": ["phone", "deal_id"]}, "Please provide either a phone number or deal ID.")

    client = ZohoClient()
    try:
        deals = await search_deals(phone=args.phone, deal_id=args.deal_id, client=client)
        if not deals:
            lead = await find_lead_by_phone(args.phone, client) if args.phone else None
            if lead:
                vehicle_model = (
                    lead.get("Vehicle_Model")
                    or lead.get("Vehicle Model")
                    or lead.get("vehicle_model")
                    or lead.get("Vehicle")
                )
                return _response(
                    True,
                    {
                        "found_as": "lead",
                        "vehicle_model": vehicle_model,
                        "message": "We have your test drive request on file and our team will confirm the schedule shortly.",
                    },
                    None,
                )
            return _response(False, None, "No matching deal was found.")
        deal = deals[0]
        result = {
            "deal_id": deal.get("id"),
            "stage": deal.get("Stage"),
            "test_drive_or_quote": deal.get("Description") or deal.get("Deal_Name"),
            "dealer_contact": deal.get("Dealer_Contact") or "Not available",
        }
        return _response(True, result, None)
    except ZohoError as exc:
        logger.exception("tool lookup_deal failed with args %s", {"phone": phone, "deal_id": deal_id})
        return _response(False, None, f"Unable to access the deal right now: {exc.message}")
    except Exception:
        logger.exception("tool lookup_deal failed with args %s", {"phone": phone, "deal_id": deal_id})
        return _response(False, None, "I couldn’t complete that request right now.")


async def update_followup_preference(
    deal_id: str,
    preferred_channel: str,
    preferred_time: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Update a deal's preferred follow-up method and time."""
    payload = {
        "deal_id": deal_id,
        "preferred_channel": preferred_channel,
        "preferred_time": preferred_time,
        "notes": notes,
    }
    missing = [field for field, value in payload.items() if field in {"deal_id", "preferred_channel", "preferred_time"} and value in (None, "")]
    if missing:
        return _response(False, {"missing_fields": missing}, "Please provide the missing required fields.")

    try:
        args = UpdateFollowupPreferenceArgs(**payload)
    except ValidationError as exc:
        return _response(False, None, exc.errors()[0]["msg"])

    client = ZohoClient()
    try:
        payload = {
            "Preferred_Channel": args.preferred_channel,
            "Preferred_Time": args.preferred_time,
            "Followup_Notes": args.notes,
        }
        result = await update_deal(args.deal_id, payload, client=client)
        return _response(True, result, None)
    except ZohoError as exc:
        return _response(False, None, f"Unable to update the follow-up preference: {exc.message}")


async def get_booking_status(booking_id: str | None = None, phone: str | None = None) -> dict[str, Any]:
    """Return the current booking status by booking ID or customer phone."""
    try:
        args = BookingStatusArgs(booking_id=booking_id, phone=phone)
    except ValidationError as exc:
        return _response(False, None, exc.errors()[0]["msg"])

    if not args.has_lookup_value:
        return _response(False, {"missing_fields": ["booking_id", "phone"]}, "Please provide a booking ID or phone number.")

    client = ZohoClient()
    try:
        deals = await search_deals(booking_id=args.booking_id, phone=args.phone, client=client)
        if not deals:
            return _response(False, None, "No booking information was found.")
        deal = deals[0]
        status = {
            "booking_id": deal.get("Booking_ID"),
            "allocation_stage": deal.get("Allocation_Stage"),
            "vin": deal.get("VIN"),
            "balance_payment_link": deal.get("Balance_Payment_Link"),
            "stage": deal.get("Stage"),
        }
        return _response(True, status, None)
    except ZohoError as exc:
        return _response(False, None, f"Unable to retrieve booking status: {exc.message}")


async def create_service_ticket(
    phone: str,
    registration_no: str,
    odometer_km: int,
    issue_or_service_type: str,
    service_center_city: str,
) -> dict[str, Any]:
    """Create a service ticket linked to the contact identified by phone number."""
    payload = {
        "phone": phone,
        "registration_no": registration_no,
        "odometer_km": odometer_km,
        "issue_or_service_type": issue_or_service_type,
        "service_center_city": service_center_city,
    }
    missing = [field for field, value in payload.items() if field in {"phone", "registration_no", "issue_or_service_type", "service_center_city"} and value in (None, "")]
    if missing:
        return _response(False, {"missing_fields": missing}, "Please provide the missing required fields.")

    try:
        args = CreateServiceTicketArgs(**payload)
    except ValidationError as exc:
        return _response(False, None, exc.errors()[0]["msg"])

    client = ZohoClient()
    try:
        contact = await find_contact_by_phone(args.phone, client)
        if not contact:
            return _response(False, None, "No customer contact was found for that phone number.")
        result = await create_service_ticket_record(
            contact_id=str(contact.get("id")),
            reg_no=args.registration_no,
            odometer=str(args.odometer_km),
            issue=args.issue_or_service_type,
            service_center=args.service_center_city,
            client=client,
        )
        return _response(True, result, None)
    except ZohoError as exc:
        return _response(False, None, f"Unable to create the service ticket: {exc.message}")


DISPATCH: dict[str, Any] = {
    "get_vehicle_info": get_vehicle_info,
    "create_lead": create_lead,
    "lookup_deal": lookup_deal,
    "update_followup_preference": update_followup_preference,
    "get_booking_status": get_booking_status,
    "create_service_ticket": create_service_ticket,
}
