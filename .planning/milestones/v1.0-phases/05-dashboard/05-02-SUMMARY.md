---
phase: 05-dashboard
plan: "02"
subsystem: ui
tags: [next.js, react, zustand, shadcn, tailwind, typescript, docker]

# Dependency graph
requires:
  - phase: 04-read-path
    provides: POST /login and GET /spans endpoints on presenter service
  - phase: 05-01
    provides: Extended GET /spans with flag_type, agent_name, from_time, to_time filters
provides:
  - Next.js 15 App Router scaffold replacing Phase 1 static stub
  - Login page at /login with form validation and inline error display
  - Zustand auth store with SSR-safe sessionStorage hydration
  - API client (api.ts) with login, listSpans, getSpanDetail, diagnose functions
  - NavBar component with account dropdown and logout
  - /spans authenticated layout with token guard
  - API proxy via next.config.ts rewrites to presenter:8000
  - Updated docker-compose.yml view service with hot-reload volumes
  - CLICKHOUSE_PASSWORD injected to all services in docker-compose.yml
  - sentence-transformers isolated to xeter[ml] optional dependency
affects: [05-03, 05-04]

# Tech tracking
tech-stack:
  added:
    - next.js 15 (App Router)
    - zustand (auth state)
    - nuqs (URL state, for Plans 03+)
    - shadcn/ui (button, card, input, label, dropdown-menu, badge, sheet, tabs, separator, table, skeleton)
    - date-fns
  patterns:
    - SSR-safe auth: token initializes as null, useHydrateAuth hook reads sessionStorage in useEffect
    - Authenticated layout pattern: SpansLayout checks hydrated+token before rendering
    - API proxy via next.config.ts rewrites — all /api/* calls route to presenter without CORS issues
    - xeter[ml] optional dep — ML-heavy packages isolated from non-ML service images

key-files:
  created:
    - services/view/src/lib/auth.ts
    - services/view/src/lib/api.ts
    - services/view/src/lib/utils.ts
    - services/view/src/providers.tsx
    - services/view/src/app/layout.tsx
    - services/view/src/app/page.tsx
    - services/view/src/app/login/page.tsx
    - services/view/src/app/spans/layout.tsx
    - services/view/src/app/spans/page.tsx
    - services/view/src/components/NavBar.tsx
    - services/view/next.config.ts
    - services/view/tsconfig.json
    - services/view/tailwind.config.ts
    - services/view/package.json
    - services/view/Dockerfile
  modified:
    - deploy/docker-compose.yml
    - xeter/pyproject.toml
    - services/worker/Dockerfile
    - services/presenter/Dockerfile

key-decisions:
  - "Auth store initializes token as null and hydrates via useEffect (useHydrateAuth) to prevent SSR mismatch — server renders with null token, client hydrates from sessionStorage"
  - "NavBar uses DropdownMenu without DropdownMenuLabel/Group — those components trigger Base UI MenuGroupRootContext error in this shadcn build"
  - "CLICKHOUSE_PASSWORD added to all four app services in docker-compose.yml — ClickHouse 25.3 enforces auth even for default user"
  - "sentence-transformers moved to xeter[ml] optional dep — prevents CUDA/torch/transformers from being installed in presenter, diagnosticer, analyser images"
  - "worker Dockerfile installs xeter[ml] to get sentence-transformers with model pre-baked"

patterns-established:
  - "SSR hydration gate: all auth-dependent components wait for hydrated==true before redirecting or rendering"
  - "Authenticated layout: SpansLayout wraps all /spans/* routes, checks token after hydration, renders null during hydration to avoid flash"
  - "API client throws on non-OK responses — callers catch for user-facing error messages"

requirements-completed:
  - AUTH-02

# Metrics
duration: ~45min (including human verification + post-checkpoint fixes)
completed: 2026-03-30
---

# Phase 5 Plan 02: Next.js 15 Login + Auth Infrastructure Summary

**Next.js 15 App Router scaffold with Zustand SSR-safe auth store, login page, API proxy to presenter, and NavBar — replacing the Phase 1 static stub**

## Performance

- **Duration:** ~45 min (including human verification loop)
- **Started:** 2026-03-30
- **Completed:** 2026-03-30
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 19

## Accomplishments
- Next.js 15 App Router app scaffolded at services/view/ with shadcn/ui, Zustand, Tailwind, nuqs — replaces the Phase 1 static serve stub
- Login page at /login: centered card form, inline error on bad credentials, redirect to /spans on success
- SSR-safe auth: Zustand store initializes token as null, useHydrateAuth hook reads sessionStorage in useEffect to eliminate hydration mismatch
- Authenticated layout for /spans/*: guards with hydrated+token check before rendering children or NavBar
- docker-compose.yml fixed: CLICKHOUSE_PASSWORD added to all services, sentence-transformers isolated to xeter[ml]

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold Next.js 15 + auth infrastructure** - `d25b437` (feat)
2. **Task 2: Login page + NavBar** - `aaa2f78` (feat)
3. **Post-checkpoint fix: SSR hydration and NavBar context** - `33b136f` (fix)
4. **Post-checkpoint fix: CLICKHOUSE_PASSWORD + ML dep isolation** - `be0d441` (fix)

**Plan metadata:** (docs commit — follows this summary)

## Files Created/Modified
- `services/view/src/lib/auth.ts` - Zustand store with useHydrateAuth hook for SSR-safe token hydration
- `services/view/src/lib/api.ts` - Typed API client: login, listSpans, getSpanDetail, diagnose
- `services/view/src/app/login/page.tsx` - Login form with validation, loading state, inline error
- `services/view/src/app/spans/layout.tsx` - Authenticated layout: guards with token, renders NavBar
- `services/view/src/components/NavBar.tsx` - Top nav with Xeter branding and account/logout dropdown
- `services/view/next.config.ts` - API proxy rewrites /api/* to presenter:8000
- `services/view/Dockerfile` - Node 20-alpine dev server replacing serve stub
- `deploy/docker-compose.yml` - Added CLICKHOUSE_PASSWORD to all services, view service with hot-reload
- `xeter/pyproject.toml` - sentence-transformers moved to [ml] optional dependency
- `services/worker/Dockerfile` - Install xeter[ml] to include sentence-transformers

## Decisions Made
- Auth store initializes token as null and hydrates via useEffect to prevent SSR mismatch — server renders with null token, client hydrates from sessionStorage on mount
- NavBar DropdownMenuLabel/Group removed — those components trigger Base UI MenuGroupRootContext error in this build
- CLICKHOUSE_PASSWORD added to all four app services — ClickHouse 25.3 enforces auth even for the default user
- sentence-transformers isolated to xeter[ml] optional dep — avoids pulling CUDA/torch into non-ML service images

## Deviations from Plan

### Auto-fixed Issues (applied post-checkpoint during human verification)

**1. [Rule 1 - Bug] SSR hydration mismatch in auth store**
- **Found during:** Task 3 (human verify — DropdownMenu threw hydration error in browser console)
- **Issue:** Auth store initialized token from sessionStorage during module load; server rendered with token=null but client rendered with token=string, causing React hydration mismatch
- **Fix:** Store initializes as `token: null`, added `hydrated: boolean` field and `useHydrateAuth()` hook that calls `hydrate()` in useEffect. All components wait for `hydrated==true` before redirecting.
- **Files modified:** `services/view/src/lib/auth.ts`, `services/view/src/app/login/page.tsx`, `services/view/src/app/spans/layout.tsx`, `services/view/src/app/page.tsx`
- **Committed in:** `33b136f`

**2. [Rule 1 - Bug] NavBar DropdownMenuLabel/Group caused Base UI MenuGroupRootContext error**
- **Found during:** Task 3 (human verify — console error on /spans page)
- **Issue:** DropdownMenuLabel and DropdownMenuGroup require a context that wasn't initialized, crashing the dropdown
- **Fix:** Removed those wrapper components; kept only DropdownMenuItem for Logout inside DropdownMenuContent
- **Files modified:** `services/view/src/components/NavBar.tsx`
- **Committed in:** `33b136f`

**3. [Rule 1 - Bug] CLICKHOUSE_PASSWORD missing from docker-compose services**
- **Found during:** Task 3 (human verify — services failed to start, ClickHouse auth error in logs)
- **Issue:** analyser, worker, diagnosticer services had no CLICKHOUSE_PASSWORD env var; ClickHouse 25.3 rejects connections from unauthenticated default user
- **Fix:** Added `CLICKHOUSE_PASSWORD: xeter_dev_password` to analyser, worker, diagnosticer environment blocks in docker-compose.yml
- **Files modified:** `deploy/docker-compose.yml`
- **Committed in:** `be0d441`

**4. [Rule 2 - Missing Critical] sentence-transformers bloating non-ML service images**
- **Found during:** Task 3 (human verify — presenter/diagnosticer image builds pulling CUDA deps)
- **Issue:** sentence-transformers was a top-level dependency, installed in all service images despite only being needed by worker
- **Fix:** Moved to `[project.optional-dependencies] ml` section; worker Dockerfile now installs `xeter[ml]`
- **Files modified:** `xeter/pyproject.toml`, `services/worker/Dockerfile`
- **Committed in:** `be0d441`

---

**Total deviations:** 4 auto-fixed (2 bugs, 1 bug, 1 missing critical)
**Impact on plan:** All fixes required for correct operation. No scope creep.

## Issues Encountered
- React hydration errors required a rethink of the auth store initialization pattern — the SSR-safe hydration hook is now the established pattern for all auth-gated components in Plans 03+

## User Setup Required
None - no external service configuration required beyond existing docker-compose stack.

## Next Phase Readiness
- Login flow verified end-to-end: form renders, errors display, valid login redirects to /spans, logout works
- Auth store + API client ready for Plans 03 (spans list) and 04 (span detail/diagnose)
- useHydrateAuth pattern established — Plans 03/04 must use it for any component reading useAuthStore
- CLICKHOUSE_PASSWORD now correctly set in all services — docker-compose stack starts cleanly

---
*Phase: 05-dashboard*
*Completed: 2026-03-30*
