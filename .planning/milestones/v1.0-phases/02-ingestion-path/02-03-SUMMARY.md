---
phase: 02-ingestion-path
plan: "03"
subsystem: api
tags: [fastapi, pydantic, clickhouse, redis, s3, minio, testing]

# Dependency graph
requires:
  - phase: 02-01
    provides: SDK emitting spans with span_id, trace_id, and all payload fields
  - phase: 02-02
    provides: auth.py (verify_api_key_header), s3.py (S3Client), batch.py (SpanBatcher/SPAN_COLUMNS), queue.py (enqueue_span_id)

provides:
  - "POST /v1/spans endpoint: auth -> S3 -> batcher -> Redis in locked order"
  - "SpanPayload Pydantic v2 model with xeter.schema.version alias"
  - "FastAPI app lifespan managing SpanBatcher, Redis, and S3Client singletons"
  - "9 integration tests covering all success criteria (auth, S3 failure, Redis enqueue, batching contract, row shape)"

affects:
  - 02-04
  - 03-embedding
  - phase 4 (read path)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lifespan singleton pattern: app.state stores batcher/redis/s3, deps retrieve via Request.app.state"
    - "S3-first ingestion: S3 upload always precedes ClickHouse batch add (data integrity guarantee)"
    - "Lifespan mocking in tests: patch factory functions in main.py module to avoid real service connections"

key-files:
  created:
    - xeter/services/analyser/schemas.py
    - xeter/services/analyser/ingest.py
    - xeter/services/analyser/main.py
    - xeter/tests/analyser/__init__.py
    - xeter/tests/analyser/test_ingest.py
  modified: []

key-decisions:
  - "Lifespan test isolation: patch get_clickhouse_client/SpanBatcher/get_redis_client/get_s3_client in main.py module to prevent real connections during TestClient startup"
  - "batcher.start/stop must be AsyncMock in tests that build their own batcher_tracked mock — MagicMock is not awaitable"
  - "Row length assertion in ingest.py (assert len(row) == len(SPAN_COLUMNS)) catches column drift at runtime before it silently corrupts ClickHouse"

patterns-established:
  - "Singleton pattern via app.state: all long-lived clients stored in lifespan, retrieved in deps via request.app.state"
  - "S3-first ordering: locked sequence S3 -> batcher.add -> enqueue_span_id, any step failure returns 5xx"

requirements-completed:
  - SDK-01
  - SDK-02
  - SDK-03
  - SDK-04
  - SDK-05
  - STOR-02
  - STOR-04
  - STOR-05

# Metrics
duration: 17min
completed: "2026-03-28"
---

# Phase 2 Plan 03: Analyser Wiring Summary

**FastAPI POST /v1/spans endpoint wiring auth, S3, ClickHouse batcher, and Redis queue in locked S3-first order, with 9 integration tests covering all Phase 2 success criteria**

## Performance

- **Duration:** 17 min
- **Started:** 2026-03-28T11:10:35Z
- **Completed:** 2026-03-28T11:27:25Z
- **Tasks:** 2
- **Files modified:** 5 created

## Accomplishments
- SpanPayload Pydantic v2 model with `xeter.schema.version` dotted alias, all optional SDK fields
- POST /v1/spans handler with locked execution order: S3 upload -> batcher.add -> Redis enqueue, any failure returns 5xx
- FastAPI app lifespan managing SpanBatcher (ClickHouse), Redis, and S3Client as app.state singletons
- 9 integration tests all passing, 8 SDK regression tests still passing

## Task Commits

Each task was committed atomically:

1. **Task 1: SpanPayload schema, ingest.py handler, main.py lifespan wiring** - `adee4fc` (feat)
2. **Task 2: Analyser integration tests** - `4c01228` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `xeter/services/analyser/schemas.py` - SpanPayload Pydantic v2 model with xeter.schema.version alias
- `xeter/services/analyser/ingest.py` - POST /v1/spans handler and app.state dependency injectors
- `xeter/services/analyser/main.py` - FastAPI app with lifespan (batcher start/stop, redis, s3)
- `xeter/tests/analyser/__init__.py` - Empty package marker
- `xeter/tests/analyser/test_ingest.py` - 9 integration tests with full lifespan mocking

## Decisions Made
- Lifespan test isolation requires patching factory functions (`get_clickhouse_client`, `SpanBatcher`, `get_redis_client`, `get_s3_client`) in the `main` module at the patch path — FastAPI dependency overrides only apply to endpoint-level deps, not lifespan startup code
- `batcher_tracked.start` and `.stop` must be `AsyncMock` in any test that creates a custom batcher mock used during lifespan startup — plain `MagicMock` is not awaitable and raises `TypeError`
- Added `assert len(row) == len(SPAN_COLUMNS)` in ingest.py as a runtime guard — catches column count drift before it silently corrupts ClickHouse data

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed batcher mock in test_s3_called_before_batcher — start/stop must be AsyncMock**
- **Found during:** Task 2 (integration test execution)
- **Issue:** `batcher_tracked` had plain `MagicMock` for `start`/`stop`; lifespan `await batcher.start()` raised `TypeError: 'MagicMock' object can't be awaited`
- **Fix:** Added `batcher_tracked.start = AsyncMock()` and `batcher_tracked.stop = AsyncMock()` in that test
- **Files modified:** `xeter/tests/analyser/test_ingest.py`
- **Verification:** All 9 tests pass
- **Committed in:** `4c01228` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Necessary fix for test correctness. No scope creep.

## Issues Encountered
- TestClient with lifespan triggers real connections to ClickHouse, Redis, S3 even when endpoint deps are overridden. Solution: patch factory functions at the `main` module level using `unittest.mock.patch` so the lifespan itself uses mocks during test startup.

## User Setup Required
None - no external service configuration required for this plan.

## Next Phase Readiness
- POST /v1/spans is functional end-to-end (behind full stack)
- All 5 Phase 2 success criteria covered by integration tests
- Phase 2 Plan 04 (end-to-end validation / docker-compose smoke test) can proceed
- Phase 3 embedding worker can consume from Redis `analysis_queue` — key is `analysis_queue`, span_id is the value, LPUSH/BRPOP FIFO

---
*Phase: 02-ingestion-path*
*Completed: 2026-03-28*
