---
phase: 21-trace-ui
plan: "02"
subsystem: ui
tags: [react, nextjs, typescript, spantree, collapsible-tree, trace-detail]

# Dependency graph
requires:
  - phase: 21-trace-ui/21-01
    provides: TraceDetailResponse types, getTraceDetail(), SpanInTrace, TraceFlagItem, TraceObject, /traces layout with NavBar + auth guard
  - phase: spans-ui
    provides: SpanDetailPanel component (reused for span drill-down from trace detail)

provides:
  - SpanTree component — collapsible VS Code-style parent/child tree built from parent_span_id links
  - /traces/[trace_id] page — fetches trace detail, renders SpanTree + SpanDetailPanel, shows trace metadata header

affects: [21-trace-ui, trace-read-path, ui-navigation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "use(params) to unwrap Promise<params> in client components (Next.js 16)"
    - "Recursive TreeNode pattern for parent/child span rendering"
    - "Orphaned spans (missing parent in payload) treated as roots via byId Map validation"
    - "Collapsed Set<string> state — empty on mount means all spans expanded by default"
    - "Chevron click stops propagation so row click (open panel) doesn't fire simultaneously"

key-files:
  created:
    - services/view/src/components/SpanTree.tsx
    - services/view/src/app/traces/[trace_id]/page.tsx
  modified: []

key-decisions:
  - "use(params) unwraps Promise<params> in client components per Next.js 16 docs — confirmed correct for this version"
  - "Orphaned spans (parent_span_id points to non-existent span) resolved to null bucket and treated as roots"
  - "Flag badge hidden at count=0 (consistent with 21-01 em-dash pattern for tables; pill only appears when flags exist)"

patterns-established:
  - "SpanTree: buildTree with Map<string|null, SpanInTrace[]> bucketing pattern for O(n) tree construction"
  - "Trace detail pages use TracesLayout (layout.tsx) for NavBar + auth; no nested layout at [trace_id] level"

requirements-completed: [UI-02]

# Metrics
duration: 15min
completed: 2026-05-15
---

# Phase 21 Plan 02: Trace Detail Page Summary

**Collapsible span hierarchy tree at /traces/[trace_id] with VS Code sidebar-style chevron toggling, flag badges, and SpanDetailPanel drill-down**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-15T00:00:00Z
- **Completed:** 2026-05-15T00:15:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- SpanTree component builds parent/child tree from parent_span_id links in O(n); orphaned spans gracefully treated as roots
- All spans expanded by default on mount; chevron toggle collapses/expands subtrees with event propagation stopped
- /traces/[trace_id] page shows trace metadata header (start_time, duration, span count, trace-level flag badge) and renders SpanTree with SpanDetailPanel integration
- Error state renders for 404 and network failures with red alert box

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SpanTree component** - `31425a8` (feat)
2. **Task 2: Create /traces/[trace_id] detail page** - `1f77fc9` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `services/view/src/components/SpanTree.tsx` — Collapsible tree component; buildTree, SpanRow, formatDuration; exports SpanTree
- `services/view/src/app/traces/[trace_id]/page.tsx` — Trace detail page; fetches getTraceDetail, renders SpanTree + SpanDetailPanel, trace metadata header, error state

## Decisions Made

- `use(params)` unwraps `Promise<params>` in client components per Next.js 16 docs — confirmed correct for this version
- Orphaned spans (parent_span_id points to non-existent span_id) resolved to null bucket and treated as roots; no crash
- Flag badge hidden at count=0 (consistent with plan spec; pill only appears when flags exist)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- UI-02 satisfied: operators can see full span hierarchy for a trace, toggle subtrees, and navigate to span details
- /traces/[trace_id] page live under TracesLayout (auth guard + NavBar from 21-01)
- Phase 21 complete — both trace list (21-01) and trace detail (21-02) are shipped

---
*Phase: 21-trace-ui*
*Completed: 2026-05-15*
