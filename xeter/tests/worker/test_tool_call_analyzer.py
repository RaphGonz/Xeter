# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
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
from unittest.mock import MagicMock, call, patch

from xeter.services.worker.base import Flag, SpanData, bow_score, hybrid_score
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "tool_coherence_threshold": 0.15,
    "unnecessary_tool_call": 0.15,
    "wrong_tool_args": 0.4,
    "no_tool": 0.6,
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
# Test 3: wrong_tool — no flag when containment match (spaCy lemma overlap)
# ---------------------------------------------------------------------------

def test_wrong_tool_choice_no_flag_containment_match():
    """Step 1: prompt shares a lemma with called tool's name+description → no flag.

    "Search for Python documentation" and "search_web Search the internet"
    both lemmatize to include "search" → intersection non-empty → no embed call.
    """
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        prompt="Search for Python documentation",
        tool_name="search_web",
        available_tools=[
            {"name": "search_web", "description": "Search the internet for information"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    flags = analyzer._check_wrong_tool_choice(span)
    assert not any(f.flag_type == "wrong_tool_choice" for f in flags)
    # Containment match short-circuits before any embedding
    embedder.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: wrong_tool — no flag when called tool is rank 1 by cosine
# ---------------------------------------------------------------------------

def test_wrong_tool_choice_no_flag_rank_1():
    """Step 2: called tool has highest cosine similarity → rank 1 → no flag."""
    dim = 384
    prompt_vec = _unit_vec(dim)

    embedder = make_mock_embedder()
    def encode_side_effect(text):
        t = text.lower()
        if "search" in t or "web" in t:
            return _unit_vec(dim)      # high sim with prompt
        elif "calculator" in t or "math" in t:
            return _orthogonal_vec(dim)  # low sim with prompt
        else:
            return prompt_vec          # prompt itself
    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_name="search_web",
        prompt="a completely neutral task",
        available_tools=[
            {"name": "search_web", "description": "Search the internet"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    with patch("xeter.services.worker.tool_call_analyzer._lemma_set", return_value=set()):
        flags = analyzer._check_wrong_tool_choice(span)

    assert not any(f.flag_type == "wrong_tool_choice" for f in flags)


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
# Test 6: wrong_tool — flag fires when called tool is rank 2
# ---------------------------------------------------------------------------

def test_wrong_tool_choice_flagged_rank_2():
    """Step 2: called tool ranks below rank 1 → wrong_tool_choice flag with rank and top_candidate.

    Calculator gets cosine ~0.2 (above tool_coherence_threshold=0.15) so the coherence
    check passes and the flag fires for rank, not low coherence.
    """
    dim = 384
    prompt_vec = _unit_vec(dim)

    embedder = make_mock_embedder()
    def encode_side_effect(text):
        t = text.lower()
        if "search" in t or "web" in t:
            return _unit_vec(dim)      # cosine 1.0 — rank 1
        elif "calculator" in t or "math" in t:
            return _low_sim_vec(dim)   # cosine ~0.2 — rank 2, above coherence floor
        else:
            return prompt_vec          # prompt
    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_name="calculator",
        prompt="a completely neutral task",
        available_tools=[
            {"name": "search_web", "description": "Search the internet"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    with patch("xeter.services.worker.tool_call_analyzer._lemma_set", return_value=set()):
        flags = analyzer._check_wrong_tool_choice(span)

    assert len(flags) == 1
    assert flags[0].flag_type == "wrong_tool_choice"
    assert flags[0].detail["rank"] == 2
    assert flags[0].detail["top_candidate"] == "search_web"
    assert flags[0].detail["actual_tool"] == "calculator"
    assert flags[0].detail["metric"] == "embedding_rank"


# ---------------------------------------------------------------------------
# Test: WTOOL-03 — immediate flag when no available_tools (None)
# ---------------------------------------------------------------------------

def test_tool_not_available_immediate_flag_no_available_tools():
    """WTOOL-03: tool called but available_tools is None → immediate flag, no embed call."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(tool_name="search_web", available_tools=None)
    flags = analyzer._check_tool_not_available(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "tool_not_available"
    assert flags[0].detail.get("metric") == "no_available_tools"
    assert flags[0].detail.get("actual_tool") == "search_web"
    # No embed call — immediate flag before any scoring
    embedder.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Test: WTOOL-03 — immediate flag when available_tools is empty list
# ---------------------------------------------------------------------------

def test_tool_not_available_immediate_flag_empty_available_tools():
    """WTOOL-03: tool called but available_tools is [] → immediate flag."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS})
    span = make_clean_span(tool_name="search_web", available_tools=[])
    flags = analyzer._check_tool_not_available(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "tool_not_available"
    assert flags[0].detail.get("metric") == "no_available_tools"
    embedder.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Test: flag.score is the called tool's own cosine, not the top tool's score
# ---------------------------------------------------------------------------

def test_unnecessary_tool_call_flags_social_prompt_with_centroid_score():
    """Social/phatic prompt triggers unnecessary_tool_call; score is centroid_score.

    Gates: token_count ≤ 20, no NER entities, no action verbs, centroid sim ≥ threshold.
    When _SOCIAL_CENTROID is None the centroid gate is skipped (score = 1.0).
    """
    import xeter.services.worker.tool_call_analyzer as _mod

    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_name="calculator",
        prompt="great!",  # short, no NER, no action verb
        available_tools=[
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )

    original_centroid = _mod._SOCIAL_CENTROID
    _mod._SOCIAL_CENTROID = None  # bypass centroid gate → score = 1.0
    try:
        flags = analyzer._check_unnecessary_tool_call(span)
    finally:
        _mod._SOCIAL_CENTROID = original_centroid

    assert len(flags) == 1
    assert flags[0].flag_type == "unnecessary_tool_call"
    assert flags[0].score == 1.0  # centroid_score when centroid is None
    assert flags[0].detail["metric"] == "social_prompt"
    assert flags[0].detail["actual_tool"] == "calculator"


# ---------------------------------------------------------------------------
# Test: no flag when tool_name is None
# ---------------------------------------------------------------------------

def test_tool_not_available_no_flag_tool_name_none():
    """Guard: tool_name is None → skip detection entirely, no flag."""
    analyzer = make_analyzer(make_mock_embedder())
    span = make_clean_span(tool_name=None)
    flags = analyzer._check_tool_not_available(span)
    assert not any(f.flag_type == "tool_not_available" for f in flags)


# ---------------------------------------------------------------------------
# Test: flag when called tool is absent from available_tools
# ---------------------------------------------------------------------------

def test_tool_not_available_flagged_tool_not_in_list():
    """Called tool absent from available_tools → tool_not_available flag, score=1.0."""
    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_name="unknown_tool",
        prompt="Do something",
        available_tools=[
            {"name": "search_web", "description": "Search the internet"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )
    flags = analyzer._check_tool_not_available(span)
    assert len(flags) == 1
    assert flags[0].flag_type == "tool_not_available"
    assert flags[0].score == 1.0
    assert flags[0].detail["metric"] == "tool_not_in_list"
    assert flags[0].detail["actual_tool"] == "unknown_tool"
    assert "search_web" in flags[0].detail["available_tools"]


# ---------------------------------------------------------------------------
# Test: flag when rank 1 but score below tool_coherence_threshold (Case C)
# ---------------------------------------------------------------------------

def test_unnecessary_tool_call_flagged_low_coherence():
    """Phatic/social prompt passes all linguistic gates → unnecessary_tool_call flag.

    _SOCIAL_CENTROID patched to None so Gate 4 is skipped (centroid_score = 1.0).
    """
    import xeter.services.worker.tool_call_analyzer as _mod

    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "unnecessary_tool_call": 0.15})
    span = make_clean_span(
        tool_name="calculator",
        prompt="Sounds great!",  # short, no NER, no action verb
        available_tools=[
            {"name": "calculator", "description": "Performs math calculations"},
            {"name": "translator", "description": "Translates text between languages"},
        ],
    )

    original_centroid = _mod._SOCIAL_CENTROID
    _mod._SOCIAL_CENTROID = None
    try:
        flags = analyzer._check_unnecessary_tool_call(span)
    finally:
        _mod._SOCIAL_CENTROID = original_centroid

    assert len(flags) == 1
    assert flags[0].flag_type == "unnecessary_tool_call"
    assert flags[0].detail["metric"] == "social_prompt"
    assert flags[0].score == 1.0  # centroid_score when centroid is None


# ---------------------------------------------------------------------------
# Test 7: wrong_args flag must NOT include low_confidence (ARGS-05)
# ---------------------------------------------------------------------------

def test_wrong_args_flag_has_no_low_confidence():
    # arg value embedding is orthogonal to prompt → low score → violation fires
    embedder = make_mock_embedder()
    def encode_side_effect(text):
        t = text.lower()
        if "calculate" in t or "square" in t or "144" in t:
            return _unit_vec()
        return _orthogonal_vec()
    embedder.encode.side_effect = encode_side_effect
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"query": "some unrelated text"}',
        prompt="Calculate the square root of 144",
        tool_output="Success",
    )
    flags = analyzer.analyze(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) >= 1, "Expected a wrong_tool_args flag"
    detail = wrong_args_flags[0].detail
    assert "low_confidence" not in detail, (
        "ARGS-05: low_confidence must be absent from wrong_tool_args flag detail"
    )
    assert detail.get("metric") == "arg_violations", (
        "Detail metric must be 'arg_violations'"
    )
    assert "violations" in detail, "Detail must contain 'violations' list"


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
# Test 9: unnecessary_tool_call flag when tool called but prompt doesn't warrant it
# ---------------------------------------------------------------------------

def test_unnecessary_tool_call_flagged_via_analyze():
    """Social prompt passes all linguistic gates → unnecessary_tool_call via analyze().

    _SOCIAL_CENTROID patched to None so Gate 4 is skipped (centroid_score = 1.0).
    """
    import xeter.services.worker.tool_call_analyzer as _mod

    embedder = make_mock_embedder(_unit_vec())
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "unnecessary_tool_call": 0.15})
    span = make_clean_span(
        tool_name="search_web",
        prompt="Sounds great!",
        available_tools=[
            {"name": "search_web", "description": "Search the internet"},
            {"name": "calculator", "description": "Performs math calculations"},
        ],
    )

    original_centroid = _mod._SOCIAL_CENTROID
    _mod._SOCIAL_CENTROID = None
    try:
        flags = analyzer.analyze(span)
    finally:
        _mod._SOCIAL_CENTROID = original_centroid

    flag_types = [f.flag_type for f in flags]
    assert "unnecessary_tool_call" in flag_types


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

    # Patch _lemma_set to return empty sets so containment never fires and
    # Step 2 (embedding ranking) runs — that's the path where the cache matters.
    with patch("xeter.services.worker.tool_call_analyzer._lemma_set", return_value=set()):
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

def test_wrong_args_ungrounded_arg_flagged():
    """Arg value with no token match and low embedding similarity → wrong_tool_args flag."""
    dim = 384
    prompt_vec = _unit_vec(dim)
    ungrounded_vec = _orthogonal_vec(dim)

    embedder = make_mock_embedder()
    def encode_side_effect(text):
        # prompt embeds to unit_vec; unrelated value embeds to orthogonal
        if "tokyo" in text.lower() or "weather" in text.lower() or "get" in text.lower():
            return prompt_vec
        return ungrounded_vec
    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"location": "zzzzzzz"}',
        prompt="Get the weather in Tokyo.",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    assert any(f.flag_type == "wrong_tool_args" for f in flags), (
        "Expected wrong_tool_args flag for ungrounded arg"
    )
    flag = [f for f in flags if f.flag_type == "wrong_tool_args"][0]
    assert flag.detail.get("metric") == "arg_violations"


def test_wrong_args_grounded_arg_no_flag():
    """Arg value present in prompt tokens → no flag even with low embedding."""
    embedder = make_mock_embedder()
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"location": "Tokyo"}',
        prompt="Get the weather in Tokyo.",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args) == 0, "Token-grounded arg must not be flagged"


