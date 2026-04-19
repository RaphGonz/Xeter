---
phase: 04-read-path
plan: 01
subsystem: api
tags: [jwt, fastapi, clickhouse, postgres, cursor-pagination, tenant-isolation]

# Dependency graph
requires:
  - phase: 03-analysis-path
    provides: span_scores table, Flag ORM model, RLS pattern
  - phase: 01-foundation
    provides: User model, postgres session factory, bcrypt auth pattern
provides:
  - POST /login returning JWT session token
  - verify_session_token FastAPI dependency (Bearer token validation)
  - GET /spans with cursor pagination, flag summaries, and score-derived status
affects: [04-read-path, 05-diagnosticer, 06-calibration]

# Tech tracking
tech-stack:
  added: [python-jose[cryptography]>=3.3]
  patterns:
    - JWT HS256 session tokens with 24h expiry
    - Header(default=None) for optional Authorization to return 401 not 422
    - base64url cursor encoding from time_begin ISO timestamps
    - ClickHouse + PostgreSQL fan-out merge pattern for span list

key-files:
  created:
    - xeter/services/presenter/deps.py
    - xeter/services/presenter/routers/auth.py (login route added to existing file)
    - xeter/services/presenter/routers/spans.py
    - xeter/tests/presenter/__init__.py
    - xeter/tests/presenter/test_auth_login.py
    - xeter/tests/presenter/test_spans_list.py
  modified:
    - xeter/services/presenter/main.py
    - xeter/pyproject.toml
    - deploy/docker-compose.yml

key-decisions:
  - "verify_session_token uses Header(default=None) not Header(...) — required header returns 422 (Pydantic validation) not 401; optional header lets function body raise the correctly-structured 401"
  - "GET /spans status derived as flagged > clean > pending — flag presence takes precedence over score presence"
  - "span_scores queried with explicit tenant_id WHERE clause (no RLS) — sole isolation mechanism for that table"
  - "ClickHouse client stored on app.state via lifespan — injected via request.app.state.ch_client in handler"

patterns-established:
  - "Presenter auth pattern: JWT dependency via verify_session_token Depends() on all dashboard routes"
  - "Cursor pagination: base64url-encode last item's time_begin, decode for WHERE time_begin < :cursor_ts"
  - "Two-DB merge: ClickHouse for immutable span data, PostgreSQL for mutable flags/scores, merged in Python"

requirements-completed: [STOR-03, DASH-05]

# Metrics
duration: 20min
completed: 2026-03-30
---

# Phase 4 Plan 1: Read Path Auth and Span List Summary

