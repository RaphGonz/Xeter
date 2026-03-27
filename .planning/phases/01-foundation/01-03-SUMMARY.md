---
phase: 01-foundation
plan: 03
subsystem: database
tags: [dal, tenant-guard, multi-tenancy, rls, bcrypt, sqlalchemy, redis, asyncpg, tdd]

# Dependency graph
requires:
  - phase: 01-02
    provides: SQLAlchemy 2.0 ORM models (Tenant, User, ApiKey) used by all three repositories
provides:
  - MissingTenantError + require_tenant() guard enforced at Python boundary before any DB call
  - TenantRepository with tenant_id guard on get_by_id
  - UserRepository with tenant_id guard on create and get_by_email
  - ApiKeyRepository with tenant_id guard on create and get_by_tenant
  - generate_api_key() returning (xtr_-prefixed plaintext, bcrypt hash)
  - verify_api_key() bcrypt verification
  - tenant_session() context manager injecting SET LOCAL app.current_tenant_id
  - get_async_engine() and get_async_session_factory() from DATABASE_URL
  - get_redis_client() from REDIS_URL
  - 13 passing unit tests proving guard raises before any DB call
affects: [02-ingestion, 03-analysis, 04-read-path, 06-hardening]

# Tech tracking
tech-stack:
  added: [passlib==1.7.4 (installed but unused — bcrypt used directly due to Python 3.14 incompatibility), asyncpg==0.31.0, bcrypt (direct)]
  patterns:
    - require_tenant() called as first line of every tenant-scoped repository method
    - tenant_session() context manager wraps session.begin() + SET LOCAL for RLS enforcement
    - bcrypt used directly (not via passlib CryptContext) due to passlib 1.7.4 incompatibility with newer bcrypt on Python 3.14
    - API keys use secrets.token_urlsafe(32) with xtr_ prefix; plaintext returned once, hash stored
    - All repository __init__ methods accept AsyncSession for testability

key-files:
  created:
    - xeter/shared/dal/base.py
    - xeter/shared/dal/tenants.py
    - xeter/shared/dal/users.py
    - xeter/shared/dal/api_keys.py
    - xeter/shared/db/postgres.py
    - xeter/shared/db/redis.py
    - xeter/tests/conftest.py
    - xeter/tests/dal/test_tenant_guard.py
  modified: []

key-decisions:
  - "bcrypt used directly instead of passlib CryptContext — passlib 1.7.4 is incompatible with Python 3.14 and newer bcrypt (AttributeError on __about__, ValueError on 72-byte limit check)"
  - "require_tenant() returns the original (un-stripped) value — strips only for emptiness check, preserves value as passed"
  - "TenantRepository.create() has no tenant_id guard — tenant creation is bootstrap-level, the tenant does not exist yet"
  - "tenant_session() uses SET LOCAL inside session.begin() — SET LOCAL requires an open transaction to scope correctly"

patterns-established:
  - "DAL guard: require_tenant(tenant_id) as first line of every tenant-scoped method — Python boundary, not DB-level"
  - "API key format: xtr_ prefix + secrets.token_urlsafe(32); hash only stored, plaintext discarded after creation"
  - "RLS injection: tenant_session() context manager uses parameterised text() for SET LOCAL — never string interpolation"
  - "Unit test pattern: AsyncMock session fixture from conftest.py — no DB connection for guard/unit tests"

requirements-completed: [AUTH-03, AUTH-04]

# Metrics
duration: 14min
completed: 2026-03-27
---

# Phase 1 Plan 03: DAL Tenant Guard + Repository Layer Summary

**Tenant guard enforced at Python boundary via require_tenant() in all three repositories, with bcrypt API key generation, PostgreSQL tenant_session() RLS injection, and 13 passing TDD unit tests**

## Performance

- **Duration:** 14 min
- **Started:** 2026-03-27T12:36:41Z
- **Completed:** 2026-03-27T12:50:00Z
- **Tasks:** 2 (RED + GREEN, no REFACTOR changes needed)
- **Files modified:** 8 created, 0 modified

## Accomplishments

- `MissingTenantError(RuntimeError)` and `require_tenant()` guard in `shared/dal/base.py` — raises before any DB interaction on None, empty, or whitespace tenant_id
- Three repository classes (TenantRepository, UserRepository, ApiKeyRepository) each calling `require_tenant()` as first line on every tenant-scoped method
- `generate_api_key()` returning `(xtr_-prefixed plaintext, bcrypt hash)` using `secrets.token_urlsafe(32)` + direct bcrypt
- `tenant_session()` async context manager that opens `session.begin()` and executes `SET LOCAL app.current_tenant_id = :tid` before yielding
- 13 unit tests proving: guard raises for None/empty/whitespace, valid UUID passes through, DB is never called on guard failure, API keys have xtr_ prefix, two keys differ, verify works and fails correctly

