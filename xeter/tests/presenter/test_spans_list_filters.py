"""
Unit tests for GET /spans filter query parameters.

Tests cover:
  - flag_type filter: returns only spans with matching flag rows
  - agent_name filter: returns only spans with matching agent_name
  - from_time filter: returns only spans with time_begin >= from_time
  - to_time filter: returns only spans with time_begin <= to_time
  - Combined time range filter (from_time + to_time)
  - Combined flag_type + agent_name filters (AND logic)
  - No filters: backward-compatible, returns all spans

Mocking strategy:
  - app.state.ch_client is patched with a MagicMock matching the filter params
  - app.dependency_overrides[get_session] injects an AsyncMock session
  - verify_session_token dependency is overridden to return the test tenant_id
"""

import urllib.parse
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import create_session_token, verify_session_token
from xeter.services.presenter.main import app
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.models import Flag

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

TENANT_A = str(uuid.uuid4())

_T1 = datetime(2026, 3, 30, 10, 0, 0, tzinfo=timezone.utc)   # earliest
_T2 = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)   # middle
_T3 = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)   # latest
_T4 = datetime(2026, 3, 30, 12, 0, 1, tzinfo=timezone.utc)   # end of span


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
        time_begin or _T1,
        time_end or _T4,
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


def _make_pg_session(flags=None, scored_span_ids=None):
    """Return an AsyncMock session.

    Simulates:
      - flags query (scalars().all()) returning the given list of Flag objects
      - span_scores query (fetchall()) returning rows for scored_span_ids
    """
    session = AsyncMock(spec=AsyncSession)

    flags_mock = MagicMock()
    flags_scalars = MagicMock()
    flags_scalars.all.return_value = flags or []
    flags_mock.scalars.return_value = flags_scalars

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


def _client_with_mocks(ch_rows, flags=None, scored_span_ids=None,
                       tenant_id=TENANT_A):
    """Create a TestClient with mocked CH + PG dependencies."""
    ch_client = _make_ch_client(ch_rows)
    pg_session = _make_pg_session(flags=flags, scored_span_ids=scored_span_ids)

    app.state.ch_client = ch_client
    app.dependency_overrides[verify_session_token] = _auth_override(tenant_id)
    app.dependency_overrides[get_session] = _session_override(pg_session)

    return TestClient(app), ch_client, pg_session


