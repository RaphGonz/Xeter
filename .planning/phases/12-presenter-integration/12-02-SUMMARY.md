---
phase: 12-presenter-integration
plan: "02"
subsystem: testing
tags: [fastapi, pytest, unittest.mock, httpx, sqlalchemy, clickhouse, idempotency, rls]

# Dependency graph
requires:
  - phase: 12-presenter-integration (plan 01)
    provides: DiagnosisService, DiagnosisResponse, POST /diagnose real endpoint, GET /diagnose/{span_id}
provides:
  - Full unit test suite for POST /diagnose (7 tests) and GET /diagnose/{span_id} (3 tests)
  - Mocking pattern for tenant_session() with begin()-as-context-manager AsyncMock
affects:
  - 13-frontend-diagnosis-ui

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Patch DiagnosisRepository at service module for POST tests, at router module for GET tests
    - session.begin() wired as MagicMock returning AsyncMock context manager to satisfy tenant_session()
    - get_ch_client overridden via dependency_overrides with has_span flag controlling result_rows
    - AsyncMock side_effect=[None, diagnosis] used for two-call idempotency/re-read pattern

key-files:
  created: []
  modified:
    - xeter/tests/presenter/test_diagnose.py

key-decisions:
  - "Patch target for POST tests is xeter.services.presenter.diagnosis_service.DiagnosisRepository (where DiagnosisService uses it)"
  - "Patch target for GET tests is xeter.services.presenter.routers.diagnose.DiagnosisRepository (where the GET route uses it directly)"
  - "Added 401 test for GET /diagnose/{span_id} beyond the 9 specified in plan — improved coverage at zero cost"

patterns-established:
  - "Two-location patch pattern: service-level tests patch service module, router-level tests patch router module"
  - "session mock: begin() = MagicMock(return_value=AsyncMock(__aenter__, __aexit__)) satisfies tenant_session()"

requirements-completed: [PRES-INT-01, PRES-INT-02, PRES-INT-03, PRES-INT-04]

# Metrics
duration: 5min
completed: 2026-04-23
---

# Phase 12 Plan 02: Diagnose Endpoint Test Suite Summary

**10-test suite replacing 4 scaffold tests: idempotency, tenant guard, 503/504/502 error codes, 200 success, and GET endpoint coverage for POST /diagnose and GET /diagnose/{span_id}**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-23T20:28:00Z
- **Completed:** 2026-04-23T20:36:09Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Removed all 4 stale scaffold tests asserting 501 behavior and flags forwarding
- Wrote 7 POST /diagnose tests covering: 401, idempotency cache hit, tenant guard 404, 503, 504, 502 sanitized error, 200 success
- Wrote 3 GET /diagnose/{span_id} tests covering: 401, 200 with existing diagnosis, 404 without diagnosis
- Established the two-location patching pattern for DiagnosisRepository (service vs router module)

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite test_diagnose.py** - `b6858fc` (feat)

## Files Created/Modified

- `xeter/tests/presenter/test_diagnose.py` - Full rewrite: 10 tests for POST /diagnose and GET /diagnose/{span_id}, session mock with begin() context manager support

## Decisions Made

- Patch target for POST /diagnose tests is `xeter.services.presenter.diagnosis_service.DiagnosisRepository` since DiagnosisService instantiates the repo internally
- Patch target for GET /diagnose/{span_id} tests is `xeter.services.presenter.routers.diagnose.DiagnosisRepository` since the GET route calls it directly in the router
- Added a 10th test (`test_get_diagnosis_returns_401_without_token`) beyond the 9 specified — covers auth guard parity between POST and GET at no additional complexity cost

## Deviations from Plan

None - plan executed exactly as written. (One bonus test added: GET 401 — improves coverage symmetry.)

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 12 is complete: DiagnosisService, both endpoints, and full test coverage are shipped
- Phase 13 (Frontend Diagnosis UI) can now rely on stable POST /diagnose and GET /diagnose/{span_id} contracts
- The GET endpoint gives the frontend a polling target; the cached idempotency path prevents re-diagnosis on page refresh

---
*Phase: 12-presenter-integration*
*Completed: 2026-04-23*
