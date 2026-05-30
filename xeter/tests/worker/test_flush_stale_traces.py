# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Tests for _flush_stale_traces() helper. All I/O is fully mocked. time.monotonic is patched to control staleness without real time.sleep calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from xeter.services.worker.main import _flush_stale_traces, WORKER_TRACE_FLUSH_TIMEOUT_S
from xeter.services.worker.base import SpanData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_test_span(
    span_id: str = "test-span-1",
    trace_id: str = "trace-1",
    tenant_id: str = "tenant-uuid-1",
) -> SpanData:
    """Build a minimal SpanData for use in flush tests."""
    return SpanData(
        span_id=span_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        agent_name="agent",
        agent_model="gpt-4",
        tool_name="some_tool",
        tool_description="does something",
        tool_arguments='{"key": "value"}',
        tool_output="done",
        prompt="do the thing",
        response="I called some_tool",
        raw_response=None,
        available_tools=[
            {"name": "some_tool", "description": "does something"},
        ],
    )


def make_mock_trace_analyzer(flags=None, scores=None):
    """Return a mock TraceAnalyzer with configurable analyze() and flush_scores() outputs."""
    mock_ta = MagicMock()
    mock_ta.analyze.return_value = flags if flags is not None else []
    mock_ta.flush_scores.return_value = scores if scores is not None else []
    return mock_ta


# ---------------------------------------------------------------------------
# Test 1: stale trace is flushed when monotonic time exceeds threshold
# ---------------------------------------------------------------------------


def test_idle_flush_fires_when_stale():
    """A trace whose last_seen is far in the past must be flushed and removed from the buffers."""
    span = make_test_span()
    trace_buffer = {"trace-A": [span]}
    trace_last_seen = {"trace-A": 0.0}
    mock_ta = make_mock_trace_analyzer(flags=[], scores=[])

    with (
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ta.analyze.assert_called_once_with([span])
    assert "trace-A" not in trace_buffer
    assert "trace-A" not in trace_last_seen


# ---------------------------------------------------------------------------
# Test 2: write_scores is called with None as span_id for trace-level scores
# ---------------------------------------------------------------------------


def test_trace_scores_written_with_none_span_id():
    """write_scores must be called with span_id=None for trace-level scores (INFRA-02)."""
    span = make_test_span()
    scores = [("trace_analyzer", "some_metric", 0.75)]
    trace_buffer = {"trace-B": [span]}
    trace_last_seen = {"trace-B": 0.0}
    mock_ta = make_mock_trace_analyzer(flags=[], scores=scores)

    with (
        patch("xeter.services.worker.main.write_scores") as mock_ws,
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ws.assert_called_once_with(None, span.tenant_id, scores)


# ---------------------------------------------------------------------------
# Test 3: non-stale trace is NOT flushed
# ---------------------------------------------------------------------------


def test_non_stale_trace_not_flushed():
    """A trace whose last_seen is within WORKER_TRACE_FLUSH_TIMEOUT_S must NOT be flushed."""
    span = make_test_span()
    # monotonic patched to 9999.0, last_seen=9998.0 → delta=1s < 30s threshold
    trace_buffer = {"trace-C": [span]}
    trace_last_seen = {"trace-C": 9998.0}
    mock_ta = make_mock_trace_analyzer()

    with (
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ta.analyze.assert_not_called()
    assert "trace-C" in trace_buffer


# ---------------------------------------------------------------------------
# Test 4: exception from analyze is caught and buffers are cleaned up
# ---------------------------------------------------------------------------


def test_exception_in_analyze_logs_and_cleans_buffer():
    """If trace_analyzer.analyze() raises, the exception must be caught and the trace removed (no memory leak)."""
    span = make_test_span()
    mock_ta = MagicMock()
    mock_ta.analyze.side_effect = RuntimeError("boom")
    trace_buffer = {"trace-D": [span]}
    trace_last_seen = {"trace-D": 0.0}

    with (
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        # Must NOT raise — the try/except/finally in _flush_stale_traces handles it
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    assert "trace-D" not in trace_buffer
    assert "trace-D" not in trace_last_seen
