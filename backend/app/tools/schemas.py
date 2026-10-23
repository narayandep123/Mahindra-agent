"""Pydantic argument schemas for automotive CRM tool calls."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.zoho.modules import normalize_phone


class ToolErrorMixin(BaseModel):
    """Common mixin to forbid extra fields."""

    model_config = ConfigDict(extra="forbid")


class VehicleInfoArgs(ToolErrorMixin):
    """Args for vehicle info lookup."""

    model: str = Field(..., min_length=1)
    variant: str | None = None


class CreateLeadArgs(ToolErrorMixin):
    """Args to create a new customer lead."""

    full_name: str = Field(..., min_length=2)
    phone: str = Field(..., min_length=10)
    email: str = Field(..., min_length=3)
    city: str = Field(..., min_length=2)
    vehicle_model: str = Field(..., min_length=2)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Ensure the phone number is a valid 10-digit Indian mobile."""
        normalized = normalize_phone(value)
        if len(normalized) != 10:
            raise ValueError("phone must be a valid 10-digit Indian mobile number")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Check that the email is formatted like a basic mailbox address."""
        pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
        if not re.fullmatch(pattern, value):
            raise ValueError("email must be a valid email address")
        return value


class LookupDealArgs(ToolErrorMixin):
    """Args for deal lookup by phone or deal ID."""

    phone: str | None = None
    deal_id: str | None = None

    @property
    def has_lookup_value(self) -> bool:
        """Return whether at least one lookup key is present."""
        return bool(self.phone or self.deal_id)


class UpdateFollowupPreferenceArgs(ToolErrorMixin):
    """Args for deal follow-up preference updates."""

    deal_id: str = Field(..., min_length=1)
    preferred_channel: Literal["SMS", "WhatsApp", "Email", "Phone"]
    preferred_time: str = Field(..., min_length=1)
    notes: str | None = None


class BookingStatusArgs(ToolErrorMixin):
    """Args for booking status lookup by ID or phone."""

    booking_id: str | None = None
    phone: str | None = None

    @property
    def has_lookup_value(self) -> bool:
        """Return whether at least one lookup key is present."""
        return bool(self.booking_id or self.phone)


class CreateServiceTicketArgs(ToolErrorMixin):
    """Args for creating a service ticket."""

    phone: str = Field(..., min_length=10)
    registration_no: str = Field(..., min_length=2)
    odometer_km: int = Field(..., ge=0)
    issue_or_service_type: str = Field(..., min_length=2)
    service_center_city: str = Field(..., min_length=2)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Ensure the phone number is a valid 10-digit Indian mobile."""
        normalized = normalize_phone(value)
        if len(normalized) != 10:
            raise ValueError("phone must be a valid 10-digit Indian mobile number")
        return normalized
