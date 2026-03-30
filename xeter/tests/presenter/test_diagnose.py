"""
Unit tests for POST /diagnose endpoint.

Tests cover:
  - Returns 501 when Diagnosticer returns 501 (scaffold response proxied correctly)
  - Returns 401 without Authorization header
  - Proxies the request body (span_id and flags forwarded correctly)
  - Returns 502 when Diagnosticer is unreachable

Mocking strategy:
  - app.state.http_client is replaced with an AsyncMock directly on app.state
  - verify_session_token dependency is overridden to return the test tenant_id
    (avoids needing a real JWT for most tests)
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from xeter.services.presenter.deps import verify_session_token
from xeter.services.presenter.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_A = str(uuid.uuid4())

_DIAGNOSE_URL = "/diagnose"
_AUTH_HEADER = {"Authorization": f"Bearer test-token"}

_NOT_IMPLEMENTED_BODY = {
    "status": "not_implemented",
    "message": "Diagnosticer not yet available",
    "span_id": "span-abc",
}


def _auth_override(tenant_id: str = TENANT_A):
    """Return a FastAPI dependency override that returns the given tenant_id."""
    def override():
        return tenant_id
    return override


def _make_http_client_mock(status_code: int, body: dict) -> AsyncMock:
    """Return an AsyncMock httpx.AsyncClient whose post() returns the given response."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.content = json.dumps(body).encode()

    client_mock = AsyncMock(spec=httpx.AsyncClient)
    client_mock.post = AsyncMock(return_value=mock_response)
    return client_mock


def _cleanup():
    """Remove dependency overrides and app.state http_client after each test."""
    app.dependency_overrides.pop(verify_session_token, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_diagnose_returns_501():
    """POST /diagnose proxies to Diagnosticer and returns 501 scaffold response."""
    http_client = _make_http_client_mock(501, _NOT_IMPLEMENTED_BODY)
    app.state.http_client = http_client
    app.dependency_overrides[verify_session_token] = _auth_override()

    client = TestClient(app)
    try:
        response = client.post(
            _DIAGNOSE_URL,
            json={"span_id": "span-abc", "flags": []},
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 501, response.text
        data = response.json()
        assert data["status"] == "not_implemented"
        assert data["span_id"] == "span-abc"
    finally:
        _cleanup()


def test_diagnose_returns_401_without_token():
    """POST /diagnose without Authorization header returns 401."""
    # Remove verify_session_token override to use the real dependency
    app.dependency_overrides.pop(verify_session_token, None)

    client = TestClient(app)
    try:
        response = client.post(
            _DIAGNOSE_URL,
            json={"span_id": "span-abc", "flags": []},
            # No Authorization header
        )
        assert response.status_code == 401, response.text
    finally:
        _cleanup()


def test_diagnose_proxies_request_body():
    """POST /diagnose forwards span_id and flags to the Diagnosticer service."""
    http_client = _make_http_client_mock(501, _NOT_IMPLEMENTED_BODY)
    app.state.http_client = http_client
    app.dependency_overrides[verify_session_token] = _auth_override()

    client = TestClient(app)
    try:
        payload = {"span_id": "span-xyz", "flags": ["wrong_tool", "no_tool"]}
        client.post(
            _DIAGNOSE_URL,
            json=payload,
            headers=_AUTH_HEADER,
        )
        # Verify the httpx client was called with the correct body
        http_client.post.assert_called_once()
        call_args = http_client.post.call_args
        assert call_args[0][0] == "/diagnose"
        forwarded_json = call_args[1]["json"]
        assert forwarded_json["span_id"] == "span-xyz"
        assert forwarded_json["flags"] == ["wrong_tool", "no_tool"]
    finally:
        _cleanup()


def test_diagnose_returns_502_on_connection_error():
    """POST /diagnose returns 502 when Diagnosticer is unreachable."""
    client_mock = AsyncMock(spec=httpx.AsyncClient)
    client_mock.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    app.state.http_client = client_mock
    app.dependency_overrides[verify_session_token] = _auth_override()

    client = TestClient(app)
    try:
        response = client.post(
            _DIAGNOSE_URL,
            json={"span_id": "span-abc", "flags": []},
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 502, response.text
        data = response.json()
        assert data["error"] == "diagnosticer_unavailable"
    finally:
        _cleanup()
