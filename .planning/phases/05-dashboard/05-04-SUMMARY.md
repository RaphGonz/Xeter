---
phase: 05-dashboard
plan: "04"
subsystem: ui
tags: [next.js, react, shadcn, typescript, sheet, tabs, badge]

# Dependency graph
requires:
  - phase: 05-03
    provides: SpanTable onSpanClick callback, api.ts listSpans/getSpanDetail/diagnose stubs
  - phase: 04-03
    provides: GET /spans/{id} endpoint, POST /diagnose endpoint (501 scaffold)
provides:
  - SpanDetailPanel component: slide-in Sheet with flags, scores, metadata, payload tabs
  - PayloadTabs component: Prompt/Response/Raw Response tabbed display
  - api.ts: SpanDetail, SpanDetailFlag, SpanScore, DiagnoseResponse typed interfaces
  - spans/page.tsx: selectedSpanId state + SpanDetailPanel wired to row clicks
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Sheet side="right" with onOpenChange callback for controlled open/close
    - useEffect on [spanId, open] triggers detail fetch when panel opens
    - 401 in detail panel: clearToken() + router.replace('/login')
    - Diagnostic button: enabled only for flagged status; disabled with message for clean/pending
    - FlagSection is sub-component to isolate diagnose loading state

key-files:
  created:
    - services/view/src/components/SpanDetailPanel.tsx
    - services/view/src/components/PayloadTabs.tsx
  modified:
    - services/view/src/lib/api.ts
    - services/view/src/app/spans/page.tsx

key-decisions:
  - "FlagSection isolated as sub-component — keeps diagnose loading state separate from panel loading state"
  - "SpanDetailPanel uses Sheet's onOpenChange for close — single source of truth for open state"
  - "api.ts getSpanDetail and diagnose given proper TypeScript return types (SpanDetail, DiagnoseResponse) — type-safe API layer"

patterns-established:
  - "Detail panel fetch: useEffect on [spanId, open] — triggers on any spanId change when panel is open"
  - "Disabled diagnostic button shown for non-flagged spans with explanatory text — UX clarity over hiding"

requirements-completed:
  - DASH-01

# Metrics
duration: ~15min
completed: 2026-03-31
---

# Phase 5 Plan 04: Span Detail Panel Summary

**Slide-in span detail panel using shadcn Sheet with flag section, diagnostic button, scores table, metadata grid, and S3 payload tabs**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-31
- **Completed:** 2026-03-31
- **Tasks:** 2 auto completed (Task 3 is checkpoint:human-verify — pending)
- **Files modified:** 4

## Accomplishments

- PayloadTabs: three-tab display (Prompt / Response / Raw Response) using shadcn Tabs; null content shows "No content available" placeholder
- SpanDetailPanel: controlled Sheet (side="right") that fetches span detail on open via getSpanDetail()
- Flag section: only shown for `status === "flagged"` — displays destructive Badge (flag_type), score, detail JSON block
- Request Diagnostic button: enabled only for flagged spans; disabled with explanatory message for clean/pending
- Diagnostic result displayed inline as grey info box; errors shown in red
- Scores section: per-analyzer score table (analyzer_name / metric_name / score)
- Metadata section: definition-list-style key-value display of all span fields; tool_arguments pretty-printed if valid JSON
- 401 error in panel triggers clearToken() + router.replace('/login')
- api.ts updated with SpanDetail, SpanDetailFlag, SpanScore, DiagnoseResponse typed interfaces
- spans/page.tsx wired: selectedSpanId state, handleSpanClick sets id, SpanDetailPanel rendered at page root

## Task Commits

Each task was committed atomically:

1. **Task 1: SpanDetailPanel + PayloadTabs + typed api interfaces** - `ee6fbc9` (feat)
2. **Task 2: Wire SpanDetailPanel into spans page** - `e87c1dc` (feat)

**Plan metadata:** (docs commit — follows human verify)

## Files Created/Modified

- `services/view/src/components/SpanDetailPanel.tsx` - Slide-in detail panel with flags, scores, metadata, payloads
- `services/view/src/components/PayloadTabs.tsx` - Tabbed payload display (Prompt/Response/Raw Response)
- `services/view/src/lib/api.ts` - Added SpanDetail, SpanDetailFlag, SpanScore, DiagnoseResponse types; typed getSpanDetail + diagnose
- `services/view/src/app/spans/page.tsx` - selectedSpanId state, handleSpanClick, SpanDetailPanel rendered

## Decisions Made

- FlagSection isolated as sub-component to keep diagnose loading state separate from panel-level loading state
- Sheet's `onOpenChange` used for close handling — single source of truth for open/closed state
- api.ts `getSpanDetail` and `diagnose` given proper TypeScript return types for type-safe API layer

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. TypeScript compiles clean, full Next.js build succeeds, 27 presenter tests pass.

## User Setup Required

None — no external service configuration required beyond existing docker-compose stack.

## Next Phase Readiness

- Task 3 (checkpoint:human-verify) pending — stack must be running for end-to-end verification
- After human verify passes, Phase 5 is complete — Phase 6 (calibration) can begin

## Self-Check: PASSED

- services/view/src/components/SpanDetailPanel.tsx: FOUND
- services/view/src/components/PayloadTabs.tsx: FOUND
- .planning/phases/05-dashboard/05-04-SUMMARY.md: FOUND
- Commit ee6fbc9 (Task 1): FOUND
- Commit e87c1dc (Task 2): FOUND

---
*Phase: 05-dashboard*
*Completed: 2026-03-31*
