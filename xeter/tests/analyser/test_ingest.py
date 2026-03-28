"""
Integration tests for POST /v1/spans and GET /healthz.

All external dependencies (PostgreSQL, ClickHouse, Redis, S3/MinIO) are
mocked. The FastAPI TestClient is used to exercise the full request-response
cycle including middleware, dependency injection, and Pydantic validation.

Lifespan mocking strategy:
  The app lifespan calls get_clickhouse_client(), get_redis_client(), and
  get_s3_client() on startup. For tests, we patch these factory functions at
  the module level AND override the FastAPI endpoint dependencies so that both
  the startup sequence and the request handlers use mocked objects throughout.

Test coverage:
  1.  GET /healthz returns 200 {"status": "ok"}
  2.  POST /v1/spans with valid API key returns 200 {"accepted": true}
  3.  POST /v1/spans with invalid API key returns 401
  4.  POST /v1/spans when S3 raises returns 500
  5.  span_id is LPUSH'd to Redis analysis_queue after acceptance
  6.  S3 is called before batcher.add (ordering guarantee)
  7.  50 spans each call batcher.add once (never direct ClickHouse inserts)
  8.  Row passed to batcher.add has 17 elements in SPAN_COLUMNS order
  9.  "xeter.schema.version" alias field is accepted (no 422)
"""

import pytest
from contextlib import contextmanager
from fastapi import HTTPException
from starlette.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from xeter.services.analyser.main import app
from xeter.services.analyser.ingest import get_batcher_dep, get_redis_dep, get_s3_client_dep
from xeter.services.analyser.auth import verify_api_key_header
from xeter.services.analyser.batch import SPAN_COLUMNS

VALID_TENANT_ID = "tenant-test-uuid"

