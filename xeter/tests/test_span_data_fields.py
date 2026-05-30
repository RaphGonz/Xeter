# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Tests for SpanData new fields: expected_output_schema and parent_span_id.

Covers:
  1. SpanData defaults both new fields to None
  2. SpanData carries expected_output_schema when set
  3. SpanData carries parent_span_id when set
  4. build_span_data() passes both fields through from a row dict
  5. build_span_data({}) does not raise KeyError and returns both fields as None
  6. _FETCH_COLUMNS contains both new column names
"""

import pytest

from xeter.services.worker.base import SpanData
from xeter.scripts.calibrate import build_span_data
from xeter.services.worker.span_fetcher import _FETCH_COLUMNS


def _minimal_span_data(**kwargs) -> SpanData:
    """Construct a SpanData with required positional fields and optional overrides."""
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


# ---------------------------------------------------------------------------
# Test 1: SpanData defaults new fields to None
# ---------------------------------------------------------------------------

def test_span_data_defaults_expected_output_schema_none():
    span = _minimal_span_data()
    assert span.expected_output_schema is None


def test_span_data_defaults_parent_span_id_none():
    span = _minimal_span_data()
    assert span.parent_span_id is None


# ---------------------------------------------------------------------------
# Test 2: SpanData carries expected_output_schema when provided
# ---------------------------------------------------------------------------

def test_span_data_carries_expected_output_schema():
    schema_str = '{"type":"object"}'
    span = _minimal_span_data(expected_output_schema=schema_str)
    assert span.expected_output_schema == schema_str


# ---------------------------------------------------------------------------
# Test 3: SpanData carries parent_span_id when provided
# ---------------------------------------------------------------------------

def test_span_data_carries_parent_span_id():
    span = _minimal_span_data(parent_span_id="abc-123")
    assert span.parent_span_id == "abc-123"


# ---------------------------------------------------------------------------
# Test 4: build_span_data() passes both fields through from row dict
# ---------------------------------------------------------------------------

def test_build_span_data_passes_both_new_fields():
    row = {
        "expected_output_schema": '{"type":"string"}',
        "parent_span_id": "p-1",
    }
    span = build_span_data(row)
    assert span.expected_output_schema == '{"type":"string"}'
    assert span.parent_span_id == "p-1"


# ---------------------------------------------------------------------------
# Test 5: build_span_data({}) does not raise and returns both fields as None
# ---------------------------------------------------------------------------

def test_build_span_data_empty_row_no_key_error():
    span = build_span_data({})
    assert span.expected_output_schema is None
    assert span.parent_span_id is None


# ---------------------------------------------------------------------------
# Test 6: _FETCH_COLUMNS contains both new column names
# ---------------------------------------------------------------------------

def test_fetch_columns_contains_expected_output_schema():
    assert "expected_output_schema" in _FETCH_COLUMNS


def test_fetch_columns_contains_parent_span_id():
    assert "parent_span_id" in _FETCH_COLUMNS
