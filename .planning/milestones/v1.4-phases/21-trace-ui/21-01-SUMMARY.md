---
phase: 21-trace-ui
plan: "01"
subsystem: ui
tags: [nextjs, react, typescript, shadcn-ui, traces, api-client]

# Dependency graph
requires:
  - phase: 20-trace-api
    provides: GET /traces and GET /traces/{trace_id} API endpoints with TraceListResponse and TraceDetailResponse shapes
provides:
  - TraceListItem, TraceDetailResponse, SpanInTrace, TraceFlagItem, TraceObject types in api.ts
  - listTraces() and getTraceDetail() API client functions
  - TraceTable component with 5 columns (trace_id truncated, span_count, flag_count, start_time, duration)
  - /traces route with auth-guarded layout and trace list page
  - NavBar updated with Spans and Traces navigation links
affects: [22-trace-detail-ui, any phase extending trace navigation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Auth-guarded layout pattern (mirrors spans/layout.tsx) — useHydrateAuth + useAuthStore hydration gate + useEffect redirect
    - TraceTable component mirrors SpanTable shadcn/ui Table style (cursor-pointer hover row, truncated ID with tooltip)

key-files:
  created:
    - services/view/src/components/TraceTable.tsx
    - services/view/src/app/traces/layout.tsx
    - services/view/src/app/traces/page.tsx
  modified:
    - services/view/src/lib/api.ts
    - services/view/src/components/NavBar.tsx

key-decisions:
  - "trace_id displayed as 8-char truncation with full ID in title tooltip (not 20-char like span_id)"
  - "NavBar now has explicit Spans link (href=/spans) in addition to new Traces link — brand link Xeter still goes to /spans"
  - "duration formatted as Xs or Xms depending on >= 1 second threshold"
  - "flag_count=0 renders em-dash (—) instead of 0 badge for visual clarity"

patterns-established:
  - "TracesLayout: exact copy of SpansLayout — auth guard via hydration + useEffect redirect; returns null until hydrated+token"
  - "TracesPage: useEffect-based fetch with 401 clearToken+redirect, loading skeleton, empty state, error message"

requirements-completed: [UI-01]

# Metrics
duration: 15min
completed: 2026-05-15
---

# Phase 21 Plan 01: Traces List UI Summary

**Traces list page with NavBar nav links, auth-guarded layout, and TraceTable component backed by new api.ts listTraces/getTraceDetail client functions**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-15T00:00:00Z
- **Completed:** 2026-05-15T00:15:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Extended api.ts with 7 new TypeScript interfaces (TraceFlagItem, ScoreItem, SpanInTrace, TraceObject, TraceDetailResponse, TraceListItem, TraceListResponse) and 2 API functions (listTraces, getTraceDetail) — zero TS errors
- Created /traces route with auth-guarded layout mirroring spans/layout.tsx and a full list page (loading skeletons, empty state, error handling, 401 auto-redirect)
- Added Spans and Traces navigation links to NavBar; nav order: Xeter brand | Spans | Traces | Docs

## Task Commits

Each task was committed atomically:

1. **Task 1: Add trace types and API functions to api.ts** - `e637b4e` (feat)
2. **Task 2: Add Spans and Traces nav links to NavBar** - `efa8047` (feat)
3. **Task 3: Create TraceTable component and /traces page + layout** - `6c9a58f` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `services/view/src/lib/api.ts` - Added 7 trace interfaces + listTraces() + getTraceDetail()
- `services/view/src/components/NavBar.tsx` - Added Spans and Traces nav links
- `services/view/src/components/TraceTable.tsx` - New — shadcn/ui Table with 5 columns, row click navigates to /traces/{trace_id}
- `services/view/src/app/traces/layout.tsx` - New — auth-guarded layout with NavBar
- `services/view/src/app/traces/page.tsx` - New — fetches listTraces(), renders TraceTable + empty state + loading state

## Decisions Made
- trace_id displayed as 8-char truncation (not 20-char like span_id in SpanTable) to fit narrower Trace ID column
- NavBar now has explicit Spans and Traces links — brand "Xeter" link still points to /spans as before
- duration >= 1s shows Xs format; < 1s shows Xms format
- flag_count=0 renders em-dash instead of a "0 flags" badge for cleaner visual appearance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- /traces page is live and auth-guarded; operators can navigate from the NavBar to see all traces
- /traces/{trace_id} route directory created; detail page (plan 21-02 or similar) can now be added
- getTraceDetail() is exported and ready for use by the trace detail page

---
*Phase: 21-trace-ui*
*Completed: 2026-05-15*
