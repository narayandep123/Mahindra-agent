"""Fetch a Zoho refresh token from an authorization grant code."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def _load_env() -> None:
    """Load environment values from the backend .env file."""
    backend_dir = Path(__file__).resolve().parent.parent
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def main() -> int:
    """Exchange a Zoho grant code for a refresh token and print it."""
    _load_env()

    if len(sys.argv) < 2:
        print("Usage: python scripts/get_refresh_token.py <grant_code>", file=sys.stderr)
        return 1

    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")
    accounts_url = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    grant_code = sys.argv[1]

    if not client_id or not client_secret:
        print(
            "Missing required environment values: ZOHO_CLIENT_ID and/or ZOHO_CLIENT_SECRET. "
            "Add them to backend/.env first.",
            file=sys.stderr,
        )
        return 1

    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": grant_code,
    }

    url = f"{accounts_url.rstrip('/')}/oauth/v2/token"
    try:
        response = httpx.post(url, data=payload, timeout=30.0)
        body = response.json()
    except Exception as exc:  # pragma: no cover - transport-level failure
        print(f"Zoho token request failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(f"Zoho token exchange failed with status {response.status_code}")
        print("Full error body:")
        print(body)
        return 1

    refresh_token = body.get("refresh_token")
    if not refresh_token:
        print("Zoho token exchange succeeded but no refresh_token was returned.")
        print("Full response body:")
        print(body)
        return 1

    print("ZOHO_REFRESH_TOKEN=" + refresh_token)
    print("Add this to your backend/.env file as ZOHO_REFRESH_TOKEN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
