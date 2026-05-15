---
phase: 21-trace-ui
plan: "03"
subsystem: ui
tags: [nextjs, react, breadcrumb, navigation, next/link]

# Dependency graph
requires:
  - phase: 21-01
    provides: SpanDetailPanel component with SpanDetail type (trace_id always present)
provides:
  - Breadcrumb "Traces › {trace_id[:8]} › {span_id[:8]}" added to SpanDetailPanel above SheetTitle
  - Clickable trace_id segment navigates to /traces/{full trace_id}
affects: [21-trace-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Breadcrumb via next/link Link component with stopPropagation on click inside Sheet drawer"
    - "Always-visible breadcrumb (non-conditional) because trace_id is non-nullable on SpanDetail"

key-files:
  created: []
  modified:
    - services/view/src/components/SpanDetailPanel.tsx

key-decisions:
  - "Breadcrumb is always shown (trace_id is non-nullable on SpanDetail — no conditional needed)"
  - "Old 'trace: {detail.trace_id}' paragraph removed — breadcrumb fully replaces it"
  - "onClick stopPropagation on Link prevents Sheet close when clicking breadcrumb"

patterns-established:
  - "Breadcrumb pattern: nav > span + span(›) + Link + span(›) + span — font-mono text-xs text-zinc-400"

requirements-completed: [UI-03]

# Metrics
duration: 5min
completed: 2026-05-15
---

# Phase 21 Plan 03: Span Detail Breadcrumb Summary

**Breadcrumb "Traces › {trace_id[:8]} › {span_id[:8]}" added to SpanDetailPanel, with clickable trace_id navigating to /traces/{full trace_id}**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-15T12:32:05Z
- **Completed:** 2026-05-15T12:37:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `Link` import from `next/link` to SpanDetailPanel
- Inserted breadcrumb `<nav>` as first element inside the detail content div, above SheetHeader
- Removed old `<p>trace: {detail.trace_id}</p>` paragraph — breadcrumb replaces it
- TypeScript compiles with zero errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Add breadcrumb to SpanDetailPanel** - `6561e8c` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `services/view/src/components/SpanDetailPanel.tsx` - Added Link import, breadcrumb nav above SheetHeader, removed old trace paragraph

## Decisions Made
- Breadcrumb is always shown unconditionally because `trace_id` is non-nullable on `SpanDetail` — no conditional guard needed
- `onClick={(e) => e.stopPropagation()}` on the Link prevents the Sheet drawer from intercepting the click
- Old "trace: {detail.trace_id}" full-ID paragraph removed — the breadcrumb's 8-char truncation replaces it (consistent with list page display)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- UI-03 satisfied: operator can navigate from any span detail view to the parent trace
- SpanDetailPanel breadcrumb is ready for browser verification
- No blockers for remaining phase 21 plans

---
*Phase: 21-trace-ui*
*Completed: 2026-05-15*
