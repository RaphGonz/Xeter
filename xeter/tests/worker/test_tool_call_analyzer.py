"""Unit tests for ToolCallAnalyzer — TDD RED phase.

Tests are written against the contract before the implementation exists.
Mock model is used so no real sentence-transformers weights are needed.
"""

from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, call

from xeter.services.worker.base import Flag, SpanData
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "wrong_tool": 0.5,
    "wrong_tool_args": 0.4,
    "no_tool": 0.6,
    "excessive_tool": 0.3,
    "parsing_error": 0.5,
    "response_anomaly": 0.4,
}


def make_mock_model():
    """Mock SentenceTransformer that returns deterministic embeddings.

    encode() returns a fixed vector.
    similarity() returns a configurable value — default low (0.3).
    """
    model = MagicMock()
    # encode() always returns a 384-dim unit vector
    model.encode.return_value = np.ones(384) / np.sqrt(384)
    # similarity() returns a 2D tensor — mock as nested list for float(sim[0][0])
    model.similarity.return_value = [[0.3]]  # default low similarity
    return model


def make_clean_span(**kwargs) -> SpanData:
    """Return a minimal SpanData with sensible defaults that can be overridden."""
    defaults = dict(
        span_id="span-1",
        tenant_id="tenant-1",
        trace_id="trace-1",
        agent_name="test-agent",
        agent_model="gpt-4",
        tool_name="search_web",
        tool_description="Searches the web for information",
        tool_arguments='{"query": "Python typing"}',
        tool_output="Python supports type hints...",
        prompt="Search for Python typing documentation",
        response="Here is what I found about Python typing.",
        available_tools=[
            {"name": "search_web", "description": "Searches the web for information"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    defaults.update(kwargs)
    return SpanData(**defaults)


def make_analyzer(model=None, thresholds=None) -> ToolCallAnalyzer:
    if model is None:
        model = make_mock_model()
    if thresholds is None:
        thresholds = dict(DEFAULT_THRESHOLDS)
    return ToolCallAnalyzer(model, thresholds)


# ---------------------------------------------------------------------------
# Test 1: name property
# ---------------------------------------------------------------------------

def test_name():
    analyzer = make_analyzer()
    assert analyzer.name == "tool_call"


# ---------------------------------------------------------------------------
# Test 2: analyze() returns a list
# ---------------------------------------------------------------------------

def test_analyze_returns_list():
    model = make_mock_model()
    model.similarity.return_value = [[0.9]]  # high similarity everywhere = clean span
    analyzer = make_analyzer(model)
    span = make_clean_span()
    result = analyzer.analyze(span)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Test 3: wrong_tool flagged when similarity below threshold
# ---------------------------------------------------------------------------

def test_wrong_tool_flagged_when_below_threshold():
    model = make_mock_model()
    # Low similarity — called tool is not ranked top
    model.similarity.return_value = [[0.2]]
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool": 0.5})
    span = make_clean_span(
        tool_name="calculator",  # called the calculator
        available_tools=[
            {"name": "search_web", "description": "Searches the web"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "wrong_tool" in flag_types


# ---------------------------------------------------------------------------
# Test 4: wrong_tool NOT flagged when similarity above threshold
# ---------------------------------------------------------------------------

def test_wrong_tool_not_flagged_when_above_threshold():
    model = make_mock_model()
    model.similarity.return_value = [[0.8]]  # high similarity
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool": 0.5})
    span = make_clean_span(
        tool_name="search_web",
        available_tools=[
            {"name": "search_web", "description": "Searches the web"},
        ],
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "wrong_tool" not in flag_types


# ---------------------------------------------------------------------------
# Test 5: scores are logged regardless of whether a flag fires (FLAG-10)
# ---------------------------------------------------------------------------

def test_scores_logged_regardless_of_flag():
    model = make_mock_model()
    model.similarity.return_value = [[0.9]]  # high similarity — no flags expected
    analyzer = make_analyzer(model)
    span = make_clean_span()
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert len(scores) > 0, "flush_scores() must return non-empty list even when no flags fire"


# ---------------------------------------------------------------------------
# Test 6: wrong_tool uses available_tools ranking (FLAG-11)
# ---------------------------------------------------------------------------

def test_wrong_tool_uses_available_tools_ranking():
    """If the called tool is not the top-ranked match for the prompt → wrong_tool flag."""
    model = make_mock_model()

    # Provide two tools; make encode return different vectors for each so we can
    # control rankings. We do this via side_effect on model.encode so the first
    # encode returns a vector aligned with "search_web", and the second (calculator)
    # returns an orthogonal vector.
    prompt_vec = np.array([1.0] + [0.0] * 383)
    search_vec = np.array([1.0] + [0.0] * 383)   # same direction as prompt → high sim
    calc_vec   = np.array([0.0, 1.0] + [0.0] * 382)  # orthogonal → low sim

    # encode() side_effect: first call = prompt, second = search_web, third = calculator
    model.encode.side_effect = [prompt_vec, search_vec, calc_vec]

    # similarity returns: high for search_web (rank 1), low for calculator (rank 2)
    # Since span.tool_name = "calculator" but top-ranked = "search_web" → wrong_tool
    model.similarity.side_effect = [
        [[0.95]],  # prompt vs search_web (tool ranking)
        [[0.05]],  # prompt vs calculator (tool ranking)
        [[0.2]],   # prompt_vs_tool_rank (below threshold)
        [[0.2]],   # prompt_vs_tool_name direct check
        [[0.2]],   # prompt_vs_tool_description direct check
        [[0.2]],   # additional calls
        [[0.2]],
        [[0.2]],
        [[0.2]],
        [[0.2]],
    ]

    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool": 0.5})
    span = make_clean_span(
        tool_name="calculator",
        prompt="Search for Python typing documentation",
        available_tools=[
            {"name": "search_web", "description": "Searches the web for information"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "wrong_tool" in flag_types


# ---------------------------------------------------------------------------
# Test 7: wrong_args flag always includes low_confidence: True (FLAG-12)
# ---------------------------------------------------------------------------

def test_wrong_args_flag_has_low_confidence():
    model = make_mock_model()
    model.similarity.return_value = [[0.1]]  # low similarity for all checks
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"query": "some unrelated text"}',
        prompt="Calculate the square root of 144",
    )
    flags = analyzer.analyze(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) >= 1, "Expected a wrong_tool_args flag"
    assert wrong_args_flags[0].detail.get("low_confidence") is True


# ---------------------------------------------------------------------------
# Test 8: no_tool flag when no tool was called but prompt implies tool use
# ---------------------------------------------------------------------------

def test_no_tool_flagged():
    model = make_mock_model()
    # High similarity between prompt and "use tool" reference string → no_tool flag
    model.similarity.return_value = [[0.9]]
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "no_tool": 0.6})
    span = make_clean_span(
        tool_name=None,
        tool_description=None,
        tool_arguments=None,
        tool_output=None,
        available_tools=None,
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "no_tool" in flag_types


# ---------------------------------------------------------------------------
# Test 9: excessive_tool flag when tool called but prompt doesn't warrant it
# ---------------------------------------------------------------------------

def test_excessive_tool_flagged():
    model = make_mock_model()
    # Low similarity between prompt and tool_name → excessive_tool flag
    model.similarity.return_value = [[0.1]]
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "excessive_tool": 0.3})
    span = make_clean_span(
        tool_name="search_web",
        prompt="Just say hello",
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "excessive_tool" in flag_types


# ---------------------------------------------------------------------------
# Test 10: parsing_error flag when model+prompt vs response similarity low
# ---------------------------------------------------------------------------

def test_parsing_error_flagged():
    model = make_mock_model()
    model.similarity.return_value = [[0.1]]  # low similarity
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "parsing_error": 0.5})
    span = make_clean_span(
        agent_model="gpt-4",
        prompt="What is 2+2?",
        response="<tool_call>search_web</tool_call>",  # nonsensical response
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "parsing_error" in flag_types


# ---------------------------------------------------------------------------
# Test 11: tool embed cache — same available_tools list must not re-embed
# ---------------------------------------------------------------------------

def test_tool_embed_cache_hit():
    model = make_mock_model()
    model.similarity.return_value = [[0.9]]
    analyzer = make_analyzer(model)

    available_tools = [
        {"name": "search_web", "description": "Searches the web"},
        {"name": "calculator", "description": "Performs math calculations"},
    ]
    span = make_clean_span(available_tools=available_tools)

    # First analyze call
    analyzer.analyze(span)
    first_encode_count = model.encode.call_count

    # Second analyze call with same tools — cache should prevent re-embedding tools
    analyzer.analyze(span)
    second_encode_count = model.encode.call_count

    # The number of encode calls for tool embeddings should not double
    # (tool embeddings = 2 per call without cache, 0 on cache hit)
    # Total encodes for non-tool texts should be consistent
    tool_embed_calls_first = 2  # two tools
    # If cache works, second call should not add 2 more tool embed calls
    added_calls = second_encode_count - first_encode_count
    assert added_calls < first_encode_count, (
        f"Expected fewer encode calls on second run (cache hit). "
        f"First: {first_encode_count}, Second total: {second_encode_count}"
    )


# ---------------------------------------------------------------------------
# Tests 12–14: response_anomaly checks (FLAG-06)
# ---------------------------------------------------------------------------

def test_response_anomaly_flagged():
    """Low prompt-vs-response similarity produces response_anomaly flag (FLAG-06)."""
    model = make_mock_model()
    model.similarity.return_value = [[0.2]]  # low similarity
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "response_anomaly": 0.4})
    span = make_clean_span(
        prompt="Search for Python typing documentation",
        response="The weather in Paris is sunny.",  # unrelated response
    )
    flags = analyzer.analyze(span)
    anomaly_flags = [f for f in flags if f.flag_type == "response_anomaly"]
    assert len(anomaly_flags) >= 1, "Expected a response_anomaly flag"
    assert anomaly_flags[0].detail.get("metric") == "prompt_vs_response"
    assert "score" in anomaly_flags[0].detail


def test_response_anomaly_not_flagged_when_above_threshold():
    """High prompt-vs-response similarity produces no response_anomaly flag."""
    model = make_mock_model()
    model.similarity.return_value = [[0.9]]  # high similarity
    analyzer = make_analyzer(model, thresholds={**DEFAULT_THRESHOLDS, "response_anomaly": 0.4})
    span = make_clean_span(
        prompt="Search for Python typing documentation",
        response="Python supports type hints via PEP 484.",
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "response_anomaly" not in flag_types


def test_response_anomaly_skipped_when_response_none():
    """_check_response_anomaly() must return [] (no crash) when response is None."""
    model = make_mock_model()
    model.similarity.return_value = [[0.2]]
    analyzer = make_analyzer(model)
    span = make_clean_span(response=None)
    # Should not raise
    result = analyzer._check_response_anomaly(span)
    assert result == []
