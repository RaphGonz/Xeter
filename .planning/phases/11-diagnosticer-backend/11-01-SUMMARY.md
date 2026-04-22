---
phase: 11-diagnosticer-backend
plan: "01"
subsystem: database
tags: [postgres, sqlalchemy, alembic, rls, anthropic, openai, ollama]

# Dependency graph
requires:
  - phase: 10-worker-enhancements
    provides: "shared/models.py Base + existing Diagnostic model pattern"
provides:
  - "diagnoses table (Alembic migration 003) with full output schema and RLS"
  - "Diagnosis SQLAlchemy ORM model importable from xeter.shared.models"
  - "anthropic==0.86.0, openai==2.22.0, ollama added to pyproject.toml"
affects: [11-02, 11-03, 11-04, 11-05, 12-presenter-integration]

# Tech tracking
tech-stack:
  added: [anthropic==0.86.0, openai==2.22.0, ollama]
  patterns:
    - "String (not PG enum) for verdict and severity — same FLAG-03 rationale"
    - "RLS tenant_isolation policy matching migration 001 pattern"
    - "Diagnosis distinct from legacy Diagnostic/diagnostics placeholder"

key-files:
  created:
    - xeter/migrations/versions/003_diagnoses.py
  modified:
    - xeter/shared/models.py
    - xeter/pyproject.toml

key-decisions:
  - "Used String (not PG enum) for verdict and severity fields — avoids migration pain on value changes, consistent with FLAG-03"
  - "diagnoses table is distinct from legacy diagnostics placeholder table — both coexist, neither modifies the other"
  - "ollama dependency unpinned (version uncertain), anthropic and openai pinned to exact versions"
  - "Docker apply skipped — Docker Desktop not running; migration file is sufficient for this plan"

patterns-established:
  - "Migration 003 pattern: revision/down_revision type-annotated Union[str, None] matching migration 002 style"
  - "RLS on diagnoses matches flags table pattern from migration 001"

requirements-completed: [DIAG-01, DIAG-02]

# Metrics
duration: 14min
completed: 2026-04-22
---

# Phase 11 Plan 01: Diagnosticer DB Foundation Summary

**PostgreSQL diagnoses table (migration 003) with 12-column output schema, RLS tenant isolation, and Diagnosis SQLAlchemy ORM — foundation for all Phase 11 plans**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-22T17:29:49Z
- **Completed:** 2026-04-22T17:44:26Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Added anthropic==0.86.0, openai==2.22.0, and ollama to pyproject.toml — Diagnosticer Docker image will include all three LLM SDK clients
- Added `Diagnosis` SQLAlchemy ORM model to `shared/models.py` with all 12 required columns; existing `Diagnostic` model left untouched
- Created `xeter/migrations/versions/003_diagnoses.py` with full RLS (tenant_isolation policy), two performance indexes, and correct revision chain (down_revision="002")

## Task Commits

Each task was committed atomically:

1. **Task 1: Add LLM SDK dependencies to pyproject.toml** - `3381162` (chore)
2. **Task 2: Add Diagnosis SQLAlchemy model to shared/models.py** - `4304219` (feat)
3. **Task 3: Write Alembic migration 003 for diagnoses table** - `f05ae72` (feat)

## Files Created/Modified

- `xeter/pyproject.toml` - Added anthropic==0.86.0, openai==2.22.0, ollama after spacy>=3.7
- `xeter/shared/models.py` - Added Text to imports; appended Diagnosis class after Diagnostic
- `xeter/migrations/versions/003_diagnoses.py` - New migration: diagnoses table, RLS, 2 indexes

## Decisions Made

- Used String (not PG enum) for verdict and severity — avoids migration pain on value changes, consistent with FLAG-03 pattern for flag_type
- `diagnoses` table is distinct from the legacy `diagnostics` placeholder table; both coexist with no cross-modification
- `ollama` left unpinned in pyproject.toml — exact patch version uncertain; anthropic and openai pinned to exact versions as specified in the plan
- Docker apply step skipped — Docker Desktop not running during execution; migration file is syntactically correct and sufficient for this plan's done criteria

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Docker Desktop was not running, so `alembic upgrade head` could not be applied. Per plan instructions this is acceptable: "If the Docker stack is not running, skip the apply step — the migration file is sufficient for the plan." Migration will be applied during integration testing.

## User Setup Required

None - no external service configuration required. Migration apply will happen when Docker stack is started.

## Next Phase Readiness

- `Diagnosis` model is importable from `xeter.shared.models` — all Phase 11 plans can now import it
- Migration 003 file is ready to apply when Docker stack starts
- LLM SDK dependencies are in pyproject.toml for the Diagnosticer Docker image build

---
*Phase: 11-diagnosticer-backend*
*Completed: 2026-04-22*
