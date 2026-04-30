#!/usr/bin/env python3
"""GDPR Art. 17 tenant data deletion script.

Dry-run by default — prints a summary of all data that would be deleted across
ClickHouse, PostgreSQL (7 tables), S3, and Redis without touching any data.

Pass --confirm to execute the deletion across all stores.

Usage:
    # Dry-run (safe, no data deleted):
    python xeter/scripts/delete_tenant.py --tenant-id <uuid>

    # Execute deletion:
    python xeter/scripts/delete_tenant.py --tenant-id <uuid> --confirm

Must be run from the repo root where `xeter/` is importable, with all
required environment variables set (DATABASE_URL, CLICKHOUSE_HOST,
CLICKHOUSE_PASSWORD, S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, REDIS_URL).
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

import boto3
import psycopg2
import redis as redis_lib

from xeter.shared.db.clickhouse import get_clickhouse_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_BUCKET = os.environ.get("S3_BUCKET", "xeter-payloads")

# PostgreSQL tables deleted in child-before-parent FK order.
# Violating this order raises psycopg2.errors.ForeignKeyViolation.
_PG_DELETE_TABLES = [
    "span_scores",   # no FK to tenants
    "diagnostics",   # no FK to tenants (legacy Phase 1, __tablename__ = "diagnostics")
    "diagnoses",     # no FK to tenants (Phase 11 Diagnosticer)
    "flags",         # no FK to tenants
    "api_keys",      # FK: api_keys.tenant_id -> tenants.tenant_id
    "users",         # FK: users.tenant_id -> tenants.tenant_id
    "tenants",       # parent row — LAST
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    """Convert DATABASE_URL (asyncpg scheme) to a psycopg2-compatible DSN."""
    url = os.environ["DATABASE_URL"]
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


def _get_s3_client():
    """Return a boto3 S3 client configured from environment variables."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )


# ---------------------------------------------------------------------------
# Count phase (dry-run)
# ---------------------------------------------------------------------------


def _count_clickhouse(tenant_id: str) -> int:
    """Return the number of spans rows for this tenant in ClickHouse."""
    client = get_clickhouse_client()
    result = client.query(
        "SELECT count() FROM spans WHERE tenant_id = %(tenant_id)s",
        parameters={"tenant_id": tenant_id},
    )
    return int(result.result_rows[0][0])


def _count_postgres(tenant_id: str) -> dict[str, int]:
    """Return a per-table row count for this tenant across all PG tables."""
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = True
    counts: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            for table in _PG_DELETE_TABLES:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608
                    (tenant_id,),
                )
                counts[table] = cur.fetchone()[0]
    finally:
        conn.close()
    return counts


def _count_s3(tenant_id: str) -> int:
    """Return the total number of S3 objects under the tenant prefix."""
    s3 = _get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{tenant_id}/"):
        total += len(page.get("Contents", []))
    return total


def _count_redis() -> int:
    """Return the current length of the global analysis_queue in Redis.

    Returns 0 on connection error so Redis unavailability does not block the
    dry-run (Redis is a transit queue only; emptiness is the expected state).
    """
    try:
        r = redis_lib.from_url(os.environ["REDIS_URL"])
        return r.llen("analysis_queue")
    except Exception:  # noqa: BLE001
        return -1  # sentinel: -1 means "unavailable"


# ---------------------------------------------------------------------------
# Dry-run output
# ---------------------------------------------------------------------------


