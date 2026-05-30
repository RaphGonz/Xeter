# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Score writer for the Embedding Worker.

Inserts one row per (analyzer_name, metric_name, score) tuple into the
span_scores table. span_scores has RLS (added in migration 004, Phase 14) —
SET LOCAL app.current_tenant_id is required inside the transaction so the
tenant_isolation policy is satisfied. Uses psycopg2 (sync), not asyncpg.

All scores for a span are inserted in a single executemany call. Errors are
logged with span_id context and re-raised so the worker loop can log-and-skip
the span rather than silently swallowing the failure.

Environment variables:
  DATABASE_URL — PostgreSQL connection string. May use postgresql+asyncpg://
                 scheme (SQLAlchemy format); the +asyncpg driver prefix is
                 stripped before connecting with psycopg2.
"""

from __future__ import annotations

import logging
import os

import psycopg2

logger = logging.getLogger(__name__)

_INSERT_SQL = (
    "INSERT INTO span_scores (span_id, tenant_id, analyzer_name, metric_name, score) "
    "VALUES (%s, %s, %s, %s, %s)"
)


def _get_dsn() -> str:
    """Return a psycopg2-compatible DSN from DATABASE_URL.

    Strips the +asyncpg driver prefix if present (SQLAlchemy uses
    postgresql+asyncpg:// but psycopg2 requires postgresql://).
    """
    url = os.environ["DATABASE_URL"]
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgres+asyncpg://", "postgresql://")
    )


def write_scores(
    span_id: str | None,
    tenant_id: str,
    scores: list[tuple[str, str, float]],
) -> None:
    """Insert all score tuples for a span into span_scores.

    Sets SET LOCAL app.current_tenant_id inside the transaction so the RLS
    tenant_isolation policy is satisfied (added in migration 004).
    Uses manual transaction management (autocommit=False) to ensure the SET LOCAL
    and INSERTs run in the same transaction scope — matching flag_writer.py pattern.

    Args:
        span_id: The span being scored, or None for trace-level scores produced by TraceAnalyzer (psycopg2 maps None to SQL NULL automatically).
        tenant_id: The owning tenant (stored on the row AND used for RLS SET LOCAL).
        scores: List of (analyzer_name, metric_name, score) tuples.
                If empty, returns immediately without connecting to PostgreSQL.

    Raises:
        psycopg2.Error: On any database error. Caller handles via log-and-skip.
    """
    if not scores:
        return

    rows = [(span_id, tenant_id, analyzer_name, metric_name, score)
            for analyzer_name, metric_name, score in scores]

    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL app.current_tenant_id = %s",
                (str(tenant_id),),
            )
            cur.executemany(_INSERT_SQL, rows)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(
            "score_writer: failed to write %d scores for span_id=%s: %s",
            len(scores), span_id, exc,
        )
        raise
    finally:
        conn.close()
