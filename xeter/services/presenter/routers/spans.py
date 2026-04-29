"""
Presenter spans router — span list and span detail endpoints.

GET /spans
  Returns a paginated list of spans with inline flag summaries and similarity scores.
  Tenant isolation is enforced by the JWT session token (via verify_session_token)
  AND by explicit WHERE tenant_id = ? clauses on all queries.

  span_scores has RLS (migration 004) + explicit WHERE tenant_id clause — both
  layers enforce tenant isolation; never omit the WHERE clause.

GET /spans/{span_id}
  Returns full span detail merging ClickHouse span row, PostgreSQL flags+scores,
  and S3 prompt/response/raw_response payloads (fetched lazily with 5s timeout).
  Returns 404 for missing or cross-tenant spans (no information leakage).
  Returns 504 on S3 timeout, 502 on other S3 errors — never partial data.

Pagination:
  Cursor-based, descending by time_begin.
  cursor is base64url-encoded ISO timestamp of the last returned span's time_begin.

Status derivation:
  "flagged"  — at least one Flag row exists for the span
  "clean"    — no flags, but at least one span_score row exists
  "pending"  — no flags and no scores (analyser has not processed the span yet)
"""

import asyncio
import base64
import json
import os
from typing import Annotated

import aioboto3
import clickhouse_connect
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import get_ch_client, verify_session_token
from xeter.services.presenter.routers.auth import get_session
from xeter.shared.models import Flag

logger = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FlagSummary(BaseModel):
    """Condensed flag record attached to a span list item."""

    flag_type: str
    score: float


class FlagDetail(BaseModel):
    """Full flag detail for the span detail response."""

    flag_type: str
    score: float
    detail: dict | None
    created_at: str


class ScoreDetail(BaseModel):
    """Similarity score record for the span detail response."""

    analyzer_name: str
    metric_name: str
    score: float


class SpanDetailResponse(BaseModel):
    """Full span detail response merging ClickHouse, PostgreSQL, and S3 data."""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    agent_name: str
    agent_model: str
    tool_name: str | None
    tool_description: str | None
    tool_arguments: str | None
    tool_output: str | None
    time_begin: str
    time_end: str
    duration_ms: float | None
    status: str  # "flagged" | "clean" | "pending"
    flags: list[FlagDetail]
    scores: list[ScoreDetail]
    prompt: str | None
    response: str | None
    raw_response: str | None


class SpanListItem(BaseModel):
    """Single span in the list response."""

    span_id: str
    trace_id: str
    agent_name: str
    agent_model: str
    tool_name: str | None
    time_begin: str
    duration_ms: float | None
    status: str  # "flagged" | "clean" | "pending"
    flags: list[FlagSummary]


class SpanListResponse(BaseModel):
    """Paginated span list response."""

    spans: list[SpanListItem]
    next_cursor: str | None


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(iso_timestamp: str) -> str:
    """Encode an ISO timestamp as a URL-safe base64 cursor string."""
    return base64.urlsafe_b64encode(iso_timestamp.encode()).decode()


def _decode_cursor(cursor: str) -> str:
    """Decode a base64url cursor string back to an ISO timestamp."""
    return base64.urlsafe_b64decode(cursor.encode()).decode()


# ---------------------------------------------------------------------------
# GET /spans handler
# ---------------------------------------------------------------------------


