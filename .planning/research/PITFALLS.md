# Pitfalls Research

**Domain:** Security hardening — adding auth hardening, RLS, DB constraints, and secrets hygiene to an existing FastAPI + Next.js AI observability platform (Xeter v1.3)
**Researched:** 2026-04-27
**Confidence:** HIGH (codebase inspected directly; official PostgreSQL docs, FastAPI community issues, and Docker Compose official docs verified)

---

## Critical Pitfalls

### Pitfall 1: httpOnly Cookie Silently Blocked by Browser in Dev Due to Cross-Port SameSite Rules

**What goes wrong:**
The refresh token cookie is set by FastAPI on `localhost:8000` and the Next.js frontend runs on `localhost:3000`. Browsers treat these as different origins (same hostname, different port = cross-origin under the SameSite model). With `SameSite=Strict`, the cookie is never sent on cross-origin requests — every call to `/auth/refresh` from the frontend appears as "no cookie" and returns 401. With `SameSite=None`, the browser requires `Secure=True` (HTTPS), which is impossible on plain `http://localhost`. Result: the cookie is set successfully (FastAPI returns `Set-Cookie` and the header appears in devtools), but the browser silently refuses to attach it on subsequent requests. The implementation appears to work in curl (which ignores SameSite) but fails in every real browser.

The current `presenter/main.py` has no CORS middleware configured at all, and `deps.py` issues tokens as `Authorization: Bearer` headers — switching to cookies requires adding CORS middleware first. Forgetting `allow_credentials=True` in the CORS config while setting cookies makes the browser reject the `Set-Cookie` header entirely.

**Why it happens:**
Developers follow production cookie security guidance (`SameSite=Strict`, `Secure=True`) without realizing neither setting is compatible with cross-port localhost development. The failure is invisible: no error from FastAPI, no browser console error — just a missing cookie.

**How to avoid:**
Drive cookie settings from an environment variable:
- Dev (`ENVIRONMENT=development`): `secure=False`, `samesite="lax"`, `httponly=True`
- Prod: `secure=True`, `samesite="strict"` (same-domain) or `samesite="lax"` (cross-subdomain), `httponly=True`

Add CORS middleware to `presenter/main.py` before any cookie work:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # never "*" with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The Next.js fetch calls to the refresh endpoint must include `credentials: "include"`. Without this, the browser does not attach cookies even if SameSite allows it.

**Warning signs:**
- `Set-Cookie` header appears in devtools but the cookie disappears after the login response
- `/auth/refresh` always returns 401 in the browser but works in curl
- No `CORSMiddleware` in `presenter/main.py`
- `allow_origins=["*"]` combined with `allow_credentials=True` (browsers block this combination)

**Phase to address:**
JWT refresh token endpoint phase. Must be the first thing verified in a real browser before any other auth work, because every subsequent test depends on it.

---

### Pitfall 2: Refresh Token Rotation Without Revocation — Logout Is Theatre

**What goes wrong:**
Adding a refresh token endpoint that rotates tokens (issues a new refresh token on each use) without a server-side revocation store means logout does nothing. The frontend calls `POST /logout`, the httpOnly cookie is cleared client-side, and the server returns 200. But any refresh token that was exfiltrated before logout — from a compromised network, XSS via a non-httpOnly cookie on the same origin, or a browser extension — remains valid until it naturally expires. The attacker silently continues refreshing access tokens indefinitely.

The gap is especially sharp here because the current system has no token expiry at all (`TOKEN_EXPIRE_HOURS = 24` in `deps.py`, no refresh cycle). Moving to 30-minute access tokens is only a security improvement if refresh tokens can actually be revoked.

**Why it happens:**
Token rotation (swap old for new on each use) is the visible security improvement and is straightforward to implement. The revocation store requires a database table, a lookup on every refresh request, and a write on logout — three extra steps that teams defer as "we'll add this later."

**How to avoid:**
Add a `refresh_tokens` PostgreSQL table:
```sql
refresh_tokens (
    jti          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now()
)
```
The refresh JWT payload must include a `jti` claim. On every `POST /auth/refresh`, look up `jti` in the table and verify `revoked_at IS NULL AND expires_at > now()`. On `POST /logout`, set `revoked_at = now()`. Add RLS (tenant_isolation policy using `app.current_tenant_id`) to the table.

If the revocation table is intentionally deferred for MVP, document the gap explicitly and cap refresh token lifetime at 7 days (not 30 days or longer).

