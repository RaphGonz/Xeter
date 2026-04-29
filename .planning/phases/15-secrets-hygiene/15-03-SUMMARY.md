---
phase: 15-secrets-hygiene
plan: "03"
subsystem: testing
tags: [bcrypt, passlib, security, ci, pytest]

# Dependency graph
requires:
  - phase: 04-read-path
    provides: presenter tests with auth login fixture
provides:
  - passlib[bcrypt] dead dependency removed from pyproject.toml
  - bcrypt>=4.0 added as a direct dependency
  - CI test enforcing bcrypt cost factor >= 12 (test_bcrypt_cost_factor_minimum)
  - Session-scoped rounds=4 fixture in test_auth_login.py replacing module-level gensalt()
affects: [future-phases, ci-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CI enforcement: assert bcrypt default gensalt() produces $2b$12$ prefix"
    - "Test fixtures: session-scoped rounds=4 bcrypt hash to avoid startup overhead"

key-files:
  created:
    - xeter/tests/test_secrets.py
  modified:
    - xeter/pyproject.toml
    - xeter/tests/presenter/test_auth_login.py

key-decisions:
  - "Replaced passlib[bcrypt]>=1.7 with bcrypt>=4.0 directly — removes dead transitive dep, eliminates supply-chain risk"
  - "rounds=4 in test fixtures only; cost-factor test uses default gensalt() to assert production minimum remains 12"

patterns-established:
  - "Cost-factor guard: test_bcrypt_cost_factor_minimum uses default gensalt() call to catch any regression"
  - "Test fixture pattern: session-scoped @pytest.fixture with rounds=4 for bcrypt hashes, helper accepts hash as parameter"

requirements-completed: [OPS-04, DB-04]

# Metrics
duration: 13min
completed: 2026-04-29
---

# Phase 15 Plan 03: Secrets Hygiene — passlib removal + bcrypt cost-factor CI guard Summary

**Removed dead passlib[bcrypt] supply-chain dependency and added CI test asserting bcrypt default gensalt() produces $2b$12$ cost-factor hash prefix**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-04-29T13:09:27Z
- **Completed:** 2026-04-29T13:21:45Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Removed `passlib[bcrypt]>=1.7` from xeter/pyproject.toml, added `bcrypt>=4.0` as direct dependency; verified passlib not importable and bcrypt functional
- Created xeter/tests/test_secrets.py with `test_bcrypt_cost_factor_minimum` — CI fails if default gensalt() ever drops below rounds=12 (OPS-04)
- Refactored xeter/tests/presenter/test_auth_login.py: replaced module-level `PASSWORD_HASH = bcrypt.gensalt()` (runs at collection with rounds=12, ~100ms) with a session-scoped fixture using rounds=4 (~1ms, computed once per session)

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove passlib from pyproject.toml and ensure bcrypt is a direct dependency** - `8344846` (chore)
2. **Task 2: Add bcrypt cost-factor CI test and update test_auth_login.py fixture** - `3a5d74c` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/pyproject.toml` - Replaced `passlib[bcrypt]>=1.7` with `bcrypt>=4.0`
- `xeter/tests/test_secrets.py` - New CI guard test asserting $2b$12$ hash prefix from default gensalt()
- `xeter/tests/presenter/test_auth_login.py` - Session-scoped `password_hash_fixture` with rounds=4; `_make_user()` accepts hash param; module-level hash removed

## Decisions Made

- Replaced passlib with a direct bcrypt dependency rather than simply removing passlib without replacement — ensures the package is explicit in requirements (DB-04)
- rounds=4 chosen for test fixtures (not production) to keep CI fast; the cost-factor test uses a separate unparameterised gensalt() call to assert the production minimum independently (OPS-04)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 15 secrets hygiene complete (plans 01, 02, 03 all done)
- bcrypt cost-factor CI guard active — any future regression in rounds value will be caught
- Ready for Phase 16

---
*Phase: 15-secrets-hygiene*
*Completed: 2026-04-29*
