---
phase: 16-auth-hardening
plan: "01"
subsystem: auth
tags: [jwt, fastapi, python, middleware, starlette]

# Dependency graph
requires:
  - phase: 15-secrets-hygiene
    provides: .env.example with SECRET_KEY and INTERNAL_API_KEY placeholders
provides:
  - SECRET_KEY hard-fail at startup in both presenter and diagnosticer
  - INTERNAL_API_KEY hard-fail at startup in diagnosticer
  - TOKEN_EXPIRE_MINUTES=30 (down from 24h) in presenter deps.py
  - create_refresh_token() exported from presenter deps.py with 30-day expiry and type=refresh claim
  - InternalApiKeyMiddleware on diagnosticer app (exempts /healthz, rejects all other requests with wrong/missing X-Internal-Api-Key)
  - /diagnose reads tenant_id from X-Tenant-Id header instead of decoding JWT
affects: [16-03-refresh-endpoint, 16-05-frontend]

# Tech tracking
tech-stack:
  added: [starlette.middleware.base.BaseHTTPMiddleware]
  patterns:
    - "Hard-fail env var: os.environ['KEY'] not os.environ.get('KEY', fallback)"
    - "Service trust boundary via INTERNAL_API_KEY middleware, X-Tenant-Id header forwarding"
    - "Middleware /healthz exemption pattern"

key-files:
  created: []
  modified:
    - xeter/services/presenter/deps.py
    - xeter/services/diagnosticer/main.py

key-decisions:
  - "SECRET_KEY uses os.environ[] hard-fail in both services — eliminates dev-key silently deployed to production (AUTH-01)"
  - "TOKEN_EXPIRE_MINUTES=30 replaces TOKEN_EXPIRE_HOURS=24 — access tokens now 30-minute lifetime"
  - "InternalApiKeyMiddleware on diagnosticer establishes service trust boundary — Presenter must pass X-Internal-Api-Key on every call except /healthz (AUTH-04)"
  - "Diagnosticer /diagnose no longer decodes JWTs — trust moves to INTERNAL_API_KEY gate, tenant_id forwarded via X-Tenant-Id header"
  - "verify_session_token kept in diagnosticer/main.py for backwards compatibility with existing test dependency_overrides"

patterns-established:
  - "Hard-fail env var: os.environ['KEY'] raises KeyError at module load time — fail loud at startup, never silently use insecure defaults"
  - "Service trust boundary: internal services accept X-Internal-Api-Key middleware, external auth handled by edge service (Presenter)"
  - "Header forwarding: Presenter forwards X-Tenant-Id to internal services after verifying JWT — avoids JWT re-decoding in downstream services"

requirements-completed: [AUTH-01, AUTH-04]

# Metrics
duration: 7min
completed: 2026-04-30
---

# Phase 16 Plan 01: Auth Hardening — Secret Hard-Fails, 30min Expiry, INTERNAL_API_KEY Middleware Summary

**Replaced soft SECRET_KEY fallbacks with os.environ[] hard-fails in both services, shortened access token expiry from 24h to 30min, added create_refresh_token() to presenter deps.py, and established Diagnosticer trust boundary via InternalApiKeyMiddleware requiring X-Internal-Api-Key on all non-healthz routes**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-30T06:36:56Z
- **Completed:** 2026-04-30T06:43:35Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Eliminated dev-key-silently-deployed-to-production risk (AUTH-01): both services now KeyError at startup if SECRET_KEY unset
- Shortened access token lifetime from 24 hours to 30 minutes; added create_refresh_token() with 30-day expiry and type=refresh claim (prerequisite for Plan 03 refresh endpoint)
- Established Diagnosticer internal trust boundary (AUTH-04): InternalApiKeyMiddleware rejects all requests missing correct X-Internal-Api-Key except /healthz liveness probe; /diagnose now reads tenant_id from X-Tenant-Id header forwarded by Presenter

## Task Commits

Each task was committed atomically:

1. **Task 1: Harden deps.py — SECRET_KEY hard-fail, 30min expiry, create_refresh_token** - `366cde4` (feat)
2. **Task 2: Harden diagnosticer/main.py — SECRET_KEY hard-fail + INTERNAL_API_KEY middleware + X-Tenant-Id** - `fed51d4` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `xeter/services/presenter/deps.py` - SECRET_KEY hard-fail, TOKEN_EXPIRE_MINUTES=30, create_refresh_token() with 30-day expiry + type=refresh
- `xeter/services/diagnosticer/main.py` - SECRET_KEY + INTERNAL_API_KEY hard-fails, InternalApiKeyMiddleware, /diagnose reads X-Tenant-Id header

## Decisions Made

- os.environ[] hard-fail (not try/except) — plan explicitly requires KeyError to surface at startup, not be swallowed
- verify_session_token left in diagnosticer/main.py — existing tests use dependency_overrides referencing it; safe to keep since the JWT decode path is no longer reachable from /diagnose
- REFRESH_TOKEN_EXPIRE_DAYS defined at module level (not inline in function) — consistent with TOKEN_EXPIRE_MINUTES pattern already in file

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. SECRET_KEY and INTERNAL_API_KEY are already in .env.example (Phase 15-01).

## Next Phase Readiness

- Plan 02 (token-expiry Alembic migration, if any DB changes) can proceed
- Plan 03 (refresh endpoint) can now import create_refresh_token() from deps.py — prerequisite satisfied
- Plan 04 (test conftest) can fix test_auth_login.py which imports SECRET_KEY from deps.py — the import will fail in test collection unless SECRET_KEY is set in env (noted in plan)
- Plan 05 (frontend) can rely on 30-min access token lifetime

---
*Phase: 16-auth-hardening*
*Completed: 2026-04-30*
