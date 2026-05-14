"""
Unit tests for POST /diagnose endpoint in the Diagnosticer service.

Mocking strategy:
  - InternalApiKeyMiddleware is the auth gate — requests without X-Internal-Api-Key return 401
  - get_ch_client overridden via app.dependency_overrides (avoids real ClickHouse)
  - assemble_context patched via unittest.mock.patch
  - get_llm_client patched via unittest.mock.patch
  - get_async_engine / get_async_session_factory patched at module level to avoid
    real DB calls (including during lifespan startup and per-request)
  - DiagnosisRepository patched to avoid real DB calls

Test cases:
  - 200: successful end-to-end flow (mocked LLM + mocked DB)
  - 401: missing X-Internal-Api-Key header
  - 401: wrong X-Internal-Api-Key header
  - 404: span not found (ValueError from assemble_context)
  - 502: LLM call fails (LLMError)
  - 422: LLM response unparseable (ParseError)
  - healthz: GET /healthz returns 200 {status: ok}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from xeter.services.diagnosticer.main import app, get_ch_client
from xeter.services.diagnosticer.providers.base import DiagnosisResult, LLMError, ParseError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_ID = str(uuid.uuid4())
SPAN_ID = "span-test-001"
TRACE_ID = "trace-test-001"

# Valid internal key matching conftest.py setdefault("INTERNAL_API_KEY", "test-internal-key")
_INTERNAL_KEY_HEADER = {
    "X-Internal-Api-Key": "test-internal-key",
    "X-Tenant-Id": TENANT_ID,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ch_client_override():
    """Return a callable that overrides get_ch_client with a mock ClickHouse client."""
    mock_ch = MagicMock()
    def override():
        return mock_ch
    return override


def _make_fake_diagnosis():
    """Return a MagicMock Diagnosis ORM instance with all expected fields."""
    d = MagicMock()
    d.diagnosis_id = uuid.uuid4()
    d.span_id = SPAN_ID
    d.trace_id = TRACE_ID
    d.verdict = "model"
    d.severity = "high"
    d.affected_field = "tool_arguments"
    d.fix = "Improve argument precision in system prompt."
    d.model_used = "claude-haiku-4-5"
    d.provider_used = "anthropic"
    d.created_at = datetime.now(tz=timezone.utc)
    return d


def _make_mock_session_factory():
    """Return a MagicMock async session factory (each call returns a context-manager session)."""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=mock_session)
    return factory


# ---------------------------------------------------------------------------
# Module-level patches applied to every test (avoids real DB in lifespan + endpoint)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Patch engine/session factory at module level and override CH client dependency.

    This prevents any test from hitting a real PostgreSQL or ClickHouse connection,
    including during TestClient lifespan startup.
    """
    mock_factory = _make_mock_session_factory()

    app.dependency_overrides[get_ch_client] = _ch_client_override()

    with patch("xeter.services.diagnosticer.main.get_async_session_factory", return_value=mock_factory):
        yield mock_factory

    # Clean up CH client override
    app.dependency_overrides.pop(get_ch_client, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiagnoseEndpoint:
    """Tests for POST /diagnose."""

    def setup_method(self):
        """No auth override needed — InternalApiKeyMiddleware controls access via X-Internal-Api-Key."""
        pass

    def teardown_method(self):
        """No auth override to clean up."""
        pass

    def test_missing_auth_returns_401(self):
        """POST /diagnose without X-Internal-Api-Key returns 401."""
        with TestClient(app) as client:
            response = client.post("/diagnose", json={"span_id": SPAN_ID})
        assert response.status_code == 401

    def test_wrong_internal_key_returns_401(self):
        """POST /diagnose with wrong X-Internal-Api-Key returns 401."""
        with TestClient(app) as client:
            response = client.post(
                "/diagnose",
                json={"span_id": SPAN_ID},
                headers={"X-Internal-Api-Key": "definitely-wrong-key"},
            )
        assert response.status_code == 401

    def test_span_not_found_returns_404(self):
        """POST /diagnose with unknown span_id returns 404."""
        with patch(
            "xeter.services.diagnosticer.main.assemble_context",
            new=AsyncMock(side_effect=ValueError(f"Span {SPAN_ID!r} not found")),
        ):
            with TestClient(app) as client:
                response = client.post("/diagnose", json={"span_id": SPAN_ID}, headers=_INTERNAL_KEY_HEADER)
        assert response.status_code == 404
        assert SPAN_ID in response.json()["detail"]

    def test_llm_error_returns_502(self):
        """POST /diagnose when LLM fails returns 502 (no DB write)."""
        mock_provider = MagicMock()
        mock_provider.diagnose = AsyncMock(side_effect=LLMError("API rate limit"))
        with (
            patch(
                "xeter.services.diagnosticer.main.assemble_context",
                new=AsyncMock(return_value=("context string", TRACE_ID)),
            ),
            patch(
                "xeter.services.diagnosticer.main.get_llm_client",
                return_value=mock_provider,
            ),
        ):
            with TestClient(app) as client:
                response = client.post("/diagnose", json={"span_id": SPAN_ID}, headers=_INTERNAL_KEY_HEADER)
        assert response.status_code == 502
        assert "LLM call failed" in response.json()["detail"]

    def test_parse_error_returns_422(self):
        """POST /diagnose when LLM response unparseable returns 422."""
        mock_provider = MagicMock()
        mock_provider.diagnose = AsyncMock(side_effect=ParseError("No tool_use block"))
        with (
            patch(
                "xeter.services.diagnosticer.main.assemble_context",
                new=AsyncMock(return_value=("context string", TRACE_ID)),
            ),
            patch(
                "xeter.services.diagnosticer.main.get_llm_client",
                return_value=mock_provider,
            ),
        ):
            with TestClient(app) as client:
                response = client.post("/diagnose", json={"span_id": SPAN_ID}, headers=_INTERNAL_KEY_HEADER)
        assert response.status_code == 422

    def test_successful_diagnosis_returns_200(self):
        """POST /diagnose returns 200 with full diagnosis fields on success."""
        fake_diagnosis = _make_fake_diagnosis()
        mock_provider = MagicMock()
        mock_provider.diagnose = AsyncMock(
            return_value=(
                DiagnosisResult(
                    verdict="model",
                    severity="high",
                    affected_field="tool_arguments",
                    fix="Improve argument precision.",
                ),
                '{"raw": "response"}',
            )
        )
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=fake_diagnosis)

        mock_tenant_session = MagicMock()
        mock_tenant_session.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_tenant_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "xeter.services.diagnosticer.main.assemble_context",
                new=AsyncMock(return_value=("context string", TRACE_ID)),
            ),
            patch(
                "xeter.services.diagnosticer.main.get_llm_client",
                return_value=mock_provider,
            ),
            patch(
                "xeter.services.diagnosticer.main.DiagnosisRepository",
                return_value=mock_repo,
            ),
            patch(
                "xeter.services.diagnosticer.main.tenant_session",
                return_value=mock_tenant_session,
            ),
        ):
            with TestClient(app) as client:
                response = client.post("/diagnose", json={"span_id": SPAN_ID}, headers=_INTERNAL_KEY_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "model"
        assert body["severity"] == "high"
        assert body["affected_field"] == "tool_arguments"
        assert "diagnosis_id" in body
        assert body["span_id"] == SPAN_ID


class TestHealthz:
    """Tests for GET /healthz."""

    def test_healthz_returns_ok(self):
        with TestClient(app) as client:
            response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
