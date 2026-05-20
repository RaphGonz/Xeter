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

def test_1_registry_has_exactly_7_keys():
    """FLAG_TYPE_TO_ANALYZER_CLASS is a dict with exactly 7 keys matching FLAG_TYPES."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS, FLAG_TYPES
    assert isinstance(FLAG_TYPE_TO_ANALYZER_CLASS, dict)
    assert set(FLAG_TYPE_TO_ANALYZER_CLASS.keys()) == set(FLAG_TYPES)
    assert len(FLAG_TYPE_TO_ANALYZER_CLASS) == 7


def test_2_all_values_are_tool_call_analyzer_class():
    """All 7 values in FLAG_TYPE_TO_ANALYZER_CLASS are the ToolCallAnalyzer class (not an instance)."""
    from xeter.scripts.calibrate import FLAG_TYPE_TO_ANALYZER_CLASS
    from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
    for key, value in FLAG_TYPE_TO_ANALYZER_CLASS.items():
        assert value is ToolCallAnalyzer, (
            f"Expected FLAG_TYPE_TO_ANALYZER_CLASS[{key!r}] to be the ToolCallAnalyzer "
            f"class, got {value!r}"
        )


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
