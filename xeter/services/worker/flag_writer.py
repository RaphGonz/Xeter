# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Flag writer for the Embedding Worker.

Inserts one row per Flag into the flags table. The flags table HAS Row-Level
Security (RLS): `tenant_id::text = current_setting('app.current_tenant_id', true)`.

The worker connects as a BYPASSRLS role (DATABASE_URL) which bypasses the policy
check automatically. SET LOCAL app.current_tenant_id is still executed inside the
transaction as a defensive measure — it is harmless with BYPASSRLS and ensures
correctness if the connection role changes.

Uses psycopg2 (sync), not asyncpg. Flag.detail is serialised to JSON before
insertion.

Environment variables:
  DATABASE_URL — PostgreSQL connection string. May use postgresql+asyncpg://
                 scheme (SQLAlchemy format); the +asyncpg driver prefix is
                 stripped before connecting with psycopg2.
"""

from __future__ import annotations

import json
import logging
import os

import psycopg2

from xeter.services.worker.base import Flag

logger = logging.getLogger(__name__)

_INSERT_SQL = (
    "INSERT INTO flags (tenant_id, span_id, trace_id, flag_type, score, detail) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
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


def write_flags(
    span_id: str | None,
    tenant_id: str,
    trace_id: str,
    flags: list[Flag],
) -> None:
    """Insert all Flag instances for a span or trace into the flags table.

    Sets SET LOCAL app.current_tenant_id inside the transaction so the RLS
    policy is satisfied. Uses manual transaction management (autocommit=False)
    to ensure the SET LOCAL and INSERTs run in the same transaction scope.

    Args:
        span_id: The span that triggered the flags, or None for trace-level
                 flags produced by TraceAnalyzer (which analyze a full trace,
                 not a single span). psycopg2 maps None to SQL NULL automatically.
        tenant_id: The owning tenant (used for RLS and the tenant_id column).
        trace_id: The trace the span belongs to.
        flags: List of Flag instances. If empty, returns immediately without
               connecting to PostgreSQL.

    Raises:
        psycopg2.Error: On any database error. Caller handles via log-and-skip.
    """
    if not flags:
        return

    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SET LOCAL app.current_tenant_id = %s",
                (str(tenant_id),),
            )
            for flag in flags:
                cur.execute(
                    _INSERT_SQL,
                    (
                        tenant_id,
                        span_id,
                        trace_id,
                        flag.flag_type,
                        flag.score,
                        json.dumps(flag.detail),
                    ),
                )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        flag_types = [f.flag_type for f in flags]
        logger.error(
            "flag_writer: failed to write %d flags for span_id=%s flag_types=%s: %s",
            len(flags), span_id, flag_types, exc,
        )
        raise
    finally:
        conn.close()
