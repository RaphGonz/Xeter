---
phase: 11-diagnosticer-backend
plan: "04"
subsystem: diagnosticer
tags: [fastapi, endpoint, llm, fail-clean, unit-tests, auth, mock]

# Dependency graph
requires:
  - phase: 11-02
    provides: "LLM provider factory (get_llm_client, LLMError, ParseError, DiagnosisResult)"
  - phase: 11-03
    provides: "DiagnosisRepository DAL and assemble_context()"
provides:
  - "Real POST /diagnose endpoint replacing 501 scaffold in xeter/services/diagnosticer/main.py"
  - "Unit test suite (6 tests) in xeter/tests/diagnosticer/test_diagnose_endpoint.py"
affects: [presenter-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "autouse pytest fixture patches get_async_engine + get_async_session_factory at module level to prevent real DB in lifespan"
    - "app.dependency_overrides[get_ch_client] overrides ClickHouse dep to avoid connection during tests"
    - "Fail-clean: assemble_context → provider.diagnose → repo.create only on success; LLMError→502, ParseError→422, ValueError→404"
    - "Lifespan creates session factory once on startup; endpoint creates fresh session factory per request from module-level engine helper"

key-files:
  created:
    - xeter/tests/diagnosticer/__init__.py
    - xeter/tests/diagnosticer/test_diagnose_endpoint.py
  modified:
    - xeter/services/diagnosticer/main.py

key-decisions:
  - "autouse fixture patches both engine factory functions at module level (not just per-test) so TestClient lifespan startup never hits real PostgreSQL"
  - "get_ch_client overridden via app.dependency_overrides rather than module-level patch — FastAPI dependency injection resolves at request time, not import time"
  - "verify_session_token kept inline in main.py (not imported from deps.py) to keep the service self-contained; mirrors Presenter pattern exactly"

# Metrics
duration: 13min
completed: 2026-04-22
---

# Phase 11 Plan 04: Diagnose Endpoint Summary

**Real POST /diagnose wired from 501 scaffold: assemble_context → LLM provider → DiagnosisRepository in fail-clean sequence, with 6-test suite covering 200/401/404/502/422 paths**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-22T18:20:17Z
- **Completed:** 2026-04-22T18:33:57Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Replaced the 501 scaffold in `xeter/services/diagnosticer/main.py` with a real endpoint: lifespan sets up async session factory, `verify_session_token` validates JWT, `get_ch_client` provides per-request ClickHouse isolation
- Fail-clean pattern enforced: `assemble_context` → `provider.diagnose` → `repo.create` strictly in order; no DB row written unless LLM parse succeeds
- Error mapping: `ValueError` from assemble_context → 404, `LLMError` → 502, `ParseError` → 422
- Created `xeter/tests/diagnosticer/test_diagnose_endpoint.py` with 6 tests using `autouse` fixture to prevent any real DB/ClickHouse connections during lifespan or request handling

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace 501 scaffold with real POST /diagnose endpoint** - `5be57ea` (feat)
2. **Task 2: Write unit tests for POST /diagnose endpoint** - `abb5086` (feat)

## Files Created/Modified

- `xeter/services/diagnosticer/main.py` — Full rewrite: lifespan, JWT auth, get_ch_client dep, DiagnoseRequest/DiagnoseResponse models, real diagnose handler with fail-clean pattern
- `xeter/tests/diagnosticer/__init__.py` — New: empty package marker
- `xeter/tests/diagnosticer/test_diagnose_endpoint.py` — New: 6 unit tests covering all critical paths

## Decisions Made

- `autouse` pytest fixture patches `get_async_engine` and `get_async_session_factory` at module level so TestClient lifespan startup never attempts a real PostgreSQL connection — without this, every test would fail before the request even fires
- `get_ch_client` overridden via `app.dependency_overrides` rather than a module-level patch because FastAPI resolves `Depends` at request dispatch time, not at import time
- `verify_session_token` defined inline in `main.py` to keep the Diagnosticer service self-contained; pattern mirrors `deps.py` in the Presenter exactly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestClient lifespan calls get_async_engine() requiring DATABASE_URL**
- **Found during:** Task 2 (first test run)
- **Issue:** `TestClient(app)` runs the lifespan context manager, which calls `get_async_engine()` → `os.environ["DATABASE_URL"]` → `KeyError`. All 6 tests failed before any request was made.
- **Fix:** Added `autouse=True` pytest fixture that patches `get_async_engine` and `get_async_session_factory` at the `xeter.services.diagnosticer.main` module level, so lifespan and endpoint calls are both covered. Also added `engine.dispose = AsyncMock()` to prevent `TypeError: 'MagicMock' object can't be awaited` on lifespan teardown.
- **Files modified:** `xeter/tests/diagnosticer/test_diagnose_endpoint.py`

**2. [Rule 1 - Bug] get_ch_client Depends not intercepted by module-level patch**
- **Found during:** Task 2 (second test run after fix 1)
- **Issue:** Even with lifespan fixed, tests for 404/502/422/200 paths tried to open a real ClickHouse connection because FastAPI resolves `Depends(get_ch_client)` at request time, which bypasses the module-level patch.
- **Fix:** Added `app.dependency_overrides[get_ch_client] = _ch_client_override()` inside the autouse fixture, cleaned up in fixture teardown via `pop`.
- **Files modified:** `xeter/tests/diagnosticer/test_diagnose_endpoint.py`

---

**Total deviations:** 2 auto-fixed (both were test infrastructure bugs, no production code changes)

## Self-Check: PASSED

- `xeter/services/diagnosticer/main.py` — FOUND (no 501 remains)
- `xeter/tests/diagnosticer/__init__.py` — FOUND
- `xeter/tests/diagnosticer/test_diagnose_endpoint.py` — FOUND
- Commit `5be57ea` — FOUND
- Commit `abb5086` — FOUND
- All 6 tests pass (pytest exit 0)
