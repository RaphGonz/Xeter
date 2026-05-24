"""Unit tests for TraceAnalyzer.

Verifies the TraceAnalyzer contract:
  - TraceAnalyzer is a subclass of BaseTraceAnalyzer
  - name property returns "trace_analyzer"
  - analyze() returns an empty list for all-None minimal spans (all checks guard-exit)
  - analyze() never returns None

No real embedder, Redis, ClickHouse, or S3 connections are needed.
EmbedderClient is mocked throughout.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from xeter.services.worker.trace_analyzer import TraceAnalyzer
from xeter.services.worker.base import BaseTraceAnalyzer, SpanData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trace_analyzer() -> TraceAnalyzer:
    """Construct a TraceAnalyzer with a mock embedder and default thresholds."""
    embedder = MagicMock()
    thresholds = {
        "stale_context": 85.0,
        "step_repetition": 85.0,
        "termination_loop_n": 3.0,
        "context_propagation_failure": 0.5,
        "history_loss": 0.4,
    }
    return TraceAnalyzer(embedder, thresholds)


def make_test_span(span_id: str = "s1", trace_id: str = "t1") -> SpanData:
    """Build a minimal SpanData for use in tests."""
    return SpanData(
        span_id=span_id,
        tenant_id="tenant-1",
        trace_id=trace_id,
        agent_name="agent",
        agent_model="gpt-4",
        tool_name=None,
        tool_description=None,
        tool_arguments=None,
        tool_output=None,
        prompt=None,
        response=None,
        raw_response=None,
        available_tools=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_trace_analyzer_is_subclass_of_base_trace_analyzer():
    """TraceAnalyzer must satisfy the BaseTraceAnalyzer contract."""
    assert issubclass(TraceAnalyzer, BaseTraceAnalyzer)


def test_trace_analyzer_name():
    """name property must return the stable string 'trace_analyzer'."""
    analyzer = make_trace_analyzer()
    assert analyzer.name == "trace_analyzer"


def test_trace_analyzer_analyze_empty_returns_empty_list():
    """analyze([]) returns an empty list — scaffold produces no flags."""
    analyzer = make_trace_analyzer()
    result = analyzer.analyze([])
    assert result == []


def test_trace_analyzer_analyze_with_spans_returns_empty_list():
    """analyze() returns [] for spans with all-None tool/prompt/response fields (all checks guard-exit)."""
    analyzer = make_trace_analyzer()
    spans = [make_test_span("s1", "t1"), make_test_span("s2", "t1")]
    result = analyzer.analyze(spans)
    assert result == []


def test_trace_analyzer_analyze_returns_list_not_none():
    """analyze() must return a list instance, never None."""
    analyzer = make_trace_analyzer()
    result = analyzer.analyze([make_test_span()])
    assert isinstance(result, list)
