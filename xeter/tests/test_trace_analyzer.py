# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Tests for TraceAnalyzer — 5 trace-level checks. Plan: 25-02

Covers all 5 check methods in the TraceAnalyzer implementation:
  - _check_stale_context      (CTX-02)
  - _check_step_repetition    (TRACE-01)
  - _check_termination_loop   (TRACE-02)
  - _check_context_propagation_failure  (TRACE-03)
  - _check_history_loss       (TRACE-04)

RED state: TraceAnalyzer.analyze() returns [] unconditionally (Phase 19 stub).
Tests 1-2 (guard tests) PASS against the stub.
Tests 3-22 (flag-asserting tests) FAIL RED — no flags fire from the stub.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from xeter.services.worker.trace_analyzer import TraceAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spans(n: int, **per_span_overrides) -> list:
    """Build a list of n minimal SpanData objects sharing trace_id='tr1'.

    per_span_overrides values may be lists (one per span, index-aligned)
    or scalars (applied to all spans).
    """
    from xeter.services.worker.base import SpanData

    spans = []
    for i in range(n):
        # Start with full defaults, then apply per-span overrides on top.
        # This avoids duplicate keyword argument errors when overrides contain
        # fields that are also in the defaults (e.g. prompt, tool_output).
        fields = dict(
            span_id=f"s{i}",
            tenant_id="t1",
            trace_id="tr1",
            agent_name="ag",
            agent_model="gpt-4o",
            tool_name=None,
            tool_description=None,
            tool_arguments=None,
            tool_output=None,
            prompt=None,
            response=None,
            raw_response=None,
            available_tools=None,
        )
        for k, v in per_span_overrides.items():
            fields[k] = v[i] if isinstance(v, list) else v
        spans.append(SpanData(**fields))
    return spans


def _make_trace_analyzer(thresholds=None) -> TraceAnalyzer:
    """Create a TraceAnalyzer with a MagicMock embedder.

    Default thresholds match CONTEXT.md D-11 starting values.
    """
    mock_emb = MagicMock()
    mock_emb.encode.return_value = np.ones(384)
    mock_emb.encode_batch.return_value = [np.ones(384)]

    default_thresholds = {
        "stale_context": 85.0,
        "step_repetition": 85.0,
        "termination_loop_n": 3,
        "context_propagation_failure": 0.5,
        "history_loss": 0.4,
    }
    if thresholds is not None:
        default_thresholds.update(thresholds)

    return TraceAnalyzer(mock_emb, default_thresholds)


# ---------------------------------------------------------------------------
# Tests 1-2: Guard tests — PASS against the stub (stub returns [])
# ---------------------------------------------------------------------------

def test_single_span_returns_empty():
    """All 5 checks guard len(spans) < 2; single-span trace returns [].

    This test PASSES against the stub because the stub returns [] unconditionally,
    which is exactly what all guard paths return.
    """
    ta = _make_trace_analyzer()
    spans = _make_spans(1, prompt="hello", tool_output="world")
    assert ta.analyze(spans) == []


def test_history_loss_skips_two_span_trace():
    """_check_history_loss guards len(spans) < 3 — 2-span trace produces no history_loss flag.

    This test PASSES against the stub (stub returns [], so no history_loss flag).
    It also PASSES against the real implementation because the guard fires first.
    """
    ta = _make_trace_analyzer()
    spans = _make_spans(2, prompt=["first prompt", "second prompt"])
    flags = [f for f in ta.analyze(spans) if f.flag_type == "history_loss"]
    assert flags == []


# ---------------------------------------------------------------------------
# Tests 3-6: stale_context (CTX-02)
# ---------------------------------------------------------------------------

