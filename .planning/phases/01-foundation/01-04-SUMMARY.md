---
phase: 01-foundation
plan: 04
subsystem: auth
tags: [fastapi, registration, api-key, seed, reset, integration-test, multi-tenancy, bcrypt]

# Dependency graph
requires:
  - phase: 01-03
    provides: TenantRepository, UserRepository, ApiKeyRepository, generate_api_key(), tenant_session(), get_async_session_factory()
provides:
  - POST /register endpoint (tenant_name, email, password) → (tenant_id, api_key, message)
  - 409 Conflict on duplicate email
  - seed.py: idempotent dev bootstrap with fixed dev-api-key-local
  - reset.py: full teardown (DROP SCHEMA CASCADE + alembic + ClickHouse) + re-seed
  - test_registration.py: 4 integration tests (skip when TEST_DATABASE_URL unset)
affects: [02-ingestion, 03-analysis, 04-read-path]

# Tech tracking
tech-stack:
  added: [structlog (installed), httpx (already installed), pytest-asyncio (already installed)]
  patterns:
    - POST /register: two-transaction pattern (tenant bootstrap in session.begin(), user+key in tenant_session() for RLS)
    - Password hashing: bcrypt.hashpw() directly (passlib Python 3.14 incompatibility, per plan 03 decision)
    - Integration tests: httpx.AsyncClient + ASGITransport + dependency_overrides for get_session
    - Seed: idempotency check via SELECT before INSERT; ClickHouse spans table created on seed
    - Reset: psycopg2 sync connection for DDL DROP SCHEMA CASCADE; then alembic upgrade head via subprocess

key-files:
  created:
    - xeter/services/presenter/routers/__init__.py
    - xeter/services/presenter/routers/auth.py
    - xeter/services/presenter/main.py
    - xeter/scripts/__init__.py
    - xeter/scripts/seed.py
    - xeter/scripts/reset.py
    - xeter/tests/dal/test_registration.py
  modified: []

key-decisions:
  - "POST /register uses two separate transactions: tenant creation in session.begin() (no RLS needed — bootstrap), then user+key in tenant_session() (RLS enforced via SET LOCAL)"
  - "Password hashing in registration uses bcrypt.hashpw() directly — same decision as plan 03 (passlib CryptContext incompatible with Python 3.14 + current bcrypt)"
  - "seed.py idempotency: checks for existing dev-tenant by name before any INSERT; exits cleanly if already seeded"
  - "reset.py uses psycopg2 (sync) for DROP SCHEMA CASCADE — asyncpg does not support DDL outside a transaction cleanly; psycopg2 with autocommit=True is the correct tool"
  - "Integration tests use dependency_overrides to inject test engine into get_session — avoids app-level DATABASE_URL and ensures test isolation"

requirements-completed: [AUTH-05, AUTH-01]

# Metrics
duration: 17min
completed: 2026-03-27
---

# Phase 1 Plan 04: Tenant Registration Endpoint + Dev Bootstrap Summary

**POST /register creates tenant, user, and bcrypt-hashed API key across two transactions (tenant bootstrap + tenant_session RLS), with seed.py providing a fixed dev-api-key-local and reset.py for full teardown**

## Performance

- **Duration:** 17 min
- **Started:** 2026-03-27T13:06:15Z
- **Completed:** 2026-03-27T13:23:34Z
- **Tasks:** 2
- **Files modified:** 7 created, 0 modified

## Accomplishments

- `POST /register`: Pydantic request/response models, duplicate email 409, bcrypt password hashing, two-transaction flow (tenant bootstrap then `tenant_session()` for RLS-scoped user + API key creation)
- `FastAPI app` (`main.py`): `/healthz` liveness probe + auth router wired with prefix="" and tags=["auth"]
- `seed.py`: Idempotent dev bootstrap — checks for existing "dev-tenant", creates tenant + user + hashed "dev-api-key-local" key + ClickHouse spans table
- `reset.py`: Full teardown via psycopg2 DROP SCHEMA CASCADE, then `alembic upgrade head` via subprocess, then ClickHouse DROP/CREATE, then seed
- `test_registration.py`: 4 integration tests — happy path (200 + xtr_ prefix check), key-once-only (verify_api_key utility + no GET endpoint), duplicate email 409, password <8 chars 422; all skip gracefully when `TEST_DATABASE_URL` unset

