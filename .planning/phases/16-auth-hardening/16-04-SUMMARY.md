---
phase: 16-auth-hardening
plan: "04"
subsystem: tests
tags: [pytest, fastapi, auth, jwt, middleware, python]

# Dependency graph
requires:
  - phase: 16-01
    provides: SECRET_KEY/INTERNAL_API_KEY hard-fails, InternalApiKeyMiddleware
  - phase: 16-03
    provides: refresh_token in LoginResponse, X-Internal-Api-Key forwarding in diagnosis_service
provides:
  - conftest.py with SECRET_KEY and INTERNAL_API_KEY env defaults before any service import
  - test_auth_login.py asserting refresh_token in login response
  - test_diagnose_endpoint.py testing InternalApiKeyMiddleware behavior
  - test_diagnose.py asserting X-Internal-Api-Key forwarded to Diagnosticer
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "conftest.py os.environ.setdefault before imports — prevents KeyError on module-level env var hard-fails"
    - "Test auth via InternalApiKeyMiddleware: pass X-Internal-Api-Key + X-Tenant-Id in headers"

key-files:
  created: []
  modified:
    - xeter/tests/conftest.py
    - xeter/tests/presenter/test_auth_login.py
    - xeter/tests/presenter/test_diagnose.py
    - xeter/tests/diagnosticer/test_diagnose_endpoint.py

key-decisions:
  - "conftest.py setdefault runs before any service module is imported — ensures module-level hard-fails succeed during test collection"
  - "test_diagnose_endpoint.py uses _INTERNAL_KEY_HEADER with both X-Internal-Api-Key and X-Tenant-Id — matches InternalApiKeyMiddleware + endpoint contract"
  - "verify_session_token dependency_overrides removed from TestDiagnoseEndpoint — Diagnosticer no longer uses JWT auth on /diagnose"

# Metrics
duration: 23min
completed: 2026-04-30
---

# Phase 16 Plan 04: Auth Hardening — Fix Test Suite for SECRET_KEY Hard-Fails and InternalApiKeyMiddleware Summary

**Fixed pytest collection KeyError by setting SECRET_KEY/INTERNAL_API_KEY defaults in conftest.py, updated login tests to assert refresh_token, rewrote diagnosticer endpoint tests to use X-Internal-Api-Key middleware, and added X-Internal-Api-Key forwarding assertions to presenter diagnose tests**

## Performance

- **Duration:** 23 min
- **Started:** 2026-04-30T07:03:51Z
- **Completed:** 2026-04-30T07:26:14Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Eliminated KeyError at pytest collection time: conftest.py now sets SECRET_KEY and INTERNAL_API_KEY defaults before any service module is imported, satisfying the os.environ[] hard-fails introduced in Plan 01
- Updated test_auth_login.py to assert both session_token and refresh_token in login response, verifying the refresh_token decodes correctly with type=refresh claim (AUTH-02 test coverage)
- Rewrote test_diagnose_endpoint.py tests to match InternalApiKeyMiddleware: missing key → 401, wrong key → 401 (new test), correct key → endpoint runs (AUTH-04 test coverage)
- Added assertions to test_diagnose.py verifying Presenter forwards X-Internal-Api-Key and X-Tenant-Id to Diagnosticer, not raw Authorization header

## Task Commits

1. **Task 1: Fix conftest.py + test_auth_login.py + test_diagnose.py** - `a26c58c` (fix)
2. **Task 2: Fix test_diagnose_endpoint.py for INTERNAL_API_KEY middleware** - `ac45842` (fix)

## Files Created/Modified

- `xeter/tests/conftest.py` - Added os.environ.setdefault for SECRET_KEY and INTERNAL_API_KEY at top of file, before all imports
- `xeter/tests/presenter/test_auth_login.py` - Updated test_login_valid_credentials_returns_token to assert refresh_token present and decodeable with type=refresh claim
- `xeter/tests/presenter/test_diagnose.py` - Added call_args assertions verifying X-Internal-Api-Key and X-Tenant-Id in Diagnosticer forward headers
- `xeter/tests/diagnosticer/test_diagnose_endpoint.py` - Replaced verify_session_token overrides with X-Internal-Api-Key header pattern; added test_wrong_internal_key_returns_401; updated all success-path calls to pass _INTERNAL_KEY_HEADER

## Decisions Made

- conftest.py setdefault approach chosen over pytest.ini env vars — ensures defaults take effect before module-level import, not just before test function execution
- Removed verify_session_token from setup_method/teardown_method entirely — the dep is no longer on /diagnose endpoint and overriding it had no auth effect
- _INTERNAL_KEY_HEADER includes both X-Internal-Api-Key and X-Tenant-Id — matches the Diagnosticer contract (middleware checks key, endpoint reads tenant_id from header)

## Deviations from Plan

### Context Discovery

**Plan 03 source changes were already committed** — `auth.py` (LoginResponse with refresh_token, POST /auth/refresh), `diagnosis_service.py` (INTERNAL_API_KEY, X-Internal-Api-Key forwarding), `main.py` (CORSMiddleware), `docker-compose.yml`, and `.env.example` were all committed in commits `08d0335`, `dc3aeca`, `a089bb5` before this plan executed. No re-application was needed.

**Tracked:** `[Context - No Action Needed] Plan 03 source changes pre-applied`

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- Plan 05 (frontend) can proceed — server-side auth (Plans 01-04) is complete
- 44 presenter + diagnosticer tests pass with no KeyError at collection

---
*Phase: 16-auth-hardening*
*Completed: 2026-04-30*
