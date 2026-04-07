"""Unit tests for ToolCallAnalyzer — TDD RED phase.

Tests are written against the contract before the implementation exists.
Mock embedder is used so no real sentence-transformers weights are needed.

The embedder client is mocked: encode() returns controllable vectors.
Cosine similarity is computed by BaseAnalyzer.compare() using numpy.
To control similarity scores, we return specific vectors from encode().
"""

from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, call

from xeter.services.worker.base import Flag, SpanData, bow_score, hybrid_score
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "wrong_tool_called": 0.5,
    "wrong_tool_args": 0.4,
    "no_tool": 0.6,
    "excessive_tool": 0.3,
    "parsing_error": 0.5,
    "response_anomaly": 0.4,
}


def _unit_vec(dim=384) -> np.ndarray:
    """Return a unit vector (all components equal)."""
    v = np.ones(dim)
    return v / np.linalg.norm(v)


def _orthogonal_vec(dim=384) -> np.ndarray:
    """Return a vector orthogonal-ish to unit_vec (cosine sim ~ 0)."""
    v = np.zeros(dim)
    v[0] = 1.0
    v[1] = -1.0
    return v / np.linalg.norm(v)


def _low_sim_vec(dim=384) -> np.ndarray:
    """Return a vector with low but nonzero similarity to unit_vec (~0.2)."""
    v = np.random.RandomState(42).randn(dim)
    # Mix a small amount of the unit direction to get low positive similarity
    unit = _unit_vec(dim)
    v = 0.2 * unit + 0.8 * (v / np.linalg.norm(v))
    return v / np.linalg.norm(v)


