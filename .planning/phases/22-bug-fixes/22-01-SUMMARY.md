---
phase: 22-bug-fixes
plan: "01"
subsystem: worker / migrations
tags: [migration, score-writer, nullable, span-id]
dependency_graph:
  requires: []
  provides:
    - span_scores.span_id nullable (migration 006)
    - write_scores accepts str | None
  affects:
    - xeter/services/worker/score_writer.py
    - xeter/migrations/versions/006_span_scores_nullable_span_id.py
tech_stack:
  added: []
  patterns:
    - Alembic ALTER TABLE via op.execute (raw SQL, no SQLAlchemy models)
    - PEP 604 union syntax (str | None) matching flag_writer.py pattern
key_files:
  created:
    - xeter/migrations/versions/006_span_scores_nullable_span_id.py
  modified:
    - xeter/services/worker/score_writer.py
decisions:
  - "Used op.execute with raw SQL for ALTER TABLE (matching migration 005 pattern; no SQLAlchemy models needed for DDL-only migration)"
  - "Used str | None PEP 604 union syntax (not Optional[str]) to match existing codebase style in flag_writer.py"
metrics:
  duration: "13m"
  completed: "2026-05-19"
---

# Phase 22 Plan 01: Nullable span_id Migration + write_scores Signature Summary

Two surgical changes that unblock trace-level score writes: Alembic migration 006 makes `span_scores.span_id` nullable, and `write_scores` signature updated from `span_id: str` to `span_id: str | None`.

## What Was Done

### Task 1: Migration 006 — make span_scores.span_id nullable

Created `xeter/migrations/versions/006_span_scores_nullable_span_id.py` modelled exactly on `005_trace_flags_schema.py`:

- `revision = "006"`, `down_revision = "005"`
- `upgrade()`: `op.execute("ALTER TABLE span_scores ALTER COLUMN span_id DROP NOT NULL;")`
- `downgrade()`: `op.execute("ALTER TABLE span_scores ALTER COLUMN span_id SET NOT NULL;")` with warning comment that NULL trace-level rows will block the downgrade
- Imports: only `typing.Sequence`, `typing.Union`, and `alembic.op` — no SQLAlchemy

**Commit:** `2d022b8`

### Task 2: Update write_scores signature to accept Optional span_id

Two targeted edits to `xeter/services/worker/score_writer.py`:

1. Line 47: `span_id: str,` → `span_id: str | None,`
2. Docstring Args `span_id:` line updated to: "The span being scored, or None for trace-level scores produced by TraceAnalyzer (psycopg2 maps None to SQL NULL automatically)."

No other lines changed. No new imports added. Existing callers passing a string span_id are fully unaffected.

**Commit:** `ddf6529`

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| 1. Migration syntax | `python -c "import ast; ast.parse(...); print('ok')"` | ok |
| 2. revision=006 | `grep -n "revision.*006" 006_...py` | line 16: `revision: str = "006"` |
| 3. down_revision=005 | `grep -n "down_revision.*005" 006_...py` | line 17: `down_revision: Union[str, None] = "005"` |
| 4. span_id: str | None | `grep -n "span_id: str | None" score_writer.py` | line 47 |
| 5. import ok | `python -c "from xeter.services.worker.score_writer import write_scores; print('import ok')"` | import ok |
| 6. signature ok | `python -c "...assert str(sig.parameters['span_id'].annotation) in ('str | None', ...)"` | signature ok |
| 7. pytest | `python -m pytest xeter/tests/ -x -q` | 95 passed, 9 skipped, 1 pre-existing failure (spaCy not installed — unrelated to this plan) |

### Pre-existing failure note

`test_tool_call_analyzer.py::test_analyze_returns_list` fails with `ModuleNotFoundError: No module named 'spacy'` — this failure exists on `HEAD~2` (before any changes in this plan) and is environment-only. No regressions introduced.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Commit | Message | Files |
|--------|---------|-------|
| `2d022b8` | `feat(22-01): add migration 006 — make span_scores.span_id nullable` | `xeter/migrations/versions/006_span_scores_nullable_span_id.py` (new) |
| `ddf6529` | `feat(22-01): update write_scores signature to accept span_id: str | None` | `xeter/services/worker/score_writer.py` |

## Self-Check: PASSED

- `xeter/migrations/versions/006_span_scores_nullable_span_id.py` exists
- `xeter/services/worker/score_writer.py` contains `span_id: str | None` at line 47
- Commits `2d022b8` and `ddf6529` exist in git log
