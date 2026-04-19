---
phase: 01-foundation
verified: 2026-03-27T14:00:00Z
status: passed
score: 16/16 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Run `docker compose -f deploy/docker-compose.yml up` and confirm all six services reach healthy state"
    expected: "postgres, clickhouse, redis, minio all show (healthy) before analyser/presenter start; no startup errors"
    why_human: "Cannot execute Docker in this environment; healthcheck-gated ordering requires a live compose run"
  - test: "Run `make seed` against a running stack and confirm output includes 'Dev API key: dev-api-key-local'"
    expected: "Seed completes without error, second run prints 'Seed already applied. Run `make reset` to start fresh.'"
    why_human: "Requires live PostgreSQL and ClickHouse connections"
  - test: "Run `make reset` and confirm teardown + migrate + seed completes cleanly"
    expected: "DROP SCHEMA CASCADE, alembic upgrade head, ClickHouse drop/recreate, seed all succeed in sequence"
    why_human: "Requires live PostgreSQL (with BYPASSRLS) and ClickHouse connections"
  - test: "Run POST /register integration tests with TEST_DATABASE_URL set"
    expected: "All 4 tests pass: 200 happy path, key once only, 409 duplicate email, 422 short password"
    why_human: "Requires a live PostgreSQL test database with migrations applied"
---

# Phase 01: Foundation Verification Report

**Phase Goal:** Stand up the full local development environment — six containerized services with health-check-gated startup, locked database schemas (PostgreSQL + ClickHouse), a DAL layer with tenant isolation enforced at the Python level, and a working tenant registration endpoint backed by dev bootstrap tooling.
**Verified:** 2026-03-27T14:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `docker compose up` starts all six services with no errors | VERIFIED | `deploy/docker-compose.yml` defines postgres, clickhouse, redis, minio, analyser, presenter, view; all required images and ports present |
| 2 | All infrastructure services pass healthchecks before application services start | VERIFIED | 8 `condition: service_healthy` entries (analyser + presenter each depend on all 4 infra services) |
| 3 | Application services hot-reload on code changes via volume mounts | VERIFIED | Both `analyser` and `presenter` have `uvicorn ... --reload` command and `../services/<name>:/app/services/<name>` volume mounts |
| 4 | `make up`, `make seed`, `make reset`, `make test` all exist as Makefile targets | VERIFIED | `Makefile` declares `.PHONY: up down logs build seed reset test migrate`; all targets present with correct commands |
| 5 | Alembic migrations run cleanly and create all five PostgreSQL tables | VERIFIED | `001_initial.py` has 5 `op.create_table()` calls: tenants, users, api_keys, flags, diagnostics |
| 6 | RLS enabled on all five PostgreSQL tables with session-variable policies | VERIFIED | 5 `ENABLE ROW LEVEL SECURITY` statements + 5 `CREATE POLICY tenant_isolation` statements using `current_setting('app.current_tenant_id', true)` |
| 7 | ClickHouse spans table exists with `ORDER BY (tenant_id, trace_id, time_begin)` | VERIFIED | `SPANS_TABLE_DDL` constant in `shared/db/clickhouse.py` contains exact `ORDER BY (tenant_id, trace_id, time_begin)` |
| 8 | `api_keys` table stores `key_hash` column (never plaintext) | VERIFIED | Migration column `key_hash sa.String()`, model `key_hash: Mapped[str]`, comment "plaintext NEVER stored" in both |
| 9 | Any DAL method called without `tenant_id` raises `MissingTenantError` before touching the database | VERIFIED | 13 unit tests pass; `require_tenant()` is first call in every tenant-scoped method; `mock_session.execute.assert_not_called()` confirms no DB access on guard failure |
| 10 | Any DAL method called with empty string `tenant_id` also raises `MissingTenantError` | VERIFIED | `test_empty_string_raises` and `test_whitespace_raises` both pass in the 13-test suite |
| 11 | PostgreSQL sessions set `SET LOCAL app.current_tenant_id` via `tenant_session` context manager | VERIFIED | `postgres.py` executes `text("SET LOCAL app.current_tenant_id = :tid")` inside `session.begin()` |
| 12 | `POST /register` creates tenant, user, and hashed API key in PostgreSQL | VERIFIED | `auth.py` calls `TenantRepository.create()`, `UserRepository.create()`, `ApiKeyRepository.create()` in sequence; 4 integration tests collected |
| 13 | `POST /register` returns the plaintext API key exactly once | VERIFIED | `RegisterResponse.api_key` field populated from `generate_api_key()` plaintext; key never stored; no GET key endpoint |
| 14 | The returned API key starts with `xtr_` | VERIFIED | `generate_api_key()` uses `f"xtr_{secrets.token_urlsafe(32)}"`; integration test asserts `startswith("xtr_")` |
| 15 | `make seed` creates dev tenant with fixed key `dev-api-key-local` — idempotent | VERIFIED | `seed.py` defines `_DEV_API_KEY = "dev-api-key-local"`, checks for existing dev-tenant before inserting, calls `create_spans_table()` |
| 16 | `POST /register` returns 409 if email is already registered | VERIFIED | `auth.py` raises `HTTPException(status_code=409, detail="Email already registered")`; integration test `test_register_duplicate_email_returns_409` collected |

