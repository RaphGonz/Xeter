# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Span fetcher for the Embedding Worker.

Fetches a span row from ClickHouse by span_id (full table scan — span_id is not
part of the ORDER BY primary key; acceptable at Phase 3 volume). Resolves S3
payload references (prompt_ref, response_ref, raw_response_ref,
available_tools_ref) into their decoded text content. Uses boto3 (sync), not
aioboto3. The returned SpanData is the contract consumed by all analyzers.

Environment variables:
  CLICKHOUSE_HOST       — ClickHouse host (default: "clickhouse")
  CLICKHOUSE_PORT       — ClickHouse HTTP port (default: 8123)
  CLICKHOUSE_DATABASE   — ClickHouse database (default: "xeter")
  S3_ENDPOINT_URL       — MinIO/S3 endpoint URL
  S3_ACCESS_KEY         — S3 access key id
  S3_SECRET_KEY         — S3 secret access key
  S3_BUCKET             — S3 bucket name (default: "xeter-payloads")
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from xeter.services.analyser.batch import get_clickhouse_client
from xeter.services.worker.base import SpanData

logger = logging.getLogger(__name__)

# ClickHouse columns fetched for span lookup (excludes time_begin, time_end,
# schema_version which are not needed by analyzers).
_FETCH_COLUMNS = [
    "span_id",
    "trace_id",
    "tenant_id",
    "agent_name",
    "agent_model",
    "tool_name",
    "tool_description",
    "tool_arguments",
    "tool_output",
    "prompt_ref",
    "response_ref",
    "raw_response_ref",
    "available_tools_ref",
    "expected_output_schema",
    "parent_span_id",
]

_FETCH_QUERY = (
    "SELECT span_id, trace_id, tenant_id, agent_name, agent_model, "
    "tool_name, tool_description, tool_arguments, tool_output, "
    "prompt_ref, response_ref, raw_response_ref, available_tools_ref, "
    "expected_output_schema, parent_span_id "
    "FROM spans WHERE span_id = %(span_id)s LIMIT 1"
)


def get_s3_client():
    """Create a boto3 S3 client from environment variables.

    Reads S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET from env —
    same variable names used by xeter.services.analyser.s3.

    Returns:
        A boto3 S3 client instance (sync).
    """
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
    )


def _fetch_s3_text(s3_client, bucket: str, key: str | None) -> str | None:
    """Fetch and unwrap a single S3 payload.

    Payloads are stored as JSON objects with a "value" key:
      {"value": "<original field string>"}

    Args:
        s3_client: A boto3 S3 client.
        bucket: S3 bucket name.
        key: S3 object key. If None or empty string, returns None immediately.

    Returns:
        The unwrapped original string, or None on missing key or S3 error.
    """
    if not key:
        return None
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        wrapper = json.loads(obj["Body"].read())
        return wrapper["value"]
    except ClientError as exc:
        logger.warning("span_fetcher: S3 fetch failed for key=%s: %s", key, exc)
        return None


def _decode_available_tools(tools_string: str | None) -> list[dict] | None:
    """Parse the available_tools JSON string into a list of tool dicts.

    The value fetched from S3 is itself a JSON string (double-encoded):
      S3 value  ->  _fetch_s3_text returns the inner string
      inner string  ->  json.loads gives list[dict]

    Args:
        tools_string: JSON string representing a list of tool dicts, or None.

    Returns:
        Parsed list[dict], or None if input is None, not valid JSON, or not a list.
    """
    if tools_string is None:
        return None
    try:
        tools = json.loads(tools_string)
        if not isinstance(tools, list):
            logger.warning(
                "span_fetcher: available_tools decoded to %s, expected list",
                type(tools).__name__,
            )
            return None
        return tools
    except json.JSONDecodeError as exc:
        logger.warning("span_fetcher: failed to decode available_tools JSON: %s", exc)
        return None


def fetch_span(span_id: str) -> SpanData:
    """Fetch a span from ClickHouse and resolve all S3 payload references.

    Queries ClickHouse for the row matching span_id (full table scan — acceptable
    at Phase 3 volume). Fetches S3 payloads for prompt, response, raw_response,
    and available_tools. Returns a fully-populated SpanData for use by analyzers.

    Args:
        span_id: The span_id to look up.

    Returns:
        A SpanData instance with all available fields populated.

    Raises:
        ValueError: If no span with the given span_id exists in ClickHouse.
    """
    ch = get_clickhouse_client()
    result = ch.query(_FETCH_QUERY, parameters={"span_id": span_id})

    if not result.result_rows:
        raise ValueError(f"span not found: {span_id}")

    row = dict(zip(result.column_names, result.first_row))

    bucket = os.environ.get("S3_BUCKET", "xeter-payloads")
    s3 = get_s3_client()

    prompt = _fetch_s3_text(s3, bucket, row.get("prompt_ref"))
    response = _fetch_s3_text(s3, bucket, row.get("response_ref"))
    raw_response = _fetch_s3_text(s3, bucket, row.get("raw_response_ref"))

    tools_raw = _fetch_s3_text(s3, bucket, row.get("available_tools_ref"))
    available_tools = _decode_available_tools(tools_raw)

    return SpanData(
        span_id=row["span_id"],
        tenant_id=row["tenant_id"],
        trace_id=row["trace_id"],
        agent_name=row["agent_name"],
        agent_model=row["agent_model"],
        tool_name=row.get("tool_name") or None,
        tool_description=row.get("tool_description") or None,
        tool_arguments=row.get("tool_arguments") or None,
        tool_output=row.get("tool_output") or None,
        prompt=prompt,
        response=response,
        raw_response=raw_response,
        available_tools=available_tools,
        expected_output_schema=row.get("expected_output_schema") or None,
        parent_span_id=row.get("parent_span_id") or None,
    )
