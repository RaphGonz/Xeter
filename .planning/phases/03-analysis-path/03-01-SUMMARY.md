---
phase: 03-analysis-path
plan: "01"
subsystem: worker
tags: [migration, abc, embeddings, calibration, foundation]
dependency_graph:
  requires:
    - 02-03 (ingest handler — SPAN_COLUMNS convention used in SpanData)
    - 001_initial.py (Alembic chain: down_revision = "001")
  provides:
    - span_scores PostgreSQL table (calibration data store)
    - BaseAnalyzer ABC (shared interface for all analyzers)
    - Flag dataclass (flag output type)
    - SpanData dataclass (span input type)
  affects:
    - 03-02 and beyond (all analyzers inherit BaseAnalyzer)
tech_stack:
  added:
    - sentence-transformers (model injected, not imported in base.py)
    - numpy (np.ndarray used for embedding vectors)
  patterns:
    - ABC with concrete helpers + abstract analyze/name
    - Threshold injection via constructor dict (no hardcoded literals)
    - Calibration-first: log_score called before threshold test
key_files:
  created:
    - xeter/migrations/versions/002_span_scores.py
    - xeter/services/worker/__init__.py
    - xeter/services/worker/base.py
  modified: []
decisions:
  - "RLS omitted from span_scores — worker connects as BYPASSRLS; Phase 4 adds read-path filtering"
  - "sentence_transformers not imported in base.py — model injected via constructor to decouple ABC from load-time weight download"
  - "Optional fields use Optional[str] / Optional[list[dict]] rather than X | None for Python 3.9 compatibility (from __future__ import annotations handles 3.10+ union syntax at runtime)"
metrics:
  duration_seconds: 412
  completed_date: "2026-03-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
---

# Phase 3 Plan 01: Embedding Worker Foundation Summary

**One-liner:** Alembic migration 002 creating `span_scores` calibration table + `BaseAnalyzer` ABC with `Flag`/`SpanData` dataclasses and embed/compare/log_score helpers.

## What Was Built

### Task 1: Alembic Migration 002 — span_scores

`xeter/migrations/versions/002_span_scores.py` creates the `span_scores` PostgreSQL table that stores every similarity score computed during analysis. Key design:

- 7 columns: `score_id` UUID PK, `span_id` String, `tenant_id` UUID, `analyzer_name` String, `metric_name` String, `score` Float, `created_at` TIMESTAMPTZ
- Two indexes: `ix_span_scores_span` on `(span_id)` and `ix_span_scores_tenant` on `(tenant_id, analyzer_name)`
- RLS intentionally omitted — internal worker uses BYPASSRLS role; Phase 4 adds read-path filtering
- Follows exact convention of 001_initial.py: file-level docstring, `op.create_table` / `op.create_index`, symmetric `downgrade()`

### Task 2: BaseAnalyzer ABC + Flag + SpanData

`xeter/services/worker/base.py` is the shared foundation all analyzers build on:

**Flag dataclass** — output of every `analyze()` call: `flag_type` (str), `score` (float that triggered it), `detail` (dict with always-present `"metric"` key).

**SpanData dataclass** — input to every `analyze()` call: all SPAN_COLUMNS from the ClickHouse spans table plus three S3-resolved fields (`prompt`, `response`, `available_tools`).

**BaseAnalyzer ABC** — concrete helpers:
- `embed(text)` — delegates to `self._model.encode()`, returns `np.ndarray` shape `(384,)`
- `compare(a, b)` — cosine similarity via `model.similarity()`, reshapes to 2D, returns float in `[-1, 1]`
- `log_score(metric_name, score)` — appends `(analyzer_name, metric_name, score)` to internal buffer; called BEFORE threshold test
- `flush_scores()` — returns and clears accumulated scores after `analyze()` returns

Abstract members that subclasses must implement: `name` (property) and `analyze(span) -> list[Flag]`.

## Verification

All four plan verification commands pass:
1. `inspect.isabstract(BaseAnalyzer)` → `True`
2. Migration revision/down_revision → `002 001`
3. `span_scores` present in `op.create_table` call — confirmed (10 occurrences)
4. `ENABLE ROW LEVEL SECURITY` absent from 002_span_scores.py — confirmed

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash    | Message                                                                  |
|---------|--------------------------------------------------------------------------|
| 04e6b6b | feat(03-01): Alembic migration 002 — span_scores table with 2 indexes, no RLS |
| 2692d0b | feat(03-01): BaseAnalyzer ABC, Flag and SpanData dataclasses in worker/base.py |

## Self-Check: PASSED

- FOUND: xeter/migrations/versions/002_span_scores.py
- FOUND: xeter/services/worker/__init__.py
- FOUND: xeter/services/worker/base.py
- FOUND: .planning/phases/03-analysis-path/03-01-SUMMARY.md
- FOUND commit: 04e6b6b (migration)
- FOUND commit: 2692d0b (BaseAnalyzer)