def make_mock_embedder(default_vec=None):
    """Mock embedder client.

    encode() returns a fixed vector by default.
    Can set .encode.side_effect for sequence of vectors.
    """
    embedder = MagicMock()
    if default_vec is None:
        default_vec = _unit_vec()
    embedder.encode.return_value = default_vec
    return embedder


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
        raw_response=None,
        available_tools=[
            {"name": "search_web", "description": "Searches the web for information"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    defaults.update(kwargs)
    return SpanData(**defaults)


def make_analyzer(embedder=None, thresholds=None) -> ToolCallAnalyzer:
    if embedder is None:
        embedder = make_mock_embedder()
    if thresholds is None:
        thresholds = dict(DEFAULT_THRESHOLDS)
    return ToolCallAnalyzer(embedder, thresholds)


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
    # All same vectors → high similarity → clean span
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span()
    result = analyzer.analyze(span)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Test 3: wrong_tool flagged when similarity below threshold
# ---------------------------------------------------------------------------

def test_wrong_tool_flagged_when_below_threshold():
    # Prompt gets one direction, tools get orthogonal → low cosine similarity
    embedder = make_mock_embedder()
    call_idx = [0]
    def encode_side_effect(text):
        call_idx[0] += 1
        # First call is prompt — give it unit vec
        # Tool descriptions get orthogonal vec → low similarity
        if call_idx[0] == 1:
            return _unit_vec()
        return _orthogonal_vec()

    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
    span = make_clean_span(
        tool_name="calculator",
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
    # All same vectors → cosine sim = 1.0
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
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
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span()
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert len(scores) > 0, "flush_scores() must return non-empty list even when no flags fire"


# ---------------------------------------------------------------------------
# Test 6: wrong_tool uses available_tools ranking (FLAG-11)
# ---------------------------------------------------------------------------

def test_wrong_tool_uses_available_tools_ranking():
    """If the called tool is not the top-ranked match for the prompt → wrong_tool flag.

    Condition: top_tool_name != span.tool_name AND top_score < threshold.
    Both tools must have LOW similarity with prompt (top_score < 0.5),
    but search_web slightly higher than calculator → search_web is top-ranked.
    Called tool is calculator (not top) → wrong_tool flag.
    """
    embedder = make_mock_embedder()

    # Build vectors where cosine(prompt, search_desc) ≈ 0.3 and cosine(prompt, calc_desc) ≈ 0.1
    # Both below threshold 0.5, but search > calc
    dim = 384
    rng = np.random.RandomState(99)
    prompt_vec = _unit_vec(dim)

    # search_web: small positive correlation with prompt
    noise1 = rng.randn(dim)
    noise1 /= np.linalg.norm(noise1)
    search_vec = 0.3 * prompt_vec + 0.95 * noise1
    search_vec /= np.linalg.norm(search_vec)

    # calculator: near-orthogonal to prompt
    noise2 = rng.randn(dim)
    noise2 /= np.linalg.norm(noise2)
    calc_vec = 0.1 * prompt_vec + 0.99 * noise2
    calc_vec /= np.linalg.norm(calc_vec)

    def encode_side_effect(text):
        t = text.lower()
        # Match tool descriptions but NOT the prompt
        if "web" in t and ("info" in t or "searches" in t):
            return search_vec
        elif "calculator" in t or "math" in t or "calcul" in t:
            return calc_vec
        else:
            return prompt_vec

    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_called": 0.5})
    span = make_clean_span(
        tool_name="calculator",
        prompt="Find Python typing documentation",
        available_tools=[
            {"name": "search_web", "description": "Searches the web for information"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "wrong_tool" in flag_types


# ---------------------------------------------------------------------------
# Test: WTOOL-03 — immediate flag when no available_tools (None)
# ---------------------------------------------------------------------------

def test_wrong_tool_immediate_flag_no_available_tools():
    """WTOOL-03: tool called but available_tools is None → immediate flag, no embed call."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(tool_name="search_web", available_tools=None)
    flags = analyzer._check_wrong_tool(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "wrong_tool"
    assert flags[0].detail.get("metric") == "no_available_tools"
    assert flags[0].detail.get("actual_tool") == "search_web"
    # No embed call — immediate flag before any scoring
    embedder.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Test: WTOOL-03 — immediate flag when available_tools is empty list
# ---------------------------------------------------------------------------

def test_wrong_tool_immediate_flag_empty_available_tools():
    """WTOOL-03: tool called but available_tools is [] → immediate flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(tool_name="search_web", available_tools=[])
    flags = analyzer._check_wrong_tool(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "wrong_tool"
    assert flags[0].detail.get("metric") == "no_available_tools"
    embedder.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Test: WTOOL-02 — reported score is top1 hybrid score
# ---------------------------------------------------------------------------

def test_wrong_tool_score_is_top1_hybrid():
    """WTOOL-02: flag.score equals the top1 hybrid score, not a gap or name score."""
    # Prompt vector = unit_vec; tool vec = orthogonal → low cosine, low hybrid → flags
    embedder = make_mock_embedder()
    call_idx = [0]
    def encode_side_effect(text):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return _unit_vec()   # prompt
        return _orthogonal_vec()  # tools → low similarity
    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(
        tool_name="calculator",
        available_tools=[
            {"name": "search_web", "description": "Searches the web"},
            {"name": "calculator", "description": "Math calculations"},
        ],
    )
    flags = analyzer._check_wrong_tool(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "wrong_tool"
    # score must be a float between 0 and 1 (the top1 hybrid score, not 1.0 sentinel)
    assert 0.0 <= flags[0].score <= 1.0
    assert flags[0].detail.get("metric") == "prompt_vs_top1_tool_hybrid"


# ---------------------------------------------------------------------------
# Test: WTOOL-01 correct case — no flag when called_tool == top1 and score >= threshold
# ---------------------------------------------------------------------------

def test_wrong_tool_no_flag_correct_tool_above_threshold():
    """WTOOL-01 correct case: top1 == called_tool, score >= threshold → no flag."""
    embedder = make_mock_embedder(_unit_vec())  # all same → cosine=1.0 → high hybrid
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(
        tool_name="search_web",
        available_tools=[{"name": "search_web", "description": "Searches the web for information"}],
    )
    flags = analyzer._check_wrong_tool(span)
    assert not any(f.flag_type == "wrong_tool" for f in flags)


# ---------------------------------------------------------------------------
# Test 7: wrong_args flag must NOT include low_confidence (ARGS-05)
# ---------------------------------------------------------------------------

def test_wrong_args_flag_has_no_low_confidence():
    # Prompt and args get orthogonal vectors → low similarity → wrong_tool_args flag
    embedder = make_mock_embedder()
    call_idx = [0]
    def encode_side_effect(text):
        call_idx[0] += 1
        # Alternate: odd calls get unit_vec, even get orthogonal
        # This ensures prompt and args embeddings differ
        if call_idx[0] % 2 == 1:
            return _unit_vec()
        return _orthogonal_vec()
    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"query": "some unrelated text"}',
        prompt="Calculate the square root of 144",
    )
    flags = analyzer.analyze(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) >= 1, "Expected a wrong_tool_args flag"
    assert "low_confidence" not in wrong_args_flags[0].detail, (
        "ARGS-05: low_confidence must be absent from wrong_tool_args flag detail"
    )


# ---------------------------------------------------------------------------
# Test 8: no_tool flag when no tool was called but prompt implies tool use
# ---------------------------------------------------------------------------

def test_no_tool_flagged():
    # High similarity between prompt and "call a function tool" reference → no_tool flag
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "no_tool": 0.6})
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
    # Low similarity between prompt and tool → excessive_tool
    embedder = make_mock_embedder()

    def encode_side_effect(text):
        if "hello" in text.lower():
            return _orthogonal_vec()  # prompt about "hello" is unrelated to tool
        return _unit_vec()

    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "excessive_tool": 0.3})
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

def test_parsing_error_flagged_unknown_model():
    """Unknown model in registry produces parsing_error flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        agent_model="unknown-model-xyz",
        raw_response='{"some": "json"}',
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "parsing_error" in flag_types


def test_parsing_error_flagged_raw_text_no_match():
    """raw_text model with no matching format pattern produces parsing_error flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        agent_model="hermes-2-pro",
        raw_response="Just a plain text response with no tool call tags.",
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "parsing_error" in flag_types


def test_parsing_error_not_flagged_when_format_matches():
    """raw_text model with matching format pattern produces no parsing_error flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        agent_model="hermes-2-pro",
        raw_response='<tool_call>{"name": "search", "arguments": {}}</tool_call>',
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "parsing_error" not in flag_types


# ---------------------------------------------------------------------------
# Test 11: tool embed cache — same available_tools list must not re-embed
# ---------------------------------------------------------------------------

def test_tool_embed_cache_hit():
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)

    available_tools = [
        {"name": "search_web", "description": "Searches the web"},
        {"name": "calculator", "description": "Performs math calculations"},
    ]
    span = make_clean_span(available_tools=available_tools)

    # First analyze call
    analyzer.analyze(span)
    first_encode_count = embedder.encode.call_count

    # Second analyze call with same tools — cache should prevent re-embedding tools
    analyzer.analyze(span)
    second_encode_count = embedder.encode.call_count

    # The number of encode calls for tool embeddings should not double
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
    embedder = make_mock_embedder()

    def encode_side_effect(text):
        if "weather" in text.lower() or "paris" in text.lower() or "sunny" in text.lower():
            return _orthogonal_vec()  # response is unrelated
        return _unit_vec()

    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "response_anomaly": 0.4})
    span = make_clean_span(
        prompt="Search for Python typing documentation",
        response="The weather in Paris is sunny.",
    )
    flags = analyzer.analyze(span)
    anomaly_flags = [f for f in flags if f.flag_type == "response_anomaly"]
    assert len(anomaly_flags) >= 1, "Expected a response_anomaly flag"
    assert anomaly_flags[0].detail.get("metric") == "prompt_vs_response"
    assert "score" in anomaly_flags[0].detail


def test_response_anomaly_not_flagged_when_above_threshold():
    """High prompt-vs-response similarity produces no response_anomaly flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "response_anomaly": 0.4})
    span = make_clean_span(
        prompt="Search for Python typing documentation",
        response="Python supports type hints via PEP 484.",
    )
    flags = analyzer.analyze(span)
    flag_types = [f.flag_type for f in flags]
    assert "response_anomaly" not in flag_types


