"""
Unit tests for GET /traces and GET /traces/{trace_id} endpoints.

Tests:
  GET /traces:
    1. test_list_traces_empty — no traces returns {traces:[], total:0, limit:50, offset:0}
    2. test_list_traces_returns_items — correct shape and values per trace item
    3. test_list_traces_flag_count — flag_count reflects PostgreSQL flags for that trace
    4. test_list_traces_tenant_isolation — ClickHouse query uses requesting tenant_id
    5. test_list_traces_missing_auth — 401 when Authorization header absent
    6. test_list_traces_pagination_params — limit and offset forwarded to CH query

  GET /traces/{trace_id}:
    7. test_get_trace_detail_basic — correct trace object and spans array
    8. test_get_trace_detail_trace_level_flags — span_id=None flags on trace.flags, not spans
    9. test_get_trace_detail_span_level_flags — span-level flags on correct span
    10. test_get_trace_detail_scores_inline — scores appear on correct span
    11. test_get_trace_detail_not_found — both CH and PG return nothing -> 404
    12. test_get_trace_detail_cross_tenant_404 — different tenant_id -> both CH and PG return nothing -> 404 (stealth)
    13. test_get_trace_detail_no_spans_yet — CH returns empty, PG returns flag -> 200, spans==[]
    14. test_get_trace_detail_missing_auth — 401 when Authorization header absent
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from xeter.services.presenter.deps import get_ch_client, verify_session_token
from xeter.services.presenter.main import app
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.models import Flag

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())
TRACE_ID_1 = "trace-aaa"
TRACE_ID_2 = "trace-bbb"
SPAN_ID_1 = "span-001"
SPAN_ID_2 = "span-002"

_T1 = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 5, 1, 10, 0, 5, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_flag(
    trace_id=TRACE_ID_1,
    span_id=SPAN_ID_1,
    tenant_id=TENANT_A,
    flag_type="wrong_tool",
    score=0.9,
    created_at=None,
) -> MagicMock:
    """Return a mock Flag ORM instance."""
    f = MagicMock(spec=Flag)
    f.trace_id = trace_id
    f.span_id = span_id  # set to None for trace-level flags
    f.tenant_id = tenant_id
    f.flag_type = flag_type
    f.score = score
    f.detail = None
    f.created_at = created_at or _T1
    return f


def _make_session_mock() -> AsyncMock:
    """Return a bare AsyncMock session."""
    return AsyncMock()


def _make_ch_mock(rows=None) -> MagicMock:
    """Return a MagicMock CH client returning the given rows from .query()."""
    ch = MagicMock()
    ch.query.return_value = MagicMock(result_rows=rows or [])
    return ch


def _auth_override(tenant_id: str):
    """Return a dependency override that returns the given tenant_id."""
    def override():
        return tenant_id
    return override


def _session_override(session):
    """Return a dependency override that yields the given session."""
    async def override():
        yield session
    return override


def _ch_client_override(ch_client):
    """Return a dependency override that yields the given CH client."""
    def override():
        yield ch_client
    return override


def _cleanup():
    """Remove all dependency overrides after each test."""
    app.dependency_overrides.pop(get_ch_client, None)
    app.dependency_overrides.pop(verify_session_token, None)
    app.dependency_overrides.pop(get_session, None)


# ClickHouse row tuple for trace list: (trace_id, span_count, start_time, duration_seconds)
_CH_TRACE_ROW = (TRACE_ID_1, 3, _T1, 5.0)

# ClickHouse row tuple for spans (trace detail): (span_id, parent_span_id, tool_name, agent_model, time_begin, time_end)
_CH_SPAN_ROW = (SPAN_ID_1, None, "search_web", "gpt-4o", _T1, _T2)

# ---------------------------------------------------------------------------
# GET /traces tests
# ---------------------------------------------------------------------------


def test_list_traces_empty():
    """GET /traces returns {traces:[], total:0, limit:50, offset:0} when tenant has no traces."""
    # Both CH queries return empty
    ch_mock = MagicMock()
    ch_mock.query.side_effect = [
        MagicMock(result_rows=[]),   # list query
        MagicMock(result_rows=[]),   # count query
    ]
    session = _make_session_mock()

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get("/traces", headers={"Authorization": "Bearer dummy"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["traces"] == []
        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0
    finally:
        _cleanup()


def test_list_traces_returns_items():
    """GET /traces returns correct trace_id, span_count, flag_count, start_time, duration per item."""
    ch_mock = MagicMock()
    ch_mock.query.side_effect = [
        MagicMock(result_rows=[_CH_TRACE_ROW]),   # list query
        MagicMock(result_rows=[[1]]),               # count query
    ]
    session = _make_session_mock()

    # PG flag count query: returns (trace_id, flag_count)
    pg_result = MagicMock()
    pg_result.fetchall.return_value = [(TRACE_ID_1, 2)]
    session.execute = AsyncMock(return_value=pg_result)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get("/traces", headers={"Authorization": "Bearer dummy"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["traces"]) == 1
        trace = data["traces"][0]
        assert trace["trace_id"] == TRACE_ID_1
        assert trace["span_count"] == 3
        assert trace["flag_count"] == 2
        assert trace["duration"] == 5.0
        assert trace["start_time"] is not None
        assert data["total"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0
    finally:
        _cleanup()


def test_list_traces_flag_count():
    """flag_count in the trace list item reflects PostgreSQL flags for that trace."""
    ch_mock = MagicMock()
    ch_mock.query.side_effect = [
        MagicMock(result_rows=[_CH_TRACE_ROW]),
        MagicMock(result_rows=[[1]]),
    ]
    session = _make_session_mock()

    # PG returns 5 flags for TRACE_ID_1
    pg_result = MagicMock()
    pg_result.fetchall.return_value = [(TRACE_ID_1, 5)]
    session.execute = AsyncMock(return_value=pg_result)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get("/traces", headers={"Authorization": "Bearer dummy"})
        assert response.status_code == 200, response.text
        trace = response.json()["traces"][0]
        assert trace["flag_count"] == 5
    finally:
        _cleanup()


def test_list_traces_tenant_isolation():
    """ClickHouse list query is called with the requesting tenant's tenant_id."""
    ch_mock = MagicMock()
    ch_mock.query.side_effect = [
        MagicMock(result_rows=[_CH_TRACE_ROW]),
        MagicMock(result_rows=[[1]]),
    ]
    session = _make_session_mock()
    pg_result = MagicMock()
    pg_result.fetchall.return_value = [(TRACE_ID_1, 0)]
    session.execute = AsyncMock(return_value=pg_result)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get("/traces", headers={"Authorization": "Bearer dummy"})
        assert response.status_code == 200, response.text

        # Both CH queries must have been called with TENANT_A's tenant_id in params
        assert ch_mock.query.call_count == 2
        for call in ch_mock.query.call_args_list:
            params = call[0][1]  # second positional arg is the params dict
            assert params.get("tenant_id") == TENANT_A
    finally:
        _cleanup()


