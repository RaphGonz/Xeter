---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Analyser Accuracy
status: unknown
last_updated: "2026-04-07T18:56:23.599Z"
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 29
  completed_plans: 27
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-06)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.1 — Phase 8: wrong_tool Rewrite (Phase 7 complete)

## Current Position

Phase: 8 of 10 (wrong_tool Rewrite)
Plan: 1 of 3 (08-01 complete — _check_wrong_tool rewritten, wrong_tool_called key rename done)
Status: Phase 8 in progress
Last activity: 2026-04-07 — Plan 08-01 complete: three-branch wrong_tool logic, wrong_tool_called rename across 6 files, 4 new tests, 36 worker tests pass

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
| Phase 08-wrong-tool-rewrite P01 | 12min | 2 tasks | 6 files |

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
- [Phase 08-wrong-tool-rewrite]: Three-branch _check_wrong_tool: no_available_tools immediate flag (WTOOL-03), Case B better tool, Case C no appropriate tool — replaces inverted AND gate
- [Phase 08-wrong-tool-rewrite]: Threshold key wrong_tool renamed to wrong_tool_called; env var WORKER_THRESHOLD_WRONG_TOOL -> WORKER_THRESHOLD_WRONG_TOOL_CALLED

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-07
Stopped at: Completed 08-01-PLAN.md (wrong_tool rewrite — three-branch logic, wrong_tool_called key rename, 4 new tests, 36 worker tests pass)
Resume file: None
