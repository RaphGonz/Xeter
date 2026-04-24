---
phase: 13-frontend-diagnosis-ui
plan: "01"
subsystem: ui
tags: [react, nextjs, typescript, date-fns, tailwind, diagnosis, badges]

# Dependency graph
requires:
  - phase: 12-presenter-integration
    provides: POST /api/diagnose and GET /api/diagnose/{span_id} endpoints with DiagnosisResponse Pydantic model
  - phase: 11-diagnosticer-backend
    provides: DiagnosisService + verdict/severity/affected_field/recommended_fix fields
provides:
  - DiagnosisResponse TypeScript interface mirroring backend Pydantic model
  - getDiagnosis() GET function in api.ts
  - diagnose() POST function in api.ts (flags param removed)
  - DiagnosisCard sub-component with colored verdict/severity badges and MetaRow fields
  - FlagSection with useEffect auto-load on mount, 404 suppressed, always-enabled Diagnose button
affects: [frontend, diagnosis-display, span-detail-panel]

# Tech tracking
tech-stack:
  added: [date-fns formatDistanceToNow (already installed)]
  patterns: [cancelled-flag cleanup pattern for async useEffect, auto-load GET then allow manual POST refresh]

key-files:
  created: []
  modified:
    - services/view/src/lib/api.ts
    - services/view/src/components/SpanDetailPanel.tsx

key-decisions:
  - "getDiagnosis 404 suppressed silently — no prior diagnosis is normal state, not an error"
  - "Diagnose button never disabled — even during loading — enables immediate retry without UX friction"
  - "key={spanId} on FlagSection forces remount and resets state when selected span changes"
  - "DiagnosisCard placed between MetaRow and FlagSection definitions — depends on MetaRow component"
  - "cancelled flag pattern prevents setState after unmount in auto-load useEffect"

patterns-established:
  - "Auto-load pattern: useEffect fires GET on mount, 404 silently ignored, result sets state for display"
  - "DiagnosisCard: verdict+severity as colored Badge pair on one row, fields as MetaRow dl items, relative timestamp at bottom"

requirements-completed: [FRONTEND-UI-01]

# Metrics
duration: 11min
completed: 2026-04-24
---

# Phase 13 Plan 01: Frontend Diagnosis UI Summary

**Diagnosis panel integration: SpanDetailPanel auto-loads prior diagnosis via GET on mount, renders structured DiagnosisCard with colored verdict/severity badges, and POSTs fresh diagnosis on button click without ever disabling the button**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-24T19:30:47Z
- **Completed:** 2026-04-24T19:41:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Replaced `DiagnoseResponse` scaffold with real 7-field `DiagnosisResponse` interface matching backend Pydantic model
- Added `getDiagnosis()` GET function and fixed `diagnose()` POST (removed flags param, sends only `{span_id}`)
- Rewrote FlagSection with useEffect auto-load, cancelled-flag cleanup, 404 suppression, and always-enabled Diagnose button
- Added `DiagnosisCard` sub-component rendering verdict/severity as color-coded Badge components, affected_field and fix as MetaRow items, and relative timestamp via `formatDistanceToNow`

## Task Commits

Each task was committed atomically:

1. **Task 1: Update api.ts — DiagnosisResponse type + getDiagnosis GET + fix diagnose POST** - `aec9912` (feat)
2. **Task 2: Rewrite FlagSection + add DiagnosisCard in SpanDetailPanel.tsx** - `a7a8c94` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `services/view/src/lib/api.ts` — DiagnosisResponse interface, getDiagnosis() GET, diagnose() POST without flags
- `services/view/src/components/SpanDetailPanel.tsx` — DiagnosisCard sub-component, rewritten FlagSection with auto-load useEffect, key={spanId} on FlagSection JSX

## Decisions Made
- `getDiagnosis` 404 response is silently suppressed — a span with no prior diagnosis is the normal initial state, surfacing a 404 error would confuse users
- Diagnose button is never disabled — always enabled allows immediate retry if a diagnosis attempt fails mid-load
- `key={detail.span_id}` on the FlagSection JSX element forces React to unmount/remount the component (resetting all state) when the user navigates to a different span
- `cancelled` flag pattern prevents `setState` calls on an unmounted component if the panel closes before the async GET resolves

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- TypeScript reported errors in SpanDetailPanel.tsx immediately after Task 1 (api.ts changed but component not yet updated) — expected, resolved by Task 2.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 13 Plan 01 complete — v1.2 Diagnosticer milestone frontend integration is done
- Backend (Phases 11-12) + Frontend (Phase 13-01) form a complete diagnosis flow
- No blockers

---
*Phase: 13-frontend-diagnosis-ui*
*Completed: 2026-04-24*
