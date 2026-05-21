---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Silent Failure Detection
status: executing
stopped_at: Phase 24 context gathered — ready for planning
last_updated: "2026-05-21T00:00:00.000Z"
last_activity: 2026-05-21 — Phase 24 context captured; 5 checks scoped (SCHEMA-01–04 + CTX-01); CTX-03 deferred; ready for /gsd:plan-phase 24
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 5
  completed_plans: 5
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-18)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Phase 24 — Structural Span Checks — context gathered, ready to plan

## Current Position

Phase: 24 — Structural Span Checks
Status: Context gathered — ready for planning
Last activity: 2026-05-21 — Phase 24 context captured; 5 checks scoped (SCHEMA-01–04 + CTX-01); CTX-03 deferred to later phase

```
Progress: [██████████] 100%
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases complete | 2 / 6 |
| Plans complete | 5 / 5 (phases 22 + 23) |
| Tests passing | 161 passed, 9 skipped (13 pre-existing spacy env failures, not regressions) |
| Flag types active | 7 (pre-v1.5) |
| Flag types targeted | +18 new (v1.5) |

## Accumulated Context

All architectural decisions logged in PROJECT.md Key Decisions table.

### Phase Sequence Rationale

- Phase 22 first: INFRA-01/INFRA-02 are hard blockers — trace flags cannot be verified without a reliable flush + score persistence path
- Phase 23 next: calibrate.py multi-analyzer support and SpanData fields must exist before any new analyzer class is written
- Phase 24: structural/deterministic checks (no embeddings) deliver lowest false-positive risk and validate the OutputSchemaAnalyzer class boundary
- Phase 25: embedding-based span checks and first trace checks depend on Phase 23 deps (tiktoken, rapidfuzz, spaCy) and Phase 24's analyzer scaffold
- Phase 26: best-effort heuristic trace checks built last; precision floors verified per check before implementation
- Phase 27: calibration only meaningful once all 18 checks are implemented

### Key Constraints for v1.5

- `wrong_tool_args` excluded from P/R calibration (low-confidence by design — PROJECT.md key decision)
- Full-suite mean precision target: ≥ 95%
- Recall floor per new check: R ≥ 0.10 (enforced by hill-climb; degenerate P=1.0,R=0.0 rejected)
- Binary flag types (no threshold sweep) must be registered in `BINARY_FLAG_TYPES` in calibrate.py
- Best-effort checks (CTX-02, TRACE-05, TRACE-07, TRACE-08) carry `low_confidence: true` in flag detail
- `no_verification` and `incomplete_verification` are mutually exclusive per trace

### Key Decisions (Phase 22)

- `_flush_stale_traces` accepts explicit params (no implicit globals) — consistent with `process_span` pattern
- `flush_scores()` called before `write_scores()` inside try block — same ordering as `process_span()`
- time.monotonic called internally in helper (not a param) — simplifies both call sites

### Key Decisions (Phase 23)

- D-04 dual-write DDL pattern: CREATE TABLE IF NOT EXISTS covers fresh deployments; idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS covers live deployments
- D-02 decorator kwarg: expected_output_schema is dict at SDK call site; serialized to JSON string before transmission to match SpanPayload Optional[str] field
- SPAN_COLUMNS position 9 reserved for expected_output_schema (after tool_arguments, before tool_output)
- D-05 static registry FLAG_TYPE_TO_ANALYZER_CLASS: all 7 existing flag types map to ToolCallAnalyzer; zero behavior change; extension point for phases 24-27
- D-08 recall floor = 0.10: exact boundary acceptable; sys.exit(1) with RECALL FLOOR ERROR message in CI output
- D-10 parent_span_id scope: SpanData + span_fetcher only (ClickHouse column already existed)

### Open Blockers

None.

## Session Continuity

Last session: 2026-05-20T21:00:00.000Z
Stopped at: Phase 23 verified — all infrastructure in place for v1.5 checks
Next: Plan Phase 24 — /gsd:plan-phase 24
