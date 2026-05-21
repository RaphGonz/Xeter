"""Tests for FLAG_TYPE_TO_ANALYZER_CLASS registry and recall floor guard.

Plan: 23-03 (Task 1 — Tests 1-6 + Task 2 — Tests 7-10)
"""

from __future__ import annotations

import inspect
import sys
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Task 1: FLAG_TYPE_TO_ANALYZER_CLASS registry (Tests 1-6)
# ---------------------------------------------------------------------------

def test_1_registry_has_exactly_12_keys():
    """FLAG_TYPE_TO_ANALYZER_CLASS is a dict with exactly 12 keys (7 ToolCallAnalyzer + 5 OutputSchemaAnalyzer) matching FLAG_TYPES."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS, FLAG_TYPES
    assert isinstance(FLAG_TYPE_TO_ANALYZER_CLASS, dict)
    assert set(FLAG_TYPE_TO_ANALYZER_CLASS.keys()) == set(FLAG_TYPES)
    assert len(FLAG_TYPE_TO_ANALYZER_CLASS) == 12


def test_2_existing_7_keys_still_map_to_tool_call_analyzer():
    """All 7 pre-Phase-24 keys in FLAG_TYPE_TO_ANALYZER_CLASS still map to the ToolCallAnalyzer class (no regression)."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS
    from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
    EXPECTED_TOOL_CALL_KEYS = {
        "tool_not_available",
        "wrong_tool_choice",
        "unnecessary_tool_call",
        "wrong_tool_args",
        "no_tool",
        "parsing_error",
        "response_anomaly",
    }
    for key in EXPECTED_TOOL_CALL_KEYS:
        assert FLAG_TYPE_TO_ANALYZER_CLASS[key] is ToolCallAnalyzer


def test_3_wrong_tool_args_maps_to_tool_call_analyzer():
    """FLAG_TYPE_TO_ANALYZER_CLASS['wrong_tool_args'] is ToolCallAnalyzer."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS
    from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
    assert FLAG_TYPE_TO_ANALYZER_CLASS["wrong_tool_args"] is ToolCallAnalyzer


def test_4_response_anomaly_maps_to_tool_call_analyzer():
    """FLAG_TYPE_TO_ANALYZER_CLASS['response_anomaly'] is ToolCallAnalyzer."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS
    from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
    assert FLAG_TYPE_TO_ANALYZER_CLASS["response_anomaly"] is ToolCallAnalyzer


def test_5_evaluate_flag_type_has_no_inline_import():
    """evaluate_flag_type() source does NOT contain the inline ToolCallAnalyzer import."""
    from xeter.scripts.calibrate import evaluate_flag_type
    source = inspect.getsource(evaluate_flag_type)
    assert "from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer" not in source, (
        "evaluate_flag_type() still contains a hardcoded inline import. "
        "The import must be at module level via the registry."
    )


def test_6_registry_lookup_is_used_by_evaluate_flag_type(monkeypatch):
    """Adding a mock class to FLAG_TYPE_TO_ANALYZER_CLASS causes evaluate_flag_type() to
    instantiate that mock class instead of ToolCallAnalyzer.
    """
    import xeter.scripts.calibrate as calibrate_mod

    # Build a mock analyzer instance that mimics ToolCallAnalyzer's interface
    mock_instance = MagicMock()
    mock_instance.analyze.return_value = []
    mock_instance.flush_scores.return_value = []

    # Build a mock analyzer class that returns our mock instance
    mock_cls = MagicMock(return_value=mock_instance)

    # Patch the registry so "wrong_tool_args" → mock_cls
    patched_registry = dict(calibrate_mod.FLAG_TYPE_TO_ANALYZER_CLASS)
    patched_registry["wrong_tool_args"] = mock_cls
    monkeypatch.setattr(calibrate_mod, "FLAG_TYPE_TO_ANALYZER_CLASS", patched_registry)

    # Build a minimal embedder mock
    mock_embedder = MagicMock()

    # One span with anomaly_type that will NOT match "wrong_tool_args" (clean span)
    # so we just need evaluate_flag_type to run and instantiate the analyzer
    spans = [
        {
            "span_id": "test-span-1",
            "anomaly_types": ["no_tool"],
            "label": "flagged",
            "prompt": "test prompt",
            "tool_name": "some_tool",
            "available_tools": [],
            "tool_arguments": None,
            "tool_output": None,
            "response": "test response",
            "raw_response": None,
            "tool_description": None,
            "expected_output_schema": None,
            "parent_span_id": None,
        }
    ]

    calibrate_mod.evaluate_flag_type(
        flag_type="wrong_tool_args",
        threshold=0.5,
        spans=spans,
        embedder=mock_embedder,
        current_thresholds={"wrong_tool_args": 0.5},
    )

    # The mock class must have been instantiated (registry was consulted)
    mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# Task 2: Recall floor guard (Tests 7-10)
