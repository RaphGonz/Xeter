---
phase: 05-dashboard
plan: "03"
subsystem: ui
tags: [next.js, react, nuqs, shadcn, tailwind, typescript, date-fns]

# Dependency graph
requires:
  - phase: 05-02
    provides: Zustand auth store, api.ts with listSpans, NuqsAdapter in providers.tsx, shadcn table/skeleton/dropdown-menu
  - phase: 05-01
    provides: GET /spans with flag_type, agent_name, from_time, to_time, cursor filter support
provides:
  - useSpanFilters hook: nuqs-based URL state for flag_type, agent_name, time_range
  - StatusDot component: color-coded status indicator for flagged/clean/pending
  - FilterBar component: three-dropdown filter bar (flag type, agent, time range)
  - SpanTable component: dense table with Status, Agent/Span ID, Score, Time columns
  - spans/page.tsx: complete span list page with filters, pagination, skeleton loading, 401 redirect
  - api.ts: timeRangeToISO helper, typed SpanListItem/SpanListResponse interfaces, cursor param in listSpans
affects: [05-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - nuqs URL state: useQueryState with parseAsString.withDefault for filter values — all filters bookmarkable
    - Agent name list derived from fetched spans (unique agent_names) — no separate /agents endpoint needed
    - Cursor pagination: nextCursor state, Load More button appends to existing spans array
    - 401 handler pattern: catch HTTP 401, clearToken(), router.replace('/login')

key-files:
  created:
    - services/view/src/hooks/useSpanFilters.ts
    - services/view/src/components/StatusDot.tsx
    - services/view/src/components/FilterBar.tsx
    - services/view/src/components/SpanTable.tsx
  modified:
    - services/view/src/app/spans/page.tsx
    - services/view/src/lib/api.ts

key-decisions:
  - "timeRangeToISO converts preset label at call time — URL stores relative label (e.g., '1h'), not absolute ISO, so links remain accurate when reopened later"
  - "Agent name dropdown populated from unique agent_names in fetched spans — avoids needing a /agents API endpoint"
  - "DropdownMenuGroup + DropdownMenuLabel used in FilterBar — wrapping required for Base UI MenuGroupRootContext"

patterns-established:
  - "URL filter state: useSpanFilters wraps nuqs useQueryState — all filter changes are reflected in URL immediately"
  - "Span list pagination: append-on-load-more pattern (not page replacement)"

requirements-completed:
  - DASH-01
  - DASH-02

# Metrics
duration: ~8min
completed: 2026-03-30
---

# Phase 5 Plan 03: Span List Page Summary

**Dense span table at /spans with nuqs URL-state filters (flag type, agent, time range), status dots, relative timestamps, and cursor-based pagination**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-30
- **Completed:** 2026-03-30
- **Tasks:** 2 auto completed (Task 3 is checkpoint:human-verify — pending)
- **Files modified:** 6

## Accomplishments
- useSpanFilters hook: nuqs useQueryState for flag_type, agent_name, time_range — all URL-serialized
- StatusDot: red/green/grey dot + label for flagged/clean/pending with flag_type in parentheses
- FilterBar: three DropdownMenu dropdowns with DropdownMenuGroup/Label wrapping (required by Base UI)
- SpanTable: shadcn Table with Status (StatusDot), Agent+SpanID (stacked), Score (highest flag score), Time (date-fns relative)
- spans/page.tsx: filter-aware fetch with useEffect, cursor pagination, skeleton loading rows, inline error, 401 redirect
- api.ts: timeRangeToISO preset-to-ISO converter, typed SpanListItem/SpanListResponse, cursor param

## Task Commits

Each task was committed atomically:

1. **Task 1: Filter hook + StatusDot + FilterBar** - `5fa9b62` (feat)
2. **Task 2: SpanTable + Span list page with pagination** - `3ae1c3f` (feat)

**Plan metadata:** (docs commit — follows human verify)

## Files Created/Modified
- `services/view/src/hooks/useSpanFilters.ts` - nuqs-based URL state hook for three filter dimensions
- `services/view/src/components/StatusDot.tsx` - Color dot + label component (flagged/clean/pending)
- `services/view/src/components/FilterBar.tsx` - Three-dropdown filter bar using shadcn DropdownMenu
- `services/view/src/components/SpanTable.tsx` - Dense span table with relative timestamps via date-fns
- `services/view/src/app/spans/page.tsx` - Span list page: filters, table, pagination, loading/error states
- `services/view/src/lib/api.ts` - Added timeRangeToISO, typed interfaces, cursor param in listSpans

## Decisions Made
- `timeRangeToISO` converts the preset label at call time: URL stores `'1h'` not an ISO timestamp, so bookmarked links remain accurate when opened later
- Agent name dropdown populated from unique `agent_names` in the fetched span list — no `/agents` endpoint needed
- `DropdownMenuGroup` + `DropdownMenuLabel` used in FilterBar as wrappers — Base UI requires the group context for labels

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required beyond existing docker-compose stack.

## Next Phase Readiness
- Task 3 (checkpoint:human-verify) still pending — stack must be running for end-to-end verification
- After human verify passes, Plan 04 (span detail panel + diagnose) can begin
- useHydrateAuth pattern used correctly in page.tsx — no SSR issues expected

---
*Phase: 05-dashboard*
*Completed: 2026-03-30*
