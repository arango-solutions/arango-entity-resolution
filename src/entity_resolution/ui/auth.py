"""Shared authentication helpers for the Entity Resolution UI.

Kept in a dedicated module so both the FastAPI app factory and the WebSocket
route can import them without a circular dependency.
"""

from __future__ import annotations

import hmac
from typing import Any, Optional


def extract_request_token(headers: Any) -> Optional[str]:
    """Extract a bearer/API-key token from request headers.

    Supports ``Authorization: Bearer <token>`` and ``X-API-Key: <token>``.
    """
    auth = headers.get("authorization") or headers.get("Authorization")
    if auth:
        parts = auth.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return auth.strip()
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    return None


def tokens_match(provided: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time comparison of a provided token against the expected one."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)
