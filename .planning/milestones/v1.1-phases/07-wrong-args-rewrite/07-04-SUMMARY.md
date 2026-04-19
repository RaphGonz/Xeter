---
phase: 07-wrong-args-rewrite
plan: "04"
subsystem: worker
tags: [yaml, detection-patterns, negation-detection, bow, wrong-args]

requires:
  - phase: 07-wrong-args-rewrite
    provides: Phase 9 planning context (NOTOOL-03, NOTOOL-04, NOTOOL-06)

provides:
  - "detection_patterns.yml schema file — external YAML editable without rebuild (NOTOOL-04)"
  - "Hybrid detection design approved: static list + dynamic tool-name BOW (NOTOOL-06)"

affects:
  - 07-wrong-args-rewrite Phase 9 (_check_tool_use_violation implementation)

tech-stack:
  added: []
  patterns:
    - "Hybrid detection: static keyword list as fallback + dynamic BOW on actual tool name tokens"
    - "External YAML for detection patterns (yaml.safe_load at init, no code rebuild needed)"

key-files:
  created:
    - xeter/services/worker/detection_patterns.yml
  modified: []

key-decisions:
  - "Hybrid approach: tool_triggering_terms is static fallback only; Phase 9 must also tokenise the actual span tool name (split on _, -, camelCase) and check BOW intersection against negation window"
  - "Two stages OR-combined: static-list hit OR dynamic BOW hit is sufficient to flag negation-of-tool-use"
  - "No embeddings for Phase 9 — pure token set intersection (stdlib only)"

patterns-established:
  - "Hybrid static+dynamic detection: static YAML list + runtime token extraction against span data"

requirements-completed: []

duration: 10min
completed: 2026-04-06
---

# Phase 07 Plan 04: detection_patterns.yml Schema Summary

**External YAML detection schema approved with hybrid design: static tool_triggering_terms fallback plus dynamic tool-name BOW tokenisation for Phase 9 negation detection**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-06
- **Completed:** 2026-04-06
- **Tasks:** 2 (Task 1 auto, Task 2 checkpoint)
- **Files modified:** 1

## Accomplishments

- Created xeter/services/worker/detection_patterns.yml with 10 negation_motifs and 12 tool_triggering_terms
- Obtained user approval for the schema (NOTOOL-06 resolved)
- Documented the hybrid detection design in the YAML file: static list (Stage 1) plus dynamic tool-name BOW matching (Stage 2)
- Design decision recorded: Phase 9 must tokenise the actual span tool name and check token set intersection against the negation window; no embeddings needed

## Task Commits

1. **Task 1: Create detection_patterns.yml draft** - `5f8f8b6` (chore)
2. **Task 2: Document hybrid detection approach** - `c06e0fe` (docs)

## Files Created/Modified

- `xeter/services/worker/detection_patterns.yml` - External detection pattern schema for Phase 9; documents hybrid static + BOW approach in inline comments

## Decisions Made

User approved the base schema and specified a design change for Phase 9:

- `tool_triggering_terms` is a static fallback list only
- Phase 9 must ALSO implement dynamic tool-name BOW matching: tokenise the actual tool name from the span (split on `_`, `-`, camelCase) and check whether any token appears within the negation window in the prompt
- Example: tool "planX" → tokens {"plan", "x"}; prompt "Don't plan anything" → "plan" is in negation window → match
- The two stages are OR-combined: either hit is sufficient to flag a violation
- No embeddings required — pure stdlib set intersection

## Deviations from Plan

None — plan executed as written. The user feedback at the checkpoint was incorporated into YAML inline comments as specified in the resume instructions.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- NOTOOL-06 blocker is resolved: schema reviewed and approved before Phase 9 implementation
- Phase 9 (_check_tool_use_violation rewrite) can proceed; detection_patterns.yml is the source of truth for both the static list and the documented BOW approach
- Phase 9 implementor must read the Stage 1 / Stage 2 comments in the YAML file before coding

---
*Phase: 07-wrong-args-rewrite*
*Completed: 2026-04-06*