def _cleanup():
    """Remove dependency overrides after each test."""
    app.dependency_overrides.pop(verify_session_token, None)
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_filter_flag_type_returns_only_matching_spans():
    """GET /spans?flag_type=wrong_tool returns only spans that have a wrong_tool flag row.

    Setup: 3 spans, only span-1 has a wrong_tool flag.
    Expected: response contains only span-1.
    """
    span1 = _ch_row(span_id="span-1", agent_name="agent-a")
    span2 = _ch_row(span_id="span-2", agent_name="agent-b")
    span3 = _ch_row(span_id="span-3", agent_name="agent-c")

    flag1 = _make_flag(span_id="span-1", flag_type="wrong_tool", score=0.9)

    client, _, _ = _client_with_mocks([span1, span2, span3], flags=[flag1])
    try:
        response = client.get(
            "/spans?flag_type=wrong_tool",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        span_ids = [s["span_id"] for s in data["spans"]]
        assert span_ids == ["span-1"], f"Expected only span-1, got {span_ids}"
    finally:
        _cleanup()


def test_filter_agent_name():
    """GET /spans?agent_name=agent-a returns only spans with agent_name=agent-a.

    Setup: 2 spans — agent-a and agent-b.
    Expected: ClickHouse receives the agent_name param; response contains only agent-a span.
    """
    span_a = _ch_row(span_id="span-a", agent_name="agent-a")
    span_b = _ch_row(span_id="span-b", agent_name="agent-b")

    # CH client returns only agent-a span (filter applied in ClickHouse)
    client, ch_client, _ = _client_with_mocks([span_a])
    try:
        response = client.get(
            "/spans?agent_name=agent-a",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["spans"]) == 1
        assert data["spans"][0]["span_id"] == "span-a"
        assert data["spans"][0]["agent_name"] == "agent-a"

        # Verify ClickHouse was queried with agent_name param
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert query_params.get("agent_name") == "agent-a"
    finally:
        _cleanup()


def test_filter_from_time():
    """GET /spans?from_time=ISO returns only spans with time_begin >= from_time.

    The from_time param must be forwarded to the ClickHouse WHERE clause.
    """
    from_time_iso = _T2.isoformat()
    from_time_encoded = urllib.parse.quote(from_time_iso)

    # CH client returns only spans after from_time (filter applied in ClickHouse)
    span2 = _ch_row(span_id="span-2", time_begin=_T2)
    span3 = _ch_row(span_id="span-3", time_begin=_T3)

    client, ch_client, _ = _client_with_mocks([span2, span3])
    try:
        response = client.get(
            f"/spans?from_time={from_time_encoded}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        span_ids = [s["span_id"] for s in data["spans"]]
        assert "span-2" in span_ids
        assert "span-3" in span_ids

        # Verify ClickHouse received the from_time param (decoded ISO string)
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert query_params.get("from_time") == from_time_iso
    finally:
        _cleanup()


def test_filter_to_time():
    """GET /spans?to_time=ISO returns only spans with time_begin <= to_time.

    The to_time param must be forwarded to the ClickHouse WHERE clause.
    """
    to_time_iso = _T2.isoformat()
    to_time_encoded = urllib.parse.quote(to_time_iso)

    # CH client returns only spans before to_time (filter applied in ClickHouse)
    span1 = _ch_row(span_id="span-1", time_begin=_T1)
    span2 = _ch_row(span_id="span-2", time_begin=_T2)

    client, ch_client, _ = _client_with_mocks([span1, span2])
    try:
        response = client.get(
            f"/spans?to_time={to_time_encoded}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        span_ids = [s["span_id"] for s in data["spans"]]
        assert "span-1" in span_ids
        assert "span-2" in span_ids

        # Verify ClickHouse received the to_time param (decoded ISO string)
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert query_params.get("to_time") == to_time_iso
    finally:
        _cleanup()


def test_filter_time_range():
    """GET /spans?from_time=X&to_time=Y returns only spans within the time window.

    Both from_time and to_time params must be forwarded to ClickHouse.
    """
    from_time_iso = _T1.isoformat()
    to_time_iso = _T2.isoformat()
    from_time_encoded = urllib.parse.quote(from_time_iso)
    to_time_encoded = urllib.parse.quote(to_time_iso)

    span1 = _ch_row(span_id="span-1", time_begin=_T1)
    span2 = _ch_row(span_id="span-2", time_begin=_T2)

    client, ch_client, _ = _client_with_mocks([span1, span2])
    try:
        response = client.get(
            f"/spans?from_time={from_time_encoded}&to_time={to_time_encoded}",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["spans"]) == 2

        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert query_params.get("from_time") == from_time_iso
        assert query_params.get("to_time") == to_time_iso
    finally:
        _cleanup()


def test_combined_filters():
    """GET /spans?flag_type=wrong_tool&agent_name=agent-a returns intersection of both filters.

    CH returns only agent-a spans (agent_name filter applied in ClickHouse).
    PostgreSQL flags query returns only wrong_tool flags.
    Result must contain only spans that satisfy both filters.
    """
    # agent-a spans, one flagged and one not
    span_a1 = _ch_row(span_id="span-a1", agent_name="agent-a")
    span_a2 = _ch_row(span_id="span-a2", agent_name="agent-a")

    flag_a1 = _make_flag(span_id="span-a1", flag_type="wrong_tool", score=0.85)
    # span-a2 has no wrong_tool flag

    client, ch_client, _ = _client_with_mocks(
        [span_a1, span_a2],
        flags=[flag_a1],
    )
    try:
        response = client.get(
            "/spans?flag_type=wrong_tool&agent_name=agent-a",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        span_ids = [s["span_id"] for s in data["spans"]]
        # Only span-a1 satisfies both filters
        assert span_ids == ["span-a1"], f"Expected only span-a1, got {span_ids}"

        # Verify ClickHouse received agent_name
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert query_params.get("agent_name") == "agent-a"
    finally:
        _cleanup()


def test_no_filters_returns_all():
    """GET /spans with no filter params returns all spans unchanged (backward-compatible)."""
    span1 = _ch_row(span_id="span-1", agent_name="agent-a")
    span2 = _ch_row(span_id="span-2", agent_name="agent-b")
    span3 = _ch_row(span_id="span-3", agent_name="agent-c")

    client, ch_client, _ = _client_with_mocks([span1, span2, span3])
    try:
        response = client.get(
            "/spans",
            headers={"Authorization": f"Bearer {create_session_token(TENANT_A)}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        span_ids = [s["span_id"] for s in data["spans"]]
        assert set(span_ids) == {"span-1", "span-2", "span-3"}

        # Verify no filter params were passed to ClickHouse
        call_args = ch_client.query.call_args
        query_params = call_args[0][1]
        assert "agent_name" not in query_params
        assert "from_time" not in query_params
        assert "to_time" not in query_params
    finally:
        _cleanup()