@router.get("/spans", response_model=SpanListResponse)
async def list_spans(
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    ch_client: Annotated[clickhouse_connect.driver.Client, Depends(get_ch_client)],
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    flag_type: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    from_time: str | None = Query(default=None),
    to_time: str | None = Query(default=None),
) -> SpanListResponse:
    """Return a paginated list of spans for the authenticated tenant.

    Steps:
      1. Query ClickHouse for spans matching tenant_id, applying cursor and
         agent_name / from_time / to_time filters in the WHERE clause when provided.
      2. Query PostgreSQL flags for those span_ids, optionally filtering by flag_type.
      3. Query PostgreSQL span_scores for those span_ids (no RLS — explicit tenant_id filter).
      4. If flag_type is set, keep only spans that have at least one matching flag.
      5. Merge results: attach flag summaries, derive status, compute duration_ms.
      6. Compute next_cursor from last span's time_begin if result count == limit.

    Filter notes:
      - agent_name, from_time, to_time are applied as ClickHouse WHERE clauses.
      - flag_type is applied post-ClickHouse by filtering on PostgreSQL flags result
        (flags live in PostgreSQL, not ClickHouse). Spans with no matching flag are
        excluded from the response. Count may be less than limit — acceptable in Phase 5.
      - All active filters are AND-combined.
      - No filter = backward-compatible, returns all spans.
    """
    # --- Step 1: ClickHouse query ---
    params = {"tenant_id": tenant_id, "limit": limit}
    where_clauses = ["tenant_id = %(tenant_id)s"]

    if cursor:
        try:
            cursor_ts = _decode_cursor(cursor)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        where_clauses.append("time_begin < %(cursor_ts)s")
        params["cursor_ts"] = cursor_ts

    if agent_name is not None:
        where_clauses.append("agent_name = %(agent_name)s")
        params["agent_name"] = agent_name

    if from_time is not None:
        where_clauses.append("time_begin >= %(from_time)s")
        params["from_time"] = from_time

    if to_time is not None:
        where_clauses.append("time_begin <= %(to_time)s")
        params["to_time"] = to_time

    where_sql = " AND ".join(where_clauses)
    ch_query = (
        f"SELECT span_id, trace_id, agent_name, agent_model, tool_name, "
        f"time_begin, time_end "
        f"FROM spans "
        f"WHERE {where_sql} "
        f"ORDER BY time_begin DESC "
        f"LIMIT %(limit)s"
    )

    ch_result = await asyncio.to_thread(ch_client.query, ch_query, params)
    rows = ch_result.result_rows  # list of tuples

    if not rows:
        return SpanListResponse(spans=[], next_cursor=None)

    span_ids = [row[0] for row in rows]

    # --- Step 2: PostgreSQL flags query (with RLS via tenant_session) ---
    # When flag_type is provided, also filter by flag_type so only matching flags
    # are returned; spans with no matching flag are excluded in Step 4.
    flags_conditions = [
        Flag.tenant_id == tenant_id,
        Flag.span_id.in_(span_ids),
    ]
    if flag_type is not None:
        flags_conditions.append(Flag.flag_type == flag_type)

    flags_result = await session.execute(
        select(Flag).where(*flags_conditions)
    )
    flags: list[Flag] = list(flags_result.scalars().all())

    # Build span_id -> [FlagSummary] index
    flags_by_span: dict[str, list[FlagSummary]] = {}
    for flag in flags:
        flags_by_span.setdefault(flag.span_id, []).append(
            FlagSummary(flag_type=flag.flag_type, score=flag.score)
        )

    # --- Step 4 (flag_type post-filter): exclude spans with no matching flag ---
    # When flag_type is active the PostgreSQL flags query already filtered by
    # flag_type, so spans absent from flags_by_span had no matching flag — drop them.
    if flag_type is not None:
        rows = [row for row in rows if row[0] in flags_by_span]
        if not rows:
            return SpanListResponse(spans=[], next_cursor=None)
        span_ids = [row[0] for row in rows]

    # --- Step 3: span_scores query (NO RLS — must include tenant_id filter) ---
    # Use raw text query since span_scores is not an ORM model
    scores_result = await session.execute(
        text(
            "SELECT span_id, analyzer_name, metric_name, score "
            "FROM span_scores "
            "WHERE tenant_id = :tid AND span_id = ANY(:span_ids)"
        ),
        {"tid": tenant_id, "span_ids": list(span_ids)},
    )
    scored_span_ids: set[str] = {row[0] for row in scores_result.fetchall()}

    # --- Step 4: Merge ---
    items: list[SpanListItem] = []
    for row in rows:
        span_id, trace_id, agent_name, agent_model, tool_name, time_begin, time_end = row

        # Compute duration_ms
        duration_ms: float | None = None
        try:
            if time_begin is not None and time_end is not None:
                # ClickHouse DateTime64 may come back as datetime objects or timestamps
                if hasattr(time_begin, "timestamp") and hasattr(time_end, "timestamp"):
                    duration_ms = (time_end.timestamp() - time_begin.timestamp()) * 1000.0
                else:
                    duration_ms = float(time_end) - float(time_begin)
        except Exception:
            duration_ms = None

        # time_begin as ISO string for response / cursor
        time_begin_str = (
            time_begin.isoformat() if hasattr(time_begin, "isoformat") else str(time_begin)
        )

        span_flags = flags_by_span.get(span_id, [])

        # Derive status
        if span_flags:
            status = "flagged"
        elif span_id in scored_span_ids:
            status = "clean"
        else:
            status = "pending"

        items.append(
            SpanListItem(
                span_id=span_id,
                trace_id=trace_id,
                agent_name=agent_name,
                agent_model=agent_model,
                tool_name=tool_name,
                time_begin=time_begin_str,
                duration_ms=duration_ms,
                status=status,
                flags=span_flags,
            )
        )

    # --- Step 5: Compute next_cursor ---
    next_cursor: str | None = None
    if len(rows) == limit:
        last_time_begin = items[-1].time_begin
        next_cursor = _encode_cursor(last_time_begin)

    return SpanListResponse(spans=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# S3 payload fetch helpers
# ---------------------------------------------------------------------------


async def _fetch_s3_payload(
    s3_client,
    bucket: str,
    key: str | None,
    tenant_id: str,
) -> str | None:
    """Fetch a single S3 object and extract the 'value' field from its JSON body.

    Returns None if key is None (field was not uploaded).
    Raises HTTPException 403 if the key's tenant prefix does not match tenant_id
    (S3-01 defence-in-depth: ClickHouse already filters by tenant_id, but the S3
    layer independently asserts ownership before any GetObject call).
    Caller is responsible for wrapping in asyncio.wait_for.
    """
    if not key:
        return None
    # S3-01: assert the key belongs to the requesting tenant before fetching
    if not key.startswith(f"{tenant_id}/"):
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "S3 key does not belong to requesting tenant"},
        )
    response = await s3_client.get_object(Bucket=bucket, Key=key)
    body = await response["Body"].read()
    data = json.loads(body)
    return data.get("value")


