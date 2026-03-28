---
phase: 02-ingestion-path
plan: "01"
subsystem: sdk
tags: [python, httpx, threading, decorator, instrumentation, sdk]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "ClickHouse schema, PostgreSQL tenant model, API key structure — SDK sends spans to Analyser which writes to these"
provides:
  - "Standalone xeter-sdk Python package installable via pip install -e sdk/"
  - "@xeter.trace(...) decorator capturing all 15 span fields"
  - "Fire-and-forget background thread span sending via httpx"
  - "No-op behaviour when XETER_ENDPOINT or XETER_API_KEY env vars absent"
  - "WARNING logging on network failure without raising"
  - "Unit test suite — 8 tests covering all core behaviours"
affects:
  - "02-ingestion-path (plans 02+): Analyser must accept POST /v1/spans with these exact field names"
  - "03-analysis: embedding worker receives span_id pushed by Analyser after receiving SDK spans"
  - "agent-developer experience: decorator signature is a stable API"

# Tech tracking
tech-stack:
  added:
    - "xeter-sdk (standalone package, sdk/)"
    - "httpx>=0.27 (HTTP client for span dispatch)"
  patterns:
    - "Fire-and-forget span sending via daemon threading.Thread — function returns immediately"
    - "No-op guard reads env vars inside wrapper, not at import time — late-binding is intentional"
    - "prompt_arg / tools_arg kwarg mapping — explicit, no magic field detection"
    - "All span fields always present in payload (null for uncaptured fields) — Analyser never receives partial spans"

key-files:
  created:
    - sdk/pyproject.toml
    - sdk/xeter_sdk/__init__.py
    - sdk/xeter_sdk/decorator.py
    - xeter/tests/sdk/__init__.py
    - xeter/tests/sdk/test_decorator.py
  modified: []

key-decisions:
  - "02-01: asyncio.run() used instead of asyncio.get_event_loop().run_until_complete() — deprecated in Python 3.14"
  - "02-01: threading.Thread patched globally in tests — decorator imports threading module so global patch intercepts correctly"
  - "02-01: response and raw_response set to null in SDK — these are agent-provided fields not available at decoration time; agents needing response capture extend the decorator"
  - "02-01: tool_arguments serialised to JSON string at SDK layer — Analyser receives pre-serialised string, not nested dict"

patterns-established:
  - "SDK env-var guard: endpoint + api_key read inside wrapper on every call (not cached at decoration time)"
  - "Background thread pattern: threading.Thread(target=_send, args=(...), daemon=True).start() — one attempt, drop on failure"
  - "Test pattern for threading: capture RealThread before patch, patch global threading.Thread, return mock with .start() side_effect starting real thread"

requirements-completed: [SDK-01, SDK-02, SDK-03, SDK-04, SDK-05]

# Metrics
duration: 12min
completed: 2026-03-28
---

# Phase 2 Plan 01: xeter-sdk Decorator Summary

**Standalone xeter-sdk package with @xeter.trace decorator: fires all 15 span fields to POST /v1/spans in a daemon background thread with zero added latency, no-ops silently when env vars absent**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-28T10:40:42Z
- **Completed:** 2026-03-28T10:52:48Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Standalone `xeter-sdk` Python package at `sdk/` with single `httpx>=0.27` dependency — installs via `pip install -e sdk/`
- `@xeter.trace(...)` decorator supports both `def` and `async def` via `inspect.iscoroutinefunction`, maps `prompt_arg` and `tools_arg` kwargs to span fields
- Fire-and-forget dispatch: daemon `threading.Thread` sends span; function returns immediately; WARNING logged on any exception, never re-raised
- 8 unit tests all passing: sync/async return value preservation, no-op without env vars, all 15 span fields present, send failure safety, prompt mapping, tools mapping, fire-and-forget timing

## Task Commits

Each task was committed atomically:

