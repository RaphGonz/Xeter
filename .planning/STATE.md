---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Silent Failure Detection
status: executing
stopped_at: Phase 25 planned — 5 plans in 4 waves (SemanticSpanAnalyzer + TraceAnalyzer implementation)
last_updated: "2026-05-24T00:00:00.000Z"
last_activity: 2026-05-24 -- Phase 25 planned, ready to execute
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 16
  completed_plans: 8
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-18)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Phase 25 — Execute: /gsd:execute-phase 25

## Current Position

Phase: 25 — Semantic Span + Structural Trace Checks
Status: Ready to execute (5 plans in 4 waves)
Last activity: 2026-05-24 -- Phase 25 planned

```
Progress: [████░░░░░░] 50%
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases complete | 3 / 6 |
| Plans complete | 8 / 8 (phases 22 + 23 + 24) |
| Tests passing | 197 passed, 9 skipped (13 pre-existing spacy env failures, not regressions) |
| Flag types active | 12 (7 pre-v1.5 + 5 new: output_schema_violation, required_fields_missing, output_truncated, type_coercion_error, context_overflow) |
| Flag types targeted | +17 new total (v1.5) — CTX-03 removed from scope |

## Accumulated Context

All architectural decisions logged in PROJECT.md Key Decisions table.

### Phase Sequence Rationale

- Phase 22 first: INFRA-01/INFRA-02 are hard blockers — trace flags cannot be verified without a reliable flush + score persistence path
- Phase 23 next: calibrate.py multi-analyzer support and SpanData fields must exist before any new analyzer class is written
- Phase 24: structural/deterministic checks (no embeddings) deliver lowest false-positive risk and validate the OutputSchemaAnalyzer class boundary
- Phase 25: embedding-based span checks and first trace checks depend on Phase 23 deps (tiktoken, rapidfuzz, spaCy) and Phase 24's analyzer scaffold
- Phase 26: best-effort heuristic trace checks built last; precision floors verified per check before implementation
- Phase 27: calibration only meaningful once all 17 checks are implemented

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

### Key Decisions (Phase 24)

- D-01 scope: SCHEMA-01 sub-case A only (response not JSON when schema set); sub-case B not tested
- D-04 invariant: log_score called before flag/clean decision; early-exit guards (field is None) do NOT log_score
- D-05: 4 binary checks log 0.0/1.0 in BINARY_FLAG_TYPES; context_overflow logs numeric token_count (calibration signal)
- D-06: OutputSchemaAnalyzer inherits (embedder, thresholds) constructor — no __init__ override
- CTX-03 (prompt_injection): removed from project scope entirely; not deferred, permanently cut
- Code review (CR-01): context_overflow hill-climb path in calibrate.py needs dedicated token-scale calibration — tracked in 24-REVIEW.md
- Code review (CR-02): patch_docker_compose missing context_overflow in key_to_env — tracked in 24-REVIEW.md

### Open Blockers

- CR-01/CR-02 from 24-REVIEW.md: calibrate.py context_overflow calibration path needs fix before Phase 27 calibration run

## Session Continuity

Last session: 2026-05-21T20:00:00.000Z
Stopped at: Phase 24 complete — OutputSchemaAnalyzer live; 5 structural checks implemented and wired
Next: Execute Phase 25 — /gsd:execute-phase 25
