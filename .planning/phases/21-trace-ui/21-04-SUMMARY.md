---
phase: 21-trace-ui
plan: "04"
subsystem: view
tags: [ui, navigation, search-params, span-deep-link]
dependency_graph:
  requires: [21-03]
  provides: [span-url-deep-link, panel-auto-open-on-nav]
  affects: [services/view/src/components/SpanDetailPanel.tsx, services/view/src/app/traces/[trace_id]/page.tsx]
tech_stack:
  added: []
  patterns: [useSearchParams initialiser pattern, URL-driven panel state]
key_files:
  created: []
  modified:
    - services/view/src/components/SpanDetailPanel.tsx
    - services/view/src/app/traces/[trace_id]/page.tsx
decisions:
  - Span deep-link uses useState(spanFromUrl) initialiser (not useEffect) — synchronous param read makes effect unnecessary
  - No Suspense boundary added — page is already 'use client' with dynamic rendering via use(params), so useSearchParams is safe
  - Direct useState(spanFromUrl) form used (not lazy initialiser) — searchParams is available synchronously at render time
metrics:
  duration: "~8 minutes"
  completed_date: "2026-05-15"
  tasks_completed: 2
  files_modified: 2
requirements_satisfied: [UI-03]
---

# Phase 21 Plan 04: Span URL Deep-Link + Auto-Open Panel Summary

**One-liner:** Wired span_id into breadcrumb URL and initialised selectedSpanId from ?span param to close the UI-03 back-navigation gap.

## What Was Built

Closed the UI-03 gap: when a user views a span in SpanDetailPanel and clicks the breadcrumb trace_id link, the destination trace page now reopens that same span automatically.

Two minimal edits:

1. `SpanDetailPanel.tsx` breadcrumb `href` gains `?span=${detail.span_id}` so the link carries the span identity forward.
2. `TraceDetailPage` reads `useSearchParams().get('span')` and uses it as the `useState` initialiser for `selectedSpanId`, causing SpanDetailPanel to open on mount when the param is present.

Navigation to `/traces/{trace_id}` without a `?span` param continues to work — `spanFromUrl` is `null` and the panel stays closed.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Append span_id to breadcrumb href | 998760c | services/view/src/components/SpanDetailPanel.tsx |
| 2 | Read ?span param and initialise selectedSpanId | 030a308 | services/view/src/app/traces/[trace_id]/page.tsx |

## Verification Results

- `grep "span=\${detail.span_id}" SpanDetailPanel.tsx` — matches line 259
- `grep "spanFromUrl\|useState(spanFromUrl)" page.tsx` — matches lines 22 and 31
- `npx tsc --noEmit` — zero errors
- `stopPropagation`, `onClose`, `SpanDetailPanel` export all preserved

## Decisions Made

- **useState(spanFromUrl) initialiser** — synchronous read from `useSearchParams()` makes a `useEffect` unnecessary. The initialiser is evaluated once on mount and produces the correct open/closed state without a re-render cycle.
- **No Suspense boundary** — the page already uses `use(params)` making it dynamically rendered; Next.js docs confirm `useSearchParams` is safe in this context without an extra Suspense wrapper.
- **No scrollIntoView/ref logic** — auto-open via `open={selectedSpanId !== null}` is sufficient; the Sheet slides in and displays the correct span without manual DOM manipulation.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `services/view/src/components/SpanDetailPanel.tsx` — modified, breadcrumb href contains `?span=${detail.span_id}`
- [x] `services/view/src/app/traces/[trace_id]/page.tsx` — modified, `useSearchParams` imported and `useState(spanFromUrl)` initialiser present
- [x] Task 1 commit `998760c` — verified via git log
- [x] Task 2 commit `030a308` — verified via git log
- [x] TypeScript build: zero errors

## Self-Check: PASSED