def test_response_anomaly_skipped_when_response_none():
    """_check_response_anomaly() must return [] (no crash) when response is None."""
    embedder = make_mock_embedder(_low_sim_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(response=None)
    result = analyzer._check_response_anomaly(span)
    assert result == []


# ---------------------------------------------------------------------------
# Tests 15–16: HYBRID-01 utility functions (bow_score, hybrid_score)
# ---------------------------------------------------------------------------

def test_bow_score_partial_overlap():
    # "hello world" vs "hello earth" — shared: {"hello"}, union: {"hello","world","earth"}
    score = bow_score("hello world", "hello earth")
    assert abs(score - 1/3) < 0.001, f"Expected ~0.333, got {score}"


def test_bow_score_identical_strings():
    score = bow_score("search for python docs", "search for python docs")
    assert score == 1.0


def test_bow_score_no_overlap():
    score = bow_score("apple banana", "cherry delta")
    assert score == 0.0


def test_bow_score_empty_string_returns_zero():
    assert bow_score("", "hello") == 0.0
    assert bow_score("hello", "") == 0.0
    assert bow_score("", "") == 0.0


def test_hybrid_score_equal_weight():
    # 0.5 * 0.8 + 0.5 * 0.2 = 0.5
    result = hybrid_score(0.8, 0.2)
    assert abs(result - 0.5) < 0.001


def test_hybrid_score_custom_weight():
    # weight=0.7: 0.7 * 1.0 + 0.3 * 0.0 = 0.7
    result = hybrid_score(1.0, 0.0, weight=0.7)
    assert abs(result - 0.7) < 0.001


def test_hybrid_score_both_max():
    assert hybrid_score(1.0, 1.0) == 1.0


# ---------------------------------------------------------------------------
# Tests for rewritten _check_wrong_args (ARGS-01, ARGS-04, ARGS-05)
# ---------------------------------------------------------------------------

def test_wrong_args_error_pattern_fires_without_embedding():
    """ARGS-01: tool_output with error pattern triggers flag; encode is never called."""
    embedder = make_mock_embedder()
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_arguments='{"query": "python docs"}',
        prompt="Search for Python typing documentation",
        tool_output="invalid argument: expected string, got integer",
    )
    flags = analyzer._check_wrong_args(span)
    assert any(f.flag_type == "wrong_tool_args" for f in flags), (
        "Expected wrong_tool_args flag from error pattern"
    )
    wrong_args = [f for f in flags if f.flag_type == "wrong_tool_args"][0]
    assert wrong_args.score == 1.0
    assert wrong_args.detail.get("metric") == "output_error_pattern"
    # ARGS-01 must short-circuit before any embed() call
    assert embedder.encode.call_count == 0, (
        f"ARGS-01 must not call embed(); got {embedder.encode.call_count} calls"
    )


def test_wrong_args_skips_all_numeric_flattened_values():
    """ARGS-04: all-numeric flattened values must not be embedded or flagged."""
    embedder = make_mock_embedder(_orthogonal_vec())  # low sim if embedded
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_arguments='{"amount": "10000 * (1 + 0.05) ** 3"}',
        prompt="Calculate compound interest",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 0, (
        "ARGS-04: all-numeric flattened values must not produce a flag"
    )


def test_wrong_args_no_low_confidence_in_detail():
    """ARGS-05: flag detail must never contain low_confidence key."""
    embedder = make_mock_embedder()
    call_idx = [0]
    def encode_side_effect(text):
        call_idx[0] += 1
        return _unit_vec() if call_idx[0] % 2 == 1 else _orthogonal_vec()
    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"query": "some unrelated text"}',
        prompt="Calculate the square root of 144",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    if wrong_args_flags:
        assert "low_confidence" not in wrong_args_flags[0].detail, (
            "ARGS-05: low_confidence must be absent"
        )