**JWT session auth (POST /login + verify_session_token dependency) and GET /spans with ClickHouse+PostgreSQL fan-out merge, cursor pagination, and status derivation (flagged/clean/pending)**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-30T00:00:00Z
- **Completed:** 2026-03-30T00:20:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- POST /login verifies bcrypt password, returns HS256 JWT session token for the tenant
- verify_session_token FastAPI dependency validates Bearer tokens and returns tenant_id string
- GET /spans queries ClickHouse for span rows, fans out to PostgreSQL for flags and span_scores, merges inline
- Cursor pagination via base64url-encoded time_begin with correct next_cursor when result count == limit
- Tenant isolation enforced at both JWT layer (tenant_id in token) and explicit WHERE clauses
- 9 unit tests pass: 3 login tests + 6 span list tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Add python-jose dep, verify_session_token dep, POST /login** - `1d92f8f` (feat) — completed prior session
2. **Task 2: GET /spans list endpoint with cursor pagination, flag summaries, and score overlays** - `41ec28a` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/services/presenter/deps.py` - SECRET_KEY config, create_session_token, verify_session_token dependency
- `xeter/services/presenter/routers/auth.py` - POST /login added to existing register router
- `xeter/services/presenter/routers/spans.py` - GET /spans handler with FlagSummary, SpanListItem, SpanListResponse models
- `xeter/services/presenter/main.py` - Lifespan with ClickHouse client on app.state, spans router wired
- `xeter/tests/presenter/test_auth_login.py` - 3 tests: valid credentials, wrong password, unknown email
- `xeter/tests/presenter/test_spans_list.py` - 6 tests: spans+flags, flag scores, 401, isolation, cursor, status
- `xeter/pyproject.toml` - python-jose[cryptography]>=3.3 dependency added
- `deploy/docker-compose.yml` - SECRET_KEY, S3_*, DIAGNOSTICER_URL env vars added to presenter service

## Decisions Made

- `verify_session_token` uses `Header(default=None)` instead of `Header(...)` — FastAPI returns 422 (Pydantic validation) for required headers when value is absent, which conflicts with the plan requirement of 401 for missing tokens. Making the header optional lets the function body raise the correctly-structured 401 HTTPException.
- GET /spans status derivation priority: flagged > clean > pending. If any flag exists the span is flagged regardless of scores; if only scores exist it is clean; neither means pending (analyser not yet run).
- `span_scores` has no PostgreSQL RLS — explicit `WHERE tenant_id = :tid` in the SQL query is the sole isolation mechanism (documented in code with CRITICAL comment).
- ClickHouse client created once in FastAPI lifespan and stored on `app.state.ch_client` — tests patch `app.state.ch_client` directly before each test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] verify_session_token header parameter made optional**
- **Found during:** Task 2 (test_span_list_missing_token_returns_401)
- **Issue:** `Header(...)` (required) causes FastAPI to return 422 Unprocessable Entity when the Authorization header is absent, not 401. Plan requires 401 for missing tokens.
- **Fix:** Changed `authorization: str = Header(...)` to `authorization: str | None = Header(default=None)`. The existing `if not authorization` check in the function body already handles the None case and raises 401.
- **Files modified:** xeter/services/presenter/deps.py
- **Verification:** test_span_list_missing_token_returns_401 passes; all 9 presenter tests pass
- **Committed in:** 41ec28a (Task 2 commit)

**2. [Rule 1 - Bug] test_span_list_missing_token_returns_401 kept get_session mock**
- **Found during:** Task 2 (test execution)
- **Issue:** Test popped verify_session_token override to use real dependency, but also removed get_session override. FastAPI resolves all dependencies before handler execution; without a get_session mock, it attempts a real DB connection (KeyError: DATABASE_URL).
- **Fix:** Test now keeps a dummy mock get_session while removing only the verify_session_token override. The real verify_session_token raises 401 before the session is used; the mock prevents a spurious KeyError.
- **Files modified:** xeter/tests/presenter/test_spans_list.py
- **Verification:** Test passes; 401 returned correctly; 9 total tests pass
- **Committed in:** 41ec28a (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - bugs in auth/test behavior)
**Impact on plan:** Both fixes required for correct 401 behavior. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required. SECRET_KEY defaults to dev value in docker-compose; set a real secret before production deployment.

## Next Phase Readiness

- POST /login and GET /spans are fully functional and tested
- verify_session_token dependency is ready for all subsequent Presenter endpoints
- Phase 4 Plan 2 (Diagnosticer scaffold + GET /spans/:span_id detail endpoint) can proceed immediately
- No blockers

---
*Phase: 04-read-path*
*Completed: 2026-03-30*

## Self-Check: PASSED

- FOUND: xeter/services/presenter/deps.py
- FOUND: xeter/services/presenter/routers/auth.py
- FOUND: xeter/services/presenter/routers/spans.py
- FOUND: xeter/tests/presenter/test_auth_login.py
- FOUND: xeter/tests/presenter/test_spans_list.py
- FOUND: .planning/phases/04-read-path/04-01-SUMMARY.md
- FOUND: commit 1d92f8f (Task 1)
- FOUND: commit 41ec28a (Task 2)
