---
phase: 16-auth-hardening
plan: "05"
subsystem: auth
tags: [nextjs, cookies, httponly, zustand, jwt, refresh-token, 401-interceptor]

# Dependency graph
requires:
  - phase: 16-03
    provides: POST /auth/refresh endpoint on Presenter, refresh_token in login response

provides:
  - POST /api/login Route Handler — proxies Presenter, sets xeter_refresh httpOnly cookie, returns only session_token
  - POST /api/auth/refresh Route Handler — reads httpOnly cookie, calls Presenter /auth/refresh
  - Pure in-memory Zustand auth store — zero sessionStorage
  - 401 interceptor in api.ts — transparent token refresh and single retry

affects: [view, frontend, auth, spans-page, login-page]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - httpOnly cookie set by Next.js Route Handler (not Presenter directly — rewrites strip Set-Cookie)
    - 401 interceptor: detect 401, call /api/auth/refresh, update Zustand, retry once
    - cookies() must be awaited in Next.js 15+

key-files:
  created:
    - services/view/src/app/api/login/route.ts
    - services/view/src/app/api/auth/refresh/route.ts
  modified:
    - services/view/src/lib/auth.ts
    - services/view/src/lib/api.ts

key-decisions:
  - "auth.ts hydrate() sets hydrated:true immediately (no storage read) — token comes from API response, eliminating infinite redirect loop on page reload"
  - "401 interceptor retries exactly once — no loop; on failed refresh, clears token and throws HTTP 401"
  - "refresh_token stripped from /api/login response — only session_token returned to browser JS"

patterns-established:
  - "Route Handler cookie pattern: const cookieStore = await cookies() — always awaited"
  - "Token never in sessionStorage — Zustand in-memory only; httpOnly cookie handles persistence"

requirements-completed: [AUTH-02]

# Metrics
duration: 12min
completed: 2026-04-30
---

# Phase 16 Plan 05: Frontend Refresh Token Flow Summary

**httpOnly xeter_refresh cookie + 401 interceptor completing AUTH-02: tokens never XSS-readable, silent re-auth on expiry via Next.js Route Handlers**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-30T07:37:29Z
- **Completed:** 2026-04-30T07:49:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- POST /api/login Route Handler proxies Presenter login, extracts refresh_token into httpOnly cookie (xeter_refresh), returns only session_token to browser
- POST /api/auth/refresh Route Handler reads httpOnly cookie and calls Presenter /auth/refresh — browser JS never touches the refresh token
- sessionStorage fully removed from auth.ts; Zustand store is now pure in-memory with hydrate() as a no-op (sets hydrated:true only)
- request() 401 interceptor in api.ts transparently refreshes the token and retries the original request once

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Route Handlers — /api/login and /api/auth/refresh** - `a6fb992` (feat)
2. **Task 2: Remove sessionStorage from auth.ts + add 401 interceptor to api.ts** - `8dfd1f5` (feat)

**Plan metadata:** committed in docs commit

## Files Created/Modified
- `services/view/src/app/api/login/route.ts` - POST /api/login: sets xeter_refresh httpOnly cookie, returns session_token
- `services/view/src/app/api/auth/refresh/route.ts` - POST /api/auth/refresh: reads cookie, proxies to Presenter /auth/refresh
- `services/view/src/lib/auth.ts` - Pure in-memory Zustand store, zero sessionStorage references
- `services/view/src/lib/api.ts` - Added 401 interceptor with single retry, imports useAuthStore

## Decisions Made
- auth.ts hydrate() sets hydrated:true immediately (no storage read) — token comes from API response, eliminating infinite redirect loop on page reload (see Pitfall 3 in research)
- 401 interceptor retries exactly once to prevent infinite loops; on failed refresh, clears token and throws HTTP 401 so login page redirect fires
- refresh_token is stripped at the Route Handler boundary — only session_token reaches browser JS at any point

## Deviations from Plan

None - plan executed exactly as written. TypeScript compiled without errors. No view test files existed to update.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AUTH-02 complete: full refresh token flow implemented end-to-end (Presenter 16-03 + View 16-05)
- Phase 16 all 5 plans complete — auth hardening milestone finished
- TypeScript compiles clean; no sessionStorage anywhere in view/src

---
*Phase: 16-auth-hardening*
*Completed: 2026-04-30*
