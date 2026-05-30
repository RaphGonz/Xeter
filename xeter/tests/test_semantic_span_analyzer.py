# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Tests for SemanticSpanAnalyzer — missing_details check.

Plan: 25-01

All 10 tests in this file MUST fail RED (ImportError or AttributeError) until
Plan 25-03 creates xeter/services/worker/semantic_span_analyzer.py.
Production imports are deferred inside helper functions and test bodies so that
pytest collection succeeds even when the module does not exist.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Test helpers (no top-level production imports)
# ---------------------------------------------------------------------------


def _minimal_span(**kwargs):
    """Construct a SpanData with required positional fields and optional overrides.

    SpanData import is deferred so pytest collection succeeds before the
    production module tree is complete.
    """
    from xeter.services.worker.base import SpanData  # noqa: PLC0415

    defaults = dict(
        span_id="s1",
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
    defaults.update(kwargs)
    return SpanData(**defaults)


def _mock_embedder(vector=None):
    """Create a MagicMock embedder that returns a fixed or supplied numpy vector."""
    mock = MagicMock()
    vec = vector if vector is not None else np.ones(384)
    mock.encode.return_value = vec
    mock.encode_batch.return_value = [vec]
    return mock


def _make_analyzer(threshold=0.6, embedder=None):
    """Instantiate SemanticSpanAnalyzer with the given threshold and embedder.

    Import is deferred — this function must not be called at module level.
    """
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer  # noqa: PLC0415

    return SemanticSpanAnalyzer(
        embedder if embedder is not None else _mock_embedder(),
        {"missing_details": threshold},
    )


# ---------------------------------------------------------------------------
# Test 1: Guard path — prompt is None
# ---------------------------------------------------------------------------


def test_missing_details_no_flag_when_prompt_is_none():
    """Guard path: prompt=None → analyze() returns []; flush_scores() returns [].

    No log_score call on guard exit (D-04 invariant).
    """
    analyzer = _make_analyzer()
    span = _minimal_span(prompt=None, response="ok")
    flags = analyzer.analyze(span)
    assert flags == []
    scores = analyzer.flush_scores()
    assert scores == []


# ---------------------------------------------------------------------------
# Test 2: Guard path — response is None
# ---------------------------------------------------------------------------


def test_missing_details_no_flag_when_response_is_none():
    """Guard path: response=None → analyze() returns []; flush_scores() returns [].

    No log_score call on guard exit (D-04 invariant).
    """
    analyzer = _make_analyzer()
    span = _minimal_span(prompt="explain X", response=None)
    flags = analyzer.analyze(span)
    assert flags == []
    scores = analyzer.flush_scores()
    assert scores == []


# ---------------------------------------------------------------------------
# Test 3: log_score invariant — score is always recorded before threshold check
# ---------------------------------------------------------------------------


def test_missing_details_logs_score_before_threshold_check():
    """log_score is called with metric='missing_details' before threshold comparison.

    Uses embedder returning identical vectors (cosine=1.0, high bow) so no flag
    fires, but flush_scores() must still contain a 'missing_details' entry.
    flush_scores() returns tuples of (analyzer_name, metric_name, score).
    """
    embedder = _mock_embedder(vector=np.ones(384))
    analyzer = _make_analyzer(threshold=0.6, embedder=embedder)
    span = _minimal_span(prompt="explain X", response="I explained X")
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert any(metric == "missing_details" for _, metric, _ in scores), (
        "flush_scores() must contain a 'missing_details' entry regardless of flag outcome"
    )


# ---------------------------------------------------------------------------
# Test 4: Flag fires when score is below threshold
# ---------------------------------------------------------------------------


def test_missing_details_returns_flag_when_score_below_threshold():
    """Orthogonal vectors force cosine=0; low bow → hybrid score ~0 < 0.6 → flag.

    encode.side_effect provides two different orthogonal vectors (one per call).
    """
    embedder = _mock_embedder()
    embedder.encode.side_effect = [
        np.array([1.0] * 192 + [0.0] * 192),
        np.array([0.0] * 192 + [1.0] * 192),
    ]
    analyzer = _make_analyzer(threshold=0.6, embedder=embedder)
    span = _minimal_span(
        prompt="explain step by step how X works in detail",
        response="unrelated",
    )
    flags = analyzer.analyze(span)
    assert any(f.flag_type == "missing_details" for f in flags), (
        "Expected a 'missing_details' flag for orthogonal vectors below threshold"
    )


# ---------------------------------------------------------------------------
# Test 5: No flag when score is above threshold
# ---------------------------------------------------------------------------


def test_missing_details_no_flag_when_score_above_threshold():
    """Identical vectors force cosine=1.0; identical text → bow=1.0 → hybrid=1.0 > 0.6 → no flag."""
    embedder = _mock_embedder(vector=np.ones(384))
    embedder.encode.return_value = np.ones(384)
    analyzer = _make_analyzer(threshold=0.6, embedder=embedder)
    identical_text = "the model explains the detailed steps"
    span = _minimal_span(prompt=identical_text, response=identical_text)
    flags = analyzer.analyze(span)
    assert flags == [], (
        "Expected no flag when cosine=1.0 and bow=1.0 both exceed threshold 0.6"
    )


# ---------------------------------------------------------------------------
# Test 6: Flag detail always contains "metric" key
# ---------------------------------------------------------------------------


def test_missing_details_flag_has_metric_key():
    """Every Flag returned by _check_missing_details must have 'metric' in detail."""
    embedder = _mock_embedder()
    embedder.encode.side_effect = [
        np.array([1.0] * 192 + [0.0] * 192),
        np.array([0.0] * 192 + [1.0] * 192),
    ]
    analyzer = _make_analyzer(threshold=0.6, embedder=embedder)
    span = _minimal_span(
        prompt="explain step by step how X works in detail",
        response="unrelated",
    )
    flags = analyzer.analyze(span)
    missing_detail_flags = [f for f in flags if f.flag_type == "missing_details"]
    assert missing_detail_flags, "Expected at least one 'missing_details' flag"
    for flag in missing_detail_flags:
        assert "metric" in flag.detail, (
            f"Flag.detail is missing 'metric' key: {flag.detail}"
        )


# ---------------------------------------------------------------------------
# Test 7: Flag detail contains "cosine" and "bow" keys
# ---------------------------------------------------------------------------


def test_missing_details_flag_has_cosine_and_bow_keys():
    """Flag.detail must have both 'cosine' and 'bow' keys for calibration transparency."""
    embedder = _mock_embedder()
    embedder.encode.side_effect = [
        np.array([1.0] * 192 + [0.0] * 192),
        np.array([0.0] * 192 + [1.0] * 192),
    ]
    analyzer = _make_analyzer(threshold=0.6, embedder=embedder)
    span = _minimal_span(
        prompt="explain step by step how X works in detail",
        response="unrelated",
    )
    flags = analyzer.analyze(span)
    missing_detail_flags = [f for f in flags if f.flag_type == "missing_details"]
    assert missing_detail_flags, "Expected at least one 'missing_details' flag"
    for flag in missing_detail_flags:
        assert "cosine" in flag.detail, (
            f"Flag.detail is missing 'cosine' key: {flag.detail}"
        )
        assert "bow" in flag.detail, (
            f"Flag.detail is missing 'bow' key: {flag.detail}"
        )


# ---------------------------------------------------------------------------
# Test 8: name property
# ---------------------------------------------------------------------------


def test_semantic_span_analyzer_name_property():
    """SemanticSpanAnalyzer(embedder, {}).name must return 'semantic_span'."""
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer  # noqa: PLC0415

    analyzer = SemanticSpanAnalyzer(_mock_embedder(), {})
    assert analyzer.name == "semantic_span", (
        f"Expected name='semantic_span', got '{analyzer.name}'"
    )


# ---------------------------------------------------------------------------
# Test 9: analyze() dispatches to _check_missing_details
# ---------------------------------------------------------------------------


def test_analyze_dispatches_to_check_missing_details():
    """analyze() must call _check_missing_details exactly once per invocation."""
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer  # noqa: PLC0415

    analyzer = SemanticSpanAnalyzer(_mock_embedder(), {"missing_details": 0.6})
    span = _minimal_span(prompt="explain X", response="I explained X")

    with patch.object(
        analyzer,
        "_check_missing_details",
        wraps=analyzer._check_missing_details,
    ) as spy:
        analyzer.analyze(span)
        spy.assert_called_once_with(span)


# ---------------------------------------------------------------------------
# Test 10: Threshold is not hardcoded — threshold dict controls flag outcome
# ---------------------------------------------------------------------------


def test_missing_details_uses_thresholds_dict_not_literal():
    """Threshold 0.99 forces flag on moderate-similarity span; 0.0 suppresses it.

    Uses vectors with cosine ~0.5 (not orthogonal, not identical). This proves
    no hardcoded numeric literal exists in the check method — only
    self._thresholds["missing_details"] is consulted.
    """
    from xeter.services.worker.semantic_span_analyzer import SemanticSpanAnalyzer  # noqa: PLC0415

    # Moderate-similarity vectors: cosine ~0.5
    vec_a = np.array([1.0] * 192 + [0.0] * 192, dtype=float)
    vec_b = np.array([1.0] * 96 + [0.0] * 96 + [1.0] * 96 + [0.0] * 96, dtype=float)

    # Normalise so compare() returns a true cosine (not dot product of large norms)
    vec_a = vec_a / np.linalg.norm(vec_a)
    vec_b = vec_b / np.linalg.norm(vec_b)

    def _build_embedder():
        emb = _mock_embedder()
        emb.encode.side_effect = [vec_a.copy(), vec_b.copy()]
        return emb

    # With threshold=0.99 → score (well below 0.99) → flag fires
    analyzer_high = SemanticSpanAnalyzer(_build_embedder(), {"missing_details": 0.99})
    span_high = _minimal_span(
        prompt="describe the procedure in full technical detail",
        response="brief answer",
    )
    flags_high = analyzer_high.analyze(span_high)
    assert any(f.flag_type == "missing_details" for f in flags_high), (
        "Expected flag when threshold=0.99 and hybrid score is well below 0.99"
    )

    # With threshold=0.0 → any score ≥ 0.0 → no flag
    analyzer_low = SemanticSpanAnalyzer(_build_embedder(), {"missing_details": 0.0})
    span_low = _minimal_span(
        prompt="describe the procedure in full technical detail",
        response="brief answer",
    )
    flags_low = analyzer_low.analyze(span_low)
    assert not any(f.flag_type == "missing_details" for f in flags_low), (
        "Expected no flag when threshold=0.0 (any score satisfies the condition)"
    )
