---
phase: 16-auth-hardening
verified: 2026-04-30T08:30:00Z
status: passed
score: 28/28 must-haves verified
re_verification: false
---

# Phase 16: Auth Hardening Verification Report

**Phase Goal:** Harden auth — eliminate dev-key risk, implement refresh tokens, add key rotation runbook. All 4 auth requirement IDs (AUTH-01, AUTH-02, AUTH-03, AUTH-04) must be verified.
**Verified:** 2026-04-30T08:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Presenter hard-fails at startup with KeyError if SECRET_KEY is unset | VERIFIED | `deps.py:48` — `SECRET_KEY = os.environ["SECRET_KEY"]` |
| 2  | Diagnosticer hard-fails at startup with KeyError if SECRET_KEY is unset | VERIFIED | `diagnosticer/main.py:53` — `SECRET_KEY = os.environ["SECRET_KEY"]` |
| 3  | Diagnosticer hard-fails at startup with KeyError if INTERNAL_API_KEY is unset | VERIFIED | `diagnosticer/main.py:54` — `INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]` |
| 4  | Access tokens expire after 30 minutes | VERIFIED | `deps.py:50` — `TOKEN_EXPIRE_MINUTES = 30`; `create_session_token` uses `timedelta(minutes=TOKEN_EXPIRE_MINUTES)` |
| 5  | TOKEN_EXPIRE_HOURS completely removed from deps.py | VERIFIED | Zero occurrences of `TOKEN_EXPIRE_HOURS` anywhere in presenter service |
| 6  | create_refresh_token() exported from deps.py with 30-day expiry and type=refresh claim | VERIFIED | `deps.py:72-83` — function present, `timedelta(days=30)`, `"type": "refresh"` in payload |
| 7  | POST /login returns both session_token and refresh_token | VERIFIED | `auth.py:200-204` — `LoginResponse` has both fields; `login()` at line 244 calls both `create_session_token` and `create_refresh_token` |
| 8  | POST /auth/refresh accepts {refresh_token: str} and returns {session_token: str} | VERIFIED | `auth.py:259-297` — `RefreshRequest`, `RefreshResponse`, endpoint at `/auth/refresh` decodes JWT, checks sub, issues new session token |
| 9  | Diagnosticer returns 401 on requests to /diagnose with wrong/missing X-Internal-Api-Key | VERIFIED | `diagnosticer/main.py:58-71` — `InternalApiKeyMiddleware` returns 401 JSON when key != INTERNAL_API_KEY |
| 10 | Diagnosticer /healthz passes without X-Internal-Api-Key | VERIFIED | `diagnosticer/main.py:60` — `if request.url.path == "/healthz": return await call_next(request)` |
| 11 | Diagnosticer /diagnose reads tenant_id from X-Tenant-Id header (not JWT) | VERIFIED | `diagnosticer/main.py:142` — `x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")`; guard at line 153 |
| 12 | Presenter forwards X-Internal-Api-Key and X-Tenant-Id to Diagnosticer | VERIFIED | `diagnosis_service.py:178-183` — `headers={"X-Internal-Api-Key": INTERNAL_API_KEY, "X-Tenant-Id": tenant_id}` |
| 13 | Presenter no longer forwards Authorization header to Diagnosticer | VERIFIED | `auth_header` parameter removed; only reference is a comment at line 143 |
| 14 | CORSMiddleware present in Presenter with allow_credentials=True and explicit allow_origins | VERIFIED | `main.py:42-48` — `CORSMiddleware` with `allow_credentials=True` and `ALLOW_ORIGINS` from env (never `"*"`) |
| 15 | INTERNAL_API_KEY module-level hard-fail in diagnosis_service.py | VERIFIED | `diagnosis_service.py:35` — `INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]` |
| 16 | docker-compose wires INTERNAL_API_KEY to both presenter and diagnosticer with no :- fallback | VERIFIED | `docker-compose.yml:147,219` — `INTERNAL_API_KEY: ${INTERNAL_API_KEY}` (no `:-` fallback in both services) |
| 17 | ENVIRONMENT and CORS_ALLOW_ORIGINS wired in docker-compose | VERIFIED | `docker-compose.yml:148-149` (presenter), `docker-compose.yml:236` (view) |
| 18 | .env.example has INTERNAL_API_KEY, ENVIRONMENT, CORS_ALLOW_ORIGINS | VERIFIED | `.env.example:36-38` — all three entries present |
| 19 | JWT_ROTATION_RUNBOOK.md exists and covers 30-minute re-login gap | VERIFIED | `docs/JWT_ROTATION_RUNBOOK.md` — contains "30-minute re-login gap" in Option A |
| 20 | Runbook covers dual-secret window option (python-jose try/except loop) | VERIFIED | Option B section documents `OLD_SECRET_KEY` and try/except decode fallback pattern |
| 21 | Runbook covers Diagnosticer-before-Presenter restart sequence | VERIFIED | "Service Restart Sequence" section — Diagnosticer first, then Presenter, with rationale |
| 22 | /api/login Route Handler sets httpOnly xeter_refresh cookie, returns only session_token | VERIFIED | `services/view/src/app/api/login/route.ts` — `httpOnly: true`, cookie name `xeter_refresh`, response strips refresh_token |
| 23 | /api/auth/refresh Route Handler reads httpOnly cookie, calls Presenter /auth/refresh | VERIFIED | `services/view/src/app/api/auth/refresh/route.ts` — reads `xeter_refresh` cookie, calls `${PRESENTER_URL}/auth/refresh` |
| 24 | sessionStorage completely absent from auth.ts | VERIFIED | Zero occurrences of `sessionStorage` in `services/view/src/lib/auth.ts` |
| 25 | Zustand hydrate() sets hydrated:true immediately (no storage read) | VERIFIED | `auth.ts:17` — `hydrate: () => set({ hydrated: true })` with comment "No storage read" |
| 26 | api.ts has 401 interceptor calling /api/auth/refresh and retrying once | VERIFIED | `api.ts:13-37` — detects `res.status === 401`, calls `/api/auth/refresh`, updates Zustand store, retries once |
| 27 | conftest.py sets SECRET_KEY and INTERNAL_API_KEY before any service import | VERIFIED | `conftest.py:12-13` — `os.environ.setdefault` calls before all other imports |
| 28 | test_auth_login.py asserts both session_token and refresh_token with correct type=refresh | VERIFIED | `test_auth_login.py:85,90-92` — asserts refresh_token present and decodes with `type == "refresh"` |

