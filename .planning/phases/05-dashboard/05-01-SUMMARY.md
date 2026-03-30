---
phase: 05-dashboard
plan: "01"
subsystem: presenter
tags: [filters, api, tdd, clickhouse, postgresql]
dependency_graph:
  requires: [04-01]
  provides: [filter-params-get-spans]
  affects: [05-02, 05-03]
tech_stack:
  added: []
  patterns: [dynamic-where-clauses, post-clickhouse-pg-filter]
key_files:
  created:
    - xeter/tests/presenter/test_spans_list_filters.py
  modified:
    - xeter/services/presenter/routers/spans.py
decisions:
  - "ISO timestamp URL encoding: tests use urllib.parse.quote to percent-encode + in timezone offset, avoiding FastAPI decoding + as space"
  - "flag_type filter is post-ClickHouse: flags live in PostgreSQL, so the filter is applied after ClickHouse fetch by filtering the PostgreSQL flags query; spans absent from flags_by_span are excluded"
  - "flag_type count may be less than limit: acceptable in Phase 5; optimization (pre-filter span_ids) deferred to Phase 6"
metrics:
  duration_seconds: 507
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_created: 1
  files_modified: 1
requirements_completed: [DASH-02]
---

# Phase 5 Plan 01: GET /spans Filter Parameters Summary

TDD implementation of flag_type, agent_name, from_time, to_time filter params on GET /spans — 7 new tests, all green, zero regressions in the 20 existing presenter tests.

## What Was Built

Extended `list_spans` in `xeter/services/presenter/routers/spans.py` with four new optional Query parameters:

- `agent_name` — forwarded to ClickHouse `WHERE agent_name = %(agent_name)s`
- `from_time` — forwarded to ClickHouse `WHERE time_begin >= %(from_time)s`
- `to_time` — forwarded to ClickHouse `WHERE time_begin <= %(to_time)s`
- `flag_type` — applied post-ClickHouse: PostgreSQL flags query includes `Flag.flag_type == flag_type`; spans with no matching flag are excluded from the response

All active filters are AND-combined. No filter = backward-compatible.

## Tasks Completed

| Task | Type | Name | Commit | Files |
|------|------|------|--------|-------|
| 1 | test (RED) | Write failing filter tests | aa88fcf | xeter/tests/presenter/test_spans_list_filters.py |
| 2 | feat (GREEN) | Add filter params to list_spans | f0bb3ce | xeter/services/presenter/routers/spans.py, xeter/tests/presenter/test_spans_list_filters.py |

## Verification

```
27 passed, 1082 warnings in 2.68s
```

All 27 presenter tests pass (7 new filter tests + 20 existing).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ISO timestamp URL encoding in filter tests**
- **Found during:** Task 2 (GREEN)
- **Issue:** The `+` character in ISO 8601 UTC offset (`+00:00`) is decoded as a space by FastAPI's query string parser when sent unencoded in a URL. This caused `test_filter_from_time` and related tests to fail when asserting the exact param value passed to ClickHouse.
- **Fix:** Added `import urllib.parse` to the test file and wrapped ISO timestamps in `urllib.parse.quote()` before embedding in URL strings. The assertions compare against the decoded ISO string (with `+`) which is what the handler receives after FastAPI query parsing.
- **Files modified:** xeter/tests/presenter/test_spans_list_filters.py
- **Commit:** f0bb3ce

## Key Decisions

1. **ISO timestamp URL encoding** — Tests use `urllib.parse.quote` to percent-encode `+` in timezone offsets, since `+` is decoded as space in query strings. This is the correct real-client behavior.

2. **flag_type filter is post-ClickHouse** — Flags live in PostgreSQL, not ClickHouse. The filter is applied by adding `Flag.flag_type == flag_type` to the PostgreSQL flags query. Spans absent from `flags_by_span` are then filtered out before merging. Count may be less than `limit` — acceptable Phase 5 behavior; pre-filter optimization (fetching matching span_ids first) is deferred to Phase 6.

3. **Dynamic where_clauses list pattern** — Same pattern used for cursor pagination is extended for the new filters, keeping the implementation consistent and easy to extend further.

## Self-Check: PASSED

Files verified:
- FOUND: xeter/tests/presenter/test_spans_list_filters.py
- FOUND: xeter/services/presenter/routers/spans.py

Commits verified:
- FOUND: aa88fcf (RED — failing tests)
- FOUND: f0bb3ce (GREEN — implementation)