**Warning signs:**
- `POST /logout` only calls `response.delete_cookie()` with no database write
- The refresh token JWT payload has no `jti` claim
- No `refresh_tokens` table (or equivalent Redis set) in the schema

**Phase to address:**
JWT refresh token endpoint phase. The revocation store must be decided before the endpoint is built — the `jti` claim must be in the JWT from day one.

---

### Pitfall 3: `current_setting('app.current_tenant_id', true)` With `missing_ok=True` Silences Missing-Variable Cases Instead of Raising

**What goes wrong:**
All existing RLS policies use `current_setting('app.current_tenant_id', true)` with the `missing_ok=true` flag. When the session variable is not set, `current_setting` returns NULL, making the USING clause `tenant_id::text = NULL`, which is always false in SQL. Rows are invisibly filtered — no error, no 401, just empty results. This is correct for the migration role (which must run without the variable set), but it becomes a silent footgun for application code.

When span_scores RLS is enabled with the same policy pattern, any code path that reads from span_scores without first calling `set_config('app.current_tenant_id', ...)` will silently return zero rows. The worker's `score_writer.py` connects without setting the variable (it uses psycopg2 directly, no `tenant_session` context manager). If future code reads span_scores via that same connection, it will see nothing — no exception, no indication of the problem.

**Why it happens:**
`missing_ok=true` is the correct choice for the migration role. Developers carry this exact pattern into application-facing code without recognizing that it trades an explicit error for silent invisibility. The bug manifests as "no data" rather than "permission denied," making it extremely hard to diagnose.

**How to avoid:**
Write an integration test that asserts the RLS policy is enforced AND does not silently return empty results for wrong reasons:
1. Connect to PostgreSQL without calling `set_config`
2. Assert `SELECT COUNT(*) FROM span_scores` returns 0 even when rows exist
3. Connect with an incorrect tenant_id and assert the same

For application code, document that any new service or code path that queries RLS-protected tables must call `set_config` before querying. The `tenant_session()` context manager in `shared/db/postgres.py` handles this correctly for async paths — make it the required pattern, not an optional one.

**Warning signs:**
- Any SELECT against span_scores, flags, or diagnoses outside a `tenant_session()` context manager block
- New services that have their own database connection without importing `tenant_session()`
- Queries returning empty results when data exists (wrong tenant variable) treated as "no data found" rather than investigated

**Phase to address:**
span_scores RLS policy phase. Write the missing-variable integration test in the same PR that adds the policy.

---

### Pitfall 4: BYPASSRLS Role Used for the Entire Worker — "Scoped to Inserts Only" Requires Two Roles, Not One DATABASE_URL

**What goes wrong:**
The v1.3 target states "Worker BYPASSRLS scoped to insert paths only." But the Worker has a single `DATABASE_URL` environment variable (visible in `docker-compose.yml`) that connects as a BYPASSRLS role. `write_scores()` in `score_writer.py` and `write_flags()` in `flag_writer.py` both derive their DSN from the same `DATABASE_URL`. There is no way to scope BYPASSRLS to inserts at the code level — BYPASSRLS is a role attribute, not an operation attribute. Any read operation that uses the same DATABASE_URL also bypasses RLS.

If any future worker code (calibration read, health check, admin query) uses the Worker's DATABASE_URL for a SELECT, it bypasses all tenant isolation silently. The scoping intent cannot be enforced by documentation alone.

**Why it happens:**
"Scope to inserts only" sounds like a code comment or a guard at the Python level. It actually requires creating two distinct PostgreSQL roles with different capabilities and two distinct connection strings.

**How to avoid:**
Create two PostgreSQL roles in the migrations:
- `xeter_worker_writer`: BYPASSRLS, INSERT-only GRANT on `span_scores` and `flags`
- `xeter_app`: no BYPASSRLS, standard SELECT/INSERT/UPDATE GRANTs, reads via `set_config` + RLS

Add two environment variables to the Worker service in docker-compose:
- `WORKER_WRITE_DATABASE_URL` — used by `write_scores()` and `write_flags()`
- `DATABASE_URL` — app role connection used for any future reads (with tenant_session)

Verify by connecting as `xeter_worker_writer` and attempting `SELECT * FROM span_scores` — it should return all rows (BYPASSRLS). Then verify that a misconfigured read through this connection is detectable by the role name in audit logs.

