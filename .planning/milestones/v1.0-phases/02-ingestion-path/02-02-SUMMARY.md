---
phase: 02-ingestion-path
plan: "02"
subsystem: api
tags: [fastapi, postgresql, s3, minio, clickhouse, redis, asyncio, bcrypt, aioboto3]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: ApiKeyRepository, verify_api_key, ApiKey model, ClickHouse spans DDL, shared DB modules

provides:
  - "auth.py: verify_api_key_header FastAPI dependency returning tenant_id"
  - "s3.py: S3Client with upload_span_payloads coroutine for MinIO"
  - "batch.py: SpanBatcher with asyncio.Queue and periodic size-or-time flush to ClickHouse"
  - "queue.py: enqueue_span_id LPUSH to analysis_queue Redis key"
  - "shared/db/session.py: shared get_session FastAPI dependency"

affects:
  - 02-03-wiring
  - 02-04-sdk
  - 03-embedding-worker

# Tech tracking
tech-stack:
  added:
    - "aioboto3==15.5.0 — async S3/MinIO client (aioboto3.Session context manager pattern)"
  patterns:
    - "asyncio.to_thread for CPU-bound bcrypt.checkpw in async handlers"
    - "asyncio.Queue + background task for in-memory span batching (size-or-time flush)"
    - "LPUSH/BRPOP FIFO pattern for Redis task queue"
    - "S3 upload all four payload fields sequentially before ClickHouse accept"

key-files:
  created:
    - xeter/services/analyser/auth.py
    - xeter/services/analyser/s3.py
    - xeter/services/analyser/batch.py
    - xeter/services/analyser/queue.py
    - xeter/shared/db/session.py
  modified:
    - xeter/pyproject.toml

key-decisions:
  - "02-02: shared/db/session.py created as shared get_session dependency — was previously duplicated per-service; auth.py import chain required canonical location"
  - "02-02: S3 uploads are sequential (not parallel) — avoids connection issues with single-threaded MinIO in local dev"
  - "02-02: SpanBatcher._flush logs errors but does not re-raise — observability data loss on crash is acceptable"

patterns-established:
  - "Pattern: bcrypt via asyncio.to_thread — CPU-bound crypto must not block the event loop in async FastAPI handlers"
  - "Pattern: SpanBatcher size-or-time flush — asyncio.wait_for timeout drives time trigger; len(buffer) >= batch_size drives size trigger"
  - "Pattern: S3-first acceptance — upload to S3 must succeed before span enters ClickHouse batch (enforced in Plan 03 handler)"

requirements-completed:
  - STOR-02
  - STOR-04
  - STOR-05

# Metrics
duration: 9min
completed: "2026-03-28"
---

# Phase 2 Plan 02: Infrastructure Modules Summary

**Four analyser infrastructure modules: API key auth via bcrypt+PostgreSQL, aioboto3 MinIO upload, asyncio.Queue batch flusher to ClickHouse, Redis LPUSH enqueue — all independently importable**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-28T10:45:57Z
- **Completed:** 2026-03-28T10:55:09Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- `auth.py`: FastAPI dependency that iterates all api_keys rows and validates x-api-key header via bcrypt (via asyncio.to_thread), returns tenant_id string
- `s3.py`: S3Client class uploading four span fields to MinIO at `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`, raises on failure for 5xx propagation
- `batch.py`: SpanBatcher with SPAN_COLUMNS (17 columns), asyncio.Queue buffering, background flush task with size-or-time trigger, graceful shutdown flush
- `queue.py`: `enqueue_span_id` LPUSH to `analysis_queue` with hard-error semantics on Redis failure
- `shared/db/session.py`: shared get_session dependency extracted so auth.py (and future services) have a canonical import location

## Task Commits

Each task was committed atomically:

1. **Task 1: auth.py and s3.py modules** - `18bb29d` (feat)
2. **Task 2: batch.py and queue.py modules** - `66ee5cc` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `xeter/services/analyser/auth.py` - FastAPI dependency validating x-api-key against PostgreSQL bcrypt hashes
- `xeter/services/analyser/s3.py` - S3Client for aioboto3 MinIO uploads with sequential field upload
- `xeter/services/analyser/batch.py` - SpanBatcher: SPAN_COLUMNS, asyncio.Queue, size-or-time flush, get_clickhouse_client factory
- `xeter/services/analyser/queue.py` - enqueue_span_id LPUSH to analysis_queue
- `xeter/shared/db/session.py` - Shared get_session FastAPI dependency (extracted from presenter)
- `xeter/pyproject.toml` - Added aioboto3==15.5.0 dependency

## Decisions Made
- Created `xeter/shared/db/session.py` to provide a canonical `get_session` dependency. Previously the presenter router had its own local copy — auth.py's import of `xeter.shared.db.session` required extracting this into the shared package.
- S3 uploads are sequential per field (not concurrent) to avoid connection pool issues with single-threaded MinIO in local development, per RESEARCH.md.
- SpanBatcher._flush catches and logs all exceptions without re-raising — observability data is acceptable to lose on crash; not re-raising keeps the flush loop alive.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created xeter/shared/db/session.py**
- **Found during:** Task 1 (auth.py implementation)
- **Issue:** `auth.py` imports `get_session` from `xeter.shared.db.session`, but that module did not exist. The import would fail at startup, blocking the Task 1 verify step.
- **Fix:** Created `xeter/shared/db/session.py` with `get_session` async generator — same implementation as the presenter's local copy, now in the canonical shared location.
- **Files modified:** xeter/shared/db/session.py (created)
- **Verification:** `from xeter.services.analyser.auth import verify_api_key_header` succeeds without error
- **Committed in:** 18bb29d (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking issue)
**Impact on plan:** The fix was explicitly anticipated by the plan note ("If not, the file to create it is in Plan 03 scope"). Creating it in Plan 02 unblocks the import while also being the right long-term location. No scope creep.

## Issues Encountered
None — all modules implemented as specified in RESEARCH.md patterns.

## User Setup Required
None - no external service configuration required for this plan.

## Self-Check: PASSED

All created files verified on disk. Commits 18bb29d and 66ee5cc confirmed in git log.

## Next Phase Readiness
- All four modules importable independently: auth.py, s3.py, batch.py, queue.py
- Plan 03 (wiring) can import and connect these modules into the Analyser FastAPI app
- `xeter.shared.db.session.get_session` is available for Plan 03 to use in app dependency injection
- `aioboto3==15.5.0` added to pyproject.toml; install with `pip install -e xeter/`

---
*Phase: 02-ingestion-path*
*Completed: 2026-03-28*
