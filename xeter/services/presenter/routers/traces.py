"""
Presenter traces router — trace list and trace detail endpoints.

GET /traces
  Returns a paginated list of traces with span counts, flag counts, start time,
  and duration. Aggregates from ClickHouse (spans) and PostgreSQL (flags).
  Tenant isolation is enforced by the JWT session token (via verify_session_token)
  AND by explicit WHERE tenant_id = ? clauses on all queries.

GET /traces/{trace_id}
  Returns full trace detail merging ClickHouse spans (sorted by time_begin ASC)
  and PostgreSQL flags + scores per span. Also returns trace-level flags
  (span_id IS NULL) on the top-level trace object.
  Returns 404 for missing or cross-tenant traces (stealth — no 403).
  Returns 200 with spans=[] when ClickHouse has no rows but PostgreSQL has at
  least one flag for that trace_id — the "no-spans-yet" case.

Tenant isolation:
  - All ClickHouse queries: WHERE tenant_id = %(tenant_id)s
  - All PostgreSQL queries: Flag.tenant_id == tenant_id or text WITH :tenant_id
  - Cross-tenant lookups return 404 because both CH and PG filter by the requesting
    tenant — the other tenant's data is invisible.

PostgreSQL session note:
  AsyncSession wraps a single connection. Two concurrent execute() calls on the
  same session cause IllegalStateChangeError. Run PG queries sequentially.
"""

import asyncio
from typing import Annotated

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


class TraceFlagItem(BaseModel):
    """A flag attached to a trace or span."""

    flag_type: str
    score: float
    detail: dict | None


class ScoreItem(BaseModel):
    """A similarity/quality score attached to a span."""

    analyzer_name: str
    metric_name: str
    score: float


class SpanInTrace(BaseModel):
    """A single span within a trace detail response."""

    span_id: str
    parent_span_id: str | None
    tool_name: str | None
    model: str  # agent_model from ClickHouse
    start_time: str  # ISO 8601 of time_begin
    end_time: str  # ISO 8601 of time_end
    input_tokens: int | None  # not in current schema — reserved for future
    output_tokens: int | None  # not in current schema — reserved for future
    flags: list[TraceFlagItem]
    scores: list[ScoreItem]


class TraceObject(BaseModel):
    """Top-level trace metadata in the detail response."""

    trace_id: str
    start_time: str | None  # None when no spans and no flags have timestamps
    duration: float  # seconds: max(time_end) - min(time_begin); 0.0 when no spans
    flags: list[TraceFlagItem]  # trace-level flags only (span_id IS NULL)


class TraceDetailResponse(BaseModel):
    """Full trace detail response."""

    trace: TraceObject
    spans: list[SpanInTrace]


class TraceListItem(BaseModel):
    """Single trace in the list response."""

    trace_id: str
    span_count: int
    flag_count: int
    start_time: str  # ISO 8601 of min(time_begin) across spans
    duration: float  # seconds: max(time_end) - min(time_begin)


class TraceListResponse(BaseModel):
    """Paginated trace list response."""

    traces: list[TraceListItem]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Helper: ISO string from datetime-like or raw value
# ---------------------------------------------------------------------------