**Score:** 28/28 truths verified

---

## Required Artifacts

| Artifact | Provides | Status | Notes |
|----------|---------|--------|-------|
| `xeter/services/presenter/deps.py` | SECRET_KEY hard-fail, TOKEN_EXPIRE_MINUTES=30, create_refresh_token() | VERIFIED | All three present; TOKEN_EXPIRE_HOURS fully removed |
| `xeter/services/diagnosticer/main.py` | SECRET_KEY + INTERNAL_API_KEY hard-fails, InternalApiKeyMiddleware | VERIFIED | Both hard-fails at module level; middleware on app; /diagnose reads X-Tenant-Id |
| `docs/JWT_ROTATION_RUNBOOK.md` | JWT_SECRET rotation procedure | VERIFIED | Option A, Option B, restart sequence, verification commands all present |
| `xeter/services/presenter/routers/auth.py` | LoginResponse.refresh_token + POST /auth/refresh | VERIFIED | Substantive implementation; stateless JWT decode; models wired |
| `xeter/services/presenter/diagnosis_service.py` | X-Internal-Api-Key + X-Tenant-Id header forwarding | VERIFIED | INTERNAL_API_KEY hard-fail; auth_header param removed; headers wired |
| `xeter/services/presenter/main.py` | CORSMiddleware | VERIFIED | allow_credentials=True; ALLOW_ORIGINS from env; never wildcard |
| `deploy/docker-compose.yml` | INTERNAL_API_KEY and ENVIRONMENT wiring | VERIFIED | INTERNAL_API_KEY without :- fallback in presenter + diagnosticer |
| `.env.example` | INTERNAL_API_KEY, ENVIRONMENT, CORS_ALLOW_ORIGINS | VERIFIED | All entries present under # App section |
| `services/view/src/app/api/login/route.ts` | POST /api/login Route Handler | VERIFIED | httpOnly cookie set; refresh_token stripped from response |
| `services/view/src/app/api/auth/refresh/route.ts` | POST /api/auth/refresh Route Handler | VERIFIED | Reads xeter_refresh cookie; calls Presenter /auth/refresh |
| `services/view/src/lib/auth.ts` | Pure in-memory Zustand store | VERIFIED | Zero sessionStorage references; hydrate() is a no-op |
| `services/view/src/lib/api.ts` | 401 interceptor | VERIFIED | Detects 401, calls /api/auth/refresh, retries once |
| `xeter/tests/conftest.py` | SECRET_KEY + INTERNAL_API_KEY env defaults before imports | VERIFIED | setdefault calls at top before pytest/unittest imports |
| `xeter/tests/presenter/test_auth_login.py` | refresh_token assertions | VERIFIED | Asserts refresh_token in response and decodes with type=refresh |
| `xeter/tests/diagnosticer/test_diagnose_endpoint.py` | InternalApiKeyMiddleware tests | VERIFIED | test_missing_auth_returns_401, test_wrong_internal_key_returns_401; _INTERNAL_KEY_HEADER pattern |
| `xeter/tests/presenter/test_diagnose.py` | X-Internal-Api-Key forwarding assertions | VERIFIED | assert call_args contain X-Internal-Api-Key and X-Tenant-Id |

