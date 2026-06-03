"""Security tests for the MCP SSE transport auth middleware (PR2)."""

import asyncio

from entity_resolution.mcp.server import (
    _extract_bearer_token,
    _TokenAuthASGIMiddleware,
)


TOKEN = "mcp-secret-token"


def test_extract_bearer_token():
    assert _extract_bearer_token("Bearer abc") == "abc"
    assert _extract_bearer_token("abc") == "abc"
    assert _extract_bearer_token(None) is None
    assert _extract_bearer_token("") is None


def _run_middleware(authorization):
    """Drive the ASGI middleware with one HTTP request; return (status, downstream_called)."""
    called = {"value": False}

    async def downstream(scope, receive, send):
        called["value"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = _TokenAuthASGIMiddleware(downstream, TOKEN)

    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    scope = {"type": "http", "headers": headers, "method": "GET", "path": "/sse"}

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(mw(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, called["value"]


def test_sse_rejects_without_token():
    status, downstream_called = _run_middleware(None)
    assert status == 401
    assert downstream_called is False


def test_sse_rejects_wrong_token():
    status, downstream_called = _run_middleware("Bearer wrong")
    assert status == 401
    assert downstream_called is False


def test_sse_accepts_valid_token():
    status, downstream_called = _run_middleware(f"Bearer {TOKEN}")
    assert status == 200
    assert downstream_called is True
