"""Zoho CRM tool implementations for the AI assistant."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.zoho.client import ZohoCRMClient


def tool_response(ok: bool, data: Any = None, error: str | None = None) -> dict[str, Any]:
    """Return a consistent payload contract for all tool results."""
    return {"ok": ok, "data": data, "error": error}


class SearchLeadsInput(BaseModel):
    """Search criteria for Zoho CRM leads."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    dealer_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class CreateServiceCaseInput(BaseModel):
    """Inputs required to create a service case in Zoho."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    description: str
    customer_name: str
    phone: str | None = None
    email: str | None = None
    priority: str = "Medium"
    dealer_id: str | None = None


class DealerProfileInput(BaseModel):
    """Inputs used to fetch a dealer profile from Zoho CRM."""

    model_config = ConfigDict(extra="forbid")

    dealer_id: str | None = None
    dealer_name: str | None = None


async def search_leads(
    args: SearchLeadsInput | dict[str, Any],
    client: ZohoCRMClient | None = None,
) -> dict[str, Any]:
    """Search for leads matching a set of filters in the CRM."""
    try:
        payload = args if isinstance(args, SearchLeadsInput) else SearchLeadsInput.model_validate(args)
    except Exception as exc:  # pragma: no cover - validation path
        return tool_response(False, None, str(exc))

    crm_client = client or ZohoCRMClient()
    criteria: list[str] = []

    if payload.customer_name:
        criteria.append(f"(First_Name:equals:{payload.customer_name} or Last_Name:equals:{payload.customer_name})")
    if payload.phone:
        criteria.append(f"(Mobile:equals:{payload.phone} or Phone:equals:{payload.phone})")
    if payload.email:
        criteria.append(f"(Email:equals:{payload.email})")
    if payload.city:
        criteria.append(f"(City:equals:{payload.city})")
    if payload.dealer_id:
        criteria.append(f"(Dealer_ID:equals:{payload.dealer_id})")

    search_criteria = " and ".join(criteria) if criteria else None

    try:
        response = await crm_client.get_records(
            module_name="Leads",
            page=1,
            per_page=payload.limit,
            criteria=search_criteria,
        )
    except Exception as exc:  # pragma: no cover - network failure path
        return tool_response(False, None, str(exc))

    return tool_response(True, response.get("data") or response, None)


async def fetch_dealer_profile(
    args: DealerProfileInput | dict[str, Any],
    client: ZohoCRMClient | None = None,
) -> dict[str, Any]:
    """Fetch a dealer or dealership profile from CRM records."""
    try:
        payload = args if isinstance(args, DealerProfileInput) else DealerProfileInput.model_validate(args)
    except Exception as exc:  # pragma: no cover - validation path
        return tool_response(False, None, str(exc))

    crm_client = client or ZohoCRMClient()
    criteria: list[str] = []

    if payload.dealer_id:
        criteria.append(f"(Dealer_ID:equals:{payload.dealer_id})")
    if payload.dealer_name:
        criteria.append(f"(Account_Name:equals:{payload.dealer_name})")

    search_criteria = " and ".join(criteria) if criteria else None

    try:
        response = await crm_client.get_records(
            module_name="Accounts",
            page=1,
            per_page=10,
            criteria=search_criteria,
        )
    except Exception as exc:  # pragma: no cover - network failure path
        return tool_response(False, None, str(exc))

    return tool_response(True, response.get("data") or response, None)


async def create_service_case(
    args: CreateServiceCaseInput | dict[str, Any],
    client: ZohoCRMClient | None = None,
) -> dict[str, Any]:
    """Create a service case with validated customer and vehicle context."""
    try:
        payload = (
            args if isinstance(args, CreateServiceCaseInput) else CreateServiceCaseInput.model_validate(args)
        )
    except Exception as exc:  # pragma: no cover - validation path
        return tool_response(False, None, str(exc))

    crm_client = client or ZohoCRMClient()
    case_payload: dict[str, Any] = {
        "Subject": payload.subject,
        "Description": payload.description,
        "Status": "Open",
        "Priority": payload.priority,
        "Dealership_ID": payload.dealer_id,
        "Customer_Name": payload.customer_name,
        "Phone": payload.phone,
        "Email": payload.email,
    }

    try:
        response = await crm_client.create_record("Cases", case_payload)
    except Exception as exc:  # pragma: no cover - network failure path
        return tool_response(False, None, str(exc))

    return tool_response(True, response.get("data") or response, None)