def _to_iso(value) -> str:
    """Convert a ClickHouse or Python datetime value to an ISO 8601 string."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# GET /traces handler
# ---------------------------------------------------------------------------


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    ch_client: Annotated[clickhouse_connect.driver.Client, Depends(get_ch_client)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TraceListResponse:
    """Return a paginated list of traces for the authenticated tenant.

    Steps:
      1. Run two concurrent ClickHouse queries:
         a. Aggregated trace rows (trace_id, span_count, start_time, duration).
         b. Total distinct trace count.
      2. If no traces found, return empty list immediately.
      3. Query PostgreSQL for flag counts per trace_id.
      4. Merge and return TraceListResponse.
    """
    # --- Step 1: Concurrent ClickHouse queries ---
    list_query = (
        "SELECT "
        "    trace_id, "
        "    count() AS span_count, "
        "    min(time_begin) AS start_time, "
        "    dateDiff('millisecond', min(time_begin), max(time_end)) / 1000.0 AS duration "
        "FROM spans "
        "WHERE tenant_id = %(tenant_id)s "
        "GROUP BY trace_id "
        "ORDER BY start_time DESC "
        "LIMIT %(limit)s "
        "OFFSET %(offset)s"
    )
    count_query = (
        "SELECT count(DISTINCT trace_id) FROM spans WHERE tenant_id = %(tenant_id)s"
    )
    params = {"tenant_id": tenant_id, "limit": limit, "offset": offset}
    count_params = {"tenant_id": tenant_id}

    ch_list_result, ch_count_result = await asyncio.gather(
        asyncio.to_thread(ch_client.query, list_query, params),
        asyncio.to_thread(ch_client.query, count_query, count_params),
    )

    rows = ch_list_result.result_rows
    total = ch_count_result.result_rows[0][0] if ch_count_result.result_rows else 0

    # --- Step 2: Short-circuit on empty ---
    if not rows:
        return TraceListResponse(traces=[], total=0, limit=limit, offset=offset)

    trace_ids = [row[0] for row in rows]

    # --- Step 3: PostgreSQL flag counts per trace ---
    # Belt-and-suspenders: RLS + explicit tenant_id WHERE clause.
    # Count ALL flags per trace regardless of span_id.
    flag_count_result = await session.execute(
        text(
            "SELECT trace_id, count(*) AS flag_count "
            "FROM flags "
            "WHERE tenant_id = :tenant_id "
            "  AND trace_id = ANY(:trace_ids) "
            "GROUP BY trace_id"
        ),
        {"tenant_id": tenant_id, "trace_ids": trace_ids},
    )
    flag_count_by_trace: dict[str, int] = {
        row[0]: row[1] for row in flag_count_result.fetchall()
    }

    # --- Step 4: Merge ---
    traces: list[TraceListItem] = []
    for row in rows:
        trace_id_val, span_count, start_time, duration = row
        traces.append(
            TraceListItem(
                trace_id=trace_id_val,
                span_count=int(span_count),
                flag_count=flag_count_by_trace.get(trace_id_val, 0),
                start_time=_to_iso(start_time),
                duration=float(duration),
            )
        )

    return TraceListResponse(traces=traces, total=int(total), limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /traces/{trace_id} handler
# ---------------------------------------------------------------------------


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace_detail(
    trace_id: str,
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    ch_client: Annotated[clickhouse_connect.driver.Client, Depends(get_ch_client)],
) -> TraceDetailResponse:
    """Return full detail for a single trace.

    Steps:
      1. Fetch all spans from ClickHouse for (tenant_id, trace_id), sorted ASC.
      2. No-spans-yet check: if ClickHouse returns zero rows, query PostgreSQL for
         any flag with this trace_id. If found → 200 with spans=[]. If not → 404.
         Cross-tenant lookups produce zero rows in both CH and PG → stealth 404.
      3. Collect span_ids from CH rows.
      4. PostgreSQL (sequential — AsyncSession not concurrent-safe):
         a. All flags for this trace (span-level and trace-level).
         b. All span_scores for span_ids in this trace.
      5. Separate trace-level flags (span_id IS NULL) from span-level flags.
      6. Compute trace start_time and duration from CH rows.
      7. Assemble and return TraceDetailResponse.
    """
    # --- Step 1: ClickHouse spans ---
    ch_query = (
        "SELECT span_id, parent_span_id, tool_name, agent_model, "
        "       time_begin, time_end "
        "FROM spans "
        "WHERE tenant_id = %(tenant_id)s AND trace_id = %(trace_id)s "
        "ORDER BY time_begin ASC"
    )
    ch_result = await asyncio.to_thread(
        ch_client.query, ch_query, {"tenant_id": tenant_id, "trace_id": trace_id}
    )
    ch_rows = ch_result.result_rows

    # --- Step 2: No-spans-yet check ---
    if not ch_rows:
        # Secondary PostgreSQL existence check before deciding 404.
        pg_existence = await session.execute(
            select(Flag).where(
                Flag.tenant_id == tenant_id,
                Flag.trace_id == trace_id,
            ).limit(1)
        )
        existing_flag = pg_existence.scalars().first()

        if existing_flag is None:
            # Neither CH nor PG has any record for (tenant_id, trace_id).
            # Covers true not-found AND cross-tenant stealth (both filters by
            # requesting tenant_id, so the other tenant's data is invisible).
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Trace not found", "status": 404},
            )

        # Trace exists in PostgreSQL but no spans in ClickHouse yet.
        # Collect all trace-level flags (span_id IS NULL) for the response.
        trace_flags_result = await session.execute(
            select(Flag).where(
                Flag.tenant_id == tenant_id,
                Flag.trace_id == trace_id,
                Flag.span_id.is_(None),
            )
        )
        trace_flags = trace_flags_result.scalars().all()

        return TraceDetailResponse(
            trace=TraceObject(
                trace_id=trace_id,
                start_time=existing_flag.created_at.isoformat()
                if hasattr(existing_flag.created_at, "isoformat")
                else str(existing_flag.created_at),
                duration=0.0,
                flags=[
                    TraceFlagItem(
                        flag_type=f.flag_type,
                        score=f.score,
                        detail=f.detail,
                    )
                    for f in trace_flags
                ],
            ),
            spans=[],
        )

    # --- Step 3: Collect span_ids ---
    span_ids = [row[0] for row in ch_rows]

    # --- Step 4a: PostgreSQL flags for this trace (all: span-level + trace-level) ---
    # Sequential execute — AsyncSession is NOT safe for concurrent use.
    all_flags_result = await session.execute(
        select(Flag).where(
            Flag.tenant_id == tenant_id,
            Flag.trace_id == trace_id,
        )
    )
    all_flags: list[Flag] = list(all_flags_result.scalars().all())

    # --- Step 4b: span_scores for all span_ids (RLS + explicit WHERE) ---
    scores_result = await session.execute(
        text(
            "SELECT span_id, analyzer_name, metric_name, score "
            "FROM span_scores "
            "WHERE tenant_id = :tid AND span_id = ANY(:span_ids)"
        ),
        {"tid": tenant_id, "span_ids": list(span_ids)},
    )
    scores_rows = scores_result.fetchall()

    # --- Step 5: Separate trace-level vs span-level flags; build indexes ---
    trace_flags_list: list[TraceFlagItem] = []
    flags_by_span: dict[str, list[TraceFlagItem]] = {}

    for flag in all_flags:
        item = TraceFlagItem(
            flag_type=flag.flag_type,
            score=flag.score,
            detail=flag.detail,
        )
        if flag.span_id is None:
            trace_flags_list.append(item)
        else:
            flags_by_span.setdefault(flag.span_id, []).append(item)

    scores_by_span: dict[str, list[ScoreItem]] = {}
    for row in scores_rows:
        sid, analyzer_name, metric_name, score = row
        scores_by_span.setdefault(sid, []).append(
            ScoreItem(analyzer_name=analyzer_name, metric_name=metric_name, score=score)
        )

    # --- Step 6: Compute trace start_time and duration from CH rows ---
    # CH rows are sorted ASC by time_begin — first row has min, last has max.
    first_time_begin = ch_rows[0][4]  # time_begin of first span
    last_time_end = ch_rows[-1][5]  # time_end of last span

    trace_start_time = _to_iso(first_time_begin)

    try:
        if hasattr(first_time_begin, "timestamp") and hasattr(last_time_end, "timestamp"):
            trace_duration = last_time_end.timestamp() - first_time_begin.timestamp()
        else:
            trace_duration = float(last_time_end) - float(first_time_begin)
    except Exception:
        trace_duration = 0.0

    # --- Step 7: Assemble response ---
    spans_out: list[SpanInTrace] = []
    for row in ch_rows:
        span_id_val, parent_span_id, tool_name, agent_model, time_begin, time_end = row
        spans_out.append(
            SpanInTrace(
                span_id=span_id_val,
                parent_span_id=parent_span_id,
                tool_name=tool_name,
                model=agent_model,
                start_time=_to_iso(time_begin),
                end_time=_to_iso(time_end),
                input_tokens=None,   # not in current ClickHouse schema
                output_tokens=None,  # not in current ClickHouse schema
                flags=flags_by_span.get(span_id_val, []),
                scores=scores_by_span.get(span_id_val, []),
            )
        )

    return TraceDetailResponse(
        trace=TraceObject(
            trace_id=trace_id,
            start_time=trace_start_time,
            duration=trace_duration,
            flags=trace_flags_list,
        ),
        spans=spans_out,
    )