## Task Commits

1. **POST /register endpoint and presenter app wiring** - `65c7dec` (feat)
2. **Seed/reset scripts and POST /register integration tests** - `202b944` (feat)

**Plan metadata:** (docs commit — see final commit below)

## Files Created/Modified

- `xeter/services/presenter/routers/auth.py` — POST /register: RegisterRequest, RegisterResponse, duplicate-email 409, two-transaction flow
- `xeter/services/presenter/routers/__init__.py` — package marker
- `xeter/services/presenter/main.py` — FastAPI app with /healthz + auth router
- `xeter/scripts/__init__.py` — package marker
- `xeter/scripts/seed.py` — idempotent dev bootstrap with fixed dev-api-key-local
- `xeter/scripts/reset.py` — DROP SCHEMA CASCADE + alembic + ClickHouse DROP + seed
- `xeter/tests/dal/test_registration.py` — 4 integration tests, auto-skip without TEST_DATABASE_URL

## Decisions Made

- **Two-transaction registration flow:** Tenant creation (step 2) cannot use `tenant_session()` because the tenant_id doesn't exist yet. After commit, user and API key creation use `tenant_session()` so RLS `SET LOCAL app.current_tenant_id` is enforced in a separate transaction. This is the correct pattern — tenant bootstrapping is inherently outside tenant scope.
- **bcrypt direct (password hashing):** Consistent with plan 03 decision — `bcrypt.hashpw()` used directly for both API key hashing (generate_api_key) and password hashing in registration. passlib CryptContext is broken on Python 3.14 + current bcrypt.
- **seed.py idempotency via name check:** Checks `SELECT * FROM tenants WHERE name = 'dev-tenant'` before inserting. Simple and reliable; avoids UNIQUE constraint errors on re-run.
- **reset.py uses psycopg2 for DDL:** `DROP SCHEMA public CASCADE` must run outside a transaction (or with `autocommit=True`). psycopg2 with `conn.autocommit = True` is the correct approach — asyncpg does not expose autocommit DDL cleanly.
- **Integration test dependency_overrides:** `app.dependency_overrides[get_session]` points at a test engine session factory, so tests hit the test DB without modifying app-level config. Overrides are cleared after each test via `app.dependency_overrides.clear()`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added structlog installation**
- **Found during:** Task 1 (router import fails)
- **Issue:** `import structlog` in auth.py raised `ModuleNotFoundError` — structlog was listed in pyproject.toml dependencies but not installed in the active environment
- **Fix:** `pip install structlog`
- **Files modified:** None (pip install only)
- **Verification:** `from xeter.services.presenter.routers.auth import router` succeeds after install

None — plan executed with one minor dependency install (structlog).

## Issues Encountered

- structlog not installed despite being in pyproject.toml. Resolved immediately with pip install.

## User Setup Required

To run the integration tests:
```
export TEST_DATABASE_URL="postgresql+asyncpg://user:pass@localhost/xeter_test"
cd xeter && alembic upgrade head  # against test DB
pytest tests/dal/test_registration.py -v
```

To run seed in dev:
```
make seed
# or: cd xeter && python scripts/seed.py
```

To reset dev environment:
```
make reset
# or: cd xeter && python scripts/reset.py
```

## Next Phase Readiness

- Phase 2 ingestion service can use `dev-api-key-local` for all local span submission tests
- `POST /register` provides the self-service registration path for Phase 2 integration tests
- `reset.py` enables clean-slate dev environment in a single command
- Phase 1 foundation is complete — all 4 plans done

---
*Phase: 01-foundation*
*Completed: 2026-03-27*
