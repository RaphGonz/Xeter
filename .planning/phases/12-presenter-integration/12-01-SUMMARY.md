---
phase: 12-presenter-integration
plan: "01"
subsystem: api
tags: [fastapi, httpx, sqlalchemy, pydantic, clickhouse, rls, idempotency]

# Dependency graph
requires:
  - phase: 11-diagnosticer-backend
    provides: POST /diagnose Diagnosticer endpoint and diagnoses table written by Diagnosticer
  - phase: 12-presenter-integration (context)
    provides: DiagnosisRepository.get_latest_for_span, tenant_session, Diagnosis ORM model
provides:
  - DiagnosisService class with trigger() — idempotency + tenant guard + HTTP forward
  - DiagnosisResponse Pydantic model shared by POST and GET endpoints
  - POST /diagnose real endpoint replacing blind proxy scaffold
  - GET /diagnose/{span_id} new polling endpoint for frontend
affects:
  - 12-02 (plan 02 tests will cover these endpoints)
  - 13-frontend-diagnosis-ui

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Sequential tenant_session blocks (not nested) to satisfy RLS constraints
    - Catch httpx.TimeoutException before httpx.HTTPError (subclass ordering for 504 vs 503)
    - Service layer instantiated fresh per request inside router (DiagnosisService())
    - Re-read from DB after successful Diagnosticer forward (Diagnosticer writes, Presenter reads)

key-files:
  created:
    - xeter/services/presenter/diagnosis_service.py
  modified:
    - xeter/services/presenter/routers/diagnose.py

key-decisions:
  - "DiagnosisResponse uses recommended_fix (API name) mapped from Diagnosis.fix (ORM field name)"
  - "Tenant guard returns 404 for both not-found and not-mine spans — prevents tenant info leakage"
  - "_sanitize_diagnosticer_error truncates to 120 chars using simple slice, no regex needed"
  - "DiagnoseRequest.flags field removed — Diagnosticer only accepts {span_id: str}"

patterns-established:
  - "Service layer pattern: DiagnosisService instantiated in router, all deps injected via trigger()"
  - "Error classification: TimeoutException → 504, ConnectError/HTTPError → 503, non-2xx → 502"
  - "Step-5 re-read pattern: after successful Diagnosticer forward, read back from DB (not parse HTTP response)"

requirements-completed: [PRES-INT-01, PRES-INT-02, PRES-INT-03, PRES-INT-04]

# Metrics
duration: 13min
completed: 2026-04-23
---

# Phase 12 Plan 01: DiagnosisService and Router Rewrite Summary

**DiagnosisService layer with idempotency, ClickHouse tenant guard, configurable timeout, and sanitized error classification replacing the blind httpx proxy scaffold**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-23T19:58:35Z
- **Completed:** 2026-04-23T20:11:46Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 rewritten)

## Accomplishments

- DiagnosisService.trigger() encapsulates the full diagnosis flow: idempotency check, ClickHouse ownership guard, Diagnosticer HTTP forward, error classification, and DB re-read
- POST /diagnose now returns cached results immediately when a diagnosis exists, and verifies span ownership before any external call
- GET /diagnose/{span_id} added as a new polling endpoint for frontend use

## Task Commits

Each task was committed atomically:

1. **Task 1: Create DiagnosisService** - `82a304b` (feat)
2. **Task 2: Replace scaffold diagnose router** - `780be9c` (feat)

## Files Created/Modified

- `xeter/services/presenter/diagnosis_service.py` - New service layer: DiagnosisService, DiagnosisResponse, _diagnosis_to_response, _sanitize_diagnosticer_error
- `xeter/services/presenter/routers/diagnose.py` - Rewritten: real POST /diagnose + new GET /diagnose/{span_id}, DiagnoseRequest without flags

## Decisions Made

- `DiagnosisResponse.recommended_fix` maps from `Diagnosis.fix` — ORM field kept as "fix" for DB consistency, API surface uses more descriptive name
- Tenant guard returns identical 404 for both "span doesn't exist" and "span belongs to another tenant" — prevents tenant enumeration attack
- `_sanitize_diagnosticer_error` uses a 120-char slice rather than regex — simpler and sufficient given the detail field is already a string
- `DiagnoseRequest.flags` field removed — the scaffold forwarded arbitrary flags but Diagnosticer's POST /diagnose only accepts `{"span_id": str}`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DiagnosisService and both endpoints are ready for unit test coverage in Plan 02
- The GET /diagnose/{span_id} endpoint gives the frontend a stable polling target
- Old test `test_diagnose_proxies_request_body` (which asserted flags forwarding) will need replacement in Plan 02 — this was anticipated in the plan

---
*Phase: 12-presenter-integration*
*Completed: 2026-04-23*