**Warning signs:**
- Worker service has only one `DATABASE_URL` in docker-compose
- `_get_dsn()` in `score_writer.py` reads from `DATABASE_URL` for both reads and writes
- No second PostgreSQL role named anything like `worker_writer` or `app_role` in the migrations

**Phase to address:**
span_scores RLS phase. The role architecture must be established before the span_scores RLS migration runs, because enabling RLS with a BYPASSRLS role still covering reads defeats the policy entirely.

---

### Pitfall 5: Table Owner Bypasses All RLS Policies — `FORCE ROW LEVEL SECURITY` Missing From All Tables

**What goes wrong:**
PostgreSQL table owners bypass RLS by default, even when RLS is enabled. The migration comment in `001_initial.py` states: "The migration role must be a superuser or BYPASSRLS role." That role owns all five tables. None of the existing migrations call `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. This means the table owner can SELECT across all tenants without setting any session variable. Every admin script, every Alembic migration, and any future service that reuses the migration DATABASE_URL can read all tenant data silently.

This is not a theoretical risk: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are two distinct commands with distinct semantics. The existing schema only uses `ENABLE`.

**Why it happens:**
Most RLS tutorials show only `ENABLE ROW LEVEL SECURITY`. The `FORCE` variant is a lesser-known second step that appears in the PostgreSQL docs but is absent from most examples.

**How to avoid:**
Add a new migration that applies `FORCE ROW LEVEL SECURITY` to every table that has RLS enabled:
```sql
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE flags FORCE ROW LEVEL SECURITY;
ALTER TABLE diagnostics FORCE ROW LEVEL SECURITY;
ALTER TABLE diagnoses FORCE ROW LEVEL SECURITY;
```
Add this to the span_scores RLS migration so both tables get FORCE together with ENABLE.

Verify with: `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('flags', 'diagnoses', 'span_scores')` — both `relrowsecurity` and `relforcerowsecurity` must be `t`.

**Warning signs:**
- `SELECT relforcerowsecurity FROM pg_class WHERE relname = 'flags'` returns `f`
- A psql connection as the migration role can SELECT rows from multiple tenants without setting `app.current_tenant_id`
- Migrations 001–003 contain `ENABLE ROW LEVEL SECURITY` but no `FORCE ROW LEVEL SECURITY`

**Phase to address:**
span_scores RLS phase. Add `FORCE ROW LEVEL SECURITY` for all existing tables in the same migration as the span_scores policy — one retroactive fix, not six separate migrations.

---

### Pitfall 6: CHECK Constraint on `diagnoses` With Existing Data Blocks Writes During Migration

**What goes wrong:**
Adding `CHECK (verdict IN ('model','architecture','prompt','unknown'))` to the `diagnoses` table using a standard `op.create_check_constraint()` call acquires an `ACCESS EXCLUSIVE` lock and performs a full table scan to validate all existing rows before the constraint becomes active. On a live system, this blocks all INSERTs and UPDATEs to `diagnoses` for the duration of the scan. If any existing row contains a verdict value outside the allowed set — possible if an LLM returned an unexpected value that passed through the "fail-clean" pipeline — the migration fails entirely and rolls back. The constraint is not applied, there is no indication of which rows violated it, and the migration must be rerun after manual data repair.

The `diagnoses` table has live data from v1.2 (LLM Diagnosticer). The same risk applies to `severity IN ('low','medium','high')`. Both constraints are on the same table with the same existing rows.

**Why it happens:**
`op.create_check_constraint()` defaults to non-NOT VALID mode. Developers test the migration against an empty development table where it passes instantly. The lock and scan only become a problem in production where data exists.

**How to avoid:**
Use a two-step approach in Alembic. Step 1 installs the constraint without validating existing data (only new writes are checked):
```python
op.execute(sa.text(
    "ALTER TABLE diagnoses ADD CONSTRAINT chk_verdict "
    "CHECK (verdict IN ('model','architecture','prompt','unknown')) NOT VALID"
))
```
Step 2, run after pre-flight verification, validates existing rows with a weaker lock that does not block writes:
```python
op.execute(sa.text("ALTER TABLE diagnoses VALIDATE CONSTRAINT chk_verdict"))
```
Pre-flight query to run before step 2:
```sql
SELECT verdict, count(*) FROM diagnoses
WHERE verdict NOT IN ('model','architecture','prompt','unknown')
GROUP BY verdict;
```
If this returns any rows, update them before VALIDATE runs. Apply the same two-step pattern to the `severity` constraint.

**Warning signs:**
- A single `op.create_check_constraint("diagnoses", "chk_verdict", ...)` call without `postgresql_not_valid=True`
- No pre-flight query in the migration runbook
- Migration tested only against an empty diagnoses table in development

**Phase to address:**
CHECK constraint migration phase. The NOT VALID pattern must be decided before any migration is written, not retrofitted after a production failure.

---

### Pitfall 7: bcrypt Cost Factor 12 Makes CI Tests Slow — Module-Level Hash Computed on Every Import

**What goes wrong:**
`test_auth_login.py` line 32 calls `bcrypt.hashpw(USER_PASSWORD.encode("utf-8"), bcrypt.gensalt())` at module level — outside any function or fixture. This runs every time the test module is imported by pytest, before any test function executes. At default cost factor 10, this takes ~100ms. At cost factor 12 (the v1.3 target minimum), it takes 300–600ms on a development machine and 600–1200ms on a CI runner with throttled CPU. With more auth tests added in v1.3, module-level bcrypt calls accumulate across the test suite.

The deeper issue: the bcrypt CI enforcement test (verifying that production code uses rounds ≥ 12) will itself need to call `bcrypt.gensalt(rounds=12)` to verify the cost. If implemented naively, the enforcement test adds another 600ms+ of bcrypt compute to every CI run.

**Why it happens:**
The module-level hash was placed outside a fixture for simplicity. At cost factor 10 (the bcrypt default), the impact is barely noticeable. The developer writing the test did not anticipate the cost factor being raised. Moving from 10 to 12 rounds doubles the time twice (4x slowdown).

**How to avoid:**
Move all bcrypt calls in test files to pytest fixtures with `scope="session"` so the hash is computed once per test session, not once per module import:
```python
@pytest.fixture(scope="session")
def hashed_password():
    # rounds=4 is intentional — fastest valid bcrypt for tests.
    # Do not raise this in tests; test the round count separately.
    return bcrypt.hashpw(b"correct-horse-battery", bcrypt.gensalt(rounds=4)).decode()