def test_wrong_args_generated_value_skipped():
    """Values longer than 120 chars or matching SQL/code patterns are skipped (no flag)."""
    embedder = make_mock_embedder()
    analyzer = make_analyzer(embedder)
    span = make_clean_span(
        tool_arguments='{"query": "SELECT * FROM orders WHERE customer_id = 99823 AND status = \'active\' ORDER BY created_at DESC LIMIT 100 OFFSET 0"}',
        prompt="Fetch active orders for customer 99823",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 0, "SQL query value must be skipped — no flag expected"


def test_wrong_args_no_low_confidence_in_detail():
    """ARGS-05: flag detail must never contain low_confidence key."""
    embedder = make_mock_embedder()
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_arguments='{"query": "zzzzz unrelated zzzzz"}',
        prompt="Fetch orders for customer ID 99823",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    if wrong_args_flags:
        assert "low_confidence" not in wrong_args_flags[0].detail, (
            "ARGS-05: low_confidence must be absent"
        )


# ---------------------------------------------------------------------------
# New tests — per-argument grounding and format heuristics
# ---------------------------------------------------------------------------

def test_wrong_args_location_mismatch_flagged():
    """fwta-001: prompt says Tokyo, args say London → token miss + low embed → flag fires."""
    dim = 384
    prompt_vec = _unit_vec(dim)
    mismatch_vec = _orthogonal_vec(dim)

    embedder = make_mock_embedder()
    def encode_side_effect(text):
        if "london" in text.lower():
            return mismatch_vec
        return prompt_vec
    embedder.encode.side_effect = encode_side_effect

    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_name="get_weather",
        tool_arguments='{"location": "London", "date": "2025-11-20"}',
        prompt="Get the current weather conditions in Tokyo, Japan on March 5th.",
        tool_output="London: 10°C overcast",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 1, "Expected wrong_tool_args flag for location mismatch"
    detail = wrong_args_flags[0].detail
    assert detail["metric"] == "arg_violations"
    assert any(v["key"] == "location" for v in detail["violations"]), (
        "'location' arg should appear in violations"
    )


def test_wrong_args_hallucinated_recipient_flagged():
    """fwta-003: prompt specifies alice@engineering.com, args use bob@marketing.com → flag."""
    embedder = make_mock_embedder()
    embedder.encode.return_value = None  # skip embedding fallback; rely on token grounding only
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_name="send_email",
        tool_arguments='{"to": "bob@marketing.com", "subject": "Q4 marketing campaign", "body": "Please review."}',
        prompt="Send an email to alice@engineering.com about the code review for PR 4521.",
        tool_output="Email delivered",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 1, "Expected wrong_tool_args flag for hallucinated recipient"
    violations = wrong_args_flags[0].detail["violations"]
    violation_keys = [v["key"] for v in violations]
    assert "to" in violation_keys or "subject" in violation_keys, (
        "At least one ungrounded arg should be reported"
    )



def test_wrong_args_multiple_violations_worst_score_wins():
    """Multiple ungrounded args: flag score = min(scores) across all violations."""
    embedder = make_mock_embedder()
    embedder.encode.return_value = None  # skip embedding fallback; rely on token grounding only
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_name="get_weather",
        tool_arguments='{"location": "zzzzzzz", "units": "xxxxxxx"}',
        prompt="Get the current weather conditions in Tokyo, Japan.",
        tool_output="Success",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 1
    flag = wrong_args_flags[0]
    violations = flag.detail["violations"]
    assert len(violations) >= 1
    # flag.score must equal the minimum score across violations
    min_violation_score = min(v["score"] for v in violations)
    assert flag.score == min_violation_score, (
        f"Flag score {flag.score} must equal worst violation score {min_violation_score}"
    )


def test_wrong_args_valid_grounded_args_no_flag():
    """Args that match prompt entities closely → no flag."""
    embedder = make_mock_embedder()
    analyzer = make_analyzer(embedder, thresholds={**DEFAULT_THRESHOLDS, "wrong_tool_args": 0.4})
    span = make_clean_span(
        tool_name="get_weather",
        tool_arguments='{"location": "Tokyo", "date": "2025-03-05"}',
        prompt="Get the current weather conditions in Tokyo, Japan on March 5th.",
        tool_output="Tokyo: 18°C sunny",
    )
    flags = analyzer._check_wrong_args(span)
    wrong_args_flags = [f for f in flags if f.flag_type == "wrong_tool_args"]
    assert len(wrong_args_flags) == 0, (
        "Grounded args (Tokyo in prompt and args) must not produce a flag"
    )
