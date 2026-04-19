---
phase: 04-read-path
plan: 02
subsystem: api
tags: [fastapi, clickhouse, postgresql, s3, aioboto3, asyncio, jwt, tenant-isolation]

# Dependency graph
requires:
  - phase: 04-read-path plan 01
    provides: verify_session_token dep, GET /spans list endpoint, ClickHouse client on app.state, get_session dep
  - phase: 02-ingestion-path
    provides: S3 key pattern (tenant_id/YYYY-MM/span_id/field.json), prompt_ref/response_ref/raw_response_ref columns in ClickHouse
  - phase: 03-analysis-path
    provides: span_scores table (no RLS), flags table with detail JSON column
provides:
  - GET /spans/{span_id} detail endpoint merging ClickHouse + PostgreSQL + S3
  - FlagDetail, ScoreDetail, SpanDetailResponse response models
  - _fetch_all_s3_payloads helper with asyncio.wait_for(5.0s) timeout
  - 7 unit tests covering all error paths and tenant isolation
affects:
  - phase 04 plan 03 (diagnosticer uses same app/session pattern)
  - phase 05 (SDK read-back will exercise this endpoint)
  - phase 06 (calibration dashboard drill-down uses this endpoint)

# Tech tracking
tech-stack:
  added: [aioboto3 (already present in analyser — now used in presenter too)]
  patterns:
    - asyncio.gather for parallel ClickHouse + PostgreSQL queries in handler
    - asyncio.wait_for(timeout=5.0) wrapping S3 coroutine to enforce hard deadline
    - 404-not-403 for cross-tenant spans (no information leakage)
    - Full 504/502 error on S3 failure — never partial data

key-files:
  created:
    - xeter/tests/presenter/test_span_detail.py
  modified:
    - xeter/services/presenter/routers/spans.py

key-decisions:
  - "GET /spans/{id} returns 404 for cross-tenant spans — WHERE tenant_id in ClickHouse query means cross-tenant lookup returns no rows, identical to not-found, preventing info leakage"
  - "_fetch_all_s3_payloads helper patched directly in tests — cleaner than patching aioboto3.Session internals in error-path tests"

patterns-established:
  - "S3 fetch timeout: asyncio.wait_for wrapping the full aioboto3 context manager coroutine, not individual gets"
  - "Error type dispatch: asyncio.TimeoutError -> 504, all other exceptions -> 502"

requirements-completed: [DASH-03, DASH-04]

# Metrics
duration: 15min
completed: 2026-03-30
---

# Phase 4 Plan 02: Span Detail Summary

**GET /spans/{id} endpoint fetching ClickHouse span + PostgreSQL flags/scores + S3 payloads in parallel, with 5s S3 timeout, 504/502 error handling, and full tenant isolation via 404-not-403**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-30T00:00:00Z
- **Completed:** 2026-03-30
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- GET /spans/{span_id} delivers full span drill-down: flags with detail JSON, similarity scores, S3 prompt/response/raw_response payloads
- asyncio.gather parallelises ClickHouse + PostgreSQL queries; S3 fetch is sequential-after-span-found per plan design
- S3 timeout enforced with asyncio.wait_for(5.0s) — 504 on timeout, 502 on other S3 errors — never partial data returned
- All 7 unit tests pass; total presenter suite now 16 tests (login + list + detail)

## Task Commits

1. **Task 1: GET /spans/{id} endpoint with parallel queries and S3 lazy fetch** - `7eb1339` (feat)
2. **Task 2: Unit tests for span detail endpoint** - `af2e091` (test)

## Files Created/Modified

- `xeter/services/presenter/routers/spans.py` — Added FlagDetail, ScoreDetail, SpanDetailResponse models and GET /spans/{span_id} handler with _fetch_all_s3_payloads helper
- `xeter/tests/presenter/test_span_detail.py` — 7 unit tests: flags+scores, S3 payloads, timeout-504, error-502, not_found-404, cross-tenant-404, missing-token-401

## Decisions Made

- GET /spans/{id} returns 404 (not 403) for cross-tenant spans — the ClickHouse WHERE tenant_id clause means the span simply isn't found, avoiding any information leakage about whether the span exists for another tenant. This is a locked decision matching the plan specification.
- _fetch_all_s3_payloads helper is extracted so tests can patch it at a coarse level for error-path tests (timeout, generic error), keeping tests clean without deep aioboto3 mock chains.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- GET /spans/{id} is live and tested — provides the span drill-down API required by the dashboard
- Plan 03 (Diagnosticer scaffold) is already committed (a48150d) — Phase 4 continues from Plan 03
- All 16 presenter unit tests pass; no regressions

## Self-Check: PASSED

- spans.py: FOUND
- test_span_detail.py: FOUND
- 04-02-SUMMARY.md: FOUND
- Commit 7eb1339: FOUND
- Commit af2e091: FOUND

---
*Phase: 04-read-path*
*Completed: 2026-03-30*