1. **Task 1: SDK package scaffold and pyproject.toml** - `cbc89ef` (chore)
2. **Task 2: Decorator implementation and unit tests** - `0401a15` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `sdk/pyproject.toml` - Standalone package definition, name="xeter-sdk", httpx dependency
- `sdk/xeter_sdk/__init__.py` - Package entry point exporting `trace`, version 0.1.0
- `sdk/xeter_sdk/decorator.py` - Full decorator implementation: sync/async wrappers, span building, daemon thread dispatch
- `xeter/tests/sdk/__init__.py` - Empty init for test package
- `xeter/tests/sdk/test_decorator.py` - 8 unit tests covering all required behaviours

## Decisions Made

- Used `asyncio.run()` instead of `asyncio.get_event_loop().run_until_complete()` — `get_event_loop()` is deprecated in Python 3.14 and raises RuntimeError when no loop exists
- Patched `threading.Thread` globally in tests (not `xeter_sdk.decorator.threading.Thread`) because the decorator module references the same `threading` module object; global patch intercepts correctly
- `response` and `raw_response` are set to `null` — these are Analyser/agent-side fields not available at decoration time. Documented via comment in decorator.py
- `tool_arguments` serialised to JSON string at SDK layer — consistent with Analyser receiving a flat JSON body

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed deprecated asyncio API incompatible with Python 3.14**
- **Found during:** Task 2 (unit test execution)
- **Issue:** `asyncio.get_event_loop()` raises `RuntimeError: There is no current event loop` in Python 3.14 — test for async function failed
- **Fix:** Replaced with `asyncio.run()` in test_async_function_returns_normally
- **Files modified:** xeter/tests/sdk/test_decorator.py
- **Verification:** test_async_function_returns_normally passes
- **Committed in:** `0401a15` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed RecursionError in fire-and-forget timing test**
- **Found during:** Task 2 (unit test execution)
- **Issue:** `threading.Thread(...)` called inside `fake_thread_init` while `threading.Thread` was patched — infinite recursion; also double `.start()` on real thread from decorator
- **Fix:** Captured `RealThread = threading.Thread` before the patch context; `fake_thread_init` returns a mock whose `.start()` side_effect starts the real thread; decorator's `.start()` call triggers the real thread exactly once
- **Files modified:** xeter/tests/sdk/test_decorator.py
- **Verification:** test_fire_and_forget_timing passes, all 8 tests pass
- **Committed in:** `0401a15` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — Python 3.14 compatibility bugs in test code)
**Impact on plan:** Both fixes required for tests to pass on Python 3.14. No scope creep. Production code (decorator.py) unchanged.

## Issues Encountered

- Python 3.14 deprecates `asyncio.get_event_loop()` and `asyncio.iscoroutinefunction()` — the deprecation warnings from pytest_asyncio are expected and pre-existing (not introduced by this plan). Test code updated to use `asyncio.run()`.

## User Setup Required

None - no external service configuration required. SDK is installed locally via `pip install -e sdk/`.

## Next Phase Readiness

- SDK is complete and ready; agent developers can instrument with 3 lines (set 2 env vars + 1 decorator)
- Plan 02-02 (Analyser POST /v1/spans endpoint) must accept the exact JSON structure produced by this SDK
- All 15 span field names are locked: `span_id, trace_id, parent_span_id, agent_name, agent_model, tool_name, tool_description, tool_arguments, tool_output, prompt, response, raw_response, available_tools_ref, time_begin, time_end, xeter.schema.version`

## Self-Check: PASSED

- sdk/pyproject.toml: FOUND
- sdk/xeter_sdk/__init__.py: FOUND
- sdk/xeter_sdk/decorator.py: FOUND
- xeter/tests/sdk/__init__.py: FOUND
- xeter/tests/sdk/test_decorator.py: FOUND
- .planning/phases/02-ingestion-path/02-01-SUMMARY.md: FOUND
- Commit cbc89ef: FOUND
- Commit 0401a15: FOUND

---
*Phase: 02-ingestion-path*
*Completed: 2026-03-28*
