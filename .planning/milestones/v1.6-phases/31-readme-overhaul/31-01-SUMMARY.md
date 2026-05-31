---
phase: 31-readme-overhaul
plan: "01"
subsystem: infra
tags: [docker-compose, alembic, migrations, seed, init-container, postgres]

requires:
  - phase: 14-db-foundation
    provides: alembic migrations at xeter/migrations/alembic.ini
  - phase: 15-secrets-hygiene
    provides: generate-secrets.sh + no :- fallbacks pattern for docker-compose

provides:
  - db-init init container service in deploy/docker-compose.yml
  - automatic migration + seed on docker compose up before app services start
  - depends_on: service_completed_successfully on worker, presenter, analyser, diagnosticer

affects: [31-02-readme, deploy, onboarding]

tech-stack:
  added: []
  patterns:
    - "Init container pattern: one-shot service with restart: no blocks app services via service_completed_successfully"

key-files:
  created: []
  modified:
    - deploy/docker-compose.yml

key-decisions:
  - "db-init reuses presenter Dockerfile (same context, no extra image) to run alembic + seed"
  - "restart: no prevents infinite retry loop on seed failure (T-31-01-02 threat mitigated)"
  - "service_completed_successfully on all four app services guarantees schema is ready before traffic"

patterns-established:
  - "Init container pattern: use restart: no + service_completed_successfully to gate app startup on one-shot migration steps"

requirements-completed:
  - DOCS-02

duration: 8min
completed: 2026-05-31
---

# Phase 31 Plan 01: db-init Init Container Summary

**db-init one-shot service added to docker-compose.yml — runs alembic upgrade head + seed before worker, presenter, analyser, and diagnosticer start**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-31T06:32:00Z
- **Completed:** 2026-05-31T06:40:13Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added `db-init` service to `deploy/docker-compose.yml` using the presenter Dockerfile; chains `alembic upgrade head` and `python -m xeter.scripts.seed` via shell
- Set `restart: "no"` to prevent infinite retry loops on seed failure
- Added `db-init: condition: service_completed_successfully` to worker, presenter, analyser, and diagnosticer; all existing depends_on entries preserved

## Task Commits

Each task was committed atomically:

1. **Task 1: Add db-init service and update depends_on blocks** - `963ce67` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `deploy/docker-compose.yml` - Added db-init service; updated depends_on for worker, presenter, analyser, diagnosticer

## Decisions Made

- db-init reuses the presenter Dockerfile (build context `..`, dockerfile `services/presenter/Dockerfile`) — same image as application services, no extra Dockerfile needed
- `restart: "no"` is the correct disposition per T-31-01-02: failure surfaces immediately in compose logs without an infinite retry loop consuming resources

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `docker compose up` now applies migrations and seeds dev data before any application service starts
- Plan 31-02 (README overhaul) can reference this init container as fact in the Quick Start section
- No blockers

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. `db-init` connects to postgres on the internal Docker network using the same DATABASE_URL trust boundary as all other services (T-31-01-01 accepted, T-31-01-02 mitigated).

## Self-Check: PASSED

- `deploy/docker-compose.yml` present and modified: FOUND
- Commit `963ce67` exists: FOUND
- YAML verification (python -c "import yaml...") passed with OK output

---
*Phase: 31-readme-overhaul*
*Completed: 2026-05-31*
