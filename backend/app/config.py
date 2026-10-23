"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Contains required runtime configuration for the backend service."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    zoho_client_id: str = Field(default="")
    zoho_client_secret: str = Field(default="")
    zoho_refresh_token: str = Field(default="")
    zoho_accounts_url: str = Field(default="https://accounts.zoho.in")
    zoho_api_url: str = Field(default="https://www.zohoapis.in")
    service_module_api_name: str = Field(default="Cases")
    assistant_name: str = Field(default="Automotive AI Assistant")

    @property
    def missing_required_fields(self) -> list[str]:
        """Return any required settings values that are missing."""
        required = [
            "groq_api_key",
            "zoho_client_id",
            "zoho_client_secret",
            "zoho_refresh_token",
        ]
        return [name for name in required if not getattr(self, name, "")]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


def validate_settings() -> Settings:
    """Validate that all required configuration values are present."""
    settings = get_settings()
    missing = settings.missing_required_fields
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            "Missing required configuration values: "
            f"{joined}. Please set them in your environment or .env file."
        )
    return settings
