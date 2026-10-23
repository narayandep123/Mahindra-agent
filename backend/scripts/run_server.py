"""Convenience script to launch the backend service."""

from __future__ import annotations

import uvicorn

from app.config.settings import get_settings


settings = get_settings()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_env == "development",
    )
