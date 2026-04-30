---
phase: 16-auth-hardening
plan: "03"
subsystem: auth
tags: [jwt, refresh-token, cors, internal-api-key, fastapi, python-jose]

# Dependency graph
requires:
  - phase: 16-01
    provides: create_refresh_token() in deps.py, InternalApiKeyMiddleware on Diagnosticer
provides:
  - POST /auth/refresh endpoint — stateless refresh token verification issuing new session tokens
  - LoginResponse.refresh_token field — login now returns both access and refresh tokens
  - Presenter->Diagnosticer trust boundary — X-Internal-Api-Key + X-Tenant-Id header forwarding
  - CORSMiddleware on Presenter — explicit allow_origins, allow_credentials=True
  - INTERNAL_API_KEY, ENVIRONMENT, CORS_ALLOW_ORIGINS wired in docker-compose and .env.example
affects: [16-04, 16-05, view-service, next-js-route-handlers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stateless refresh token: verify HS256 JWT sub claim, issue new session token — no DB lookup"
    - "Service trust boundary: X-Internal-Api-Key + X-Tenant-Id headers replace Authorization forwarding"
    - "CORS: explicit allow_origins from env var (never wildcard with allow_credentials=True)"
    - "Module-level os.environ[] hard-fail for secrets — KeyError on startup if unset"

key-files:
  created: []
  modified:
    - xeter/services/presenter/routers/auth.py
    - xeter/services/presenter/diagnosis_service.py
    - xeter/services/presenter/main.py
    - xeter/services/presenter/routers/diagnose.py
    - deploy/docker-compose.yml
    - .env.example

key-decisions:
  - "POST /auth/refresh is stateless — no DB revocation table; refresh token revocation deferred to AUTH-F01"
  - "RefreshRequest/RefreshResponse models added to auth.py alongside LoginResponse — single file owns all auth shapes"
  - "INTERNAL_API_KEY module-level hard-fail in diagnosis_service.py (os.environ[]) — Presenter fails to start if unset"
  - "CORS_ALLOW_ORIGINS env var split on comma — supports multi-origin deployments without code change"
  - "diagnose.py Request param retained — still needed for request.app.state.http_client; only auth_header arg removed"

patterns-established:
  - "Refresh token: decode JWT, check sub claim, call create_session_token() — no DB lookup needed"
  - "Internal service calls: X-Internal-Api-Key + X-Tenant-Id headers, no Authorization forwarding"
  - "CORS configuration: ALLOW_ORIGINS from os.environ.get with comma-split, never wildcard with credentials"

requirements-completed: [AUTH-02, AUTH-04]

# Metrics
duration: 12min
completed: 2026-04-30
---

# Phase 16 Plan 03: Auth Hardening — Refresh Token + Internal Key + CORS Summary

**Stateless POST /auth/refresh endpoint, Presenter->Diagnosticer INTERNAL_API_KEY forwarding, CORSMiddleware with explicit allow_origins, and env var wiring in docker-compose and .env.example**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-30T07:01:19Z
- **Completed:** 2026-04-30T07:13:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- LoginResponse now returns both session_token and refresh_token; login() calls create_refresh_token() from deps
- POST /auth/refresh: stateless — decodes refresh JWT, checks sub claim, issues new short-lived session token; returns 401 on JWTError or missing sub
- diagnosis_service.py: auth_header removed; Presenter now forwards X-Internal-Api-Key + X-Tenant-Id to Diagnosticer, completing the service trust boundary established in Plan 01
- CORSMiddleware added to Presenter with allow_credentials=True and CORS_ALLOW_ORIGINS env var (comma-split, never wildcard)
- docker-compose.yml: INTERNAL_API_KEY (no :- fallback) added to presenter and diagnosticer; ENVIRONMENT and CORS_ALLOW_ORIGINS added to presenter; ENVIRONMENT added to view
- .env.example: INTERNAL_API_KEY, ENVIRONMENT, CORS_ALLOW_ORIGINS entries added under # App section

## Task Commits

Each task was committed atomically:

1. **Task 1: Update auth.py — LoginResponse + create_refresh_token + POST /auth/refresh** - `08d0335` (feat)
2. **Task 2: Update diagnosis_service.py (INTERNAL_API_KEY) + main.py (CORSMiddleware)** - `dc3aeca` (feat)
3. **Task 3: Wire INTERNAL_API_KEY + ENVIRONMENT + CORS_ALLOW_ORIGINS into docker-compose and .env.example** - `a089bb5` (chore)

**Plan metadata:** (docs: complete plan — see final commit)

## Files Created/Modified
- `xeter/services/presenter/routers/auth.py` - Added create_refresh_token import, refresh_token field on LoginResponse, login() returns both tokens, RefreshRequest/RefreshResponse models, POST /auth/refresh endpoint
- `xeter/services/presenter/diagnosis_service.py` - INTERNAL_API_KEY module-level hard-fail, auth_header param removed from trigger(), X-Internal-Api-Key + X-Tenant-Id header forwarding
- `xeter/services/presenter/main.py` - CORSMiddleware with allow_credentials=True and CORS_ALLOW_ORIGINS env var, ENVIRONMENT var
- `xeter/services/presenter/routers/diagnose.py` - Removed auth_header=... argument from service.trigger() call
- `deploy/docker-compose.yml` - INTERNAL_API_KEY (no fallback) in presenter + diagnosticer, ENVIRONMENT in presenter + view, CORS_ALLOW_ORIGINS in presenter
- `.env.example` - Added INTERNAL_API_KEY, ENVIRONMENT, CORS_ALLOW_ORIGINS

## Decisions Made
- POST /auth/refresh is stateless — no DB revocation table; refresh token revocation deferred to AUTH-F01 (accepted v1.3 tradeoff, documented in STATE.md)
- CORS_ALLOW_ORIGINS split on comma at startup — supports multi-origin (staging + prod) without code change
- diagnose.py Request parameter retained — still required for request.app.state.http_client; only auth_header keyword arg was removed from the trigger() call
- Module-level os.environ["INTERNAL_API_KEY"] in diagnosis_service.py — Presenter service fails loudly at startup if INTERNAL_API_KEY is unset (matches existing SECRET_KEY pattern)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required beyond what .env.example documents.

## Next Phase Readiness
- AUTH-02 satisfied: POST /auth/refresh endpoint ready for Next.js Route Handler (Plan 04) to call
- AUTH-04 satisfied: Presenter->Diagnosticer internal key forwarding complete; Diagnosticer InternalApiKeyMiddleware (Plan 01) now receives the correct header
- CORS configured: Presenter ready for browser requests from Next.js frontend
- Plan 04 can proceed: Next.js Route Handlers for /api/auth/login and /api/auth/refresh that set httpOnly cookies

---
*Phase: 16-auth-hardening*
*Completed: 2026-04-30*
