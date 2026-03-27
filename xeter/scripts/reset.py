"""
Reset script: drops all DB schemas and recreates them from scratch, then re-runs seed.
Run: python -m xeter.scripts.reset  (or: make reset)

WARNING: This deletes ALL data. For dev environment use only.

Steps:
  1. Prints a 3-second cancellation window
  2. Drops and recreates the PostgreSQL public schema
  3. Runs `alembic upgrade head` to recreate all tables
  4. Drops and recreates the ClickHouse spans table
  5. Runs seed.py to populate fixed dev credentials

Prerequisites:
  DATABASE_URL   — postgresql+asyncpg://... (for seed)
  POSTGRES_URL   — postgresql://...         (sync, for schema DROP/CREATE — may include SUPERUSER/BYPASSRLS)
                   Falls back to DATABASE_URL if not set (replacing asyncpg scheme).
  CLICKHOUSE_*   — optional, defaults to localhost:8123
"""

import asyncio
import os
import subprocess
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from xeter.shared.db.clickhouse import get_clickhouse_client, create_spans_table
from xeter.scripts.seed import main as seed_main

# Alembic ini is expected at the root of the xeter package (where alembic.ini lives)
_ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def _get_sync_postgres_url() -> str:
    """Return a synchronous PostgreSQL DSN for DDL operations.

    Prefers POSTGRES_URL env var (may include BYPASSRLS privileges).
    Falls back to DATABASE_URL, substituting the asyncpg driver with psycopg2.
    """
    url = os.environ.get("POSTGRES_URL")
    if url:
        return url
    url = os.environ.get("DATABASE_URL", "")
    # Replace asyncpg driver for synchronous use
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _reset_postgres() -> None:
    """Drop and recreate the PostgreSQL public schema, then run Alembic migrations."""
    import psycopg2  # type: ignore

    sync_url = _get_sync_postgres_url()
    print("Dropping PostgreSQL public schema...")
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE")
            cur.execute("CREATE SCHEMA public")
        print("Schema dropped and recreated.")
    finally:
        conn.close()

    print("Running alembic upgrade head...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        capture_output=False,
    )
    print("Migrations applied.")


def _reset_clickhouse() -> None:
    """Drop and recreate the ClickHouse spans table."""
    client = get_clickhouse_client()
    print("Dropping ClickHouse spans table...")
    client.command("DROP TABLE IF EXISTS spans")
    print("Recreating ClickHouse spans table...")
    create_spans_table(client)
    print("ClickHouse spans table ready.")


async def main() -> None:
    """Run the full reset sequence."""
    print("WARNING: This will delete all data. Ctrl+C to cancel. Proceeding in 3 seconds...")
    time.sleep(3)

    _reset_postgres()
    _reset_clickhouse()

    print("Running seed...")
    await seed_main()

    print("Reset complete.")


if __name__ == "__main__":
    asyncio.run(main())