def test_list_traces_missing_auth():
    """GET /traces returns 401 when Authorization header is missing."""
    # Remove verify_session_token override — use the real dependency
    app.dependency_overrides.pop(verify_session_token, None)

    # Keep a mock get_session to avoid a real DB connection attempt
    session = _make_session_mock()
    app.dependency_overrides[get_session] = _session_override(session)
    ch_mock = _make_ch_mock(rows=[])
    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)

    client = TestClient(app)
    try:
        response = client.get("/traces")  # no auth header
        assert response.status_code == 401, response.text
    finally:
        _cleanup()


def test_list_traces_pagination_params():
    """limit and offset query params are forwarded to the ClickHouse query."""
    ch_mock = MagicMock()
    ch_mock.query.side_effect = [
        MagicMock(result_rows=[_CH_TRACE_ROW]),
        MagicMock(result_rows=[[10]]),
    ]
    session = _make_session_mock()
    pg_result = MagicMock()
    pg_result.fetchall.return_value = [(TRACE_ID_1, 0)]
    session.execute = AsyncMock(return_value=pg_result)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            "/traces?limit=10&offset=20",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Response reflects the requested pagination params
        assert data["limit"] == 10
        assert data["offset"] == 20

        # The list query (first call) should have limit=10, offset=20 in its params
        first_call_params = ch_mock.query.call_args_list[0][0][1]
        assert first_call_params.get("limit") == 10
        assert first_call_params.get("offset") == 20
    finally:
        _cleanup()


