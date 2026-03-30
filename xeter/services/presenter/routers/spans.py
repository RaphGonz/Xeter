"""
Presenter spans router — span list endpoint.

GET /spans
  Returns a paginated list of spans with inline flag summaries and similarity scores.
  Tenant isolation is enforced by the JWT session token (via verify_session_token)
  AND by explicit WHERE tenant_id = ? clauses on all queries.

  CRITICAL: span_scores has NO PostgreSQL RLS. The WHERE tenant_id clause is the
  SOLE isolation mechanism for that table — never omit it.

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
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from xeter.services.presenter.deps import verify_session_token
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
    request: Request,
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> SpanListResponse:
    """Return a paginated list of spans for the authenticated tenant.

    Steps:
      1. Query ClickHouse for spans matching tenant_id, applying cursor if present.
      2. Query PostgreSQL flags for those span_ids.
      3. Query PostgreSQL span_scores for those span_ids (no RLS — explicit tenant_id filter).
      4. Merge results: attach flag summaries, derive status, compute duration_ms.
      5. Compute next_cursor from last span's time_begin if result count == limit.
    """
    ch_client = request.app.state.ch_client

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
    # Use plain select with explicit tenant_id filter in addition to RLS
    flags_result = await session.execute(
        select(Flag).where(
            Flag.tenant_id == tenant_id,
            Flag.span_id.in_(span_ids),
        )
    )
    flags: list[Flag] = list(flags_result.scalars().all())

    # Build span_id -> [FlagSummary] index
    flags_by_span: dict[str, list[FlagSummary]] = {}
    for flag in flags:
        flags_by_span.setdefault(flag.span_id, []).append(
            FlagSummary(flag_type=flag.flag_type, score=flag.score)
        )

    # --- Step 3: span_scores query (NO RLS — must include tenant_id filter) ---
    # Use raw text query since span_scores is not an ORM model
    scores_result = await session.execute(
        text(
            "SELECT span_id, analyzer_name, metric_name, score "
            "FROM span_scores "
            "WHERE tenant_id = :tid AND span_id IN :span_ids"
        ),
        {"tid": tenant_id, "span_ids": tuple(span_ids)},
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