```
`rounds=4` is the minimum bcrypt accepts. It makes fixtures 64x faster than `rounds=10`. Tests still exercise the bcrypt API correctly — they are testing application logic, not cryptographic strength.

The CI enforcement test should verify the production `bcrypt.gensalt()` call uses `rounds >= 12` by inspecting the hash output (the `$2b$12$` prefix encodes the cost factor) or by mocking `gensalt` and asserting it was called with the correct rounds argument — not by calling `hashpw` with production cost in the test body.

**Warning signs:**
- `bcrypt.hashpw(...)` or `bcrypt.gensalt()` appears at module level (outside any function/fixture/class) in test files
- CI test run time increases by more than 20 seconds after raising cost factor
- The bcrypt enforcement test takes more than 2 seconds individually
- `pytest --collect-only` takes noticeably longer than before

**Phase to address:**
bcrypt cost enforcement phase. The fixture refactor must be in the same PR that raises the production cost factor — raising cost factor without fixing test fixtures causes CI timeout failures immediately.

---

### Pitfall 8: `CHANGE_ME_BEFORE_DEPLOY` Placeholders Don't Cover the Two Actual Leak Vectors

**What goes wrong:**
Replacing `xeter_dev_password` with `CHANGE_ME_BEFORE_DEPLOY` in `docker-compose.yml` prevents accidental production deployment with the dev password. But the two real leak vectors are different:

**Leak vector 1 — the `:-fallback` default:** `docker-compose.yml` currently has `SECRET_KEY: ${SECRET_KEY:-dev-secret-key-change-in-production}`. If a developer copies docker-compose.yml to a new environment and forgets to set `SECRET_KEY` in `.env`, the fallback `dev-secret-key-change-in-production` is used silently. The service starts, appears healthy, and signs JWTs with a known weak key. `deps.py` reinforces this with `SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")` — two layers of silent fallback.

**Leak vector 2 — `.env` committed to git:** `generate-secrets.sh` writes a `.env` file. If `.env` is not in `.gitignore` at the time the file is created, the first `git add .` commits all generated secrets. Git history is permanent — rotating the secrets does not remove the historical commit. The ANTHROPIC_API_KEY is particularly dangerous here: it was already present in `docker-compose.yml` as `${ANTHROPIC_API_KEY:-}` and would appear in the generated `.env`.