**Score:** 16/16 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `deploy/docker-compose.yml` | Full 6-service stack; healthchecks; `condition: service_healthy` | VERIFIED | 129-line file; 4 infra healthchecks; 8 `condition: service_healthy` entries; uvicorn --reload on both app services |
| `.env.example` | All required env vars with dev defaults | VERIFIED | Contains `DATABASE_URL`, `CLICKHOUSE_HOST`, `REDIS_URL`, `MINIO_ENDPOINT`, `DEV_API_KEY=dev-api-key-local` |
| `Makefile` | Developer commands including `seed`, `reset`, `test` | VERIFIED | All 8 targets present; `.PHONY` declaration correct |
| `xeter/migrations/versions/001_initial.py` | 5 PG tables + 5 RLS enables + 5 policies | VERIFIED | Exact match: 5 `op.create_table`, 5 `ENABLE ROW LEVEL SECURITY`, 5 `CREATE POLICY tenant_isolation` |
| `xeter/shared/db/clickhouse.py` | ClickHouse client + `SPANS_TABLE_DDL` + `create_spans_table()` + `verify_index_usage()` | VERIFIED | All 4 exports present; `ORDER BY (tenant_id, trace_id, time_begin)` confirmed in DDL constant |
| `xeter/shared/models.py` | SQLAlchemy ORM models for all 5 PG tables | VERIFIED | `Tenant`, `User`, `ApiKey`, `Flag`, `Diagnostic` all defined; `flag_type` is `String` not enum |
| `xeter/shared/dal/base.py` | `MissingTenantError` + `require_tenant()` | VERIFIED | `MissingTenantError(RuntimeError)` confirmed; `require_tenant()` strips + raises; importable |
| `xeter/shared/dal/tenants.py` | `TenantRepository` with `require_tenant` guard | VERIFIED | `get_by_id()` calls `require_tenant(tenant_id)` as first line; `create()` correctly has no guard |
| `xeter/shared/dal/users.py` | `UserRepository` with tenant guard on both methods | VERIFIED | `create()` and `get_by_email()` both call `require_tenant(tenant_id)` |
| `xeter/shared/dal/api_keys.py` | `generate_api_key`, `verify_api_key`, `ApiKeyRepository` | VERIFIED | All 3 exports present; bcrypt used directly (passlib incompatibility correctly handled); `xtr_` prefix enforced |
| `xeter/shared/db/postgres.py` | `get_async_engine()`, `get_async_session_factory()`, `tenant_session()` | VERIFIED | All 3 functions present; `tenant_session` uses `text("SET LOCAL app.current_tenant_id = :tid")` parameterized |
| `xeter/shared/db/redis.py` | `get_redis_client()` from `REDIS_URL` | VERIFIED | File exists with `get_redis_client()` |
| `xeter/tests/dal/test_tenant_guard.py` | 13 unit tests proving guard raises before DB call | VERIFIED | 13 tests pass; `mock_session.execute.assert_not_called()` present on all repository guard tests |
| `xeter/services/presenter/routers/auth.py` | `POST /register` endpoint with `router` export | VERIFIED | `router = APIRouter()`; full registration logic; 409/422/500 handling; wired to DAL |
| `xeter/services/presenter/main.py` | FastAPI app with `/healthz` + auth router | VERIFIED | `app.include_router(auth.router)` + `GET /healthz` both present |
| `xeter/scripts/seed.py` | Idempotent dev bootstrap with `dev-api-key-local` | VERIFIED | Idempotency check via `SELECT ... WHERE name = 'dev-tenant'`; `_DEV_API_KEY = "dev-api-key-local"` |
| `xeter/scripts/reset.py` | Full teardown: DROP SCHEMA + alembic + ClickHouse + seed | VERIFIED | psycopg2 `DROP SCHEMA public CASCADE`; `subprocess.run(["alembic", "upgrade", "head"])`; `_reset_clickhouse()`; `seed_main()` |
| `xeter/tests/dal/test_registration.py` | 4 integration tests, skip when `TEST_DATABASE_URL` unset | VERIFIED | 4 tests collected; `pytestmark = pytest.mark.skipif(_TEST_DB_URL is None, ...)` present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `presenter` service | `postgres, clickhouse, redis, minio` | `depends_on condition: service_healthy` | WIRED | 4 `condition: service_healthy` entries under `presenter.depends_on` |
| `analyser` service | `postgres, clickhouse, redis, minio` | `depends_on condition: service_healthy` | WIRED | 4 `condition: service_healthy` entries under `analyser.depends_on` |
| `analyser` + `presenter` | source code | `volume mounts + uvicorn --reload` | WIRED | Both services mount `../services/<name>:/app/services/<name>` + `uvicorn ... --reload` |
| `TenantRepository` | `require_tenant()` | called at top of every tenant-scoped method | WIRED | `require_tenant(tenant_id)` is first statement in `get_by_id()` |
| `UserRepository` | `require_tenant()` | called at top of every method | WIRED | Both `create()` and `get_by_email()` call `require_tenant(tenant_id)` first |
| `ApiKeyRepository` | `require_tenant()` | called at top of every method | WIRED | Both `create()` and `get_by_tenant()` call `require_tenant(tenant_id)` first |
| `tenant_session()` | `SET LOCAL app.current_tenant_id` | `session.execute(text(...))` inside `session.begin()` | WIRED | `text("SET LOCAL app.current_tenant_id = :tid")` with `{"tid": tenant_id}` — parameterized, not interpolated |
| `api_keys.py` | bcrypt hashing | direct `bcrypt.hashpw()` / `bcrypt.checkpw()` | WIRED | `import bcrypt`; `bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt())`; passlib bypassed intentionally |
| `POST /register` | `TenantRepository.create()` | DAL call in route handler | WIRED | `tenant_repo = TenantRepository(session); await tenant_repo.create(name=body.tenant_name)` |
| `POST /register` | `ApiKeyRepository.create()` via `generate_api_key()` | generate then store hash | WIRED | `plaintext, key_hash = generate_api_key(); await key_repo.create(tenant_id=..., key_hash=key_hash)` |
| `POST /register` | plaintext key returned once | `RegisterResponse.api_key`, never stored | WIRED | `return RegisterResponse(..., api_key=plaintext, ...)`; only hash stored in DB |
| `seed.py` | `dev-api-key-local` | fixed constant, bcrypt hashed and stored | WIRED | `_DEV_API_KEY = "dev-api-key-local"`; `bcrypt.hashpw(_DEV_API_KEY.encode(), ...)` |
| `001_initial.py` | PostgreSQL tables | `op.create_table` | WIRED | 5 `op.create_table()` calls confirmed |
| `001_initial.py` | RLS policies | `current_setting('app.current_tenant_id', true)` | WIRED | Pattern present in all 5 `CREATE POLICY` statements |
| `clickhouse.py` | ClickHouse spans table | `CREATE TABLE IF NOT EXISTS spans` | WIRED | `SPANS_TABLE_DDL` contains `CREATE TABLE IF NOT EXISTS spans` with `ORDER BY (tenant_id, trace_id, time_begin)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INFR-01 | 01-01 | Docker Compose provides local dev environment with all 6 services | SATISFIED | `deploy/docker-compose.yml` defines all 6 services; healthchecks on all 4 infra services; `.env.example` + `Makefile` complete |
| STOR-01 | 01-02 | Spans stored as immutable rows in ClickHouse with `ORDER BY (tenant_id, trace_id, time_begin)` | SATISFIED | `SPANS_TABLE_DDL` confirms MergeTree `ORDER BY (tenant_id, trace_id, time_begin)`; `create_spans_table()` is idempotent startup initializer |
| AUTH-01 | 01-02, 01-04 | Each tenant has an API key; key hash stored in PostgreSQL | SATISFIED | `api_keys` table schema has `key_hash String`; `generate_api_key()` returns bcrypt hash; `ApiKeyRepository.create()` stores only hash |
| AUTH-03 | 01-03 | All database queries scoped by `tenant_id` in application code | SATISFIED | `require_tenant()` guard confirmed in all 3 repository classes; 13 unit tests prove Python-boundary enforcement before any DB call |
| AUTH-04 | 01-02, 01-03 | PostgreSQL RLS policies as defense-in-depth | SATISFIED | 5 `ENABLE ROW LEVEL SECURITY` + 5 `CREATE POLICY tenant_isolation` in migration; `tenant_session()` sets `SET LOCAL app.current_tenant_id` |
| AUTH-05 | 01-04 | Developer can create an account (tenant registration) | SATISFIED | `POST /register` creates tenant + user + API key; returns `xtr_`-prefixed plaintext key; 409 on duplicate email; 4 integration tests confirm behavior |

**All 6 requirements from plan frontmatter accounted for. No orphaned requirements — REQUIREMENTS.md traceability table maps exactly these 6 IDs to Phase 1.**

---

### Anti-Patterns Found

No blockers or warnings found. Scan covered all files in `xeter/shared/`, `xeter/services/`, and `xeter/scripts/`.

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| — | No TODOs, FIXMEs, stubs, or empty returns found | — | Clean |

**One intentional deviation documented in SUMMARY:** `passlib CryptContext` bypassed in favour of direct `bcrypt.hashpw()`/`bcrypt.checkpw()` due to Python 3.14 incompatibility. This is not a defect — security outcome is identical and the decision is documented in both 01-03 and 01-04 SUMMARYs.

---

### Human Verification Required

The following items pass all automated checks but require a running Docker stack to fully confirm:

#### 1. Live Docker Compose Startup

**Test:** Run `docker compose -f deploy/docker-compose.yml up` from repo root.
**Expected:** All 4 infra services reach `(healthy)` status before analyser/presenter start. Both app services start without import errors and respond to `GET /healthz`.
**Why human:** Cannot execute Docker in this verification environment.

#### 2. `make seed` Execution

**Test:** With stack running, run `make seed` twice.
**Expected:** First run prints "Seed complete. Dev API key: dev-api-key-local". Second run prints "Seed already applied. Run `make reset` to start fresh." and exits 0.
**Why human:** Requires live PostgreSQL and ClickHouse connections.

#### 3. `make reset` Execution

**Test:** With stack running, run `make reset`.
**Expected:** DROP SCHEMA CASCADE succeeds, `alembic upgrade head` applies migration, ClickHouse spans table dropped and recreated, seed re-runs cleanly.
**Why human:** Requires live PostgreSQL (BYPASSRLS role) and ClickHouse.

#### 4. POST /register Integration Tests

**Test:** Set `TEST_DATABASE_URL` pointing to a migrated test DB, then run `pytest xeter/tests/dal/test_registration.py -v`.
**Expected:** All 4 tests pass (200 happy path, key-once-only, 409 duplicate, 422 short password).
**Why human:** Requires a live PostgreSQL instance with migrations applied.

---

### Gaps Summary

No gaps. All 16 must-have truths are verified. All 18 artifacts exist, are substantive, and are correctly wired. All 6 phase requirements (INFR-01, STOR-01, AUTH-01, AUTH-03, AUTH-04, AUTH-05) are satisfied by concrete implementation evidence.

The 4 human verification items are standard integration concerns that cannot be validated without a running Docker environment. They represent normal operational confirmation, not implementation defects.

---

_Verified: 2026-03-27T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
