---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [docker, docker-compose, postgres, clickhouse, redis, minio, fastapi, uvicorn, python, makefile]

# Dependency graph
requires: []
provides:
  - "Docker Compose stack with all six services (postgres, clickhouse, redis, minio, analyser, presenter, view)"
  - "Healthcheck-gated startup ordering via condition: service_healthy"
  - "Hot-reload for backend stubs via uvicorn --reload and volume mounts"
  - ".env.example with all required dev defaults"
  - "Makefile with up, down, logs, build, seed, reset, test, migrate targets"
  - "Python package scaffold under xeter/ (shared/dal, shared/db, services, migrations, tests, scripts)"
  - "pyproject.toml with all Phase 1 Python dependencies pinned"
affects:
  - 01-02-schemas
  - 01-03-dal
  - 01-04-registration
  - All subsequent phases (docker compose up is the entry point)

# Tech tracking
tech-stack:
  added:
    - "postgres:16-alpine"
    - "clickhouse/clickhouse-server:25.3"
    - "redis:7-alpine"
    - "minio/minio:latest"
    - "python:3.12-slim (analyser + presenter Dockerfiles)"
    - "node:20-alpine (view Dockerfile)"
    - "FastAPI 0.135.2"
    - "uvicorn[standard] >=0.32"
    - "SQLAlchemy 2.0.48"
    - "asyncpg 0.31.0"
    - "Alembic 1.18.4"
    - "clickhouse-connect 0.15.0"
    - "passlib[bcrypt] >=1.7"
    - "structlog, httpx, pytest, pytest-asyncio 0.24.0, anyio"
  patterns:
    - "condition: service_healthy on all infra service depends_on (app services never start before infra is ready)"
    - "Volume-mount + uvicorn --reload for hot reload without image rebuild"
    - "Stub services with /healthz endpoint during Phase 1 (replaced with real logic in later plans)"

key-files:
  created:
    - deploy/docker-compose.yml
    - .env.example
    - Makefile
    - services/analyser/Dockerfile
    - services/analyser/main.py
    - services/presenter/Dockerfile
    - services/presenter/main.py
    - services/view/Dockerfile
    - services/view/index.html
    - services/view/package.json
    - xeter/pyproject.toml
  modified: []

key-decisions:
  - "Removed obsolete 'version' top-level key from docker-compose.yml (Docker Compose v2 deprecates it)"
  - "Used pytest-asyncio==0.24.0 instead of plan-specified 1.3.0 (1.3.0 does not exist; 0.24.0 is the stable release)"
  - "View stub uses 'serve' static server instead of Next.js dev server (Next.js scaffolded in later phase)"
  - "MinIO healthcheck uses curl (not mc) per plan spec — mc is not bundled in the standard minio image"

patterns-established:
  - "Stub pattern: each app service has a minimal FastAPI app with GET /healthz returning {status: ok}"
  - "All infra services use interval: 10s, timeout: 5s, retries: 5, start_period: 30s healthchecks"

requirements-completed:
  - INFR-01

# Metrics
duration: 15min
completed: 2026-03-27
---

# Phase 1 Plan 01: Docker Compose Infrastructure Stack Summary

**Six-service Docker Compose stack with healthcheck-gated startup, uvicorn hot-reload volume mounts, and a full Python package scaffold ready for Plan 02 schema work**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-27T12:10:07Z
- **Completed:** 2026-03-27T12:24:48Z
- **Tasks:** 2
- **Files created:** 18

## Accomplishments

- Docker Compose stack with all 6 services: postgres, clickhouse, redis, minio, analyser (stub), presenter (stub), view (stub)
- 8 `condition: service_healthy` dependencies ensuring infra is healthy before any app service starts
- uvicorn `--reload` + volume mounts on both backend stubs enabling hot reload without image rebuild
- `.env.example` with all required dev defaults including `dev-api-key-local` fixed seed key
- `Makefile` with `up`, `down`, `logs`, `build`, `seed`, `reset`, `test`, `migrate` targets
- Python package scaffold under `xeter/` (shared/dal, shared/db, services, migrations, tests, scripts) + pinned `pyproject.toml`

## Task Commits

Each task was committed atomically:

1. **Task 1: Docker Compose stack with healthcheck-gated startup** - `950ae54` (feat)
2. **Task 2: Environment config and Makefile** - `ffb9396` (feat)

**Plan metadata:** _(final docs commit, see below)_

## Files Created/Modified

- `deploy/docker-compose.yml` - Full 6-service stack with healthchecks and depends_on conditions
- `.env.example` - All required env vars with dev defaults (DATABASE_URL, CLICKHOUSE_HOST, REDIS_URL, MINIO_ENDPOINT, DEV_API_KEY)
- `Makefile` - Developer commands (up, down, logs, build, seed, reset, test, migrate)
- `services/analyser/Dockerfile` - python:3.12-slim + FastAPI + uvicorn stub
- `services/analyser/main.py` - Minimal FastAPI with GET /healthz
- `services/presenter/Dockerfile` - python:3.12-slim + FastAPI + uvicorn stub
- `services/presenter/main.py` - Minimal FastAPI with GET /healthz
- `services/view/Dockerfile` - node:20-alpine with serve static server
- `services/view/index.html` - Phase 1 placeholder page
- `services/view/package.json` - Shell package.json for Next.js scaffolding later
- `xeter/pyproject.toml` - All Phase 1 Python dependencies pinned

## Decisions Made

- Removed obsolete `version: "3.9"` key from docker-compose.yml (Docker Compose v2 issues a deprecation warning)
- Used `pytest-asyncio==0.24.0` — plan specified `1.3.0` which does not exist (the package uses 0.x versioning)
- View stub uses `serve` static server in Phase 1 — Next.js dev server requires a full project scaffold which arrives in a later plan
- MinIO healthcheck uses `curl` as specified — `mc` (MinIO Client) is not bundled in the standard `minio/minio:latest` image

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected non-existent pytest-asyncio version**
- **Found during:** Task 2 (pyproject.toml creation)
- **Issue:** Plan specified `pytest-asyncio==1.3.0` which does not exist; package uses 0.x versioning (latest stable is 0.24.0)
- **Fix:** Used `pytest-asyncio==0.24.0` instead
- **Files modified:** `xeter/pyproject.toml`
- **Verification:** Version exists on PyPI; compatible with Python 3.12
- **Committed in:** `ffb9396` (Task 2 commit)

**2. [Rule 1 - Bug] Removed obsolete `version` key from docker-compose.yml**
- **Found during:** Task 1 verification
- **Issue:** Docker Compose v2 emits a deprecation warning for top-level `version:` key; causes noise in CI/CD logs
- **Fix:** Removed `version: "3.9"` line; file is still valid per current Docker Compose spec
- **Files modified:** `deploy/docker-compose.yml`
- **Verification:** `docker compose config --quiet` returns no warnings
- **Committed in:** `950ae54` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for correctness; no scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None — no external service configuration required beyond Docker being installed.

## Next Phase Readiness

- `docker compose -f deploy/docker-compose.yml config` validates cleanly
- All 4 infra services have healthchecks; both app services have `condition: service_healthy` on all 4
- Plan 02 (schemas) can begin: ClickHouse and PostgreSQL are defined in compose, connection strings are in `.env.example`
- Python package scaffold ready to receive Alembic migration and models in Plan 02

---
*Phase: 01-foundation*
*Completed: 2026-03-27*
