# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Unit tests for _fetch_s3_payload S3 tenant-prefix assertion (S3-01).

Tests import _fetch_s3_payload directly and exercise the tenant ownership guard
without starting a real S3 connection. The s3_client argument is an AsyncMock.

Tests:
  1. test_correct_prefix_calls_get_object        — matching prefix proceeds to GetObject
  2. test_wrong_prefix_raises_403                — mismatched prefix raises HTTPException 403
  3. test_none_key_returns_none                  — None key short-circuits before prefix check
  4. test_month_segment_key_format_accepted      — {tenant}/{YYYY-MM}/{span}/{field} still accepted
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from xeter.services.presenter.routers.spans import _fetch_s3_payload

TENANT_A = "aaaaaaaa-0000-0000-0000-000000000001"
TENANT_B = "bbbbbbbb-0000-0000-0000-000000000002"
SPAN_ID = "span-xyz-001"
BUCKET = "xeter-payloads"


def _make_s3_client(payload_value: str = "hello prompt") -> AsyncMock:
    """Return an AsyncMock s3_client that returns a valid JSON payload."""
    body_mock = AsyncMock()
    body_mock.read = AsyncMock(return_value=json.dumps({"value": payload_value}).encode())
    response_mock = {"Body": body_mock}
    client = AsyncMock()
    client.get_object = AsyncMock(return_value=response_mock)
    return client


@pytest.mark.asyncio
async def test_correct_prefix_calls_get_object():
    """Key matching tenant prefix proceeds to GetObject and returns value."""
    key = f"{TENANT_A}/2026-04/{SPAN_ID}/prompt.json"
    s3 = _make_s3_client("the prompt text")
    result = await _fetch_s3_payload(s3, BUCKET, key, TENANT_A)
    assert result == "the prompt text"
    s3.get_object.assert_called_once_with(Bucket=BUCKET, Key=key)


@pytest.mark.asyncio
async def test_wrong_prefix_raises_403():
    """Key belonging to a different tenant raises HTTPException with status 403."""
    key = f"{TENANT_B}/2026-04/{SPAN_ID}/prompt.json"  # tenant B's key
    s3 = _make_s3_client()
    with pytest.raises(HTTPException) as exc_info:
        await _fetch_s3_payload(s3, BUCKET, key, TENANT_A)  # but requesting as tenant A
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "forbidden"
    s3.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_none_key_returns_none():
    """None key short-circuits immediately — no S3 call, no prefix check."""
    s3 = _make_s3_client()
    result = await _fetch_s3_payload(s3, BUCKET, None, TENANT_A)
    assert result is None
    s3.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_month_segment_key_format_accepted():
    """Historical key format {tenant}/{YYYY-MM}/{span}/{field}.json is accepted."""
    key = f"{TENANT_A}/2026-03/{SPAN_ID}/response.json"
    s3 = _make_s3_client("the response")
    result = await _fetch_s3_payload(s3, BUCKET, key, TENANT_A)
    assert result == "the response"
    s3.get_object.assert_called_once()
