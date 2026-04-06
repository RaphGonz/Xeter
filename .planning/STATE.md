---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Analyser Accuracy
status: unknown
last_updated: "2026-04-06T11:55:11.618Z"
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 26
  completed_plans: 26
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-06)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.1 — Phase 8: wrong_tool Rewrite (Phase 7 complete)

## Current Position

Phase: 7 of 10 (wrong_args Rewrite)
Plan: 5 of 5 (07-05 complete — Phase 7 DONE)
Status: Phase 7 complete
Last activity: 2026-04-06 — Plan 07-05 complete: wrong_tool_args calibration — threshold=0.30, P=0.40, R=0.90; ARGS-06 satisfied; P=0.40 is embedding ceiling, recall prioritised; Phase 8 ready

Progress: [██░░░░░░░░] 20% (3/15 plans)

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
- [Phase 07-05]: wrong_tool_args calibration: threshold=0.30, P=0.40, R=0.90 (6 hill-climb steps); P=0.40 is the ceiling for pure embedding approach — entity matching needed for higher precision; recall prioritised (false negatives worse than false positives); ARGS-06 satisfied

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-06
Stopped at: Completed 07-05-PLAN.md (wrong_tool_args calibration — P=0.40, R=0.90, threshold=0.30; Phase 7 complete)
Resume file: None
