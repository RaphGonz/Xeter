"""
FastAPI application entry point for the Xeter Analyser service.

Manages the full lifespan of background resources:
  - SpanBatcher (ClickHouse batch writer) — started on startup, stopped on shutdown
  - Redis client — created on startup, closed on shutdown
  - S3Client — created on startup (stateless, recreated each startup)

Resources are stored on app.state so that endpoint dependencies can retrieve
them via Request.app.state (see ingest.py dependency injectors).

Routes:
  GET  /healthz      — liveness probe (no dependencies checked)
  POST /v1/spans     — span ingestion (from ingest router)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from xeter.services.analyser.batch import SpanBatcher, get_clickhouse_client
from xeter.services.analyser.ingest import router as ingest_router
from xeter.services.analyser.s3 import get_s3_client
from xeter.shared.db.clickhouse import create_spans_table, alter_spans_add_expected_output_schema
from xeter.shared.db.redis import get_redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of shared resources.

    Startup:
      1. Create ClickHouse client and start SpanBatcher background task
      2. Create Redis async client (lazy — no network call until first command)
      3. Create S3Client

    Shutdown:
      1. Stop SpanBatcher (cancels flush loop, flushes remaining rows)
      2. Close Redis connection
    """
    # Startup
    logger.info("analyser: starting up")
    ch_client = get_clickhouse_client()
    create_spans_table(ch_client)
    alter_spans_add_expected_output_schema(ch_client)
    app.state.batcher = SpanBatcher(ch_client)
    await app.state.batcher.start()
    app.state.redis = get_redis_client()
    app.state.s3_client = get_s3_client()
    logger.info("analyser: ready")

    yield

    # Shutdown
    logger.info("analyser: shutting down")
    await app.state.batcher.stop()
    await app.state.redis.aclose()
    logger.info("analyser: shutdown complete")


app = FastAPI(
    title="Xeter Analyser",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(ingest_router)


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe — returns 200 if the process is alive.

    Does not check connectivity to ClickHouse, Redis, or S3.
    Use a separate readiness probe for dependency health checks.
    """
    return {"status": "ok"}
