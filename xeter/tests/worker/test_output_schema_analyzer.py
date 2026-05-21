"""Unit tests for OutputSchemaAnalyzer — TDD RED phase.

All checks are deterministic; mock embedder is passed through constructor but
never called by any Phase 24 check method.
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import MagicMock

from xeter.services.worker.base import Flag, SpanData
from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "context_overflow": 8000,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_embedder():
    """Return a MagicMock embedder. Phase 24 checks never call self.embed()."""
    return MagicMock()


def make_span(**kwargs) -> SpanData:
    """Return a minimal SpanData with sensible defaults overridable by kwargs."""
    defaults = dict(
        span_id="span-1",
        tenant_id="tenant-1",
        trace_id="trace-1",
        agent_name="test-agent",
        agent_model="gpt-4o",
        tool_name=None,
        tool_description=None,
        tool_arguments=None,
        tool_output=None,
        prompt=None,
        response=None,
        raw_response=None,
        available_tools=None,
        expected_output_schema=None,
        parent_span_id=None,
    )
    defaults.update(kwargs)
    return SpanData(**defaults)


def make_analyzer(thresholds=None) -> OutputSchemaAnalyzer:
    """Construct an OutputSchemaAnalyzer with a mock embedder."""
    return OutputSchemaAnalyzer(
        make_mock_embedder(),
        thresholds if thresholds is not None else dict(DEFAULT_THRESHOLDS),
    )


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

def test_name_property_returns_output_schema():
    analyzer = make_analyzer()
    assert analyzer.name == "output_schema"


def test_analyze_returns_list_on_empty_span():
    analyzer = make_analyzer()
    result = analyzer.analyze(make_span())
    assert isinstance(result, list)


def test_constructor_accepts_embedder_and_thresholds():
    """D-06: OutputSchemaAnalyzer(embedder, thresholds) constructs without error; embedder is unused."""
    OutputSchemaAnalyzer(MagicMock(), {"context_overflow": 8000})


# ---------------------------------------------------------------------------
# SCHEMA-01: output_schema_violation (sub-case A only per D-01)
# ---------------------------------------------------------------------------

def test_schema_01_fires_when_schema_set_and_response_not_json():
    """SCHEMA-01 fires when expected_output_schema is set and response is not valid JSON."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        response="this is plain text not json",
    )
    flags = analyzer.analyze(span)
    violation_flags = [f for f in flags if f.flag_type == "output_schema_violation"]
    assert len(violation_flags) == 1


def test_schema_01_does_not_fire_when_schema_none():
    """SCHEMA-01 does not fire when expected_output_schema is None."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=None,
        response="this is plain text",
    )
    flags = analyzer.analyze(span)
    violation_flags = [f for f in flags if f.flag_type == "output_schema_violation"]
    assert len(violation_flags) == 0


def test_schema_01_does_not_fire_when_response_is_valid_json():
    """SCHEMA-01 does not fire when the response is valid JSON."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        response='{"key": "value"}',
    )
    flags = analyzer.analyze(span)
    violation_flags = [f for f in flags if f.flag_type == "output_schema_violation"]
    assert len(violation_flags) == 0


def test_schema_01_does_not_fire_when_response_none():
    """SCHEMA-01 does not fire when response is None (guard: no response to validate)."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        response=None,
    )
    flags = analyzer.analyze(span)
    violation_flags = [f for f in flags if f.flag_type == "output_schema_violation"]
    assert len(violation_flags) == 0


def test_schema_01_log_score_clean_path():
    """D-04: log_score records 0.0 for output_schema_violation on a clean (valid JSON) span."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        response='{"key": "value"}',
    )
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert ("output_schema", "output_schema_violation", 0.0) in scores


# ---------------------------------------------------------------------------
# SCHEMA-02: required_fields_missing
# ---------------------------------------------------------------------------

def test_schema_02_fires_when_required_field_missing():
    """SCHEMA-02 fires when tool_arguments is missing a required field from the schema."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "required": ["query", "limit"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }),
        tool_arguments='{"limit": 10}',
    )
    flags = analyzer.analyze(span)
    missing_flags = [f for f in flags if f.flag_type == "required_fields_missing"]
    assert len(missing_flags) == 1
    assert "missing_fields" in missing_flags[0].detail
    assert len(missing_flags[0].detail["missing_fields"]) > 0


def test_schema_02_does_not_fire_when_all_required_present():
    """SCHEMA-02 does not fire when all required fields are present in tool_arguments."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
            },
        }),
        tool_arguments='{"query": "python"}',
    )
    flags = analyzer.analyze(span)
    missing_flags = [f for f in flags if f.flag_type == "required_fields_missing"]
    assert len(missing_flags) == 0
    scores = analyzer.flush_scores()
    assert ("output_schema", "required_fields_missing", 0.0) in scores


