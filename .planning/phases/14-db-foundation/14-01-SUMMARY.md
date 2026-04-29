---
phase: 14-db-foundation
plan: "01"
subsystem: database
tags: [postgres, diagnosticer, check-constraints, migration, psycopg2]

requires:
  - phase: 11-diagnosticer-backend
    provides: "DiagnosisResult dataclass and LLM provider implementations (base, anthropic, openai, ollama)"

provides:
  - "DiagnosisResult.verdict Literal aligned to DB CHECK constraint: ('model','architecture','prompt','unknown')"
  - "DiagnosisResult.severity Literal aligned to DB CHECK constraint: ('low','medium','high')"
  - "All four provider tool/schema enums updated to match DB vocabulary"
  - "xeter/scripts/preflight_diagnoses_audit.py — standalone script to detect violating rows before migration 004 runs"

affects:
  - 14-db-foundation (plan 02 — migration 004 VALIDATE CONSTRAINT depends on providers emitting correct vocabulary)

tech-stack:
  added: []
  patterns:
    - "_get_dsn() DSN-stripping pattern (strip +asyncpg prefix) for psycopg2 connections — consistent with flag_writer.py"
    - "Standalone pre-flight audit script pattern: exit 0 = safe, exit 1 = violations with repair SQL printed"

key-files:
  created:
    - xeter/scripts/preflight_diagnoses_audit.py
  modified:
    - xeter/services/diagnosticer/providers/base.py
    - xeter/services/diagnosticer/providers/anthropic.py
    - xeter/services/diagnosticer/providers/openai.py
    - xeter/services/diagnosticer/providers/ollama.py

key-decisions:
  - "Vocabulary alignment done in providers BEFORE migration 004 runs — ensures no new bad rows enter the DB in the window between now and VALIDATE CONSTRAINT"
  - "Pre-flight script uses psycopg2 with tuple parameterization (%s with Python tuple) for IN clause — psycopg2 adapts tuples to SQL (val1, val2, ...) correctly"

patterns-established:
  - "Pre-flight audit scripts: exit 0 = safe to migrate, exit 1 = violations found with repair SQL"

requirements-completed:
  - DB-03

duration: 7min
completed: 2026-04-29
---

# Phase 14 Plan 01: Provider Vocabulary Alignment Summary

**Provider enums and DiagnosisResult Literals realigned to DB-approved vocabulary ('unknown' not 'undetermined', no 'critical' severity) with a standalone pre-flight audit script for migration 004**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-29T06:27:43Z
- **Completed:** 2026-04-29T06:34:26Z
- **Tasks:** 2
- **Files modified:** 5 (4 providers + 1 new script)

## Accomplishments

- Updated all four provider files (base, anthropic, openai, ollama) so no future diagnoses row can contain verdict='undetermined' or severity='critical'
- Created preflight_diagnoses_audit.py that queries existing data and exits 0 (safe) or 1 (violations + repair SQL)
- All 6 existing diagnosticer tests continue to pass — vocabulary change had no runtime impact on mock-based tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Update DiagnosisResult Literals and all provider enums** - `1c38cb8` (feat)
2. **Task 2: Write pre-flight audit script** - `46076fa` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `xeter/services/diagnosticer/providers/base.py` - verdict Literal: "undetermined" -> "unknown"; severity Literal: removed "critical"
- `xeter/services/diagnosticer/providers/anthropic.py` - verdict enum and description updated; severity enum updated
- `xeter/services/diagnosticer/providers/openai.py` - verdict enum and description updated; severity enum updated
- `xeter/services/diagnosticer/providers/ollama.py` - _DiagnosisOutput Pydantic Literal types updated
- `xeter/scripts/preflight_diagnoses_audit.py` - New standalone pre-flight audit script for migration 004

## Decisions Made

None - followed plan as specified. Changes were surgical (exact string replacements only as directed).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `grep -rn "undetermined|\"critical\"` on the providers directory initially showed matches in `.pyc` bytecode cache files — not a real failure. Source files were clean. Added `--include="*.py"` filter to confirm source-only pass.

## User Setup Required

None - no external service configuration required. Run `python xeter/scripts/preflight_diagnoses_audit.py` manually before executing migration 004 (requires DATABASE_URL in environment).

## Next Phase Readiness

- Plan 02 (migration 004) can now proceed: providers emit only DB-approved vocabulary, no new violating rows will be written
- Before running `alembic upgrade head` to revision 004, operator should run `python xeter/scripts/preflight_diagnoses_audit.py` to confirm existing data is clean
- If violations found in existing data, repair SQL is printed by the script

---
*Phase: 14-db-foundation*
*Completed: 2026-04-29*