**Why it happens:**
Teams treat "use environment variables" as the secure pattern. It is more secure than hardcoding, but env vars are visible via `docker inspect <container>`, appear in CI/CD logs on failure, and are committed if `.gitignore` is incomplete.

**How to avoid:**
1. Remove ALL fallback defaults for security-sensitive values in docker-compose and application code. `SECRET_KEY: ${SECRET_KEY}` (no `:-fallback`) causes docker-compose to fail loudly if the variable is unset. In `deps.py`: `SECRET_KEY = os.environ["SECRET_KEY"]` — `KeyError` on startup, not silent fallback.

2. Ensure `.env` is in `.gitignore` before writing `generate-secrets.sh`. Verify with `git check-ignore -v .env` — if it prints nothing (not ignored), the file will be committed.

3. Add a guard at the top of `generate-secrets.sh`:
```bash
if git ls-files --error-unmatch .env 2>/dev/null; then
    echo "ERROR: .env is already tracked by git. Remove it from tracking first."
    exit 1
fi
```

4. Add `.env.example` (with `CHANGE_ME` values) to version control. The generate-secrets script copies from `.env.example` and substitutes random values.

**Warning signs:**
- `${VAR:-fallback-value}` pattern in docker-compose.yml for any secret
- `os.environ.get("SECRET_KEY", "...")` in any service code (the `.get()` with default is the problem)
- `git check-ignore -v .env` prints nothing
- `generate-secrets.sh` does not check if `.env` is git-tracked before writing

**Phase to address:**
Secrets hygiene phase. The `:-fallback` removal and `.gitignore` verification must happen before the generate-secrets script is written, not as a follow-up.

---

### Pitfall 9: MinIO Bucket Policy — `mc mb` Creates the Bucket But Does Not Enforce Private Policy

**What goes wrong:**
The `minio-init` container in `docker-compose.yml` runs `mc mb local/xeter-payloads --ignore-existing` to create the bucket. MinIO's default for a newly created bucket is private (no anonymous access). But the policy state is stored in MinIO's internal state on the volume — it is not re-applied on container restart. Two failure modes:

1. A developer manually runs `mc policy set download local/xeter-payloads` for debugging (to view an object directly in the browser). The policy persists on the volume after they stop debugging. No alert, no indication — the bucket silently remains public.

2. MinIO's default "private" is implemented as an absence of a policy, not an explicit DENY. The absence of a policy means anonymous access defaults to denied, but it also means the effective policy is not visible in the IAM audit trail. An explicit `mc policy set none` creates a policy document that is auditable.

Additionally, all five application services (Analyser, Presenter, Worker, Diagnosticer, embedder) use the same `S3_ACCESS_KEY` / `S3_SECRET_KEY` root credentials. If any one service has a vulnerability, the attacker gets full read/write access to the entire bucket across all tenants.

**Why it happens:**
MinIO deprecated S3-style ACLs in favour of bucket policies. Developers accustomed to AWS S3 `private` ACL on bucket creation assume `mc mb` sets the same posture. MinIO's ACL implementation is intentionally limited — `mc policy` is the correct tool, not `mc mb` flags.

**How to avoid:**
Update the `minio-init` command to explicitly set the private policy after bucket creation:
```
mc mb local/xeter-payloads --ignore-existing && mc policy set none local/xeter-payloads
```

Add a verification step to the runbook: after deployment, run `mc policy get local/xeter-payloads`. Expected output: `Access permission for 'local/xeter-payloads' is 'none'`. Any other output is a misconfiguration.

For the IAM documentation, create per-service MinIO service accounts:
- Analyser: `s3:PutObject` only
- Presenter: `s3:GetObject` only
- Worker: `s3:PutObject` + `s3:GetObject`

