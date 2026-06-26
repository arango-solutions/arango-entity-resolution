"""Shared authentication helpers for the Entity Resolution UI.

Kept in a dedicated module so both the FastAPI app factory and the WebSocket
route can import them without a circular dependency.
"""

from __future__ import annotations

import hmac
from typing import Any, Dict, Optional

ANONYMOUS_REVIEWER = "anonymous"


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


def parse_reviewers(value: Optional[str]) -> Dict[str, str]:
    """Parse an ``ER_UI_REVIEWERS`` string into a ``{token: display_name}`` map.

    Format: comma-separated ``token=Display Name`` pairs, e.g.
    ``"abc123=Alice,def456=Bob"``. Blank/malformed entries are ignored.
    """
    mapping: Dict[str, str] = {}
    if not value:
        return mapping
    for pair in value.split(","):
        if "=" not in pair:
            continue
        token, name = pair.split("=", 1)
        token, name = token.strip(), name.strip()
        if token and name:
            mapping[token] = name
    return mapping


def resolve_reviewer(
    headers: Any,
    reviewers_map: Optional[Dict[str, str]] = None,
) -> str:
    """Resolve the acting reviewer for attribution (not access control).

    Priority:
    1. ``X-Reviewer`` header (free-text session name from the UI).
    2. ``token -> display name`` from ``reviewers_map`` (the request's bearer/API token).
    3. ``"anonymous"``.
    """
    explicit = headers.get("x-reviewer") or headers.get("X-Reviewer")
    if explicit and explicit.strip():
        return explicit.strip()
    if reviewers_map:
        token = extract_request_token(headers)
        if token and token in reviewers_map:
            return reviewers_map[token]
    return ANONYMOUS_REVIEWER
