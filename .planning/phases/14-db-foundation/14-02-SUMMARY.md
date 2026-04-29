---
phase: 14-db-foundation
plan: "02"
subsystem: api
tags: [fastapi, s3, security, tenant-isolation, pytest]

# Dependency graph
requires:
  - phase: 04-read-path
    provides: _fetch_s3_payload and _fetch_all_s3_payloads helpers in spans.py
provides:
  - Tenant-prefix guard in _fetch_s3_payload rejecting cross-tenant S3 keys with HTTP 403
  - Unit test suite (4 tests) proving the guard behaviour at the function level
affects:
  - 16-score-writer (uses presenter S3 fetch patterns as reference)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Defence-in-depth S3 key assertion: check key.startswith(f'{tenant_id}/') before GetObject"
    - "Propagate tenant_id through async S3 fetch chain: caller → _fetch_all → _fetch_s3_payload"

key-files:
  created:
    - xeter/tests/presenter/test_s3_key_assertion.py
  modified:
    - xeter/services/presenter/routers/spans.py
    - xeter/tests/presenter/test_span_detail.py

key-decisions:
  - "S3-01 guard uses key.startswith(f'{tenant_id}/') — works for all key formats past and present"
  - "Guard raises HTTP 403 (not 404) to distinguish tenant ownership violation from missing resource"
  - "Guard fires before any GetObject call to prevent cross-tenant data access even if ClickHouse filter is bypassed"

patterns-established:
  - "Tenant-prefix check pattern: assert key.startswith before any S3 read, raise 403 on mismatch"

requirements-completed:
  - S3-01

# Metrics
duration: 12min
completed: 2026-04-29
---

# Phase 14 Plan 02: S3 Tenant-Prefix Guard Summary

**Defence-in-depth S3 key assertion: _fetch_s3_payload now rejects cross-tenant keys with HTTP 403 before any GetObject call, enforcing S3-01 at the fetch layer independently of ClickHouse tenant filtering.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-29T00:00:00Z
- **Completed:** 2026-04-29T00:12:00Z
- **Tasks:** 2
- **Files modified:** 3 (spans.py, test_span_detail.py, new test_s3_key_assertion.py)

## Accomplishments
- Added `tenant_id: str` as fourth parameter to `_fetch_s3_payload`; raises `HTTPException(403)` when `key.startswith(f"{tenant_id}/")` is False
- Threaded `tenant_id` through `_fetch_all_s3_payloads` and updated the `get_span_detail` call site
- Created 4-test unit suite in `test_s3_key_assertion.py` covering reject, accept, None short-circuit, and historical key format
- Fixed existing test fixtures (Rule 1): `_ch_span_row` keys updated to start with `TENANT_A/` so the guard passes in the HTTP-stack tests
- Full presenter suite: 37 tests pass, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tenant_id parameter and prefix guard to _fetch_s3_payload** - `3996dcb` (feat)
2. **Task 2: Write unit tests for S3 key tenant-prefix assertion** - `25c21c6` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `xeter/services/presenter/routers/spans.py` - Updated `_fetch_s3_payload` with tenant_id guard; updated `_fetch_all_s3_payloads` signature; updated `get_span_detail` call
- `xeter/tests/presenter/test_s3_key_assertion.py` - New: 4 unit tests directly calling `_fetch_s3_payload`
- `xeter/tests/presenter/test_span_detail.py` - Fixed `_ch_span_row` default refs to use TENANT_A prefix

## Decisions Made
- HTTP 403 chosen over 404 to make tenant ownership violations semantically distinct from missing resources
- Guard placed before `get_object` call (not after) so no S3 network traffic occurs for cross-tenant attempts
- `key.startswith(f"{tenant_id}/")` covers all historical and current key formats (`{tenant}/{YYYY-MM}/{span}/{field}.json`)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_span_detail.py fixture keys to use TENANT_A prefix**
- **Found during:** Task 1 (adding the prefix guard)
- **Issue:** `_ch_span_row` defaulted to `"tenant/2026-03/..."` keys; these would fail the new `key.startswith(f"{tenant_id}/")` guard since `tenant_id` is a UUID, not the literal string `"tenant"`
- **Fix:** Changed `_ch_span_row` defaults from hardcoded `"tenant/..."` to `f"{TENANT_A}/2026-03/{span_id}/..."` using a sentinel-default pattern in the function body
- **Files modified:** `xeter/tests/presenter/test_span_detail.py`
- **Verification:** All 7 existing `test_span_detail.py` tests pass after the fix
- **Committed in:** `3996dcb` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Auto-fix required for correctness — existing tests would have broken without it. No scope creep.

## Issues Encountered
None beyond the fixture key mismatch documented above as a deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- S3-01 guard is in place; the Presenter S3 layer now independently enforces tenant ownership
- Phase 14 Plan 03 (or next plan) can proceed without dependency on this guard being missing
- No blockers

---
*Phase: 14-db-foundation*
*Completed: 2026-04-29*