# ---------------------------------------------------------------------------

def _invoke_recall_floor(flag_type: str, best_recall: float):
    """Call the actual _check_recall_floor() from calibrate.py.

    This ensures tests exercise the real implementation, not a copy.
    """
    from xeter.scripts.calibrate import _check_recall_floor
    _check_recall_floor(flag_type, best_recall)


def test_7_recall_floor_triggers_exit_when_recall_below_floor():
    """_check_recall_floor with best_recall=0.05 causes sys.exit(1) (recall < 0.10)."""
    with pytest.raises(SystemExit) as exc_info:
        _invoke_recall_floor("wrong_tool_args", 0.05)
    assert exc_info.value.code == 1


def test_8_recall_floor_no_exit_at_exactly_floor():
    """_check_recall_floor with best_recall=0.10 does NOT call sys.exit(1) (at floor — acceptable)."""
    # Should not raise
    _invoke_recall_floor("wrong_tool_args", 0.10)


def test_9_recall_floor_no_exit_above_floor():
    """_check_recall_floor with best_recall=0.50 does NOT call sys.exit(1) (well above floor)."""
    # Should not raise
    _invoke_recall_floor("wrong_tool_args", 0.50)


def test_10_recall_floor_error_message_contains_flag_type_and_recall(capsys):
    """When sys.exit(1) is triggered, stdout contains flag_type name and 'recall'/'RECALL'."""
    with pytest.raises(SystemExit):
        _invoke_recall_floor("wrong_tool_args", 0.05)

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "wrong_tool_args" in output, (
        f"Expected flag_type 'wrong_tool_args' in output but got: {output!r}"
    )
    assert "recall" in output.lower(), (
        f"Expected 'recall' (case-insensitive) in output but got: {output!r}"
    )


# ---------------------------------------------------------------------------
# Phase 24: OutputSchemaAnalyzer routing (Tests 11-15)
# ---------------------------------------------------------------------------

def test_11_output_schema_checks_map_to_output_schema_analyzer():
    """All 5 Phase 24 flag types route to OutputSchemaAnalyzer via the registry."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS
    from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer
    for flag_type in [
        "output_schema_violation",
        "required_fields_missing",
        "output_truncated",
        "type_coercion_error",
        "context_overflow",
    ]:
        assert FLAG_TYPE_TO_ANALYZER_CLASS[flag_type] is OutputSchemaAnalyzer


def test_12_binary_flag_types_includes_4_phase_24_schema_checks():
    """BINARY_FLAG_TYPES contains the 4 deterministic Phase 24 schema checks (excludes context_overflow)."""
    from xeter.scripts.calibrate import BINARY_FLAG_TYPES
    for flag_type in [
        "output_schema_violation",
        "required_fields_missing",
        "output_truncated",
        "type_coercion_error",
    ]:
        assert flag_type in BINARY_FLAG_TYPES


def test_13_context_overflow_not_in_binary_flag_types():
    """context_overflow is threshold-tunable per D-05 — must NOT appear in BINARY_FLAG_TYPES."""
    from xeter.scripts.calibrate import BINARY_FLAG_TYPES
    assert "context_overflow" not in BINARY_FLAG_TYPES


def test_14_context_overflow_in_default_thresholds():
    """DEFAULT_THRESHOLDS contains context_overflow at the D-03 default value of 8000."""
    from xeter.scripts.calibrate import DEFAULT_THRESHOLDS
    assert "context_overflow" in DEFAULT_THRESHOLDS
    assert DEFAULT_THRESHOLDS["context_overflow"] == 8000


def test_15_flag_types_list_has_12_entries():
    """FLAG_TYPES list has exactly 12 entries after Phase 24 — required so calibrate.py main() iterates over all new flag types."""
    from xeter.scripts.calibrate import FLAG_TYPES
    assert len(FLAG_TYPES) == 12
    for flag_type in [
        "output_schema_violation",
        "required_fields_missing",
        "output_truncated",
        "type_coercion_error",
        "context_overflow",
    ]:
        assert flag_type in FLAG_TYPES
