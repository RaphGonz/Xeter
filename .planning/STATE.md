---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Silent Failure Detection
status: executing
stopped_at: Phase 26 planned — 3 plans (RED/GREEN/WIRE) in 3 waves; ready to execute
last_updated: "2026-05-26T00:00:00.000Z"
last_activity: 2026-05-26 -- Phase 26 planned (3 plans)
progress:
  total_phases: 6
  completed_phases: 4
  total_plans: 24
  completed_plans: 13
  percent: 67
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-18)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Phase 26 — Best-effort heuristic trace checks

## Current Position

Phase: 26 — Best-Effort Proxy Checks (planned, ready to execute)
Status: Ready to execute — 3 plans in 3 waves
Last activity: 2026-05-26 -- Phase 26 planned (26-01 RED, 26-02 GREEN, 26-03 WIRE)

```
Progress: [██████░░░░] 67%
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases complete | 4 / 6 |
| Plans complete | 13 / 21 (phases 22 + 23 + 24 + 25) |
| Tests passing | 235 passed, 9 skipped (13 pre-existing spacy env failures, not regressions) |
| Flag types active | 18 (12 pre-Phase-25 + 6 new: missing_details, stale_context, step_repetition, termination_loop, context_propagation_failure, history_loss) |
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

### Key Decisions (Phase 25)

- SemanticSpanAnalyzer inherits BaseAnalyzer directly (BaseSpanAnalyzer not distinct in codebase) — CR-01 from review flags this; tracked in 25-REVIEW.md
- termination_loop_n calibration via hill-climb produces int cast of 0 for all floats — CR-03 from review; needs integer grid sweep before Phase 27 calibration run
- stale_context and step_repetition scores stored on 0–100 scale (fuzz output) vs 0–1 for all other metrics — WR-01 from review; cosmetic for now

### Open Blockers

- CR-01/CR-02 from 24-REVIEW.md: calibrate.py context_overflow calibration path needs fix before Phase 27 calibration run
- CR-03 from 25-REVIEW.md: termination_loop_n must use integer grid sweep [2,3,4,5] in hill_climb before Phase 27 calibration run
- CR-02 from 25-REVIEW.md: patch_docker_compose missing 6 new Phase 25 env vars — fix before Phase 27

## Session Continuity

Last session: 2026-05-24T12:00:00.000Z
Stopped at: Phase 25 complete — SemanticSpanAnalyzer (CTX-04) + TraceAnalyzer (CTX-02, TRACE-01–04) implemented, wired, verified 13/13
Next: Plan Phase 26 — /gsd:plan-phase 26
