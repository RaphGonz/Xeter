"""Integration tests for the Embedding Worker loop.

All I/O (fetch_span, write_scores, write_flags) is fully mocked — no real Redis,
ClickHouse, PostgreSQL, or S3 connections are made.

The tests exercise process_span() directly, injecting mock analyzers so the
registry extensibility (FLAG-01) and dispatcher logic can be verified in
isolation.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from xeter.services.worker.main import process_span
from xeter.services.worker.base import Flag, SpanData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_test_span() -> SpanData:
    """Build a minimal SpanData for use in tests."""
    return SpanData(
        span_id="test-span-1",
        tenant_id="tenant-uuid-1",
        trace_id="trace-1",
        agent_name="agent",
        agent_model="gpt-4",
        tool_name="wrong_tool",
        tool_description="does something unrelated",
        tool_arguments='{"address": "bob@example.com"}',
        tool_output="done",
        prompt="send an email to alice@example.com",
        response="I called wrong_tool",
        raw_response=None,
        available_tools=[
            {"name": "email_sender", "description": "sends email"},
            {"name": "wrong_tool", "description": "database query"},
        ],
    )


def make_mock_analyzer(flags=None, scores=None):
    """Return a mock analyzer with configurable analyze() and flush_scores() outputs."""
    analyzer = MagicMock()
    analyzer.analyze.return_value = flags if flags is not None else []
    analyzer.flush_scores.return_value = scores if scores is not None else []
    return analyzer


# ---------------------------------------------------------------------------
# Test 1: all analyzers are called
# ---------------------------------------------------------------------------


def test_process_span_calls_all_analyzers():
    """Both analyzers in the list must each receive the span from analyze()."""
    span = make_test_span()

    analyzer_a = make_mock_analyzer()
    analyzer_b = make_mock_analyzer()

    with (
        patch("xeter.services.worker.main.fetch_span", return_value=span),
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
    ):
        process_span("test-span-1", [analyzer_a, analyzer_b])

    analyzer_a.analyze.assert_called_once_with(span)
    analyzer_b.analyze.assert_called_once_with(span)


# ---------------------------------------------------------------------------
# Test 2: write_scores called for every span even when no flags
# ---------------------------------------------------------------------------


def test_process_span_writes_scores_for_every_span():
    """write_scores must be called even when the analyzer returns no flags."""
    span = make_test_span()
    scores = [("tool_call_analyzer", "wrong_tool", 0.82)]

    analyzer = make_mock_analyzer(flags=[], scores=scores)

    with (
        patch("xeter.services.worker.main.fetch_span", return_value=span),
        patch("xeter.services.worker.main.write_scores") as mock_write_scores,
        patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    ):
        process_span("test-span-1", [analyzer])

    mock_write_scores.assert_called_once_with("test-span-1", "tenant-uuid-1", scores)
    mock_write_flags.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: write_flags called when analyzer returns flags
# ---------------------------------------------------------------------------


def test_process_span_writes_flags_when_present():
    """write_flags must be called when the analyzer returns at least one Flag."""
    span = make_test_span()
    flag = Flag(
        flag_type="wrong_tool",
        score=0.82,
        detail={"metric": "wrong_tool", "tool_used": "wrong_tool"},
    )

    analyzer = make_mock_analyzer(flags=[flag], scores=[("tool_call_analyzer", "wrong_tool", 0.82)])

    with (
        patch("xeter.services.worker.main.fetch_span", return_value=span),
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    ):
        process_span("test-span-1", [analyzer])

    mock_write_flags.assert_called_once_with(
        "test-span-1", "tenant-uuid-1", "trace-1", [flag]
    )


# ---------------------------------------------------------------------------
# Test 4: write_flags NOT called when analyzer returns empty flags
# ---------------------------------------------------------------------------


def test_process_span_no_write_flags_when_clean():
    """write_flags must NOT be called when all analyzers return empty flag lists."""
    span = make_test_span()

    analyzer = make_mock_analyzer(flags=[], scores=[("tool_call_analyzer", "no_tool", 0.2)])

    with (
        patch("xeter.services.worker.main.fetch_span", return_value=span),
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    ):
        process_span("test-span-1", [analyzer])

    mock_write_flags.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: exception from fetch_span propagates out of process_span
# ---------------------------------------------------------------------------


def test_process_span_propagates_fetch_span_exception():
    """An exception from fetch_span propagates out so the BRPOP loop can log-and-skip."""
    analyzer = make_mock_analyzer()

    with (
        patch(
            "xeter.services.worker.main.fetch_span",
            side_effect=ValueError("span not found: missing-span"),
        ),
        patch("xeter.services.worker.main.write_scores") as mock_write_scores,
        patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    ):
        with pytest.raises(ValueError, match="span not found: missing-span"):
            process_span("missing-span", [analyzer])

    # Neither writer should have been called
    mock_write_scores.assert_not_called()
    mock_write_flags.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: ANALYZERS registry extensibility (FLAG-01 proof)
# ---------------------------------------------------------------------------


def test_analyzers_registry_extensibility():
    """Verify that adding a second analyzer to the list dispatches both without
    modifying process_span. This is the FLAG-01 extensibility proof: the
    registry is open for extension at zero modification cost.
    """
    span = make_test_span()

    flag_a = Flag(
        flag_type="wrong_tool",
        score=0.85,
        detail={"metric": "wrong_tool", "tool_used": "wrong_tool"},
    )
    flag_b = Flag(
        flag_type="no_tool",
        score=0.72,
        detail={"metric": "no_tool"},
    )

    analyzer_a = make_mock_analyzer(
        flags=[flag_a],
        scores=[("analyzer_a", "wrong_tool", 0.85)],
    )
    analyzer_b = make_mock_analyzer(
        flags=[flag_b],
        scores=[("analyzer_b", "no_tool", 0.72)],
    )

    with (
        patch("xeter.services.worker.main.fetch_span", return_value=span),
        patch("xeter.services.worker.main.write_scores") as mock_write_scores,
        patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    ):
        # Pass BOTH analyzers — this is the extensibility proof
        process_span("test-span-1", [analyzer_a, analyzer_b])

    # Both analyzers must have been called
    analyzer_a.analyze.assert_called_once_with(span)
    analyzer_b.analyze.assert_called_once_with(span)
    analyzer_a.flush_scores.assert_called_once()
    analyzer_b.flush_scores.assert_called_once()

    # write_scores receives ALL scores from BOTH analyzers
    expected_scores = [
        ("analyzer_a", "wrong_tool", 0.85),
        ("analyzer_b", "no_tool", 0.72),
    ]
    mock_write_scores.assert_called_once_with("test-span-1", "tenant-uuid-1", expected_scores)

    # write_flags receives ALL flags from BOTH analyzers
    mock_write_flags.assert_called_once_with(
        "test-span-1", "tenant-uuid-1", "trace-1", [flag_a, flag_b]
    )