---

## Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `deps.py` | `routers/auth.py` | `from xeter.services.presenter.deps import create_refresh_token` | WIRED | `auth.py:37` — explicit import; used at line 244 in login() |
| `routers/auth.py` | `deps.py` | `SECRET_KEY, ALGORITHM` imported for /auth/refresh decode | WIRED | `auth.py:35-38` — top-level import; used in refresh_token() at line 290 |
| `diagnosis_service.py` | `diagnosticer/main.py` | `X-Internal-Api-Key` header → `InternalApiKeyMiddleware` | WIRED | `diagnosis_service.py:180` sends header; `main.py:63` checks it in middleware |
| `docker-compose.yml` | `.env.example` | `INTERNAL_API_KEY: ${INTERNAL_API_KEY}` var without fallback | WIRED | Both files have INTERNAL_API_KEY; docker-compose has no :- fallback |
| `/api/login/route.ts` | `Presenter /login` | `fetch(${PRESENTER_URL}/login)`, reads refresh_token, sets httpOnly cookie | WIRED | `route.ts:10-31` — complete flow; cookie set; only session_token returned |
| `/api/auth/refresh/route.ts` | `Presenter /auth/refresh` | reads xeter_refresh cookie, POSTs to `${PRESENTER_URL}/auth/refresh` | WIRED | `route.ts:7-25` — cookie read; POST to presenter; session_token forwarded |
| `api.ts` | `/api/auth/refresh/route.ts` | `fetch('/api/auth/refresh', { method: 'POST' })` on 401 | WIRED | `api.ts:15` — exact path matches Route Handler; response used to update store and retry |
| `conftest.py` | `deps.py` module-level | `os.environ.setdefault('SECRET_KEY', ...)` before import | WIRED | `conftest.py:12` — setdefault before pytest imports satisfy hard-fail at collection |
| `conftest.py` | `diagnosticer/main.py` module-level | `os.environ.setdefault('INTERNAL_API_KEY', ...)` before import | WIRED | `conftest.py:13` — setdefault satisfies INTERNAL_API_KEY hard-fail at collection |

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUTH-01 | 16-01, 16-04 | Session tokens expire after 30 minutes; server hard-fails on startup if SECRET_KEY unset | SATISFIED | `deps.py` TOKEN_EXPIRE_MINUTES=30; both services use os.environ["SECRET_KEY"]; no fallback anywhere in codebase |
| AUTH-02 | 16-03, 16-04, 16-05 | Silent refresh via httpOnly refresh token cookie — POST /auth/refresh; Next.js Route Handlers; sessionStorage removed | SATISFIED | /auth/refresh endpoint in auth.py; both Route Handlers exist; zero sessionStorage in auth.ts; 401 interceptor in api.ts |
| AUTH-03 | 16-02 | Operator has documented JWT_SECRET rotation runbook covering dual-secret window and restart sequence | SATISFIED | `docs/JWT_ROTATION_RUNBOOK.md` — Option A (30-min gap), Option B (try/except dual-secret), restart sequence (Diagnosticer-first) |
| AUTH-04 | 16-01, 16-03, 16-04 | Presenter-to-Diagnosticer calls authenticated by INTERNAL_API_KEY; middleware rejects wrong/missing key with 401 | SATISFIED | InternalApiKeyMiddleware in diagnosticer; INTERNAL_API_KEY hard-fail in both diagnosticer and diagnosis_service; X-Internal-Api-Key forwarded in every call |

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `diagnosis_service.py:143` | Comment referencing removed `auth_header` parameter | Info | Documentation only — comment in docstring noting old parameter was removed. Not a stub or dead code. No impact. |

