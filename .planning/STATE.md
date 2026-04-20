---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Analyser Accuracy
status: complete
last_updated: "2026-04-20"
progress:
  total_phases: 10
  completed_phases: 10
  total_plans: 31
  completed_plans: 31
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-20)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Between milestones — v1.1 shipped 2026-04-18, ready for v1.2 planning

## Current Position

v1.1 Analyser Accuracy: COMPLETE
- Phase 7: wrong_args Rewrite — 5/5 plans ✓
- Phase 8: wrong_tool Rewrite — 3/3 plans ✓
- Phase 9: no_tool_used + wrong_tool_choice — 1/1 plan ✓
- Phase 10: unnecessary_tool_call — 1/1 plan ✓

Full-suite mean precision ≥ 95%. All 4 analyzer methods rewritten and calibrated.

## Accumulated Context

### Decisions

All decisions logged in PROJECT.md Key Decisions table.

Key v1.1 decisions:
- Three-branch `_check_wrong_tool`: no_available_tools immediate flag, Case B better tool, Case C no appropriate tool
- Threshold key `wrong_tool` renamed to `wrong_tool_called`
- `tool_use_violation` windowed proximity deferred — `no_tool_used` covers the priority case
- Social centroid chosen for `unnecessary_tool_call` over necessity-delta (simpler, P=1.0)
- Hybrid scoring (50/50 cosine+BOW) as shared utility in `base.py`

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-20 — v1.1 milestone completed and archived.
Next: `/gsd:new-milestone` to define v1.2.