# ---------------------------------------------------------------------------
# GET /traces/{trace_id} tests
# ---------------------------------------------------------------------------


def test_get_trace_detail_basic():
    """GET /traces/{trace_id} returns correct trace object and spans array."""
    ch_mock = _make_ch_mock(rows=[_CH_SPAN_ROW])
    session = _make_session_mock()

    # PG call 1: all flags (no flags for this test)
    flags_result = MagicMock()
    flags_result.scalars.return_value.all.return_value = []
    # PG call 2: span_scores (no scores for this test)
    scores_result = MagicMock()
    scores_result.fetchall.return_value = []
    session.execute = AsyncMock(side_effect=[flags_result, scores_result])

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        # trace object
        trace = data["trace"]
        assert trace["trace_id"] == TRACE_ID_1
        assert trace["duration"] == pytest.approx(5.0, abs=0.01)
        assert trace["start_time"] is not None
        assert trace["flags"] == []

        # spans array
        assert len(data["spans"]) == 1
        span = data["spans"][0]
        assert span["span_id"] == SPAN_ID_1
        assert span["tool_name"] == "search_web"
        assert span["model"] == "gpt-4o"
        assert span["parent_span_id"] is None
        assert span["input_tokens"] is None
        assert span["output_tokens"] is None
        assert span["flags"] == []
        assert span["scores"] == []
    finally:
        _cleanup()


def test_get_trace_detail_trace_level_flags():
    """Flags with span_id=None appear on trace.flags, NOT on any span."""
    ch_mock = _make_ch_mock(rows=[_CH_SPAN_ROW])
    session = _make_session_mock()

    # A trace-level flag (span_id=None)
    trace_flag = _make_flag(trace_id=TRACE_ID_1, span_id=None, flag_type="trace_anomaly", score=0.85)

    flags_result = MagicMock()
    flags_result.scalars.return_value.all.return_value = [trace_flag]
    scores_result = MagicMock()
    scores_result.fetchall.return_value = []
    session.execute = AsyncMock(side_effect=[flags_result, scores_result])

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        # Trace-level flag must appear on trace.flags
        assert len(data["trace"]["flags"]) == 1
        assert data["trace"]["flags"][0]["flag_type"] == "trace_anomaly"
        assert abs(data["trace"]["flags"][0]["score"] - 0.85) < 0.001

        # No flags on the span
        assert data["spans"][0]["flags"] == []
    finally:
        _cleanup()


def test_get_trace_detail_span_level_flags():
    """Span-level flags (span_id not None) appear inline on the correct span."""
    ch_mock = _make_ch_mock(rows=[_CH_SPAN_ROW])
    session = _make_session_mock()

    # A span-level flag for SPAN_ID_1
    span_flag = _make_flag(trace_id=TRACE_ID_1, span_id=SPAN_ID_1, flag_type="wrong_tool", score=0.9)

    flags_result = MagicMock()
    flags_result.scalars.return_value.all.return_value = [span_flag]
    scores_result = MagicMock()
    scores_result.fetchall.return_value = []
    session.execute = AsyncMock(side_effect=[flags_result, scores_result])

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        # Trace-level flags list must be empty
        assert data["trace"]["flags"] == []

        # Span-level flag must appear on the correct span
        span = data["spans"][0]
        assert span["span_id"] == SPAN_ID_1
        assert len(span["flags"]) == 1
        assert span["flags"][0]["flag_type"] == "wrong_tool"
        assert abs(span["flags"][0]["score"] - 0.9) < 0.001
    finally:
        _cleanup()


