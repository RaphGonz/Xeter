# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Ingestion router for the Analyser service.

Provides:
  - router: APIRouter with POST /v1/spans handler
  - get_batcher_dep: dependency that retrieves SpanBatcher from app.state
  - get_redis_dep: dependency that retrieves Redis client from app.state
  - get_s3_client_dep: dependency that retrieves S3Client from app.state

POST /v1/spans execution order (locked — do not reorder):
  1. Auth: verify_api_key_header returns tenant_id (raises 401 on failure)
  2. S3: upload all payload fields before any ClickHouse or Redis write
     — if S3 fails, return 500 immediately (span not accepted)
  3. Batcher: add row to ClickHouse batch queue
  4. Redis: LPUSH span_id to analysis_queue
     — if Redis fails, return 500 (enqueue failure is hard error)
  5. Return {"accepted": True}

This ordering guarantees:
  - ClickHouse never has a row without its S3 payloads
  - Redis only receives span_ids that are in ClickHouse
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from xeter.services.analyser.auth import verify_api_key_header
from xeter.services.analyser.batch import SPAN_COLUMNS, SpanBatcher
from xeter.services.analyser.queue import enqueue_span_id
from xeter.services.analyser.s3 import S3Client
from xeter.services.analyser.schemas import SpanPayload

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency injectors — retrieve singletons stored in app.state at startup
# ---------------------------------------------------------------------------


def get_batcher_dep(request: Request) -> SpanBatcher:
    """Return the SpanBatcher instance stored in app.state during lifespan."""
    return request.app.state.batcher


def get_redis_dep(request: Request) -> Redis:
    """Return the Redis client stored in app.state during lifespan."""
    return request.app.state.redis


def get_s3_client_dep(request: Request) -> S3Client:
    """Return the S3Client instance stored in app.state during lifespan."""
    return request.app.state.s3_client


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/v1/spans", status_code=200)
async def ingest_span(
    span: SpanPayload,
    tenant_id: str = Depends(verify_api_key_header),
    s3: S3Client = Depends(get_s3_client_dep),
    batcher: SpanBatcher = Depends(get_batcher_dep),
    redis: Redis = Depends(get_redis_dep),
) -> dict:
    """Accept a single span from the SDK.

    Execution order: S3 upload -> ClickHouse batch add -> Redis enqueue.

    Args:
        span:      Validated SpanPayload from request body.
        tenant_id: Tenant UUID returned by API key verification.
        s3:        S3Client from app.state.
        batcher:   SpanBatcher from app.state.
        redis:     Redis client from app.state.

    Returns:
        {"accepted": True} on success.

    Raises:
        HTTPException(401): Propagated from verify_api_key_header.
        HTTPException(500): S3 upload failed or Redis enqueue failed.
    """
    # Step 1: Upload payload fields to S3 (must succeed before ClickHouse write)
    try:
        refs = await s3.upload_span_payloads(
            tenant_id,
            span.span_id,
            span.prompt,
            span.response,
            span.raw_response,
            span.available_tools_ref,
        )
    except Exception as exc:
        logger.error("ingest: S3 upload failed for span %s: %s", span.span_id, exc)
        raise HTTPException(status_code=500, detail="payload storage failed")

    # Step 2: Build ClickHouse row in SPAN_COLUMNS order
    # SPAN_COLUMNS = [span_id, trace_id, parent_span_id, tenant_id, agent_name,
    #                 agent_model, tool_name, tool_description, tool_arguments,
    #                 expected_output_schema, tool_output, prompt_ref,
    #                 response_ref, raw_response_ref, available_tools_ref,
    #                 time_begin, time_end, schema_version]
    row = [
        span.span_id,
        span.trace_id or "",
        span.parent_span_id,
        tenant_id,
        span.agent_name,
        span.agent_model,
        span.tool_name,
        span.tool_description,
        span.tool_arguments,
        span.expected_output_schema,
        span.tool_output,
        refs["prompt_ref"],
        refs["response_ref"],
        refs["raw_response_ref"],
        refs["available_tools_ref"],
        span.time_begin,
        span.time_end,
        span.schema_version,
    ]

    # Guard: row must match SPAN_COLUMNS exactly (catch drift at startup)
    assert len(row) == len(SPAN_COLUMNS), (
        f"Row length mismatch: got {len(row)}, expected {len(SPAN_COLUMNS)}"
    )

    # Step 3: Add to ClickHouse batch queue
    await batcher.add(row)

    # Step 4: Enqueue span_id in Redis for the analysis worker
    try:
        await enqueue_span_id(redis, span.span_id)
    except Exception as exc:
        logger.error("ingest: Redis enqueue failed for span %s: %s", span.span_id, exc)
        raise HTTPException(status_code=500, detail="enqueue failed")

    return {"accepted": True}
