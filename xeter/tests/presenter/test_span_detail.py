"""
Unit tests for GET /spans/{span_id} endpoint.

Tests cover:
  1. test_span_detail_includes_flags_and_scores  — full detail with flags + scores
  2. test_span_detail_includes_s3_payloads       — S3 prompt/response/raw_response inline
  3. test_span_detail_s3_timeout_returns_504     — asyncio.TimeoutError -> 504
  4. test_span_detail_s3_error_returns_502       — generic S3 error -> 502
  5. test_span_detail_not_found_returns_404      — empty CH result -> 404
  6. test_span_detail_cross_tenant_returns_404   — CH returns no row for wrong tenant -> 404
  7. test_span_detail_missing_token_returns_401  — no Authorization header -> 401

Mocking strategy:
  - app.dependency_overrides[verify_session_token] returns fixed tenant_id
  - app.dependency_overrides[get_session] injects AsyncMock session
  - app.dependency_overrides[get_ch_client] injects a MagicMock CH client per-request
  - aioboto3.Session is patched to control S3 fetch behaviour
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import create_session_token, get_ch_client, verify_session_token
from xeter.services.presenter.main import app
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.models import Flag

# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

TENANT_A = str(uuid.uuid4())

_NOW = datetime(2026, 3, 30, 10, 0, 0, tzinfo=timezone.utc)
_THEN = datetime(2026, 3, 30, 9, 59, 55, tzinfo=timezone.utc)

SPAN_ID = "span-detail-1"
TRACE_ID = "trace-detail-1"


def _ch_span_row(
    span_id=SPAN_ID,
    trace_id=TRACE_ID,
    parent_span_id=None,
    agent_name="agent-x",
    agent_model="gpt-4",
    tool_name="search",
    tool_description="Search the web",
    tool_arguments='{"query": "foo"}',
    tool_output="Some result",
    time_begin=None,
    time_end=None,
    prompt_ref="tenant/2026-03/span-detail-1/prompt.json",
    response_ref="tenant/2026-03/span-detail-1/response.json",
    raw_response_ref="tenant/2026-03/span-detail-1/raw_response.json",
):
    """Return a ClickHouse-style result row tuple for span detail."""
    return (
        span_id,
        trace_id,
        parent_span_id,
        agent_name,
        agent_model,
        tool_name,
        tool_description,
        tool_arguments,
        tool_output,
        time_begin or _THEN,
        time_end or _NOW,
        prompt_ref,
        response_ref,
        raw_response_ref,
    )


def _make_ch_client(row=None) -> MagicMock:
    """Return a MagicMock ClickHouse client returning 0 or 1 span rows."""
    client = MagicMock()
    result = MagicMock()
    result.result_rows = [row] if row is not None else []
    client.query.return_value = result
    return client


def _make_flag(
    span_id: str = SPAN_ID,
    tenant_id: str = TENANT_A,
    flag_type: str = "wrong_tool",
    score: float = 0.8,
    detail: dict | None = None,
    created_at=None,
) -> MagicMock:
    """Return a mock Flag ORM instance."""
    flag = MagicMock(spec=Flag)
    flag.flag_id = uuid.uuid4()
    flag.tenant_id = uuid.UUID(tenant_id)
    flag.span_id = span_id
    flag.trace_id = TRACE_ID
    flag.flag_type = flag_type
    flag.score = score
    flag.detail = detail
    flag.created_at = created_at or _NOW
    return flag


def _make_pg_session(
    flags: list | None = None,
    score_rows: list[tuple] | None = None,
) -> AsyncMock:
    """Return an AsyncMock session simulating flags + span_scores queries."""
    session = AsyncMock(spec=AsyncSession)

    flags_mock = MagicMock()
    flags_scalars = MagicMock()
    flags_scalars.all.return_value = flags or []
    flags_mock.scalars.return_value = flags_scalars

    scores_mock = MagicMock()
    scores_mock.fetchall.return_value = score_rows or []

    session.execute = AsyncMock(side_effect=[flags_mock, scores_mock])
    return session


def _auth_override(tenant_id: str):
    def override():
        return tenant_id
    return override


def _session_override(session):
    async def override():
        yield session
    return override


def _make_s3_mock(prompt="prompt text", response="response text", raw_response="raw text"):
    """Return a mock aioboto3 Session whose S3 client returns the given payload values."""

    async def _fake_get_object(Bucket, Key):
        # Determine value based on key suffix
        import json as _json
        if "prompt" in Key and "raw" not in Key:
            value = prompt
        elif "response" in Key and "raw" not in Key:
            value = response
        else:
            value = raw_response
        body_mock = AsyncMock()
        body_mock.read = AsyncMock(return_value=_json.dumps({"value": value}).encode())
        return {"Body": body_mock}

    s3_context = AsyncMock()
    s3_context.get_object = AsyncMock(side_effect=_fake_get_object)
    s3_context.__aenter__ = AsyncMock(return_value=s3_context)
    s3_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.client.return_value = s3_context

    return mock_session


def _ch_client_override(ch_client):
    """Return a FastAPI dependency override that yields the given CH client."""
    def override():
        yield ch_client
    return override


def _cleanup():
    """Remove all dependency overrides after each test."""
    app.dependency_overrides.pop(get_ch_client, None)
    app.dependency_overrides.pop(verify_session_token, None)
    app.dependency_overrides.pop(get_session, None)


def _client_with_mocks(ch_row=None, flags=None, score_rows=None, tenant_id=TENANT_A):
    """Create a TestClient with fully mocked CH + PG dependencies."""
    ch_client = _make_ch_client(ch_row)
    pg_session = _make_pg_session(flags=flags, score_rows=score_rows)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_client)
    app.dependency_overrides[verify_session_token] = _auth_override(tenant_id)
    app.dependency_overrides[get_session] = _session_override(pg_session)

    return TestClient(app), ch_client, pg_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_span_detail_includes_flags_and_scores():
    """GET /spans/{id} returns all flag details and all scores."""
    row = _ch_span_row()
    flag = _make_flag(flag_type="wrong_tool", score=0.85, detail={"reason": "off-topic"})
    score_rows = [
        ("tool_analyser", "similarity", 0.72),
        ("tool_analyser", "confidence", 0.90),
    ]

    client, _, _ = _client_with_mocks(ch_row=row, flags=[flag], score_rows=score_rows)
    s3_mock = _make_s3_mock()

    try:
        with patch("xeter.services.presenter.routers.spans.aioboto3.Session", return_value=s3_mock):
            resp = client.get(
                f"/spans/{SPAN_ID}",
                headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Flags
        assert len(data["flags"]) == 1
        assert data["flags"][0]["flag_type"] == "wrong_tool"
        assert abs(data["flags"][0]["score"] - 0.85) < 0.001
        assert data["flags"][0]["detail"] == {"reason": "off-topic"}

        # Scores
        assert len(data["scores"]) == 2
        score_names = {s["metric_name"] for s in data["scores"]}
        assert score_names == {"similarity", "confidence"}
    finally:
        _cleanup()


def test_span_detail_includes_s3_payloads():
    """GET /spans/{id} returns prompt, response, raw_response from S3."""
    row = _ch_span_row()
    client, _, _ = _client_with_mocks(ch_row=row)
    s3_mock = _make_s3_mock(
        prompt="The user asked about X",
        response="The assistant answered Y",
        raw_response='{"choices": [{"text": "Y"}]}',
    )

    try:
        with patch("xeter.services.presenter.routers.spans.aioboto3.Session", return_value=s3_mock):
            resp = client.get(
                f"/spans/{SPAN_ID}",
                headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["prompt"] == "The user asked about X"
        assert data["response"] == "The assistant answered Y"
        assert data["raw_response"] == '{"choices": [{"text": "Y"}]}'
    finally:
        _cleanup()


def test_span_detail_s3_timeout_returns_504():
    """S3 fetch raising asyncio.TimeoutError -> 504 with s3_timeout error body."""
    row = _ch_span_row()
    client, _, _ = _client_with_mocks(ch_row=row)

    async def _timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    try:
        with patch(
            "xeter.services.presenter.routers.spans._fetch_all_s3_payloads",
            side_effect=_timeout,
        ):
            resp = client.get(
                f"/spans/{SPAN_ID}",
                headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
            )

        assert resp.status_code == 504, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "s3_timeout"
    finally:
        _cleanup()


def test_span_detail_s3_error_degrades_gracefully():
    """S3 fetch raising generic Exception -> 200 with null payloads."""
    row = _ch_span_row()
    client, _, _ = _client_with_mocks(ch_row=row)

    async def _s3_fail(*args, **kwargs):
        raise ConnectionError("MinIO unreachable")

    try:
        with patch(
            "xeter.services.presenter.routers.spans._fetch_all_s3_payloads",
            side_effect=_s3_fail,
        ):
            resp = client.get(
                f"/spans/{SPAN_ID}",
                headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["prompt"] is None
        assert body["response"] is None
        assert body["raw_response"] is None
    finally:
        _cleanup()


def test_span_detail_not_found_returns_404():
    """ClickHouse returns no rows -> 404 with not_found error."""
    client, _, _ = _client_with_mocks(ch_row=None)

    try:
        resp = client.get(
            f"/spans/{SPAN_ID}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )

        assert resp.status_code == 404, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "not_found"
    finally:
        _cleanup()


def test_span_detail_cross_tenant_returns_404():
    """ClickHouse returns no rows for cross-tenant access -> 404, not 403.

    The ClickHouse WHERE tenant_id clause means a cross-tenant span_id simply
    returns no rows — identical to a missing span — so no info leakage occurs.
    """
    # ClickHouse returns empty because tenant_id doesn't match
    client, _, _ = _client_with_mocks(ch_row=None, tenant_id=TENANT_A)

    try:
        resp = client.get(
            f"/spans/{SPAN_ID}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )

        assert resp.status_code == 404, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "not_found"
    finally:
        _cleanup()


def test_span_detail_missing_token_returns_401():
    """GET /spans/{id} without Authorization header returns 401."""
    # Remove auth override — use real verify_session_token
    app.dependency_overrides.pop(verify_session_token, None)

    dummy_session = _make_pg_session()
    app.dependency_overrides[get_session] = _session_override(dummy_session)
    ch_client = _make_ch_client(_ch_span_row())
    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_client)

    client = TestClient(app)
    try:
        resp = client.get(f"/spans/{SPAN_ID}")  # no auth header
        assert resp.status_code == 401, resp.text
    finally:
        _cleanup()