def test_get_trace_detail_scores_inline():
    """Scores appear inline on the correct span object."""
    ch_mock = _make_ch_mock(rows=[_CH_SPAN_ROW])
    session = _make_session_mock()

    flags_result = MagicMock()
    flags_result.scalars.return_value.all.return_value = []
    scores_result = MagicMock()
    scores_result.fetchall.return_value = [
        (SPAN_ID_1, "tc_analyzer", "cosine", 0.95),
    ]
    session.execute = AsyncMock(side_effect=[flags_result, scores_result])

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        span = data["spans"][0]
        assert span["span_id"] == SPAN_ID_1
        assert len(span["scores"]) == 1
        score = span["scores"][0]
        assert score["analyzer_name"] == "tc_analyzer"
        assert score["metric_name"] == "cosine"
        assert abs(score["score"] - 0.95) < 0.001
    finally:
        _cleanup()


def test_get_trace_detail_not_found():
    """Both CH and PG return nothing -> 404 with error=not_found."""
    # CH returns nothing
    ch_mock = _make_ch_mock(rows=[])
    session = _make_session_mock()

    # PG existence probe returns None (no flag found)
    pg_existence = MagicMock()
    pg_existence.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=pg_existence)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["error"] == "not_found"
    finally:
        _cleanup()


def test_get_trace_detail_cross_tenant_404():
    """Cross-tenant access returns stealth 404 (TENANT_B requesting TRACE_ID_1 owned by TENANT_A)."""
    # Override auth to TENANT_B
    # CH returns nothing — TENANT_B has no spans for TRACE_ID_1
    ch_mock = _make_ch_mock(rows=[])
    session = _make_session_mock()

    # PG existence probe returns None — TENANT_B has no flags for TRACE_ID_1
    pg_existence = MagicMock()
    pg_existence.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=pg_existence)

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_B)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["error"] == "not_found"
    finally:
        _cleanup()


def test_get_trace_detail_no_spans_yet():
    """CH returns empty rows but PG has a flag -> 200 with spans=[] (no-spans-yet case)."""
    # CH returns nothing — spans not yet in ClickHouse
    ch_mock = _make_ch_mock(rows=[])
    session = _make_session_mock()

    # PG existence probe: returns a trace-level flag (span_id=None)
    existing_flag = _make_flag(trace_id=TRACE_ID_1, span_id=None, created_at=_T1)

    pg_existence = MagicMock()
    pg_existence.scalars.return_value.first.return_value = existing_flag

    # PG second query: all trace-level flags (span_id IS NULL)
    pg_trace_flags = MagicMock()
    pg_trace_flags.scalars.return_value.all.return_value = [existing_flag]

    session.execute = AsyncMock(side_effect=[pg_existence, pg_trace_flags])

    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)
    app.dependency_overrides[verify_session_token] = _auth_override(TENANT_A)
    app.dependency_overrides[get_session] = _session_override(session)

    client = TestClient(app)
    try:
        response = client.get(
            f"/traces/{TRACE_ID_1}",
            headers={"Authorization": "Bearer dummy"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["spans"] == []
        assert data["trace"]["trace_id"] == TRACE_ID_1
        assert data["trace"]["duration"] == 0.0
        assert data["trace"]["start_time"] is not None
    finally:
        _cleanup()


def test_get_trace_detail_missing_auth():
    """GET /traces/{trace_id} returns 401 when Authorization header is missing."""
    # Remove auth override — use the real verify_session_token
    app.dependency_overrides.pop(verify_session_token, None)

    # Keep mocked session and CH to avoid real DB connection attempt
    session = _make_session_mock()
    app.dependency_overrides[get_session] = _session_override(session)
    ch_mock = _make_ch_mock(rows=[])
    app.dependency_overrides[get_ch_client] = _ch_client_override(ch_mock)

    client = TestClient(app)
    try:
        response = client.get(f"/traces/{TRACE_ID_1}")  # no auth header
        assert response.status_code == 401, response.text
    finally:
        _cleanup()