No blocker or warning anti-patterns found. No TODO/FIXME/placeholder comments. No stub implementations. No empty handlers. No dev-key fallbacks anywhere in the codebase.

---

## Human Verification Required

### 1. Silent refresh flow end-to-end

**Test:** Log in to the app, wait 30 minutes (or manually expire the access token), then make an authenticated action (e.g., load the spans list).
**Expected:** The action succeeds without a redirect to login — the 401 interceptor transparently refreshes the token and retries.
**Why human:** Requires a live browser, running services, and observing network tab behavior across a token expiry boundary.

### 2. httpOnly cookie not accessible from browser JS

**Test:** After logging in via /api/login, open browser DevTools console and run `document.cookie`.
**Expected:** `xeter_refresh` does NOT appear in document.cookie output. It should be invisible to JavaScript.
**Why human:** httpOnly attribute enforcement requires browser verification.

### 3. Rotation runbook — old token rejected after key rotation (Option A)

**Test:** Follow Option A steps in `docs/JWT_ROTATION_RUNBOOK.md` in a dev environment. Use the verification commands in the runbook to confirm an old token returns 401 post-restart and a new login succeeds.
**Expected:** Old token → 401. New login → 200 with valid session_token.
**Why human:** Requires running Docker services and performing an actual restart with a new SECRET_KEY.

---

## Commit Verification

All 10 task commits from SUMMARY files verified in git history:

| Commit | Description |
|--------|-------------|
| `366cde4` | feat(16-01): harden presenter deps.py |
| `fed51d4` | feat(16-01): harden diagnosticer main.py |
| `144f3c5` | docs(16-02): add JWT_SECRET rotation runbook |
| `08d0335` | feat(16-03): add refresh_token to LoginResponse + POST /auth/refresh |
| `dc3aeca` | feat(16-03): INTERNAL_API_KEY header forwarding + CORSMiddleware |
| `a089bb5` | chore(16-03): wire INTERNAL_API_KEY + ENVIRONMENT + CORS_ALLOW_ORIGINS |
| `a26c58c` | fix(16-04): fix conftest.py + test_auth_login.py + test_diagnose.py |
| `ac45842` | fix(16-04): update test_diagnose_endpoint.py for InternalApiKeyMiddleware |
| `a6fb992` | feat(16-05): add login and auth/refresh Route Handlers |
| `8dfd1f5` | feat(16-05): remove sessionStorage from auth.ts, add 401 interceptor |

---

## Summary

Phase 16 goal fully achieved. All four auth requirement IDs are satisfied:

- **AUTH-01**: Both services use `os.environ["SECRET_KEY"]` (KeyError on startup if unset). Access tokens expire in 30 minutes. No soft fallback exists anywhere in the codebase.
- **AUTH-02**: Full refresh token flow implemented end-to-end — Presenter issues refresh tokens at login, POST /auth/refresh endpoint verifies them stateless, Next.js Route Handlers set/read the httpOnly `xeter_refresh` cookie, sessionStorage is fully removed from auth.ts, and api.ts has a single-retry 401 interceptor.
- **AUTH-03**: `docs/JWT_ROTATION_RUNBOOK.md` documents Option A (simple rotation with 30-minute re-login gap), Option B (dual-secret window using python-jose try/except loop), and the Diagnosticer-before-Presenter restart sequence.
- **AUTH-04**: `InternalApiKeyMiddleware` on Diagnosticer enforces X-Internal-Api-Key on all non-/healthz routes. Presenter's `diagnosis_service.py` forwards `X-Internal-Api-Key` + `X-Tenant-Id` on every call. INTERNAL_API_KEY is a hard-fail in both Diagnosticer and Presenter. docker-compose wires it without a :- fallback.

Three items flagged for human verification (live browser/service behavior — cannot be verified statically).

---

_Verified: 2026-04-30T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
