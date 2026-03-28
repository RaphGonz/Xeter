---
phase: 03-analysis-path
plan: 04
subsystem: worker
tags: [redis, sentence-transformers, docker, clickhouse, postgresql, s3]

# Dependency graph
requires:
  - phase: 03-analysis-path
    provides: BaseAnalyzer ABC, ToolCallAnalyzer, span_fetcher, score_writer, flag_writer
provides:
  - BRPOP worker loop consuming analysis_queue from Redis
  - process_span(span_id, analyzers) dispatcher with injectable analyzer list
  - ANALYZERS registry pattern (extensible — append to list only)
  - Worker Dockerfile pre-baking all-MiniLM-L6-v2 sentence-transformers model
  - Worker service in deploy/docker-compose.yml wired to all four backends
  - Integration tests confirming registry extensibility (FLAG-01 proof)
affects: [04-read-path, 06-calibration]

# Tech tracking
tech-stack:
  added: [sentence-transformers>=5.0.0, psycopg2-binary>=2.9.0, boto3>=1.35.0]
  patterns:
    - ANALYZERS registry via injectable list — extend by appending, not modifying
    - Model loaded once in main() then injected into ToolCallAnalyzer constructor
    - process_span takes analyzers parameter for test injection without monkeypatching

key-files:
  created:
    - xeter/services/worker/main.py
    - services/worker/main.py
    - services/worker/__init__.py
    - services/worker/Dockerfile
    - xeter/tests/worker/test_worker_loop.py
  modified:
    - xeter/pyproject.toml
    - deploy/docker-compose.yml

key-decisions:
  - "process_span takes analyzers as parameter (not module global) — enables test injection without monkeypatching"
  - "Model loaded lazily inside main() — importing the module during tests does not trigger 80MB model download"
  - "BRPOP (right-pop) used with LPUSH for FIFO queue ordering — matches queue.py push direction"
  - "Worker Dockerfile pre-bakes model into image layer via RUN python -c — avoids runtime download on first span"

patterns-established:
  - "ANALYZERS extensibility: import new analyzer class, append to analyzers list in main() — zero other changes"
  - "Threshold config from env with numeric defaults — all 5 thresholds are first-class env vars"
  - "SIGTERM handled via running flag + BRPOP timeout=2 — clean shutdown within ~2 seconds"

requirements-completed:
  - FLAG-01
  - FLAG-02
  - FLAG-03
  - FLAG-04
  - FLAG-05
  - FLAG-06
  - FLAG-07
  - FLAG-08
  - FLAG-09
  - FLAG-10
  - FLAG-11
  - FLAG-12
  - STOR-03

# Metrics
duration: 18min
completed: 2026-03-28
---

# Phase 3 Plan 4: Embedding Worker Assembly Summary

**BRPOP worker loop with injectable ANALYZERS registry, pre-baked Docker image, and 6-test integration suite proving FLAG-01 extensibility**

## Performance

- **Duration:** 18 min
- **Started:** 2026-03-28T22:12:32Z
- **Completed:** 2026-03-28T22:30:38Z
- **Tasks:** 2
- **Files modified:** 7 (5 created, 2 modified)

## Accomplishments

- Worker main loop complete: BRPOP on `analysis_queue`, dispatches to all analyzers, writes scores always, writes flags conditionally, SIGTERM-safe via `running` flag + timeout=2
- Docker build chain complete: `services/worker/Dockerfile` copies xeter package, installs deps, pre-bakes `all-MiniLM-L6-v2` into image, `docker-compose.yml` wires worker to all four backends with 5 threshold env vars
- Integration test suite: 6 tests covering all-analyzers-called, scores-always-written, flags-conditional, clean-span, exception-propagation, and registry extensibility (FLAG-01 proof) — all 20 worker tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Worker main loop + ANALYZERS registry + dependency additions** - `19c4368` (feat)
2. **Task 2: Docker entry point + Dockerfile + docker-compose worker service + integration test** - `715bc06` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/services/worker/main.py` — BRPOP loop, process_span(span_id, analyzers), THRESHOLDS dict, signal handlers, main() entry point
- `services/worker/main.py` — Docker entry point delegating to xeter.services.worker.main.main()
- `services/worker/__init__.py` — empty package marker
- `services/worker/Dockerfile` — python:3.12-slim, installs xeter, pre-bakes all-MiniLM-L6-v2 model
- `xeter/tests/worker/test_worker_loop.py` — 6 integration tests with fully mocked I/O
- `xeter/pyproject.toml` — added sentence-transformers>=5.0.0, psycopg2-binary>=2.9.0, boto3>=1.35.0
- `deploy/docker-compose.yml` — added worker service with all 5 WORKER_THRESHOLD_* env vars

## Decisions Made

- `process_span` takes `analyzers` as an explicit parameter rather than reading a module global — this allows integration tests to inject mock analyzers without monkeypatching and makes the dispatch contract explicit
- Model loaded lazily inside `main()` — importing the module does not trigger the sentence-transformers model download, making test imports fast
- BRPOP (right-pop) used with LPUSH writes — gives FIFO ordering, consistent with queue.py push direction documented in 03-RESEARCH.md
- Dockerfile pre-bakes model via `RUN python -c "... SentenceTransformer('all-MiniLM-L6-v2')"` — model cached in image layer, no 80MB download when first span arrives

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`sentence_transformers` was not installed in the local Python environment before Task 1 verification. Installed via `pip install sentence-transformers` (Rule 3 - blocking). The package was already specified in pyproject.toml as a dependency; the install was a local environment setup step only, not a code change. All tests continued to pass after installation.

## User Setup Required

None - no external service configuration required. The worker service is fully configured via environment variables in `deploy/docker-compose.yml`.

## Next Phase Readiness

- Full analysis path complete: ingestion (Phase 2) → analysis worker (Phase 3) → ready for read path (Phase 4)
- Worker reads from Redis queue, fetches from ClickHouse + S3, writes scores to PostgreSQL, writes flags to PostgreSQL
- Phase 4 (read path) can now query `span_scores` and `flags` tables populated by the worker
- FLAG-01 extensibility confirmed by test: second analyzer dispatched by appending to list only

---
*Phase: 03-analysis-path*
*Completed: 2026-03-28*
