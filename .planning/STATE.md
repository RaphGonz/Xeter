---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Analyser Accuracy
status: unknown
last_updated: "2026-04-06T09:36:35.871Z"
progress:
  total_phases: 7
  completed_phases: 6
  total_plans: 26
  completed_plans: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-06)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.1 — Phase 7: wrong_args Rewrite

## Current Position

Phase: 7 of 10 (wrong_args Rewrite)
Plan: 5 of 5 (07-03 complete)
Status: In progress
Last activity: 2026-04-06 — Plan 07-03 complete: _check_wrong_args two-path rewrite (ARGS-01 through ARGS-05); 26 tests pass

Progress: [█░░░░░░░░░] 7% (1/15 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 0 (v1.1)
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

*Updated after each plan completion*
| Phase 07-wrong-args-rewrite P01 | 14min | 1 tasks | 1 files |
| Phase 07-wrong-args-rewrite P03 | 10min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

All decisions logged in PROJECT.md Key Decisions table.

Recent decisions affecting current work:
- v1.1 start: SBERT cannot encode negation polarity — `_check_tool_use_violation` must use keyword regex only (no cosine)
- v1.1 start: wrong_tool AND gate was inverted — fix is surgical (invert threshold direction, report gap not top_score)
- v1.1 start: wrong_tool_args excluded from P/R calibration removed — rewrite enables re-inclusion once low_confidence flag is gone
- 07-02: HYBRID-01 utility functions placed module-level in base.py; stdlib set ops only, no new deps; default weight=0.5
- 07-04: detection_patterns.yml uses hybrid detection — static tool_triggering_terms list (fallback) + dynamic tool-name BOW matching (tokenise on _, -, camelCase; set intersection with negation window); stages OR-combined; no embeddings needed
- 07-01: Use set() not {} for BINARY_FLAG_TYPES (Python {} is always dict); guard None P/R for binary types in serialization
- [Phase 07-wrong-args-rewrite]: detection_patterns.yml hybrid design: tool_triggering_terms is static fallback; Phase 9 also tokenises actual span tool name (split on _, -, camelCase) and checks BOW set intersection against negation window; stages OR-combined; no embeddings
- [Phase 07-03]: ARGS-05: low_confidence removed from wrong_tool_args flag detail; enables re-inclusion in calibration
- [Phase 07-03]: Two-path _check_wrong_args: error-regex priority (ARGS-01) fires score=1.0 without embedding; semantic path uses hybrid_score on flattened arg values (not raw JSON)

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-06
Stopped at: Completed 07-03-PLAN.md (wrong_args two-path rewrite, 26 tests pass)
Resume file: None
