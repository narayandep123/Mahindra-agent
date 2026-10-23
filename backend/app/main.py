"""FastAPI application entrypoint for the automotive assistant monorepo."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import validate_settings
from app.routes import router as chat_router
from app.zoho.client import ZohoClient

validate_settings()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Automotive AI Assistant")
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a friendly JSON payload for invalid request bodies."""
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": "Please provide a valid session_id and a message under 1000 characters."},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a friendly JSON payload when an unexpected error occurs."""
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "Sorry, something went wrong. Please try again in a moment."},
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Create the shared Zoho client for CRM tool calls."""
    app.state.zoho_client = ZohoClient()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Close the shared Zoho client when the app stops."""
    zoho_client = getattr(app.state, "zoho_client", None)
    if zoho_client is not None:
        await zoho_client._client.aclose()


app.include_router(chat_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str | bool | None]:
    """Return a minimal health payload for the API service."""
    return {"ok": True, "status": "healthy", "error": None}