async def _fetch_all_s3_payloads(
    prompt_ref: str | None,
    response_ref: str | None,
    raw_response_ref: str | None,
    tenant_id: str,
) -> tuple[str | None, str | None, str | None]:
    """Fetch all three S3 payloads in parallel using aioboto3.

    Wraps the entire fetch in a 5-second timeout.

    Raises:
        asyncio.TimeoutError: If the combined fetch exceeds 5 seconds.
        Exception: For any other S3 error.
    """
    bucket = os.environ.get("S3_BUCKET", "xeter-payloads")
    endpoint_url = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")
    access_key = os.environ.get("S3_ACCESS_KEY", "")
    secret_key = os.environ.get("S3_SECRET_KEY", "")

    session = aioboto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    async def _fetch_all():
        async with session.client(
            "s3",
            endpoint_url=endpoint_url,
        ) as s3:
            return await asyncio.gather(
                _fetch_s3_payload(s3, bucket, prompt_ref, tenant_id),
                _fetch_s3_payload(s3, bucket, response_ref, tenant_id),
                _fetch_s3_payload(s3, bucket, raw_response_ref, tenant_id),
            )

    return await asyncio.wait_for(_fetch_all(), timeout=5.0)


# ---------------------------------------------------------------------------
# GET /spans/{span_id} handler
# ---------------------------------------------------------------------------