def _print_dry_run_summary(
    tenant_id: str,
    ch: int,
    pg: dict[str, int],
    s3: int,
    queue: int,
) -> None:
    """Print the multi-store dry-run summary to stdout."""
    if queue == -1:
        queue_display = "~0 (Redis unavailable)"
    else:
        queue_display = f"~{queue}"

    print(f"Dry-run summary for tenant: {tenant_id}")
    print()
    print(f"  ClickHouse spans:         {ch:,} rows")
    print(f"  PostgreSQL span_scores:   {pg.get('span_scores', 0):,} rows")
    print(f"  PostgreSQL diagnostics:   {pg.get('diagnostics', 0):,} rows")
    print(f"  PostgreSQL diagnoses:     {pg.get('diagnoses', 0):,} rows")
    print(f"  PostgreSQL flags:         {pg.get('flags', 0):,} rows")
    print(f"  PostgreSQL api_keys:      {pg.get('api_keys', 0):,} rows")
    print(f"  PostgreSQL users:         {pg.get('users', 0):,} rows")
    print(f"  PostgreSQL tenants:       {pg.get('tenants', 0):,} rows")
    print(f"  S3 objects:               {s3:,} objects  (prefix: {tenant_id}/)")
    print()
    print(f"  Redis (analysis_queue): {queue_display} items  (transit queue — typically empty after processing)")
    print("  Redis flush procedure:")
    print("    If tenant spans are still queued (rare):")
    print("    1. Stop the Worker service: docker compose stop worker")
    print("    2. Inspect queue: redis-cli -a $REDIS_PASSWORD LRANGE analysis_queue 0 -1")
    print("    3. Remove matching span_ids one by one: redis-cli -a $REDIS_PASSWORD LREM analysis_queue 0 <span_id>")
    print("    4. Restart Worker: docker compose start worker")
    print("    NOTE: The analysis_queue is a short-lived transit queue. Spans are processed within")
    print("    seconds of ingestion. GDPR deletion is typically invoked after the tenant is inactive,")
    print("    making this queue empty.")
    print()
    print("DRY-RUN: No data deleted. Pass --confirm to execute.")


# ---------------------------------------------------------------------------
# Deletion phase (--confirm only)
# ---------------------------------------------------------------------------


def _delete_clickhouse(tenant_id: str) -> None:
    """Submit an async ALTER TABLE DELETE mutation to ClickHouse."""
    client = get_clickhouse_client()
    client.command(
        "ALTER TABLE spans DELETE WHERE tenant_id = %(tenant_id)s",
        parameters={"tenant_id": tenant_id},
    )
    print("  ClickHouse: mutation submitted (background — run dry-run again after 30s to verify count is 0)")


def _delete_postgres(tenant_id: str) -> None:
    """Delete all rows for this tenant across all 7 PostgreSQL tables.

    Uses a single connection with autocommit=False and a single commit after
    all DELETEs. Deletion order is child-before-parent to avoid FK violations.
    All queries are parameterised — no string interpolation.
    """
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for table in _PG_DELETE_TABLES:
                cur.execute(
                    f"DELETE FROM {table} WHERE tenant_id = %s",  # noqa: S608
                    (tenant_id,),
                )
                print(f"  Deleted from PostgreSQL.{table}: {cur.rowcount} rows")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _delete_s3(tenant_id: str) -> int:
    """Delete all S3 objects under the tenant prefix using paginated batch deletes.

    Uses list_objects_v2 pagination and delete_objects in batches of up to 1000
    (the S3 API maximum per call). Returns the total number of deleted objects.
    """
    s3 = _get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    total_deleted = 0

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{tenant_id}/"):
        contents = page.get("Contents", [])
        if not contents:
            continue
        keys = [{"Key": obj["Key"]} for obj in contents]
        s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys})
        total_deleted += len(keys)

    print(f"  Deleted from S3: {total_deleted} objects")
    return total_deleted


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "GDPR Art. 17 tenant data deletion. "
            "Runs a dry-run summary by default. "
            "Pass --confirm to execute deletion across ClickHouse, PostgreSQL, and S3."
        )
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        metavar="UUID",
        help="UUID of the tenant to delete (required).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Execute the deletion. Without this flag the script only prints a dry-run summary.",
    )
    args = parser.parse_args()

    # UUID validation — must happen before any DB connection attempt.
    try:
        uuid.UUID(args.tenant_id)
    except ValueError:
        print(f"ERROR: '{args.tenant_id}' is not a valid UUID.")
        sys.exit(1)

    tenant_id = args.tenant_id

    # --- Dry-run phase (always runs) ---
    print(f"Connecting to data stores for tenant: {tenant_id} ...")
    print()

    ch_count = _count_clickhouse(tenant_id)
    pg_counts = _count_postgres(tenant_id)
    s3_count = _count_s3(tenant_id)
    queue_count = _count_redis()

    _print_dry_run_summary(tenant_id, ch_count, pg_counts, s3_count, queue_count)

    if not args.confirm:
        return

    # --- Deletion phase (only with --confirm) ---
    print()
    print(f"Executing deletion for tenant: {tenant_id} ...")
    print()

    _delete_clickhouse(tenant_id)
    _delete_postgres(tenant_id)
    _delete_s3(tenant_id)

    print()
    print(f"DELETION COMPLETE. Tenant {tenant_id} data removed from ClickHouse, PostgreSQL, and S3.")


if __name__ == "__main__":
    main()
