# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Unit tests for context_assembly module in the Diagnosticer service.

Covers:
  - test_substitution_includes_span_fields: _format_context with stub span + empty flags returns
    string containing each provided span value and "(no flags)".
  - test_substitution_renders_flags: _format_context with non-empty flags returns string with
    "type=", "score=", and "detail=" for each flag.
  - test_payload_text_interpolated: prompt_text and response_text appear verbatim in output.
  - test_template_read_at_import: module exposes _PROMPT_TEMPLATE as a non-empty str.
  - test_missing_prompt_file_raises: re-importing the module with prompt.md unreadable raises
    FileNotFoundError.
"""

from __future__ import annotations

import importlib
import unittest.mock
from unittest.mock import MagicMock

import pytest

from xeter.services.diagnosticer import context_assembly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_span(**kwargs) -> dict:
    """Return a minimal span dict with sane defaults."""
    defaults = {
        "span_id": "span-001",
        "trace_id": "trace-001",
        "agent_name": "test-agent",
        "agent_model": "test-model",
        "tool_name": "test-tool",
        "tool_description": "A test tool",
        "tool_arguments": "{}",
        "tool_output": "result",
        "time_begin": "2026-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


def _make_stub_flag(flag_type: str = "wrong_tool", score: float = 0.85, detail: dict | None = None) -> MagicMock:
    """Return a MagicMock with Flag-compatible attributes."""
    flag = MagicMock()
    flag.flag_type = flag_type
    flag.score = score
    flag.detail = detail
    return flag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatContext:
    """Tests for _format_context."""

    def test_substitution_includes_span_fields(self):
        """_format_context with a stub span and empty flags returns string with all span values."""
        span = _make_stub_span()
        result = context_assembly._format_context(span, [], "PROMPT_TEXT", "RESPONSE_TEXT")

        assert span["span_id"] in result
        assert span["trace_id"] in result
        assert span["agent_name"] in result
        assert span["agent_model"] in result
        assert span["tool_name"] in result
        assert span["tool_description"] in result
        assert span["tool_arguments"] in result
        assert span["tool_output"] in result
        assert span["time_begin"] in result
        assert "(no flags)" in result

    def test_substitution_renders_flags(self):
        """_format_context with non-empty flags renders each flag with type=, score=, detail=."""
        span = _make_stub_span()
        flags = [
            _make_stub_flag("wrong_tool", 0.9, {"signal": "high"}),
            _make_stub_flag("wrong_tool_args", 0.6, None),
        ]
        result = context_assembly._format_context(span, flags, "PROMPT", "RESPONSE")

        assert "type=wrong_tool" in result
        assert "type=wrong_tool_args" in result
        assert "score=0.9000" in result
        assert "score=0.6000" in result
        assert "detail=" in result
        assert "(no flags)" not in result

    def test_payload_text_interpolated(self):
        """prompt_text and response_text appear verbatim in the output."""
        span = _make_stub_span()
        prompt_text = "UNIQUE_PROMPT_CONTENT_abc123"
        response_text = "UNIQUE_RESPONSE_CONTENT_xyz789"
        result = context_assembly._format_context(span, [], prompt_text, response_text)

        assert prompt_text in result
        assert response_text in result

    def test_template_read_at_import(self):
        """Module exposes _PROMPT_TEMPLATE as a non-empty str."""
        assert isinstance(context_assembly._PROMPT_TEMPLATE, str)
        assert len(context_assembly._PROMPT_TEMPLATE) > 0
        # Template must contain at least one placeholder
        assert "{span_id}" in context_assembly._PROMPT_TEMPLATE
        assert "{flags_section}" in context_assembly._PROMPT_TEMPLATE

    def test_missing_prompt_file_raises(self):
        """Re-importing context_assembly with prompt.md unreadable raises FileNotFoundError."""
        # Patch pathlib.Path.read_text to raise FileNotFoundError during reload.
        # Use a finally block to reload cleanly afterward so sibling tests are unaffected.
        with unittest.mock.patch(
            "pathlib.Path.read_text",
            side_effect=FileNotFoundError("prompt.md not found"),
        ):
            with pytest.raises(FileNotFoundError):
                importlib.reload(context_assembly)
        # Restore the module to a working state
        try:
            importlib.reload(context_assembly)
        except Exception:
            pass
