# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Tests for expected_output_schema wiring through the ingest pipeline.

Verifies:
  - SpanPayload accepts and defaults expected_output_schema to None
  - SPAN_COLUMNS contains expected_output_schema at index 9 (after tool_arguments)
  - SPAN_COLUMNS has exactly 18 items
  - ingest.py row construction includes expected_output_schema at the matching position

These tests are the RED gate for plan 23-02.
"""

import pytest

from xeter.services.analyser.batch import SPAN_COLUMNS
from xeter.services.analyser.schemas import SpanPayload


def _minimal_payload(**kwargs) -> SpanPayload:
    """Return a minimally valid SpanPayload with required fields."""
    defaults = {
        "span_id": "s",
        "agent_name": "a",
        "agent_model": "m",
        "time_begin": "t",
        "time_end": "t",
    }
    defaults.update(kwargs)
    return SpanPayload(**defaults)


class TestSpanPayloadExpectedOutputSchema:
    """SpanPayload field presence and default value."""

    def test_defaults_to_none(self):
        """expected_output_schema is None when not provided."""
        span = _minimal_payload()
        assert span.expected_output_schema is None

    def test_accepts_json_string(self):
        """expected_output_schema stores a JSON string when provided."""
        span = _minimal_payload(expected_output_schema='{"type":"object"}')
        assert span.expected_output_schema == '{"type":"object"}'


class TestSpanColumnsExpectedOutputSchema:
    """SPAN_COLUMNS list structure after inserting expected_output_schema."""

    def test_span_columns_length_is_18(self):
        """SPAN_COLUMNS must contain exactly 18 items after the new column is added."""
        assert len(SPAN_COLUMNS) == 18

    def test_expected_output_schema_at_index_9(self):
        """expected_output_schema is at index 9, immediately after tool_arguments."""
        assert SPAN_COLUMNS[9] == "expected_output_schema"


class TestIngestRowLength:
    """Row construction from SpanPayload must match SPAN_COLUMNS length."""

    def test_row_length_matches_span_columns(self):
        """A row built from SpanPayload must have 18 items (len == len(SPAN_COLUMNS)).

        This test simulates the row construction in ingest.py by building the row
        list from a mock SpanPayload instance with expected_output_schema set.
        The row must satisfy len(row) == len(SPAN_COLUMNS) == 18.
        """
        span = _minimal_payload(expected_output_schema='{"type":"string"}')

        # Replicate the row construction from ingest.py with a stub for S3 refs
        stub_refs = {
            "prompt_ref": "s3://prompt",
            "response_ref": "s3://response",
            "raw_response_ref": "s3://raw",
            "available_tools_ref": "s3://tools",
        }

        row = [
            span.span_id,
            span.trace_id or "",
            span.parent_span_id,
            "tenant-123",                  # tenant_id (from auth)
            span.agent_name,
            span.agent_model,
            span.tool_name,
            span.tool_description,
            span.tool_arguments,
            span.expected_output_schema,   # index 9 — the new field
            span.tool_output,              # index 10
            stub_refs["prompt_ref"],
            stub_refs["response_ref"],
            stub_refs["raw_response_ref"],
            stub_refs["available_tools_ref"],
            span.time_begin,
            span.time_end,
            span.schema_version,
        ]

        # This is the same assert that ingest.py enforces at runtime
        assert len(row) == len(SPAN_COLUMNS), (
            f"Row length mismatch: got {len(row)}, expected {len(SPAN_COLUMNS)}"
        )
        assert len(row) == 18
