# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Unit tests for GET /spans endpoint.

Tests cover:
  - Returns spans with inline flag summaries
  - FlagSummary has correct score values
  - Missing Authorization header returns 401
  - Tenant isolation (ClickHouse query uses correct tenant_id)
  - Cursor pagination (next_cursor present when result count == limit)
  - Status derivation: "flagged" / "clean" / "pending"

Mocking strategy:
  - app.dependency_overrides[get_session] injects an AsyncMock session
  - app.dependency_overrides[get_ch_client] injects a MagicMock CH client per-request
  - verify_session_token dependency is overridden to return the test tenant_id
    (avoids needing a real JWT for most tests)
"""

import base64
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
# Fixtures / helpers
# ---------------------------------------------------------------------------

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())

_NOW = datetime(2026, 3, 30, 10, 0, 0, tzinfo=timezone.utc)
_THEN = datetime(2026, 3, 30, 9, 59, 55, tzinfo=timezone.utc)  # 5 s earlier


def _ch_row(span_id="span-1", trace_id="trace-1", agent_name="agent-a",
            agent_model="gpt-4", tool_name="search_web",
            time_begin=None, time_end=None):
    """Return a ClickHouse-style result row tuple."""
    return (
        span_id,
        trace_id,
        agent_name,
        agent_model,
        tool_name,
        time_begin or _THEN,
        time_end or _NOW,
    )


def _make_flag(span_id: str, tenant_id: str = TENANT_A,
               flag_type: str = "wrong_tool", score: float = 0.8) -> Flag:
    """Return a mock Flag ORM instance."""
    flag = MagicMock(spec=Flag)
    flag.flag_id = uuid.uuid4()
    flag.tenant_id = uuid.UUID(tenant_id)
    flag.span_id = span_id
    flag.trace_id = "trace-1"
    flag.flag_type = flag_type
    flag.score = score
    flag.detail = None
    return flag


def _make_ch_client(rows: list) -> MagicMock:
    """Return a MagicMock ClickHouse client that returns the given rows."""
    client = MagicMock()
    result = MagicMock()
    result.result_rows = rows
    client.query.return_value = result
    return client


def _make_pg_session(flags: list[Flag] | None = None,
                     scored_span_ids: list[str] | None = None) -> AsyncMock:
    """Return an AsyncMock session.

    Simulates:
      - flags query (scalars().all()) returning the given list of Flag objects
      - span_scores query (fetchall()) returning rows for scored_span_ids
    """
    session = AsyncMock(spec=AsyncSession)

    # First call to session.execute -> flags query
    flags_mock = MagicMock()
    flags_scalars = MagicMock()
    flags_scalars.all.return_value = flags or []
    flags_mock.scalars.return_value = flags_scalars

    # Second call to session.execute -> span_scores query
    scores_mock = MagicMock()
    score_rows = [(sid,) for sid in (scored_span_ids or [])]
    scores_mock.fetchall.return_value = score_rows

    session.execute = AsyncMock(side_effect=[flags_mock, scores_mock])
    return session


def _auth_override(tenant_id: str):
    """Return a FastAPI dependency override that returns the given tenant_id."""
    def override():
        return tenant_id
    return override


def _session_override(session):
    """Return a FastAPI dependency override that yields the given session."""
    async def override():
        yield session
    return override


def _ch_client_override(ch_client):
    """Return a FastAPI dependency override that yields the given CH client."""
    def override():
        yield ch_client
    return override


def _client_with_mocks(ch_rows, flags=None, scored_span_ids=None,
                       tenant_id=TENANT_A):
    """Create a TestClient with mocked CH + PG dependencies."""
    ch_client = _make_ch_client(ch_rows)
    pg_session = _make_pg_session(flags=flags, scored_span_ids=scored_span_ids)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_client)
    app.dependency_overrides[verify_session_token] = _auth_override(tenant_id)
    app.dependency_overrides[get_session] = _session_override(pg_session)

    return TestClient(app), ch_client, pg_session


def _cleanup():
    """Remove dependency overrides after each test."""
    app.dependency_overrides.pop(get_ch_client, None)
    app.dependency_overrides.pop(verify_session_token, None)
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_span_list_returns_spans_with_flags():
    """GET /spans returns 2 items; first has a flag summary, second has empty flags."""
    span1 = _ch_row(span_id="span-1")
    span2 = _ch_row(span_id="span-2")
    flag1 = _make_flag(span_id="span-1", flag_type="wrong_tool", score=0.75)

    client, _, _ = _client_with_mocks([span1, span2], flags=[flag1])
    try:
        response = client.get(
            "/spans",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["spans"]) == 2

        first_span = data["spans"][0]
        assert first_span["span_id"] == "span-1"
        assert len(first_span["flags"]) == 1
        assert first_span["flags"][0]["flag_type"] == "wrong_tool"

        second_span = data["spans"][1]
        assert second_span["span_id"] == "span-2"
        assert second_span["flags"] == []
    finally:
        _cleanup()


def test_span_list_includes_flag_scores():
    """FlagSummary in the response carries the correct score value."""
    span1 = _ch_row(span_id="span-1")
    flag1 = _make_flag(span_id="span-1", flag_type="wrong_args", score=0.92)

    client, _, _ = _client_with_mocks([span1], flags=[flag1])
    try:
        response = client.get(
            "/spans",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        flags = response.json()["spans"][0]["flags"]
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "wrong_args"
        assert abs(flags[0]["score"] - 0.92) < 0.001
    finally:
        _cleanup()


def test_span_list_missing_token_returns_401():
    """GET /spans without Authorization header returns 401.

    Uses the real verify_session_token dependency to confirm the 401 is
    returned when Authorization is absent. get_session is still mocked to
    avoid a real DATABASE_URL being required (FastAPI resolves dependencies
    concurrently; verify_session_token raising 401 short-circuits the handler
    but a mock session prevents a KeyError during dependency resolution).
    """
    # Remove verify_session_token override — use the real dependency
    app.dependency_overrides.pop(verify_session_token, None)

    # Keep a mock get_session to avoid real DB connection attempt
    dummy_session = _make_pg_session()
    app.dependency_overrides[get_session] = _session_override(dummy_session)

    client = TestClient(app)
    try:
        response = client.get("/spans")  # no auth header
        assert response.status_code == 401, response.text
    finally:
        _cleanup()


def test_span_list_cross_tenant_isolation():
    """ClickHouse query is called with the authenticated tenant's tenant_id."""
    span1 = _ch_row(span_id="span-a1", trace_id="trace-a")

    client, ch_client, _ = _client_with_mocks([span1], tenant_id=TENANT_A)
    try:
        response = client.get(
            "/spans",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Only span-a1 is returned
        assert len(data["spans"]) == 1
        assert data["spans"][0]["span_id"] == "span-a1"

        # Verify ClickHouse was queried with TENANT_A's tenant_id
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]  # positional arg: params dict
        assert query_params["tenant_id"] == TENANT_A
    finally:
        _cleanup()


