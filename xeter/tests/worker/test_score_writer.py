"""Unit tests for score_writer.write_scores.

All PostgreSQL I/O is mocked — no real database connections.

Tests:
  1. test_write_scores_empty_returns_without_connecting  — empty scores short-circuits
  2. test_write_scores_sets_local_tenant_id              — SET LOCAL called before executemany
  3. test_write_scores_commits_on_success                — commit called after executemany
  4. test_write_scores_rolls_back_and_raises_on_error    — rollback + re-raise on failure
  5. test_write_scores_rows_shaped_correctly             — executemany receives correct row tuples
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_mock_conn():
    """Return a mock psycopg2 connection with a context-manager cursor."""
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    return conn, cursor


@patch("xeter.services.worker.score_writer.psycopg2.connect")
def test_write_scores_empty_returns_without_connecting(mock_connect):
    """Empty scores list returns immediately — no psycopg2.connect call."""
    from xeter.services.worker.score_writer import write_scores
    write_scores("span-1", "tenant-1", [])
    mock_connect.assert_not_called()


@patch("xeter.services.worker.score_writer._get_dsn", return_value="postgresql://fake")
@patch("xeter.services.worker.score_writer.psycopg2.connect")
def test_write_scores_sets_local_tenant_id(mock_connect, mock_dsn):
    """SET LOCAL app.current_tenant_id must be the FIRST execute call."""
    conn, cursor = _make_mock_conn()
    mock_connect.return_value = conn

    from xeter.services.worker.score_writer import write_scores
    write_scores("span-1", "tenant-abc", [("analyzer", "metric", 0.9)])

    first_call = cursor.execute.call_args_list[0]
    assert "SET LOCAL app.current_tenant_id" in first_call.args[0]
    assert first_call.args[1] == ("tenant-abc",)

    cursor.executemany.assert_called_once()


@patch("xeter.services.worker.score_writer._get_dsn", return_value="postgresql://fake")
@patch("xeter.services.worker.score_writer.psycopg2.connect")
def test_write_scores_commits_on_success(mock_connect, mock_dsn):
    """commit() is called after successful executemany."""
    conn, cursor = _make_mock_conn()
    mock_connect.return_value = conn

    from xeter.services.worker.score_writer import write_scores
    write_scores("span-1", "tenant-1", [("a", "b", 1.0)])

    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()


@patch("xeter.services.worker.score_writer._get_dsn", return_value="postgresql://fake")
@patch("xeter.services.worker.score_writer.psycopg2.connect")
def test_write_scores_rolls_back_and_raises_on_error(mock_connect, mock_dsn):
    """On executemany failure: rollback is called and exception is re-raised."""
    conn, cursor = _make_mock_conn()
    mock_connect.return_value = conn
    cursor.executemany.side_effect = RuntimeError("db error")

    from xeter.services.worker.score_writer import write_scores
    with pytest.raises(RuntimeError, match="db error"):
        write_scores("span-1", "tenant-1", [("a", "b", 1.0)])

    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


@patch("xeter.services.worker.score_writer._get_dsn", return_value="postgresql://fake")
@patch("xeter.services.worker.score_writer.psycopg2.connect")
def test_write_scores_rows_shaped_correctly(mock_connect, mock_dsn):
    """executemany receives rows as (span_id, tenant_id, analyzer_name, metric_name, score)."""
    conn, cursor = _make_mock_conn()
    mock_connect.return_value = conn

    from xeter.services.worker.score_writer import write_scores
    write_scores(
        "span-xyz",
        "tenant-999",
        [("cosine_analyzer", "similarity", 0.85), ("bow_analyzer", "overlap", 0.6)],
    )

    rows_passed = cursor.executemany.call_args.args[1]
    assert rows_passed[0] == ("span-xyz", "tenant-999", "cosine_analyzer", "similarity", 0.85)
    assert rows_passed[1] == ("span-xyz", "tenant-999", "bow_analyzer", "overlap", 0.6)