SAMPLE_SPAN = {
    "span_id": "span-001",
    "trace_id": "trace-001",
    "agent_name": "test-agent",
    "agent_model": "gpt-4",
    "time_begin": "2026-03-28T10:00:00Z",
    "time_end": "2026-03-28T10:00:01Z",
    "xeter.schema.version": "1.0",
    "prompt": "Call the search tool",
    "response": "Search result",
    "raw_response": "{}",
    "available_tools_ref": '["search_tool"]',
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_batcher():
    batcher = MagicMock()
    batcher.add = AsyncMock()
    batcher.start = AsyncMock()
    batcher.stop = AsyncMock()
    return batcher


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.lpush = AsyncMock()
    redis.aclose = AsyncMock()
    return redis


@pytest.fixture
def mock_s3():
    s3 = MagicMock()
    s3.upload_span_payloads = AsyncMock(
        return_value={
            "prompt_ref": "t/2026-03/span-001/prompt.json",
            "response_ref": "t/2026-03/span-001/response.json",
            "raw_response_ref": "t/2026-03/span-001/raw_response.json",
            "available_tools_ref": "t/2026-03/span-001/available_tools.json",
        }
    )
    return s3


@contextmanager
def _make_client(mock_batcher, mock_redis, mock_s3, auth_override=None):
    """Context manager that creates a TestClient with all external deps mocked.

    Patches:
    - get_clickhouse_client() in batch.py -> returns MagicMock (lifespan uses it)
    - get_redis_client() in main.py -> returns mock_redis
    - get_s3_client() in main.py -> returns mock_s3
    - SpanBatcher constructor -> returns mock_batcher

    FastAPI dependency overrides:
    - verify_api_key_header -> auth_override (default: returns VALID_TENANT_ID)
    - get_batcher_dep -> mock_batcher
    - get_redis_dep -> mock_redis
    - get_s3_client_dep -> mock_s3
    """
    if auth_override is None:
        auth_override = lambda: VALID_TENANT_ID

    app.dependency_overrides[verify_api_key_header] = auth_override
    app.dependency_overrides[get_batcher_dep] = lambda: mock_batcher
    app.dependency_overrides[get_redis_dep] = lambda: mock_redis
    app.dependency_overrides[get_s3_client_dep] = lambda: mock_s3

    with (
        patch("xeter.services.analyser.main.get_clickhouse_client", return_value=MagicMock()),
        patch("xeter.services.analyser.main.SpanBatcher", return_value=mock_batcher),
        patch("xeter.services.analyser.main.get_redis_client", return_value=mock_redis),
        patch("xeter.services.analyser.main.get_s3_client", return_value=mock_s3),
        TestClient(app) as c,
    ):
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client(mock_batcher, mock_redis, mock_s3):
    """TestClient with all external deps overridden for standard tests."""
    with _make_client(mock_batcher, mock_redis, mock_s3) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_healthz(client):
    """GET /healthz returns 200 and {status: ok}."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_span_accepted(client):
    """POST /v1/spans with valid span returns 200 and {accepted: true}."""
    response = client.post("/v1/spans", json=SAMPLE_SPAN)
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_invalid_api_key_returns_401(mock_batcher, mock_redis, mock_s3):
    """POST /v1/spans with an invalid API key returns 401."""
    def raise_401():
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    with _make_client(mock_batcher, mock_redis, mock_s3, auth_override=raise_401) as c:
        response = c.post("/v1/spans", json=SAMPLE_SPAN)
    assert response.status_code == 401


def test_s3_failure_returns_500(mock_batcher, mock_redis):
    """POST /v1/spans when S3 raises returns 500 and span is not accepted."""
    s3_failing = MagicMock()
    s3_failing.upload_span_payloads = AsyncMock(side_effect=Exception("S3 down"))

    with _make_client(mock_batcher, mock_redis, s3_failing) as c:
        response = c.post("/v1/spans", json=SAMPLE_SPAN)

    assert response.status_code == 500
    # Batcher must NOT have been called — span was not accepted
    mock_batcher.add.assert_not_called()


def test_span_id_enqueued_in_redis(client, mock_redis):
    """After a valid POST /v1/spans, span_id is LPUSH'd to Redis analysis_queue."""
    response = client.post("/v1/spans", json=SAMPLE_SPAN)
    assert response.status_code == 200

    assert mock_redis.lpush.called, "Expected redis.lpush to be called"
    # lpush(key, value) — check the value argument
    call_args = mock_redis.lpush.call_args
    assert call_args[0][1] == "span-001", (
        f"Expected span_id 'span-001' in lpush, got: {call_args}"
    )


def test_s3_called_before_batcher(mock_batcher, mock_redis, mock_s3):
    """S3 upload must be called before batcher.add (ordering guarantee).

    Uses a shared parent mock to record call order across both mocks.
    """
    parent = MagicMock()
    parent.upload_span_payloads = AsyncMock(
        return_value={
            "prompt_ref": "t/2026-03/span-001/prompt.json",
            "response_ref": "t/2026-03/span-001/response.json",
            "raw_response_ref": "t/2026-03/span-001/raw_response.json",
            "available_tools_ref": "t/2026-03/span-001/available_tools.json",
        }
    )
    parent.add = AsyncMock()

    # Wire both to the parent so mock_calls is shared
    s3_tracked = MagicMock()
    s3_tracked.upload_span_payloads = parent.upload_span_payloads
    batcher_tracked = MagicMock()
    batcher_tracked.add = parent.add
    # start/stop must be AsyncMock so lifespan can await them
    batcher_tracked.start = AsyncMock()
    batcher_tracked.stop = AsyncMock()

    app.dependency_overrides[verify_api_key_header] = lambda: VALID_TENANT_ID
    app.dependency_overrides[get_batcher_dep] = lambda: batcher_tracked
    app.dependency_overrides[get_redis_dep] = lambda: mock_redis
    app.dependency_overrides[get_s3_client_dep] = lambda: s3_tracked

    with (
        patch("xeter.services.analyser.main.get_clickhouse_client", return_value=MagicMock()),
        patch("xeter.services.analyser.main.SpanBatcher", return_value=batcher_tracked),
        patch("xeter.services.analyser.main.get_redis_client", return_value=mock_redis),
        patch("xeter.services.analyser.main.get_s3_client", return_value=s3_tracked),
        TestClient(app) as c,
    ):
        response = c.post("/v1/spans", json=SAMPLE_SPAN)

    app.dependency_overrides.clear()

    assert response.status_code == 200

    calls = parent.mock_calls
    call_names = [c[0] for c in calls]
    assert "upload_span_payloads" in call_names, "upload_span_payloads was not called"
    assert "add" in call_names, "batcher.add was not called"
    s3_index = call_names.index("upload_span_payloads")
    add_index = call_names.index("add")
    assert s3_index < add_index, (
        f"S3 must be called before batcher.add but got order: {call_names}"
    )


def test_batching_uses_batch_not_individual_inserts(client, mock_batcher):
    """50 spans each call batcher.add once — never 50 direct ClickHouse inserts.

    This test verifies the batching contract: every span goes through
    batcher.add(). The actual ClickHouse flush frequency depends on
    XETER_BATCH_SIZE and XETER_FLUSH_INTERVAL, but the ADD path is always
    batched, never individual insert() calls.
    """
    for i in range(50):
        span = dict(SAMPLE_SPAN)
        span["span_id"] = f"span-{i:03d}"
        response = client.post("/v1/spans", json=span)
        assert response.status_code == 200, f"Span {i} failed: {response.json()}"

    assert mock_batcher.add.call_count == 50, (
        f"Expected 50 batcher.add calls, got {mock_batcher.add.call_count}"
    )


def test_all_required_span_fields_present_in_batch_row(client, mock_batcher):
    """Row passed to batcher.add has 17 elements in SPAN_COLUMNS order.

    Verifies:
    - Row length matches SPAN_COLUMNS (17 columns)
    - row[0] == span_id
    - row[3] == tenant_id (injected by auth dependency)
    """
    response = client.post("/v1/spans", json=SAMPLE_SPAN)
    assert response.status_code == 200

    mock_batcher.add.assert_called_once()
    row = mock_batcher.add.call_args[0][0]

    assert len(row) == len(SPAN_COLUMNS), (
        f"Row length {len(row)} != SPAN_COLUMNS length {len(SPAN_COLUMNS)}"
    )
    assert row[0] == "span-001", f"row[0] (span_id) expected 'span-001', got {row[0]!r}"
    assert row[3] == VALID_TENANT_ID, (
        f"row[3] (tenant_id) expected {VALID_TENANT_ID!r}, got {row[3]!r}"
    )


def test_schema_version_field_accepted(client):
    """xeter.schema.version alias field is parsed correctly — no 422 validation error."""
    span_with_version = dict(SAMPLE_SPAN)
    span_with_version["xeter.schema.version"] = "1.0"

    response = client.post("/v1/spans", json=span_with_version)
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}: {response.json()}"
    )
    assert response.json() == {"accepted": True}