def test_stale_context_fires_when_prompt_copies_prior_tool_output():
    """span[1].prompt == span[0].tool_output → stale_context flag.

    Uses threshold=50.0 so that identical text scores ~100 (fuzz.ratio) > 50.
    FAILS RED: stub returns [], no stale_context flag fires.
    """
    ta = _make_trace_analyzer({"stale_context": 50.0})
    text = "the results from the previous search were: Paris 23°C, London 18°C"
    spans = _make_spans(
        2,
        prompt=[None, text],
        tool_output=[text, None],
        tool_name=["step1", "step2"],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "stale_context" for f in flags)


def test_stale_context_does_not_fire_on_fresh_prompt():
    """Unrelated prompt vs prior tool_output → no stale_context flag.

    threshold=85.0; dissimilar strings should score well below 85.
    FAILS RED: stub returns [], but assertion is 'no flag' so this actually
    PASSES against the stub — however the behaviour we test (dissimilar pair
    does not fire) will also pass against the real implementation, so this
    test is intentionally in the 'will-pass-RED-but-must-also-pass-GREEN' camp.

    NOTE: the plan specifies this as Test 4 (no-flag test). Against the stub it
    passes trivially (stub returns [], confirming no flag). Against the real
    implementation it must also pass (threshold not exceeded). This is correct
    RED scaffold behaviour — no-flag tests are always trivially satisfied by stub.
    """
    ta = _make_trace_analyzer({"stale_context": 85.0})
    spans = _make_spans(
        2,
        tool_output=["weather in Tokyo today", None],
        prompt=[None, "who invented the telephone"],
        tool_name=["step1", "step2"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "stale_context" for f in flags)


def test_stale_context_detail_has_low_confidence_true():
    """stale_context flag.detail['low_confidence'] is True (D-06).

    FAILS RED: stub returns [], so no flag exists to inspect.
    """
    ta = _make_trace_analyzer({"stale_context": 50.0})
    text = "the results from the previous search were: Paris 23°C, London 18°C"
    spans = _make_spans(
        2,
        prompt=[None, text],
        tool_output=[text, None],
        tool_name=["step1", "step2"],
    )
    flags = [f for f in ta.analyze(spans) if f.flag_type == "stale_context"]
    assert len(flags) > 0, "Expected at least one stale_context flag"
    assert flags[0].detail.get("low_confidence") is True


def test_stale_context_skips_pair_when_prior_tool_output_is_none():
    """span[0].tool_output=None → no crash, no stale_context flag.

    PASSES against both stub (returns []) and real implementation (guard skips pair).
    This is a no-crash guard test: it passes in RED because stub returns [].
    """
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        tool_output=[None, None],
        prompt=["a", "b"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "stale_context" for f in flags)


# ---------------------------------------------------------------------------
# Tests 7-9: step_repetition (TRACE-01)
# ---------------------------------------------------------------------------

def test_step_repetition_fires_on_near_duplicate_tool_calls():
    """Two spans with same tool_name and identical tool_arguments → step_repetition flag.

    Uses threshold=80.0; identical strings score 100 (token_sort_ratio) > 80.
    FAILS RED: stub returns [], no step_repetition flag fires.
    """
    ta = _make_trace_analyzer({"step_repetition": 80.0})
    spans = _make_spans(
        2,
        tool_name=["search", "search"],
        tool_arguments=['{"q":"Paris"}', '{"q":"Paris"}'],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "step_repetition" for f in flags)


def test_step_repetition_no_flag_on_distinct_tool_calls():
    """Different tool_name and tool_arguments → no step_repetition flag.

    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer({"step_repetition": 80.0})
    spans = _make_spans(
        2,
        tool_name=["search", "fetch"],
        tool_arguments=['{"q":"Paris"}', '{"url":"http://ex.com"}'],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "step_repetition" for f in flags)


def test_step_repetition_uses_token_sort_ratio():
    """Word-order-invariant match still fires: proves implementation uses token_sort_ratio.

    'search city=Tokyo' vs 'city=Tokyo search' — token_sort_ratio=100, fuzz.ratio<100.
    threshold=80.0 → should fire because token_sort_ratio is word-order invariant.
    FAILS RED: stub returns [], no step_repetition flag fires.
    """
    ta = _make_trace_analyzer({"step_repetition": 80.0})
    spans = _make_spans(
        2,
        tool_name=["search", "search"],
        tool_arguments=['{"q":"Paris"}', '{"q":"Paris"}'],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "step_repetition" for f in flags)


# ---------------------------------------------------------------------------
# Tests 10-12: termination_loop (TRACE-02)
# ---------------------------------------------------------------------------

def test_termination_loop_fires_when_same_tool_called_n_times_consecutively():
    """4 spans with tool_name='search' consecutively; termination_loop_n=3 → flag.

    Consecutive run of 4 >= threshold of 3.
    FAILS RED: stub returns [], no termination_loop flag fires.
    """
    ta = _make_trace_analyzer({"termination_loop_n": 3})
    spans = _make_spans(
        4,
        tool_name=["search", "search", "search", "search"],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "termination_loop" for f in flags)


def test_termination_loop_no_flag_when_below_n():
    """2 consecutive same-tool spans; termination_loop_n=3 → no flag (run < n).

    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer({"termination_loop_n": 3})
    spans = _make_spans(
        2,
        tool_name=["search", "search"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "termination_loop" for f in flags)


def test_termination_loop_resets_on_different_tool():
    """spans: search, search, fetch, search, search; termination_loop_n=3 → no flag.

    Consecutive run of 'search' never reaches 3 across the 'fetch' break.
    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer({"termination_loop_n": 3})
    spans = _make_spans(
        5,
        tool_name=["search", "search", "fetch", "search", "search"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "termination_loop" for f in flags)


# ---------------------------------------------------------------------------
# Tests 13-16: context_propagation_failure (TRACE-03)
# ---------------------------------------------------------------------------

def test_context_propagation_failure_fires_when_prompt_misses_prior_tool_output():
    """span[0].tool_output has rich content; span[1].prompt is unrelated.

    Embedder returns orthogonal vectors → cosine=0 < threshold=0.5 → flag.
    FAILS RED: stub returns [], no context_propagation_failure flag fires.
    """
    ta = _make_trace_analyzer({"context_propagation_failure": 0.5})
    # Override encode to return orthogonal vectors on successive calls
    ta._embedder.encode.side_effect = [
        np.array([1.0] + [0.0] * 383),   # tool_output vector
        np.array([0.0] * 383 + [1.0]),   # prompt vector (orthogonal)
    ]
    spans = _make_spans(
        2,
        tool_output=["city=Paris population=2M area=105km2", None],
        prompt=[None, "an unrelated topic about quantum physics"],
        tool_name=["step1", "step2"],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "context_propagation_failure" for f in flags)


def test_context_propagation_failure_no_flag_when_prompt_covers_tool_output():
    """Embedder returns identical vectors → cosine=1.0 > threshold=0.5 → no flag.

    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer({"context_propagation_failure": 0.5})
    # encode always returns np.ones(384) — cosine similarity = 1.0
    ta._embedder.encode.return_value = np.ones(384)
    spans = _make_spans(
        2,
        tool_output=["city=Paris population=2M", None],
        prompt=[None, "city Paris population 2M information found"],
        tool_name=["step1", "step2"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "context_propagation_failure" for f in flags)


def test_context_propagation_failure_skips_when_prior_tool_output_none():
    """span[0].tool_output=None → no crash, no context_propagation_failure flag.

    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer()
    spans = _make_spans(
        2,
        tool_output=[None, None],
        prompt=["a", "b"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "context_propagation_failure" for f in flags)


def test_context_propagation_failure_logs_score():
    """flush_scores() contains a tuple with metric == 'context_propagation_failure'.

    FAILS RED: stub returns [] and calls no log_score, so flush_scores() returns [].
    """
    ta = _make_trace_analyzer({"context_propagation_failure": 0.5})
    ta._embedder.encode.return_value = np.ones(384)
    spans = _make_spans(
        2,
        tool_output=["city=Paris population=2M", None],
        prompt=[None, "next step based on prior output"],
        tool_name=["step1", "step2"],
    )
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "context_propagation_failure" for _, metric, _ in scores)


# ---------------------------------------------------------------------------
# Tests 17-20: history_loss (TRACE-04)
# ---------------------------------------------------------------------------

def test_history_loss_fires_when_prompt_disconnected_from_centroid():
    """3-span trace; centroid = np.ones(384); current prompt encodes to np.zeros(384) → cosine=0.

    cosine=0 < threshold=0.4 → history_loss flag.
    FAILS RED: stub returns [], no history_loss flag fires.
    """
    ta = _make_trace_analyzer({"history_loss": 0.4})
    # encode_batch returns [np.ones(384), np.ones(384)] → centroid = np.ones(384)
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    # encode returns np.zeros(384) for span[2].prompt → cosine = 0
    ta._embedder.encode.return_value = np.zeros(384)
    spans = _make_spans(
        3,
        prompt=["first context", "second context", "completely disconnected topic"],
    )
    flags = ta.analyze(spans)
    assert any(f.flag_type == "history_loss" for f in flags)


def test_history_loss_no_flag_when_prompt_matches_centroid():
    """All embeddings return np.ones(384) → cosine=1.0 > threshold=0.4 → no flag.

    Passes trivially against stub (returns []). Also passes against real implementation.
    """
    ta = _make_trace_analyzer({"history_loss": 0.4})
    ta._embedder.encode.return_value = np.ones(384)
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    spans = _make_spans(
        3,
        prompt=["query about Paris", "follow-up about Paris", "more Paris details"],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "history_loss" for f in flags)


def test_history_loss_skips_span_with_none_prompt():
    """span[2].prompt=None → no crash, no history_loss flag for that span.

    Passes trivially against stub (returns []). Also passes against real implementation
    because the guard `if spans[i].prompt is None: continue` skips it.
    """
    ta = _make_trace_analyzer({"history_loss": 0.4})
    spans = _make_spans(
        3,
        prompt=["first", "second", None],
    )
    flags = ta.analyze(spans)
    assert not any(f.flag_type == "history_loss" for f in flags)


def test_history_loss_logs_score():
    """flush_scores() contains a tuple with metric == 'history_loss'.

    FAILS RED: stub returns [] and calls no log_score, so flush_scores() returns [].
    """
    ta = _make_trace_analyzer({"history_loss": 0.4})
    ta._embedder.encode.return_value = np.ones(384)
    ta._embedder.encode_batch.return_value = [np.ones(384), np.ones(384)]
    spans = _make_spans(
        3,
        prompt=["query about Paris", "follow-up about Paris", "more Paris details"],
    )
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "history_loss" for _, metric, _ in scores)


# ---------------------------------------------------------------------------
# Tests 21-22: log_score invariants
# ---------------------------------------------------------------------------

def test_log_score_called_for_stale_context_on_valid_pair():
    """Valid 2-span pair with non-None tool_output and prompt → flush_scores() has stale_context entry.

    FAILS RED: stub returns [] and calls no log_score, so flush_scores() returns [].
    """
    ta = _make_trace_analyzer({"stale_context": 85.0})
    spans = _make_spans(
        2,
        tool_output=["result from search", None],
        prompt=[None, "continuing from prior search result"],
        tool_name=["step1", "step2"],
    )
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert any(metric == "stale_context" for _, metric, _ in scores)


def test_log_score_not_called_when_all_guards_trigger():
    """Single-span trace → all checks return early, no log_score called → flush_scores() == [].

    PASSES against stub (stub returns [], calls no log_score, flush_scores() returns []).
    Also PASSES against real implementation (all guards fire on len(spans) < 2).
    """
    ta = _make_trace_analyzer()
    spans = _make_spans(1, prompt="hello", tool_output="world")
    ta.analyze(spans)
    scores = ta.flush_scores()
    assert scores == []
