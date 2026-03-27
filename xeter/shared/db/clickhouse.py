"""
ClickHouse client setup and spans table DDL for Xeter.

The spans table uses MergeTree with ORDER BY (tenant_id, trace_id, time_begin).
This ORDER BY is a one-way door — do not change it after any data has been written.
Changing the primary key of a MergeTree table requires a full table rebuild.

Schema initialization:
    Client connection is established by get_clickhouse_client().
    The spans table is created (if not exists) by calling create_spans_table(client).
    This is called on application startup — ClickHouse has no Alembic equivalent.

Column notes:
    tool_arguments: Stored as Nullable(String) containing JSON-serialized content.
    The application layer serializes before write and deserializes after read.
    If a payload exceeds ~4 KB, consider adding a tool_arguments_ref column
    pointing to an S3 object key instead (deferred to Phase 2).
"""

import os

import clickhouse_connect

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def get_clickhouse_client() -> clickhouse_connect.driver.Client:
    """Return a ClickHouse HTTP client configured from environment variables.

    Environment variables (all optional, sensible defaults for local dev):
        CLICKHOUSE_HOST     — default: localhost
        CLICKHOUSE_PORT     — default: 8123 (HTTP interface)
        CLICKHOUSE_DB       — default: default
        CLICKHOUSE_USER     — default: default
        CLICKHOUSE_PASSWORD — default: "" (empty)
    """
    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        database=os.environ.get("CLICKHOUSE_DB", "default"),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Spans table DDL
#
# ORDER BY (tenant_id, trace_id, time_begin) — immutable one-way door.
# This primary key enables efficient queries for:
#   - All spans for a tenant (leading key column)
#   - All spans in a trace for a tenant (tenant_id + trace_id prefix)
#   - Time-ordered spans within a trace (full key)
# ---------------------------------------------------------------------------

SPANS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS spans (
    tenant_id           String,
    trace_id            String,
    span_id             String,
    parent_span_id      Nullable(String),
    time_begin          DateTime64(3, 'UTC'),
    time_end            DateTime64(3, 'UTC'),
    agent_name          String,
    agent_model         String,
    recipient           String,
    recipient_model     Nullable(String),
    tool_name           Nullable(String),
    tool_description    Nullable(String),
    tool_arguments      Nullable(String),
    tool_output         Nullable(String),
    available_tools_ref Nullable(String),
    prompt_ref          String,
    response_ref        String,
    raw_response_ref    String,
    schema_version      String DEFAULT '1.0'
)
ENGINE = MergeTree()
ORDER BY (tenant_id, trace_id, time_begin)
SETTINGS index_granularity = 8192
"""


# ---------------------------------------------------------------------------
# Schema initializer
# ---------------------------------------------------------------------------


def create_spans_table(client: clickhouse_connect.driver.Client) -> None:
    """Create the spans table in ClickHouse if it does not already exist.

    This is idempotent — safe to call on every application startup.
    ClickHouse has no migration framework equivalent to Alembic; schema
    management is done via CREATE TABLE IF NOT EXISTS at startup.

    Args:
        client: A ClickHouse client returned by get_clickhouse_client().
    """
    client.command(SPANS_TABLE_DDL)


# ---------------------------------------------------------------------------
# EXPLAIN verification helper
#
# Used in integration tests to confirm that tenant+trace queries hit the
# primary key index rather than performing a full table scan.
# ---------------------------------------------------------------------------

_EXPLAIN_QUERY = """
EXPLAIN indexes = 1
SELECT span_id, agent_name, time_begin
FROM spans
WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
  AND trace_id = 'test-trace-id'
ORDER BY time_begin ASC
"""


def verify_index_usage(client: clickhouse_connect.driver.Client) -> str:
    """Run EXPLAIN on a representative tenant+trace query and return raw output.

    The returned string contains the EXPLAIN plan including index usage
    information. Integration tests should assert that the output does NOT
    contain "FullScan" or equivalent indicators of a full table scan.

    Args:
        client: A ClickHouse client returned by get_clickhouse_client().

    Returns:
        The EXPLAIN output as a single string (rows joined by newlines).
    """
    result = client.query(_EXPLAIN_QUERY)
    rows = [str(row[0]) for row in result.result_rows]
    return "\n".join(rows)