@router.get("/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span_detail(
    span_id: str,
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    ch_client: Annotated[clickhouse_connect.driver.Client, Depends(get_ch_client)],
) -> SpanDetailResponse:
    """Return full detail for a single span.

    Steps:
      1. Parallel: fetch span from ClickHouse (with tenant_id filter) + flags from
         PostgreSQL + scores from PostgreSQL.
      2. Return 404 if span not found or belongs to another tenant.
      3. Sequential: fetch S3 payloads using _ref columns from ClickHouse row.
         Wrapped in asyncio.wait_for(timeout=5.0).
      4. Return 504 on S3 timeout, 502 on other S3 errors — no partial data.
      5. Merge and return SpanDetailResponse.
    """
    # --- Step 1: Fetch ClickHouse span concurrently with PostgreSQL queries ---
    # NOTE: The two PostgreSQL queries (_fetch_pg_flags, _fetch_pg_scores) MUST run
    # sequentially on the shared AsyncSession. SQLAlchemy's AsyncSession wraps a
    # single connection whose state machine cannot handle concurrent execute() calls —
    # doing so raises IllegalStateChangeError. The ClickHouse query uses a separate
    # client and can still run concurrently with the PG work.

    async def _fetch_ch_span():
        ch_query = (
            "SELECT span_id, trace_id, parent_span_id, agent_name, agent_model, "
            "tool_name, tool_description, tool_arguments, tool_output, "
            "time_begin, time_end, prompt_ref, response_ref, raw_response_ref "
            "FROM spans "
            "WHERE tenant_id = %(tenant_id)s AND span_id = %(span_id)s "
            "LIMIT 1"
        )
        result = await asyncio.to_thread(
            ch_client.query, ch_query, {"tenant_id": tenant_id, "span_id": span_id}
        )
        rows = result.result_rows
        return rows[0] if rows else None

    async def _fetch_pg_data():
        # Run flags and scores queries sequentially on the same session.
        # AsyncSession is NOT safe for concurrent use — two simultaneous execute()
        # calls on the same session cause IllegalStateChangeError.
        flags_result = await session.execute(
            select(Flag).where(
                Flag.tenant_id == tenant_id,
                Flag.span_id == span_id,
            )
        )
        flags = list(flags_result.scalars().all())

        # span_scores has RLS (migration 004) + explicit WHERE tenant_id — both layers required
        scores_result = await session.execute(
            text(
                "SELECT analyzer_name, metric_name, score "
                "FROM span_scores "
                "WHERE tenant_id = :tid AND span_id = :sid"
            ),
            {"tid": tenant_id, "sid": span_id},
        )
        scores = scores_result.fetchall()

        return flags, scores

    ch_span, (pg_flags, pg_scores) = await asyncio.gather(
        _fetch_ch_span(),
        _fetch_pg_data(),
    )

    # --- Step 2: 404 on missing or cross-tenant span ---
    if ch_span is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Span not found", "status": 404},
        )

    (
        ch_span_id, trace_id, parent_span_id, agent_name, agent_model,
        tool_name, tool_description, tool_arguments, tool_output,
        time_begin, time_end, prompt_ref, response_ref, raw_response_ref,
    ) = ch_span

    # --- Step 3: Fetch S3 payloads ---
    try:
        prompt, response, raw_response = await _fetch_all_s3_payloads(
            prompt_ref, response_ref, raw_response_ref, tenant_id
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "s3_timeout", "message": "S3 payload fetch timed out", "status": 504},
        )
    except Exception as exc:
        logger.error("s3_fetch_failed", span_id=span_id, error=str(exc))
        prompt, response, raw_response = None, None, None

    # --- Step 5: Merge and return ---

    # Compute duration_ms
    duration_ms: float | None = None
    try:
        if time_begin is not None and time_end is not None:
            if hasattr(time_begin, "timestamp") and hasattr(time_end, "timestamp"):
                duration_ms = (time_end.timestamp() - time_begin.timestamp()) * 1000.0
            else:
                duration_ms = float(time_end) - float(time_begin)
    except Exception:
        duration_ms = None

    # ISO strings for response
    time_begin_str = (
        time_begin.isoformat() if hasattr(time_begin, "isoformat") else str(time_begin)
    )
    time_end_str = (
        time_end.isoformat() if hasattr(time_end, "isoformat") else str(time_end)
    )

    # Build FlagDetail list
    flag_details: list[FlagDetail] = []
    for flag in pg_flags:
        created_at_str = (
            flag.created_at.isoformat()
            if hasattr(flag.created_at, "isoformat")
            else str(flag.created_at)
        )
        flag_details.append(
            FlagDetail(
                flag_type=flag.flag_type,
                score=flag.score,
                detail=flag.detail,
                created_at=created_at_str,
            )
        )

    # Build ScoreDetail list
    score_details: list[ScoreDetail] = [
        ScoreDetail(analyzer_name=row[0], metric_name=row[1], score=row[2])
        for row in pg_scores
    ]

    # Derive status
    if flag_details:
        status = "flagged"
    elif score_details:
        status = "clean"
    else:
        status = "pending"

    return SpanDetailResponse(
        span_id=ch_span_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        agent_name=agent_name,
        agent_model=agent_model,
        tool_name=tool_name,
        tool_description=tool_description,
        tool_arguments=tool_arguments,
        tool_output=tool_output,
        time_begin=time_begin_str,
        time_end=time_end_str,
        duration_ms=duration_ms,
        status=status,
        flags=flag_details,
        scores=score_details,
        prompt=prompt,
        response=response,
        raw_response=raw_response,
    )
