"""OpenAI-compatible tool definitions for the automotive AI agent."""

from __future__ import annotations

from app.tools.schemas import (
    BookingStatusArgs,
    CreateLeadArgs,
    CreateServiceTicketArgs,
    LookupDealArgs,
    UpdateFollowupPreferenceArgs,
    VehicleInfoArgs,
)


def _tool_definition(name: str, description: str, schema_model: type[object]) -> dict[str, object]:
    """Create an OpenAI-format tool definition from a Pydantic model."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema_model.model_json_schema(),
        },
    }


TOOL_DEFINITIONS: list[dict[str, object]] = [
    _tool_definition(
        "get_vehicle_info",
        "Return vehicle information, variant details, and indicative price ranges for a model.",
        VehicleInfoArgs,
    ),
    _tool_definition(
        "create_lead",
        "Create a new customer lead for test drives or purchase inquiries.",
        CreateLeadArgs,
    ),
    _tool_definition(
        "lookup_deal",
        "Find a customer deal by phone or deal ID and summarize the status and follow-up details.",
        LookupDealArgs,
    ),
    _tool_definition(
        "update_followup_preference",
        "Update a deal's communication channel and preferred callback time.",
        UpdateFollowupPreferenceArgs,
    ),
    _tool_definition(
        "get_booking_status",
        "Fetch booking status details by booking ID or customer phone.",
        BookingStatusArgs,
    ),
    _tool_definition(
        "create_service_ticket",
        "Create a service ticket linked to the contact found by phone number.",
        CreateServiceTicketArgs,
    ),
]

DISPATCH: dict[str, str] = {
    "get_vehicle_info": "get_vehicle_info",
    "create_lead": "create_lead",
    "lookup_deal": "lookup_deal",
    "update_followup_preference": "update_followup_preference",
    "get_booking_status": "get_booking_status",
    "create_service_ticket": "create_service_ticket",
}
