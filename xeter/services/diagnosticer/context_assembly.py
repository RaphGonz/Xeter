"""
Context assembly for the Diagnosticer service.

Pulls data from three sources:
  1. ClickHouse: span row (tool_name, tool_arguments, agent fields, S3 refs)
  2. PostgreSQL (RLS): all flag rows for the span (type, score, detail)
  3. S3/MinIO: prompt_text and response_text payloads (inlined, {"value": "..."} envelope)

Returns a single formatted string ready to pass as the user message to the LLM.

S3 fetch timeout (5s): on timeout, substitutes '[S3 fetch timed out]' in the context
string rather than raising — the LLM can still diagnose from other fields.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aioboto3
import clickhouse_connect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.shared.db.postgres import tenant_session
from xeter.shared.models import Flag

# ---------------------------------------------------------------------------
# ClickHouse span query
# ---------------------------------------------------------------------------

_SPAN_QUERY = (
    "SELECT span_id, trace_id, agent_name, agent_model, tool_name, "
    "tool_description, tool_arguments, tool_output, time_begin, "
    "prompt_ref, response_ref "
    "FROM spans "
    "WHERE span_id = %(span_id)s AND tenant_id = %(tenant_id)s "
    "LIMIT 1"
)


def _fetch_span_sync(
    ch_client: clickhouse_connect.driver.Client,
    span_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    """Sync ClickHouse query — called via asyncio.to_thread."""
    result = ch_client.query(
        _SPAN_QUERY,
        parameters={"span_id": span_id, "tenant_id": tenant_id},
    )
    if not result.result_rows:
        return None
    return dict(zip(result.column_names, result.first_row))


# ---------------------------------------------------------------------------
# S3 payload fetch
# ---------------------------------------------------------------------------

async def _fetch_s3_payloads(
    prompt_ref: str | None,
    response_ref: str | None,
) -> tuple[str, str]:
    """Fetch prompt and response payloads from S3 in parallel.

    Unwraps the {"value": "..."} envelope written by the ingestion pipeline.
    On asyncio.TimeoutError (5s), returns '[S3 fetch timed out]' for both fields.
    On missing ref (None), returns '[not available]'.
    """
    bucket = os.environ.get("S3_BUCKET", "xeter-payloads")  # [safe-default]
    endpoint_url = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")  # [safe-default] docker-compose value
    s3_session = aioboto3.Session(
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),  # [must-set-in-prod] returns None silently; use os.environ[] for fail-fast
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),  # [must-set-in-prod] returns None silently; use os.environ[] for fail-fast
    )

    async def _fetch(key: str | None) -> str:
        if not key:
            return "[not available]"
        try:
            async with s3_session.client("s3", endpoint_url=endpoint_url) as s3:
                resp = await s3.get_object(Bucket=bucket, Key=key)
                body = await resp["Body"].read()
                return json.loads(body).get("value", "[empty payload]")
        except Exception:
            return "[S3 fetch error]"

    try:
        prompt_text, response_text = await asyncio.wait_for(
            asyncio.gather(_fetch(prompt_ref), _fetch(response_ref)),
            timeout=5.0,
        )
        return prompt_text, response_text
    except asyncio.TimeoutError:
        return "[S3 fetch timed out]", "[S3 fetch timed out]"


# ---------------------------------------------------------------------------
# PostgreSQL flags query
# ---------------------------------------------------------------------------

async def _fetch_flags(
    session: AsyncSession,
    span_id: str,
    tenant_id: str,
) -> list[Flag]:
    """Fetch all flag rows for a span via RLS-protected PostgreSQL query."""
    import uuid as _uuid
    async with tenant_session(session, tenant_id) as s:
        result = await s.execute(
            select(Flag).where(
                Flag.span_id == span_id,
                Flag.tenant_id == _uuid.UUID(str(tenant_id)),
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Context string formatter
# ---------------------------------------------------------------------------

def _format_context(
    span: dict[str, Any],
    flags: list[Flag],
    prompt_text: str,
    response_text: str,
) -> str:
    """Format all data into a single context string for the LLM."""
    flag_lines = []
    for f in flags:
        detail_str = json.dumps(f.detail) if f.detail else "none"
        flag_lines.append(
            f"  - type={f.flag_type}, score={f.score:.4f}, detail={detail_str}"
        )
    flags_section = "\n".join(flag_lines) if flag_lines else "  (no flags)"

    return f"""You are diagnosing a failing AI agent tool call. Analyze the data below and identify the root cause.

## Span Information
- span_id: {span.get('span_id', 'unknown')}
- trace_id: {span.get('trace_id', 'unknown')}
- agent_name: {span.get('agent_name', 'unknown')}
- agent_model: {span.get('agent_model', 'unknown')}
- tool_name: {span.get('tool_name', 'unknown')}
- tool_description: {span.get('tool_description', 'unknown')}
- tool_arguments: {span.get('tool_arguments', 'unknown')}
- tool_output: {span.get('tool_output', 'unknown')}
- time_begin: {span.get('time_begin', 'unknown')}

## Prompt Text (full content)
{prompt_text}

## Response Text (full content)
{response_text}

## Anomaly Flags (all flags for this span, with scores)
{flags_section}

## Task
Based on the above, call the `record_diagnosis` tool with your root-cause analysis.
"""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def assemble_context(
    span_id: str,
    tenant_id: str,
    session: AsyncSession,
    ch_client: clickhouse_connect.driver.Client,
) -> tuple[str, str]:
    """Assemble the full LLM context string for a span diagnosis.

    Args:
        span_id: ClickHouse span to diagnose.
        tenant_id: Tenant UUID string (for RLS and ClickHouse filtering).
        session: SQLAlchemy AsyncSession (for PostgreSQL flags query).
        ch_client: ClickHouse client (sync, wrapped with asyncio.to_thread).

    Returns:
        Tuple of (context_string, trace_id).
        context_string: Formatted string ready to pass to LLM as user message.
        trace_id: Extracted from span row (needed for diagnosis row storage).

    Raises:
        ValueError: If the span is not found in ClickHouse.
    """
    # Fetch span from ClickHouse (sync client, run in thread)
    span = await asyncio.to_thread(_fetch_span_sync, ch_client, span_id, tenant_id)
    if span is None:
        raise ValueError(f"Span {span_id!r} not found in ClickHouse for tenant {tenant_id!r}")

    trace_id = span.get("trace_id", "")

    # Fetch flags from PostgreSQL and S3 payloads in parallel
    flags, (prompt_text, response_text) = await asyncio.gather(
        _fetch_flags(session, span_id, tenant_id),
        _fetch_s3_payloads(span.get("prompt_ref"), span.get("response_ref")),
    )

    context_string = _format_context(span, flags, prompt_text, response_text)
    return context_string, trace_id