Root credentials (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`) should not appear in application service environment blocks.

**Warning signs:**
- `minio-init` command does not include `mc policy set none` after `mc mb`
- All services in docker-compose share identical `S3_ACCESS_KEY` / `S3_SECRET_KEY` values
- No `mc policy get` verification step in the runbook
- A browser can load `http://localhost:9100/xeter-payloads/any-key` without authentication

**Phase to address:**
MinIO bucket policy documentation phase. The `mc policy set none` addition to minio-init must ship in the same change as the documentation.

---

### Pitfall 10: Refresh Token + Next.js 15 App Router — Client Components Cannot Read httpOnly Cookies, Access Token Must Be in the Response Body

**What goes wrong:**
With the refresh token in an httpOnly cookie and the access token used as a `Bearer` header (the current system pattern in `deps.py`), the frontend needs to silently refresh the access token when it expires. The standard approach — a fetch interceptor that catches 401, calls `/auth/refresh`, and retries — works only if `/auth/refresh` returns the new access token in the JSON response body.

If the implementation sets both tokens as cookies (moving away from the current Bearer header pattern), Client Components in Next.js 15 App Router cannot read httpOnly cookies at all — `document.cookie` does not return httpOnly cookies by design. The interceptor cannot get the new access token. The user is silently logged out.

The `presenter/deps.py` currently returns tokens as Bearer headers and reads them from the `Authorization` header — this is correct. The risk is that developers building the refresh endpoint copy cookie-only patterns from tutorials and return the new access token only as a cookie.

**Why it happens:**
Many refresh token tutorials target server-rendered apps where cookies carry everything and JS never needs to read the token. In Next.js 15 with a mix of Server and Client Components, the token must be readable by Client Component fetch interceptors.

**How to avoid:**
The `/auth/refresh` endpoint contract must:
1. Read the refresh token from the httpOnly cookie (unreadable by JS — sent automatically by browser)
2. Validate and rotate it (write new httpOnly refresh cookie to the response)
3. Return the new short-lived access token in the JSON response body: `{"access_token": "...", "expires_in": 1800}`

The Client Component fetch interceptor reads `response.json().access_token` and stores it in memory (not in any cookie or localStorage). This is the only pattern compatible with httpOnly refresh cookies + Client Component fetch interceptors.

**Warning signs:**
- `/auth/refresh` returns 200 with no JSON body (only sets cookies)
- The access token is stored in a non-httpOnly cookie to make it readable by JS (defeats the XSS protection)
- The frontend interceptor uses `document.cookie` to read the access token after refresh
- No `expires_in` field in the refresh response (frontend cannot schedule preemptive refresh)

**Phase to address:**
JWT refresh token endpoint phase. The response contract must be decided before any frontend integration code is written.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single `DATABASE_URL` for both Worker writes and future reads | Zero additional config | Any future read path in Worker bypasses RLS silently; impossible to scope BYPASSRLS to inserts in code | Never — split into write and read connection strings from the start |
| `os.environ.get("SECRET_KEY", "default")` fallback | App starts without config | Weak known key used silently when env var not set; no startup failure to alert | Never for security-critical secrets |
| `bcrypt.hashpw()` at module scope in tests | Simple fixture setup | CI slowdown at cost factor 12; makes enforcement tests slow and unreliable | Never — use `scope="session"` fixtures with `rounds=4` |
| Single S3 credential pair for all services | Simple docker-compose | Full bucket access from any compromised container | Acceptable in local dev; never in production deployment |
| `ENABLE ROW LEVEL SECURITY` without `FORCE` | Migrations run cleanly as owner | Table owner (migration role) bypasses all tenant policies silently | Never |
| Deferred refresh token revocation | No extra table needed | Logout does not invalidate exfiltrated tokens | Only if refresh token lifetime ≤ 1 hour AND explicitly documented as a known gap |
| Single-step CHECK constraint migration | Simpler migration code | Full table lock blocks writes during scan; fails if any existing row violates constraint | Never on tables with live data |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-----------------|
| FastAPI `set_cookie` + Next.js cross-origin | `secure=True` on http://localhost | `secure=False` in dev (env-driven), `secure=True` in prod only |
| FastAPI CORS + cookie credentials | `allow_origins=["*"]` with `allow_credentials=True` | Browsers block this combination; use explicit `allow_origins=["http://localhost:3000"]` |
| asyncpg SQLAlchemy pool + SET LOCAL | Session variable lost when connection returns to pool | The `tenant_session()` context manager in `shared/db/postgres.py` sets the variable inside `session.begin()` — correct, but only if all queries go through it |
| MinIO `mc mb` on init | Assuming `mc mb` sets private policy | Must follow with `mc policy set none` explicitly |
| Alembic `create_check_constraint` + live data | Constraint added without NOT VALID holds full ACCESS EXCLUSIVE lock | Two-step: `ALTER TABLE ... ADD CONSTRAINT ... NOT VALID`, then `VALIDATE CONSTRAINT` |
| Docker env var + generated `.env` | `.env` committed to git on first `git add .` | Verify `.gitignore` entry before writing generate-secrets.sh; add git-tracked guard in the script |
| psycopg2 score_writer + no `tenant_session` | Score reads using BYPASSRLS connection bypass all RLS policies | BYPASSRLS connection restricted to writes; reads use app role with tenant_session |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| `missing_ok=true` in RLS policy used in application code | Missing tenant variable returns empty results (orphaned rows) rather than permission error — invisible bug | Integration test asserting COUNT=0 without set_config; document tenant_session() as required, not optional |
| Refresh token without revocation table | Stolen tokens valid until natural expiry even after logout | `refresh_tokens` table with `jti` and `revoked_at`; verify on each refresh request |
| BYPASSRLS role used for Worker reads | Cross-tenant data visible to any Worker read path | Separate roles: BYPASSRLS for writes only, app role for reads |
| `os.environ.get("SECRET_KEY", "fallback")` pattern | Weak known key used in production if env var not set | `os.environ["SECRET_KEY"]` — KeyError on startup forces explicit configuration |
| All services share same S3 credentials | One compromised service = full bucket read/write | Per-service MinIO IAM service accounts with least-privilege policies |
| `ENABLE ROW LEVEL SECURITY` without `FORCE` | Table owner bypasses all tenant isolation policies | `ALTER TABLE ... FORCE ROW LEVEL SECURITY` on every RLS-protected table |
| Single-step CHECK constraint on live table | Blocks writes during full table scan; fails on first bad row with no row identification | NOT VALID + VALIDATE CONSTRAINT two-step; pre-flight violation query before VALIDATE |

---

## "Looks Done But Isn't" Checklist

- [ ] **httpOnly cookie in dev:** Cookie appears in browser devtools Application > Cookies AND the `Cookie` header is present on the subsequent refresh request — `Set-Cookie` received is not the same as cookie sent
- [ ] **Refresh token revocation:** POST /logout writes to the database. Test: call /logout, then POST /auth/refresh with the old cookie — should return 401, not a new token
- [ ] **span_scores RLS:** Connect via psql without calling `set_config`. Assert `SELECT COUNT(*) FROM span_scores` returns 0 even when rows exist — silently empty, not error
- [ ] **BYPASSRLS scoping:** grep the codebase for all code paths that call `_get_dsn()` or read `DATABASE_URL` in the Worker. Verify none are used for SELECT operations
- [ ] **FORCE ROW LEVEL SECURITY:** Run `SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN ('flags','diagnoses','span_scores','users','api_keys')` — all must be `t`
- [ ] **CHECK constraint NOT VALID:** After step 1 migration, run `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'chk_verdict'` — must contain `NOT VALID` annotation
- [ ] **bcrypt enforcement test:** Temporarily change `gensalt(rounds=12)` to `gensalt(rounds=10)` and verify the CI test fails. Then restore and verify the test passes
- [ ] **Secret fallback removed:** `grep -r 'environ.get.*SECRET_KEY' xeter/` — any match with a second argument is a bug. `grep ':-' deploy/docker-compose.yml` — any match on a secret variable is a bug
- [ ] **MinIO private policy:** After minio-init starts, run `mc policy get local/xeter-payloads` — expected output is `none`, not `download` or `public`
- [ ] **.env gitignored:** `git check-ignore -v .env` returns a hit (shows the .gitignore rule that matches). If it prints nothing, `.env` is not ignored

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| httpOnly cookie SameSite wrong in dev | LOW | Update FastAPI `set_cookie` with env-driven `samesite` parameter; add CORSMiddleware with explicit origins; retest in browser |
| Refresh token revocation missing post-launch | MEDIUM | Add `refresh_tokens` table migration; invalidate all existing tokens (forced re-login for all users); deploy |
| BYPASSRLS leakage discovered after RLS enabled | MEDIUM | Create new app role without BYPASSRLS; update DATABASE_URL references; rolling redeploy of affected services |
| CHECK constraint migration fails due to existing violations | LOW | Run pre-flight violation query; UPDATE offending rows manually; re-run NOT VALID migration; then VALIDATE |
| `.env` committed to git | HIGH | Rotate ALL secrets immediately (assume compromised); `git filter-repo` to scrub history; regenerate all credentials; invalidate LLM API keys with providers |
| MinIO bucket accidentally set to public | HIGH | `mc policy set none` immediately; audit MinIO access logs; rotate S3_ACCESS_KEY and S3_SECRET_KEY for all services |
| `FORCE ROW LEVEL SECURITY` not applied | LOW | New migration: `ALTER TABLE ... FORCE ROW LEVEL SECURITY` for each table; no data change required |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| httpOnly cookie SameSite cross-origin in dev | JWT refresh token endpoint | Browser manual test: cookie sent on refresh call from localhost:3000 to localhost:8000 |
| Refresh token no revocation store | JWT refresh token endpoint | Test: POST /logout → POST /auth/refresh with old cookie → 401 |
| SET LOCAL silent empty results | span_scores RLS policy | Integration test: connect without set_config, assert COUNT=0 with data present |
| BYPASSRLS role used for reads | span_scores RLS (role architecture) | Two connection strings in Worker docker-compose; `\du` shows BYPASSRLS on writer role only |
| Table owner bypasses RLS (FORCE missing) | span_scores RLS migration | `SELECT relforcerowsecurity FROM pg_class` returns t for all RLS tables |
| CHECK constraint locks live table | CHECK constraint migration | NOT VALID in step 1 confirmed; VALIDATE runs separately with pre-flight query |
| bcrypt cost CI tests slow | bcrypt enforcement CI phase | CI enforcement test fails at rounds=10, passes at rounds=12, completes in under 2 seconds |
| CHANGE_ME + env fallback still leaks | Secrets hygiene phase | `git check-ignore -v .env` returns hit; `grep 'environ.get.*SECRET_KEY'` finds no defaults |
| MinIO no explicit private policy | Bucket policy documentation phase | `mc policy get` returns none; minio-init command includes explicit `mc policy set none` |
| Refresh token + App Router — access token not in response body | JWT refresh token endpoint | Interceptor reads `response.json().access_token`, not `document.cookie` |

---

## Sources

- [FastAPI GitHub Issues — Cookies not set for cross-domain requests #3267](https://github.com/fastapi/fastapi/issues/3267)
- [FastAPI CORS and Cookie Fix for React/Next.js](https://sqlpey.com/javascript/cors-cookie-fastapi-react-fix/)
- [Chrome 80 SameSite=None Secure impact on localhost development](https://medium.com/swlh/how-the-new-chrome-80-cookie-rule-samesite-none-secure-affects-web-development-c06380220ced)
- [PostgreSQL Documentation: Row Security Policies — BYPASSRLS and FORCE ROW LEVEL SECURITY](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Common Postgres Row-Level-Security footguns — Bytebase](https://www.bytebase.com/blog/postgres-row-level-security-footguns/)
- [constraint-missing-not-valid — Squawk linter for Postgres migrations](https://squawkhq.com/docs/constraint-missing-not-valid)
- [Alembic Migrations Without Downtime — Exness Tech Blog](https://medium.com/exness-blog/alembic-migrations-without-downtime-a3507d5da24d)
- [Zero-Downtime Alembic Migrations on PostgreSQL — Gold Lapel](https://goldlapel.com/grounds/replication-scaling-cloud/alembic-zero-downtime-migrations)
- [Stop Using Environment Variables for Secrets in Docker Compose — Medium](https://medium.com/@bernard.sofeng/stop-using-environment-variables-for-secrets-in-docker-compose-fd0be09ebcc5)
- [Manage secrets securely in Docker Compose — Docker Official Docs](https://docs.docker.com/compose/how-tos/use-secrets/)
- [asyncpg — session parameters not preserved in connection pool — Issue #541](https://github.com/MagicStack/asyncpg/issues/541)
- [MinIO Bucket Policies — copyprogramming.com guide](https://copyprogramming.com/howto/simple-minio-bucket-policy)
- [MinIO docs: private vs public — Issue #1508](https://github.com/minio/minio/issues/1508)
- [Essential JWT Security Part 2: Refresh Tokens and Revocation — DEV Community](https://dev.to/rahuls24/essential-jwt-security-part-2-refresh-tokens-and-revocation-made-simple-12pf)
- Xeter codebase direct inspection: `xeter/migrations/versions/001_initial.py`, `xeter/migrations/versions/002_span_scores.py`, `xeter/migrations/versions/003_diagnoses.py`, `xeter/services/presenter/deps.py`, `xeter/services/presenter/routers/auth.py`, `xeter/services/worker/score_writer.py`, `xeter/services/worker/main.py`, `deploy/docker-compose.yml`, `xeter/tests/presenter/test_auth_login.py`

---
*Pitfalls research for: Xeter v1.3 Security Hardening — adding auth hardening, RLS, DB constraints, and secrets hygiene to an existing FastAPI + Next.js system*
*Researched: 2026-04-27*
