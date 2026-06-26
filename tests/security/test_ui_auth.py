"""Security tests for the Web UI authentication layer (PR2)."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from entity_resolution.ui.app import create_app
from entity_resolution.ui.auth import (
    ANONYMOUS_REVIEWER,
    extract_request_token,
    parse_reviewers,
    resolve_reviewer,
    tokens_match,
)


TOKEN = "s3cr3t-token-value"


class _FakeHeaders(dict):
    """dict subclass standing in for case-insensitive header access in tests."""


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def test_extract_bearer_token():
    assert extract_request_token({"authorization": "Bearer abc"}) == "abc"


def test_extract_api_key_token():
    assert extract_request_token({"x-api-key": "abc"}) == "abc"


def test_extract_token_none_when_absent():
    assert extract_request_token({}) is None


def test_tokens_match():
    assert tokens_match("abc", "abc") is True
    assert tokens_match("abc", "xyz") is False
    assert tokens_match(None, "abc") is False
    assert tokens_match("abc", None) is False
    assert tokens_match("", "") is False


# ---------------------------------------------------------------------------
# Reviewer identity (attribution, not auth) — plan 2.0
# ---------------------------------------------------------------------------

def test_parse_reviewers():
    assert parse_reviewers("a=Alice, b=Bob") == {"a": "Alice", "b": "Bob"}
    assert parse_reviewers("") == {}
    assert parse_reviewers(None) == {}
    assert parse_reviewers("garbage,c=Carol") == {"c": "Carol"}


def test_resolve_reviewer_header_wins():
    assert resolve_reviewer({"x-reviewer": "Alice"}, {"tok": "Bob"}) == "Alice"


def test_resolve_reviewer_from_token_map():
    assert resolve_reviewer({"authorization": "Bearer tok"}, {"tok": "Bob"}) == "Bob"


def test_resolve_reviewer_anonymous_default():
    assert resolve_reviewer({}, {}) == ANONYMOUS_REVIEWER
    assert resolve_reviewer({"authorization": "Bearer unknown"}, {"tok": "Bob"}) == ANONYMOUS_REVIEWER


# ---------------------------------------------------------------------------
# HTTP auth middleware (db is None so passing auth surfaces as 503, not 200)
# ---------------------------------------------------------------------------

def _client(auth_token):
    return TestClient(create_app(db=None, auth_token=auth_token))


def test_health_is_exempt_from_auth():
    client = _client(TOKEN)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_api_requires_token_when_enabled():
    client = _client(TOKEN)
    resp = client.get("/api/collections")
    assert resp.status_code == 401


def test_api_rejects_wrong_token():
    client = _client(TOKEN)
    resp = client.get("/api/collections", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_api_accepts_valid_bearer_token():
    client = _client(TOKEN)
    resp = client.get("/api/collections", headers={"Authorization": f"Bearer {TOKEN}"})
    # Auth passed; db is None so the db-connection middleware returns 503.
    assert resp.status_code != 401


def test_api_accepts_valid_api_key_header():
    client = _client(TOKEN)
    resp = client.get("/api/collections", headers={"X-API-Key": TOKEN})
    assert resp.status_code != 401


def test_no_auth_mode_allows_api_without_token():
    client = _client(None)
    resp = client.get("/api/collections")
    assert resp.status_code != 401


# ---------------------------------------------------------------------------
# WebSocket auth
# ---------------------------------------------------------------------------

class _FakeDB:
    def has_collection(self, name):
        return False


def test_ws_rejects_without_token():
    client = TestClient(create_app(db=_FakeDB(), auth_token=TOKEN))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/pipeline/run123") as ws:
            ws.receive_json()


def test_ws_accepts_with_token_query_param():
    client = TestClient(create_app(db=_FakeDB(), auth_token=TOKEN))
    with client.websocket_connect(f"/ws/pipeline/run123?token={TOKEN}") as ws:
        msg = ws.receive_json()
        # Auth passed and the handler ran (no runs collection on the fake db).
        assert msg["type"] == "error"


# ---------------------------------------------------------------------------
# CLI public-bind guard
# ---------------------------------------------------------------------------

def test_cli_refuses_public_bind_without_token(monkeypatch):
    from click.testing import CliRunner
    from entity_resolution.cli import main

    monkeypatch.delenv("ER_UI_AUTH_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["ui", "--serve-host", "0.0.0.0"])
    assert result.exit_code == 1
    assert "Refusing to bind" in result.output