def test_schema_02_does_not_fire_when_schema_or_args_none():
    """SCHEMA-02 does not fire when schema or tool_arguments is None (early-exit guard)."""
    analyzer1 = make_analyzer()
    span_no_schema = make_span(
        expected_output_schema=None,
        tool_arguments='{"query": "x"}',
    )
    flags1 = analyzer1.analyze(span_no_schema)
    missing_flags1 = [f for f in flags1 if f.flag_type == "required_fields_missing"]
    assert len(missing_flags1) == 0

    analyzer2 = make_analyzer()
    span_no_args = make_span(
        expected_output_schema='{"type": "object", "required": ["query"]}',
        tool_arguments=None,
    )
    flags2 = analyzer2.analyze(span_no_args)
    missing_flags2 = [f for f in flags2 if f.flag_type == "required_fields_missing"]
    assert len(missing_flags2) == 0


def test_schema_02_does_not_fire_on_malformed_schema_json():
    """SCHEMA-02 does not fire when expected_output_schema is not valid JSON (early return)."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema="{not valid json",
        tool_arguments='{"query": "x"}',
    )
    flags = analyzer.analyze(span)
    missing_flags = [f for f in flags if f.flag_type == "required_fields_missing"]
    assert len(missing_flags) == 0


# ---------------------------------------------------------------------------
# SCHEMA-04: type_coercion_error
# ---------------------------------------------------------------------------

def test_schema_04_fires_when_number_passed_as_string():
    """SCHEMA-04 fires when a field that should be integer is passed as a string."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }),
        tool_arguments='{"count": "5"}',
    )
    flags = analyzer.analyze(span)
    type_flags = [f for f in flags if f.flag_type == "type_coercion_error"]
    assert len(type_flags) == 1
    assert "type_errors" in type_flags[0].detail
    assert len(type_flags[0].detail["type_errors"]) > 0


def test_schema_04_fires_when_boolean_passed_as_integer():
    """SCHEMA-04 fires when a field that should be boolean is passed as an integer."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "properties": {
                "flag": {"type": "boolean"},
            },
        }),
        tool_arguments='{"flag": 1}',
    )
    flags = analyzer.analyze(span)
    type_flags = [f for f in flags if f.flag_type == "type_coercion_error"]
    assert len(type_flags) == 1


def test_schema_04_does_not_fire_when_types_correct():
    """SCHEMA-04 does not fire when all types in tool_arguments match the schema."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }),
        tool_arguments='{"count": 5}',
    )
    flags = analyzer.analyze(span)
    type_flags = [f for f in flags if f.flag_type == "type_coercion_error"]
    assert len(type_flags) == 0
    scores = analyzer.flush_scores()
    assert ("output_schema", "type_coercion_error", 0.0) in scores


