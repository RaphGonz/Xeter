---
phase: 03-analysis-path
plan: "03"
subsystem: worker-io
tags: [worker, clickhouse, s3, postgresql, psycopg2, boto3]

dependency_graph:
  requires:
    - 03-01-PLAN.md  # SpanData, Flag, BaseAnalyzer in worker/base.py
    - xeter/services/analyser/batch.py  # get_clickhouse_client factory
  provides:
    - xeter/services/worker/span_fetcher.py  # fetch_span()
    - xeter/services/worker/score_writer.py  # write_scores()
    - xeter/services/worker/flag_writer.py   # write_flags()
  affects:
    - 03-04-PLAN.md  # worker loop will call all three modules

tech_stack:
  added:
    - boto3  # sync S3 client for payload fetch
    - psycopg2-binary  # sync PostgreSQL for score and flag writes
  patterns:
    - S3 double-decode: {"value": "..."} envelope -> json.loads -> inner string -> json.loads for tools
    - DATABASE_URL scheme transform: +asyncpg prefix stripped for psycopg2 compatibility
    - RLS bypass: SET LOCAL app.current_tenant_id inside manual transaction in flag_writer

key_files:
  created:
    - xeter/services/worker/span_fetcher.py
    - xeter/services/worker/score_writer.py
    - xeter/services/worker/flag_writer.py
  modified: []

decisions:
  - DATABASE_URL +asyncpg prefix stripped in both writer modules — same env var used by SQLAlchemy (async) and psycopg2 (sync)
  - SET LOCAL app.current_tenant_id in flag_writer even though BYPASSRLS connection — defensive, harmless, preserves correctness if role changes
  - raw_response fetched but not returned in SpanData — S3 call made for completeness; field unused in Phase 3 analyzers
  - Full table scan on ClickHouse spans WHERE span_id — accepted at Phase 3 volume; span_id not in ORDER BY key

metrics:
  duration_seconds: 453
  completed_date: "2026-03-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
---

# Phase 3 Plan 03: Worker I/O Modules Summary

Sync I/O connectors for the Embedding Worker: span_fetcher (ClickHouse + S3 boto3), score_writer and flag_writer (psycopg2 to PostgreSQL span_scores and flags tables).

## What Was Built

Three I/O modules that isolate all external system access from the analyzer logic.

**`xeter/services/worker/span_fetcher.py`**

- `fetch_span(span_id)` queries ClickHouse via `get_clickhouse_client()` (imported from analyser batch.py), maps the row to a dict by zip(column_names, first_row), then fetches S3 payloads for prompt, response, and available_tools.
- `_fetch_s3_text()` unwraps the `{"value": "..."}` S3 envelope. Returns None on `botocore.exceptions.ClientError` — S3 failure degrades gracefully rather than crashing the worker.
- `_decode_available_tools()` handles the double-encode: the S3 value is a JSON string that itself represents a `list[dict]`. Returns None on malformed input (no exception propagated).
- `get_s3_client()` factory reads `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` from env.

**`xeter/services/worker/score_writer.py`**

- `write_scores(span_id, tenant_id, scores)` short-circuits immediately on empty scores list.
- Connects via psycopg2 (DATABASE_URL with `+asyncpg` stripped). Uses `executemany` for a single round-trip per span.
- span_scores has no RLS — no SET LOCAL required.

**`xeter/services/worker/flag_writer.py`**

- `write_flags(span_id, tenant_id, trace_id, flags)` short-circuits on empty flags list.
- Uses manual transaction (`autocommit=False`, explicit commit/rollback) to ensure `SET LOCAL app.current_tenant_id` and the INSERTs share the same transaction scope.
- `Flag.detail` serialised via `json.dumps()` before INSERT.

## Verification Results

All four plan verification checks passed:

1. All three modules import cleanly.
2. `_decode_available_tools('[{"name":"t"}]')` returns `[{'name': 't'}]`.
3. No `asyncio` found in score_writer.py or flag_writer.py.
4. `replace.*asyncpg` pattern confirmed in score_writer.py (and flag_writer.py).

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit  | Description |
|------|---------|-------------|
| 1    | ee0859f | feat(03-03): span_fetcher — ClickHouse span lookup + S3 payload decoding |
| 2    | d2392f0 | feat(03-03): score_writer and flag_writer — synchronous PostgreSQL writes |

## Self-Check: PASSED

- xeter/services/worker/span_fetcher.py — FOUND
- xeter/services/worker/score_writer.py — FOUND
- xeter/services/worker/flag_writer.py — FOUND
- Commit ee0859f — FOUND
- Commit d2392f0 — FOUND