## Task Commits

Each task was committed atomically:

1. **RED phase: failing tests for DAL tenant guard** - `43c5631` (test)
2. **GREEN phase: DAL tenant guard + repositories + session factory** - `b6adb43` (feat)

**Plan metadata:** (docs commit — see final commit below)

_Note: TDD tasks — RED (test) → GREEN (feat). No REFACTOR commit needed._

## Files Created/Modified

- `xeter/shared/dal/base.py` — MissingTenantError(RuntimeError) + require_tenant() guard
- `xeter/shared/dal/tenants.py` — TenantRepository: create() (no guard), get_by_id() (guarded)
- `xeter/shared/dal/users.py` — UserRepository: create() and get_by_email() both guarded
- `xeter/shared/dal/api_keys.py` — generate_api_key(), verify_api_key(), ApiKeyRepository (guarded)
- `xeter/shared/db/postgres.py` — get_async_engine(), get_async_session_factory(), tenant_session()
- `xeter/shared/db/redis.py` — get_redis_client() from REDIS_URL env var
- `xeter/tests/conftest.py` — mock_session fixture (AsyncMock) for unit tests
- `xeter/tests/dal/test_tenant_guard.py` — 13 unit tests across 3 test classes

## Decisions Made

- **bcrypt direct instead of passlib CryptContext:** passlib 1.7.4 is incompatible with Python 3.14 and newer bcrypt — raises `AttributeError: module 'bcrypt' has no attribute '__about__'` and `ValueError: password cannot be longer than 72 bytes` during backend detection. Using `bcrypt.hashpw()` and `bcrypt.checkpw()` directly provides identical security guarantees.
- **require_tenant() returns original value:** Strips only for the emptiness check but returns the value as passed, so the caller can pass it directly to queries without modification.
- **TenantRepository.create() has no guard:** Tenant creation is bootstrap-level — the tenant does not yet exist, so there is no owning tenant_id to enforce.
- **SET LOCAL inside session.begin():** PostgreSQL SET LOCAL scopes to the current transaction. Opening `session.begin()` explicitly ensures the variable is set before any query runs and cleared when the transaction ends.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used bcrypt directly instead of passlib CryptContext**
- **Found during:** GREEN phase (api_keys.py implementation)
- **Issue:** passlib 1.7.4 raises `AttributeError: module 'bcrypt' has no attribute '__about__'` and then `ValueError: password cannot be longer than 72 bytes` on Python 3.14 with current bcrypt. The CryptContext bcrypt backend is broken on this Python version.
- **Fix:** Used `bcrypt.hashpw()` / `bcrypt.checkpw()` directly. The plan's requirement is "bcrypt hashing" — the security outcome is identical.
- **Files modified:** `xeter/shared/dal/api_keys.py`
- **Verification:** `verify_api_key` tests pass; bcrypt direct test confirmed in shell before implementation
- **Committed in:** b6adb43 (GREEN phase commit)

**2. [Rule 3 - Blocking] Installed missing passlib and asyncpg packages**
- **Found during:** Pre-implementation dependency check
- **Issue:** `passlib` and `asyncpg` not installed; imports would fail
- **Fix:** `pip install passlib bcrypt asyncpg` — installed passlib==1.7.4, asyncpg==0.31.0
- **Files modified:** None (pip install only)
- **Verification:** `import passlib.context` and `import asyncpg` both succeed
- **Committed in:** b6adb43 (GREEN phase commit)

---

**Total deviations:** 2 auto-fixed (2 blocking — dependency and library compatibility)
**Impact on plan:** bcrypt used directly achieves identical security. asyncpg required for async SQLAlchemy with PostgreSQL. No scope creep.

## Issues Encountered

- passlib 1.7.4 / bcrypt / Python 3.14 incompatibility: the passlib bcrypt backend performs an internal 72-byte wrap bug detection test that fails with current bcrypt. Resolved by using bcrypt directly, which has no such compatibility issue.

## User Setup Required

None — no external service configuration required for the DAL files themselves. Running against a live database requires:
- `DATABASE_URL` env var (postgresql+asyncpg:// scheme for async)
- `REDIS_URL` env var (redis:// scheme)

## Next Phase Readiness

- All three repositories are importable and tested — ready for service layer use in Phase 2
- `tenant_session()` provides the RLS injection pattern for any service that writes tenant-scoped data
- `generate_api_key()` / `verify_api_key()` are ready for the auth service in Phase 2
- Phase 1 Plan 04 (Docker Compose + environment wiring) can reference these DAL files for service configuration

---
*Phase: 01-foundation*
*Completed: 2026-03-27*