def test_schema_02_and_schema_04_co_fire_independently():
    """Pitfall 2: SCHEMA-02 and SCHEMA-04 must both fire when span has missing AND wrong-type fields."""
    analyzer = make_analyzer()
    # Schema requires "query" (string) and "limit" (integer).
    # tool_arguments is missing "query" entirely AND has "limit" as wrong type.
    span = make_span(
        expected_output_schema=json.dumps({
            "type": "object",
            "required": ["query", "limit"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        }),
        tool_arguments='{"limit": "ten"}',  # missing "query", "limit" is wrong type
    )
    flags = analyzer.analyze(span)
    flag_types = {f.flag_type for f in flags}
    assert "required_fields_missing" in flag_types
    assert "type_coercion_error" in flag_types


# ---------------------------------------------------------------------------
# CTX-01: context_overflow
# ---------------------------------------------------------------------------

def test_ctx_01_fires_when_tokens_exceed_threshold():
    """CTX-01 fires when prompt token count exceeds the context_overflow threshold."""
    analyzer = make_analyzer(thresholds={"context_overflow": 1000})
    long_prompt = "word " * 5000  # well over 1000 cl100k tokens
    span = make_span(prompt=long_prompt)
    flags = analyzer.analyze(span)
    overflow_flags = [f for f in flags if f.flag_type == "context_overflow"]
    assert len(overflow_flags) == 1
    detail = overflow_flags[0].detail
    assert detail.get("metric") == "prompt_token_count"
    assert isinstance(detail.get("token_count"), int)
    assert detail["token_count"] > 1000
    assert detail.get("threshold") == 1000


def test_ctx_01_does_not_fire_when_tokens_under_threshold():
    """CTX-01 does not fire when prompt is well under the threshold."""
    analyzer = make_analyzer(thresholds={"context_overflow": 8000})
    span = make_span(prompt="short prompt")
    flags = analyzer.analyze(span)
    overflow_flags = [f for f in flags if f.flag_type == "context_overflow"]
    assert len(overflow_flags) == 0


def test_ctx_01_does_not_fire_when_prompt_none():
    """CTX-01 does not fire when prompt is None (early-exit guard)."""
    analyzer = make_analyzer()
    span = make_span(prompt=None)
    flags = analyzer.analyze(span)
    overflow_flags = [f for f in flags if f.flag_type == "context_overflow"]
    assert len(overflow_flags) == 0


def test_ctx_01_log_score_records_token_count_on_clean_span():
    """D-04: log_score records the actual numeric token count (not 0.0) on a clean span."""
    analyzer = make_analyzer(thresholds={"context_overflow": 8000})
    span = make_span(prompt="short prompt")
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    # Find prompt_token_count entry
    token_scores = [s for s in scores if s[0] == "output_schema" and s[1] == "prompt_token_count"]
    assert len(token_scores) == 1
    token_count_logged = token_scores[0][2]
    # Must be the actual count (not 0.0 — the numeric count IS the calibration signal)
    assert isinstance(token_count_logged, float)
    assert token_count_logged > 0.0


def test_ctx_01_log_score_records_token_count_on_fired_span():
    """D-04: log_score records the token count > threshold when the flag fires."""
    analyzer = make_analyzer(thresholds={"context_overflow": 1000})
    span = make_span(prompt="word " * 5000)
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    token_scores = [s for s in scores if s[0] == "output_schema" and s[1] == "prompt_token_count"]
    assert len(token_scores) == 1
    assert token_scores[0][2] > 1000.0


# ---------------------------------------------------------------------------
# SCHEMA-03: output_truncated
# ---------------------------------------------------------------------------

def test_schema_03_fires_on_openai_finish_reason_length():
    """SCHEMA-03 fires when raw_response contains OpenAI finish_reason=length."""
    analyzer = make_analyzer()
    span = make_span(
        raw_response=json.dumps({"choices": [{"finish_reason": "length"}]}),
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 1


def test_schema_03_fires_on_anthropic_stop_reason_max_tokens():
    """Pitfall 4: SCHEMA-03 fires when raw_response contains Anthropic stop_reason=max_tokens."""
    analyzer = make_analyzer()
    span = make_span(
        raw_response=json.dumps({"stop_reason": "max_tokens"}),
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 1


def test_schema_03_fires_on_unclosed_delimiter_in_response():
    """SCHEMA-03 fires when response has an unclosed JSON delimiter (truncation heuristic)."""
    analyzer = make_analyzer()
    span = make_span(
        response='{"key": "value", "list": [1, 2',  # opens { and [ but not closed
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 1


def test_schema_03_fires_on_unclosed_delimiter_in_tool_arguments():
    """SCHEMA-03 fires when tool_arguments has an unclosed JSON delimiter."""
    analyzer = make_analyzer()
    span = make_span(
        tool_arguments='{"query": "python typing',  # unclosed string+object
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 1


def test_schema_03_does_not_fire_on_malformed_but_closed_json():
    """Pitfall 3: SCHEMA-03 does NOT fire on malformed JSON that still ends with a closing delimiter."""
    analyzer = make_analyzer()
    # This is malformed JSON (undefined is not valid) but ends with }
    span = make_span(response='{"key": undefined}')
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 0


def test_schema_03_does_not_fire_when_finish_reason_stop():
    """SCHEMA-03 does not fire when finish_reason=stop (normal completion)."""
    analyzer = make_analyzer()
    span = make_span(
        raw_response=json.dumps({"choices": [{"finish_reason": "stop"}]}),
        response='{"valid": "json"}',
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 0
    scores = analyzer.flush_scores()
    assert ("output_schema", "output_truncated", 0.0) in scores


def test_schema_03_does_not_fire_on_malformed_raw_response():
    """Guard: SCHEMA-03 does not crash or fire when raw_response is not valid JSON."""
    analyzer = make_analyzer()
    span = make_span(
        raw_response="not valid json at all",
        response='{"valid": "json"}',
    )
    flags = analyzer.analyze(span)
    truncated_flags = [f for f in flags if f.flag_type == "output_truncated"]
    assert len(truncated_flags) == 0
    scores = analyzer.flush_scores()
    assert ("output_schema", "output_truncated", 0.0) in scores


# ---------------------------------------------------------------------------
# log_score invariant tests (D-04)
# ---------------------------------------------------------------------------

def test_log_score_records_all_four_binary_metrics_on_clean_span():
    """D-04: All 4 binary metrics plus prompt_token_count logged for a fully clean span."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        tool_arguments="{}",
        response="{}",
        raw_response=json.dumps({"choices": [{"finish_reason": "stop"}]}),
        prompt="short",
    )
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    score_map = {(s[1], s[2]) for s in scores if s[0] == "output_schema"}

    assert ("output_schema_violation", 0.0) in score_map
    assert ("required_fields_missing", 0.0) in score_map
    assert ("output_truncated", 0.0) in score_map
    assert ("type_coercion_error", 0.0) in score_map
    # prompt_token_count must also be present (any positive float)
    token_entries = [s for s in scores if s[0] == "output_schema" and s[1] == "prompt_token_count"]
    assert len(token_entries) == 1
    assert token_entries[0][2] > 0.0


def test_log_score_records_metric_on_fired_check():
    """D-04: log_score records 1.0 for output_schema_violation when the check fires."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema='{"type": "object"}',
        response="plain text not json",
    )
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert ("output_schema", "output_schema_violation", 1.0) in scores


def test_early_guards_do_not_log_score():
    """D-04: When all SpanData fields are None, no log_score entries are recorded (early-exit guards)."""
    analyzer = make_analyzer()
    span = make_span(
        expected_output_schema=None,
        response=None,
        tool_arguments=None,
        raw_response=None,
        prompt=None,
    )
    analyzer.analyze(span)
    scores = analyzer.flush_scores()
    assert scores == []