def test_span_list_cursor_pagination():
    """When limit items are returned, next_cursor is set and decodes to last time_begin."""
    limit = 2
    rows = [
        _ch_row(span_id=f"span-{i}",
                time_begin=datetime(2026, 3, 30, 10, 0, i, tzinfo=timezone.utc),
                time_end=datetime(2026, 3, 30, 10, 0, i + 1, tzinfo=timezone.utc))
        for i in range(limit)
    ]

    client, _, _ = _client_with_mocks(rows)
    try:
        response = client.get(
            f"/spans?limit={limit}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["spans"]) == limit
        assert data["next_cursor"] is not None

        # Decode cursor and verify it matches last span's time_begin
        cursor_decoded = base64.urlsafe_b64decode(data["next_cursor"]).decode()
        last_time_begin = data["spans"][-1]["time_begin"]
        assert cursor_decoded == last_time_begin
    finally:
        _cleanup()


def test_span_list_status_derivation():
    """Span status is 'flagged', 'clean', or 'pending' based on flags/scores."""
    span_flagged = _ch_row(span_id="span-flagged")
    span_clean = _ch_row(span_id="span-clean")
    span_pending = _ch_row(span_id="span-pending")

    flag = _make_flag(span_id="span-flagged", flag_type="wrong_tool", score=0.7)

    client, _, _ = _client_with_mocks(
        [span_flagged, span_clean, span_pending],
        flags=[flag],
        scored_span_ids=["span-clean"],
    )
    try:
        response = client.get(
            "/spans",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        spans_by_id = {s["span_id"]: s for s in response.json()["spans"]}

        assert spans_by_id["span-flagged"]["status"] == "flagged"
        assert spans_by_id["span-clean"]["status"] == "clean"
        assert spans_by_id["span-pending"]["status"] == "pending"
    finally:
        _cleanup()
