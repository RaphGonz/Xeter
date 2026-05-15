---
phase: 18-cleanup-baseanalyzer-refactor
plan: "01"
subsystem: infra
tags: [fastapi, python, security, env-vars, auth, clickhouse, s3]

# Dependency graph
requires:
  - phase: 17-gdpr
    provides: Migration 004 (RLS on span_scores table) that made the stale comments wrong
provides:
  - "diagnosticer/main.py without dead verify_session_token and without jose/SECRET_KEY dependencies"
  - "spans.py with accurate RLS comment state post-migration-004"
  - "9 service files with inline safety annotations on all os.environ.get() defaults"
affects: [19-baseanalyzer-hierarchy, 20-traceanalyzer-scaffold, 21-v1.4-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Env var safety annotation pattern: [safe-default], [must-set-in-prod], [empty-ok] tags on every os.environ.get()"

key-files:
  created: []
  modified:
    - xeter/services/diagnosticer/main.py
    - xeter/tests/diagnosticer/test_diagnose_endpoint.py
    - xeter/services/presenter/routers/spans.py
    - xeter/services/analyser/batch.py
    - xeter/services/analyser/s3.py
    - xeter/services/diagnosticer/context_assembly.py
    - xeter/services/diagnosticer/providers/__init__.py
    - xeter/services/diagnosticer/providers/ollama.py
    - xeter/services/presenter/main.py
    - xeter/services/presenter/diagnosis_service.py
    - xeter/services/worker/main.py

key-decisions:
  - "InternalApiKeyMiddleware is the sole auth boundary for Diagnosticer — verify_session_token was dead code never referenced by any route"
  - "span_scores has both RLS (migration 004) AND explicit tenant_id WHERE clause — belt-and-suspenders intentional; both layers retained"
  - "Env var annotation tags [safe-default]/[must-set-in-prod] chosen over code changes — latent risks documented inline without altering fail-fast behavior of os.environ[] accesses"

patterns-established:
  - "Env var safety annotation: every os.environ.get() in service files carries [safe-default] or [must-set-in-prod] inline comment explaining production posture"

requirements-completed: [CLEAN-01, CLEAN-02, CLEAN-03]

# Metrics
duration: 18min
completed: 2026-05-14
---

# Phase 18 Plan 01: Cleanup — Dead Code + Stale Comments + Env Var Audit Summary

**Deleted dead verify_session_token (jose/JWT auth never used by routes), corrected 2 stale "NO RLS" comments post-migration-004, and annotated all os.environ.get() defaults with [safe-default]/[must-set-in-prod] tags across 9 service files**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-14T12:11:30Z
- **Completed:** 2026-05-14T12:29:00Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments

- Removed `verify_session_token()` function, `from jose import JWTError, jwt` import, `SECRET_KEY` and `ALGORITHM` constants from `diagnosticer/main.py` — these were dead code since the route never used Depends(verify_session_token); `InternalApiKeyMiddleware` is the documented sole auth boundary
- Corrected 2 stale span_scores RLS comments in `spans.py` (lines 161 and 247) that said "NO RLS" — wrong since migration 004 added RLS in Phase 14; lines 9 and 442 were already correct
- Added `[safe-default]` / `[must-set-in-prod]` annotations to all `os.environ.get()` defaults across 9 files: 7 `[must-set-in-prod]` (CLICKHOUSE_PASSWORD, S3_ACCESS_KEY x2, S3_SECRET_KEY x2, ENVIRONMENT, CORS_ALLOW_ORIGINS) and 16 `[safe-default]` annotations; pending CLEAN-03 todo from 2026-04-24 now resolved

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove dead verify_session_token from diagnosticer** - `acdd568` (fix)
2. **Task 2: Correct stale RLS comments in spans.py** - `17d68c6` (fix)
3. **Task 3: Annotate env var defaults with safety status** - `d67d97e` (chore)

## Files Created/Modified

- `xeter/services/diagnosticer/main.py` - Dead function + jose imports + SECRET_KEY + ALGORITHM removed; auth boundary comment added
- `xeter/tests/diagnosticer/test_diagnose_endpoint.py` - Removed verify_session_token from import line
- `xeter/services/presenter/routers/spans.py` - 2 stale RLS comments corrected; S3 block env vars annotated
- `xeter/services/analyser/batch.py` - CLICKHOUSE_* and batch size/interval vars annotated
- `xeter/services/analyser/s3.py` - S3_BUCKET annotated [safe-default]
- `xeter/services/diagnosticer/context_assembly.py` - S3_BUCKET/S3_ENDPOINT_URL [safe-default]; S3_ACCESS_KEY/S3_SECRET_KEY [must-set-in-prod]
- `xeter/services/diagnosticer/providers/__init__.py` - DIAGNOSTICER_PROVIDER/MODEL annotated [safe-default]
- `xeter/services/diagnosticer/providers/ollama.py` - OLLAMA_HOST annotated [safe-default]
- `xeter/services/presenter/main.py` - DIAGNOSTICER_URL [safe-default]; ENVIRONMENT and CORS_ALLOW_ORIGINS [must-set-in-prod]
- `xeter/services/presenter/diagnosis_service.py` - DIAGNOSTICER_TIMEOUT_SECONDS annotated [safe-default]
- `xeter/services/worker/main.py` - EMBEDDER_URL and all threshold calibration values annotated [safe-default]

## Decisions Made

- `verify_session_token` was deleted rather than deprecated — it was never referenced by any route as a Depends(), making it purely dead code with no migration path needed
- Both RLS layers (migration 004 + explicit tenant_id WHERE) are intentional and retained — comments now accurately describe the belt-and-suspenders design
- Env var annotations are inline comments only — did not convert `os.environ.get()` to `os.environ[]` for the None-returning cases (S3_ACCESS_KEY/S3_SECRET_KEY in context_assembly) as that would be a behavioral change outside this plan's scope; marked [must-set-in-prod] to flag the risk

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure `xeter/tests/worker/test_tool_call_analyzer.py::test_analyze_returns_list` fails due to `spacy` not installed in this environment. This failure predates this plan and is unrelated to any changes made. All 87 other tests pass (7 diagnosticer + 80 other; 4 skipped).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Codebase is now clean of dead auth code and stale security comments
- All env var defaults are documented — production deployment checklist is now embedded in the code
- Ready for Phase 18-02: BaseAnalyzer hierarchy refactor (already committed: 90d7b80)

---
*Phase: 18-cleanup-baseanalyzer-refactor*
*Completed: 2026-05-14*
