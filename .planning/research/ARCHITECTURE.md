# Architecture Research

**Domain:** Security hardening — FastAPI + Next.js 15 + PostgreSQL (v1.3)
**Researched:** 2026-04-27
**Confidence:** HIGH (all claims verified against codebase + official PostgreSQL docs)

---

## Standard Architecture

### System Overview (existing, unchanged by v1.3)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client Layer                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Next.js 15 View  (port 3000)                                │   │
│  │  - Zustand auth store (sessionStorage → migrating to cookie) │   │
│  │  - next.config.ts rewrites /api/* → http://presenter:8000/*  │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                        API Layer                                     │
│  ┌──────────────────┐          ┌──────────────────┐                 │
│  │  Analyser        │          │  Presenter       │                 │
│  │  (port 4318)     │          │  (port 8000)     │                 │
│  │  OTel ingestion  │          │  - /auth/login   │                 │
│  └────────┬─────────┘          │  - /auth/refresh │  (NEW v1.3)    │
│           │ Redis BRPOP        │  - /spans        │                 │
│  ┌────────┴─────────┐          │  - /diagnose     │                 │
│  │  Worker          │          └────────┬─────────┘                 │
│  │  (no port)       │                   │ httpx forward             │
│  │  embedding+flags │          ┌────────┴─────────┐                 │
│  └──────────────────┘          │  Diagnosticer    │                 │
│                                │  (port 8001)     │                 │
│                                │  LLM root cause  │                 │
│                                └──────────────────┘                 │
├─────────────────────────────────────────────────────────────────────┤
│                        Storage Layer                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │ PostgreSQL │  │ ClickHouse │  │   Redis    │  │   MinIO    │    │
│  │ (port 5432)│  │ (port 8123)│  │ (port 6379)│  │ (port 9100)│    │
│  │ RLS on 6   │  │ spans OLAP │  │ work queue │  │ S3 payloads│    │
│  │ of 7 tables│  │            │  │            │  │            │    │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | v1.3 Change |
|-----------|----------------|-------------|
| Analyser | OTel span ingestion, ClickHouse + S3 write | None |
| Worker | Embedding, heuristic flagging, writes flags + span_scores | score_writer.py modified |
| Presenter | Auth, dashboard API, Diagnosticer proxy | New /auth/refresh route added |
| Diagnosticer | LLM root-cause analysis, writes diagnoses | None |
| View (Next.js) | Dashboard UI, /api/* proxy to Presenter | Two Route Handlers added |
| PostgreSQL | Relational storage with RLS | span_scores RLS + diagnoses CHECK constraints |

---

## v1.3 Integration Points

### 1. JWT Refresh Token Flow

**Where the cookie gets set — same-origin topology answer:**

The Next.js app proxies all `/api/*` requests to the Presenter via `next.config.ts` rewrites. This means the browser's effective origin for all API calls is `localhost:3000` (or the deployed domain). The Presenter runs at `presenter:8000` inside Docker — a different host, but the browser never sees it directly.

**The consequence:** A `Set-Cookie` header returned by the Presenter and passed through Next.js rewrites is not forwarded to the browser by default — Next.js rewrites strip upstream response headers including `Set-Cookie`. Even if they were forwarded, the cookie domain would be the upstream host (`presenter:8000`), which the browser would reject. Therefore the Presenter cannot set a cookie that the browser stores.

**Correct integration pattern — Next.js Route Handler as cookie setter:**

```
Browser → POST /api/login (Next.js origin)
  → Next.js Route Handler (NEW: app/api/login/route.ts)
    → server-side fetch: POST http://presenter:8000/login
      ← {session_token, refresh_token}  (both in JSON body)
    ← Set-Cookie: refresh_token=...; HttpOnly; SameSite=Lax; Path=/api/auth/refresh
    ← {session_token} (in JSON body, for Zustand in-memory access token)
```

The Route Handler is a new file at `services/view/src/app/api/login/route.ts`. It calls the Presenter, receives both tokens in the JSON response body (Presenter does not set any cookies), then uses Next.js `cookies().set()` to write the httpOnly refresh token cookie on the browser-facing response. The `cookies().set()` API is only available in Route Handlers and Server Actions.

The login rewrite rule in `next.config.ts` must NOT match `/api/login` anymore once the Route Handler exists — Next.js Route Handlers take priority over rewrites for the same path, so no change to `next.config.ts` is required.

**The Presenter change — /auth/refresh endpoint:**

`POST /auth/refresh` is added to `xeter/services/presenter/routers/auth.py`. It receives the refresh token in the request body (the Next.js Route Handler reads the httpOnly cookie and forwards the raw token value as a plain JSON field), validates it, and returns a new short-lived access token.

```
Browser → POST /api/auth/refresh (Next.js origin, cookie sent automatically)
  → Next.js Route Handler (NEW: app/api/auth/refresh/route.ts)
    → reads refresh_token cookie from incoming request
    → server-side fetch: POST http://presenter:8000/auth/refresh
      body: {refresh_token: "<value from cookie>"}
      ← {session_token: "new-short-lived-jwt"}
    ← {session_token} (Zustand updates in-memory access token)
```

**Token lifetimes and storage:**

| Token | Lifetime | Storage | Who reads it |
|-------|----------|---------|-------------|
| Access token | 30 min | Zustand in-memory only | Zustand, sent as Authorization header |
| Refresh token | 7 days (conventional) | httpOnly cookie on Next.js origin | Next.js Route Handler only |

The current `auth.ts` stores the access token in `sessionStorage`. This must be removed — sessionStorage is JavaScript-accessible and defeats the security of the httpOnly refresh cookie. On page reload, the app triggers `POST /api/auth/refresh` silently; if the cookie is valid, a new access token is issued.

**Presenter refresh token implementation:**

No database table is needed. The refresh token is a long-lived HS256 JWT with claims `{"sub": tenant_id, "exp": ..., "type": "refresh"}` signed with `SECRET_KEY` (or a separate `REFRESH_SECRET_KEY` env var). Revocation is client-side only (clear cookie on logout). This is sufficient for v1.3 — a `refresh_tokens` table with server-side revocation adds complexity with no current benefit for a solo-developer SaaS.

**SameSite setting:**

Use `SameSite=Lax`. The cookie is set on the same origin the browser uses (`localhost:3000` in dev, the deployed domain in production). There is no cross-site scenario because the Presenter is not directly accessible from the browser. `SameSite=Strict` would break OAuth redirect flows if added later. `SameSite=None` would require `Secure=true` and is unnecessary.

Use `Secure=true` in production (HTTPS). In local Docker dev with HTTP, `Secure=false` or omit the flag.

**CORS implications — do not add CORSMiddleware to Presenter:**

The browser never sends requests directly to Presenter. Next.js proxies all traffic server-side. `allow_credentials=True` on Presenter's CORSMiddleware is unnecessary and adds attack surface. Do not add it.

**New and modified components:**

| File | Status | Purpose |
|------|--------|---------|
| `services/view/src/app/api/login/route.ts` | NEW | Login Route Handler: calls Presenter, sets httpOnly cookie |
| `services/view/src/app/api/auth/refresh/route.ts` | NEW | Refresh Route Handler: reads cookie, calls Presenter /auth/refresh |
| `xeter/services/presenter/routers/auth.py` | MODIFIED | Add POST /auth/refresh route |
| `xeter/services/presenter/deps.py` | MODIFIED | TOKEN_EXPIRE_HOURS 24 → 30 min, add refresh token helpers |
| `services/view/src/lib/auth.ts` | MODIFIED | Remove sessionStorage, access token in memory only, add refresh interceptor |

---

### 2. span_scores RLS — Adding Tenant Isolation

**Current state:** `span_scores` has no RLS (migration 002 comment: "RLS intentionally omitted — worker connects as BYPASSRLS role"). The spans router comment confirms: "CRITICAL: span_scores has NO PostgreSQL RLS. The WHERE tenant_id clause is the SOLE isolation mechanism for that table."

**Target state:** Add `tenant_isolation` policy mirroring the flags and diagnoses tables.

**Migration 004 adds:**

```sql
ALTER TABLE span_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON span_scores
    USING (tenant_id::text = current_setting('app.current_tenant_id', true));
```

**Worker impact:** The Worker's `score_writer.py` currently uses `psycopg2` with no `SET LOCAL` (unlike `flag_writer.py` which does set it). If the `xeter` PostgreSQL user has the `BYPASSRLS` attribute, the new policy is transparent — inserts continue without `SET LOCAL`. If not, inserts will fail because no `app.current_tenant_id` is set in the session.

To make `score_writer.py` safe regardless of the user's BYPASSRLS status, add `SET LOCAL` inside an explicit transaction — matching the pattern already used by `flag_writer.py`. This is the `score_writer.py` modification (see section 3 below).

**Presenter read path:** The Presenter already uses `tenant_session()` (which calls `SET LOCAL`) for all PostgreSQL reads. Once RLS is enabled on `span_scores`, the Presenter's existing `WHERE tenant_id = ?` clause becomes double-enforced — both by the application query and by the RLS policy.

**New component:** `xeter/migrations/versions/004_security.py` — NEW migration file.

---

### 3. Worker Role Scoping — Making score_writer.py RLS-safe

**The BYPASSRLS constraint:** BYPASSRLS is a role-level attribute that cannot be scoped to specific operations (INSERT only). When a role has BYPASSRLS, it bypasses all RLS for all operations on all tables. This is confirmed by the official PostgreSQL documentation and cannot be overridden by policies.

**The correct approach for v1.3:** Modify `score_writer.py` to execute `SET LOCAL app.current_tenant_id` inside an explicit transaction, matching the `flag_writer.py` pattern exactly. This makes the worker's write path correct whether the database user has BYPASSRLS or not, and ensures that if BYPASSRLS is ever removed from the `xeter` user in future, score writes continue to work without further code changes.

**Current score_writer.py pattern (uses context manager, no SET LOCAL):**

```python
with psycopg2.connect(_get_dsn()) as conn:
    with conn.cursor() as cur:
        cur.executemany(_INSERT_SQL, rows)
```

**Target pattern (explicit transaction with SET LOCAL — same as flag_writer.py):**

```python
conn = psycopg2.connect(_get_dsn())
conn.autocommit = False
try:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.current_tenant_id = %s", (str(tenant_id),))
        cur.executemany(_INSERT_SQL, rows)
    conn.commit()
except Exception as exc:
    conn.rollback()
    logger.error("score_writer: failed to write %d scores for span_id=%s: %s",
                 len(scores), span_id, exc)
    raise
finally:
    conn.close()
```

Note: `SET LOCAL` only scopes to the current transaction. Using the `with psycopg2.connect()` context manager leaves `autocommit` at its default (False in psycopg2), but the connection is closed on context exit — `SET LOCAL` would have no effect because no explicit `COMMIT` is issued. The flag_writer.py pattern of explicit `conn.autocommit = False` + manual commit/rollback is required.

**Modified component:** `xeter/services/worker/score_writer.py`

---

### 4. CHECK Constraints on diagnoses Table — Migration Strategy

**Target constraints:**
- `verdict IN ('model', 'architecture', 'prompt', 'unknown')`
- `severity IN ('low', 'medium', 'high')`

**Existing data risk:** The diagnoses table was created in migration 003 and has rows since v1.2 shipped (2026-04-25). The DAL docstring in `diagnoses.py` documents `undetermined` as a verdict value and `critical` as a severity value. These violate the proposed CHECK constraints. If rows with these values exist, a standard `ALTER TABLE ADD CONSTRAINT` (without NOT VALID) will fail immediately with a constraint violation error.

**Migration strategy — NOT VALID:**

```sql
-- Step 1: Add constraint without validating existing rows (instantaneous)
-- New inserts are validated immediately; existing rows are not checked yet.
ALTER TABLE diagnoses
    ADD CONSTRAINT chk_verdict
    CHECK (verdict IN ('model', 'architecture', 'prompt', 'unknown'))
    NOT VALID;

ALTER TABLE diagnoses
    ADD CONSTRAINT chk_severity
    CHECK (severity IN ('low', 'medium', 'high'))
    NOT VALID;
```

This goes in the Alembic `upgrade()` function of migration 004.

**Step 2 (manual, not in migration):** After auditing and correcting any existing rows:

```sql
-- SHARE UPDATE EXCLUSIVE lock — concurrent reads and writes continue
ALTER TABLE diagnoses VALIDATE CONSTRAINT chk_verdict;
ALTER TABLE diagnoses VALIDATE CONSTRAINT chk_severity;
```

Do not put VALIDATE CONSTRAINT inside the Alembic migration. If rows violate the constraint, the migration would fail mid-execution and leave Alembic's version table out of sync.

**Prerequisite:** Before running VALIDATE CONSTRAINT, update any existing diagnoses rows where `verdict = 'undetermined'` → `'unknown'` and `severity = 'critical'` → `'high'`. Also update the Diagnosticer provider implementations to only produce values in the allowed sets.

**Lock behavior:**
- `ADD CONSTRAINT NOT VALID`: Takes `ACCESS EXCLUSIVE` briefly, releases immediately (no scan). Safe.
- `VALIDATE CONSTRAINT`: Takes `SHARE UPDATE EXCLUSIVE`. Concurrent SELECT, INSERT, UPDATE, DELETE all continue. Only DDL is blocked. Safe for production.

---

### 5. bcrypt CI Test

**Target:** A test that fails if the bcrypt cost factor drops below 12.

**Where it lives:** `xeter/tests/test_bcrypt_rounds.py` (new file in the existing test suite).

**Implementation:** bcrypt salts have the format `$2b$NN$...` where NN is the cost factor as a zero-padded integer. Parse it from `bcrypt.gensalt()` output.

```python
import bcrypt

def test_bcrypt_rounds_at_least_12():
    salt = bcrypt.gensalt()
    # Salt format: b'$2b$12$...' — cost factor is field 3 (0-indexed: 2)
    rounds = int(salt.split(b"$")[2])
    assert rounds >= 12, f"bcrypt cost factor is {rounds}, must be >= 12"
```

No integration point — purely a standalone test.

---

### 6. docker-compose Secrets

**Files modified/created:**

| File | Status | Change |
|------|--------|--------|
| `deploy/docker-compose.yml` | MODIFIED | Replace hardcoded passwords with env var references |
| `.env.example` | MODIFIED | Defaults to CHANGE_ME_BEFORE_DEPLOY |
| `deploy/generate-secrets.sh` | NEW | Writes .env with openssl rand -hex 32 values |

**Substitution map — docker-compose.yml:**

Current `xeter_dev_password` literal appears in 12+ places. Replace with:

| Secret | Env var name | docker-compose syntax |
|--------|--------------|-----------------------|
| Postgres password | `POSTGRES_PASSWORD` | `${POSTGRES_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}` |
| ClickHouse password | `CLICKHOUSE_PASSWORD` | `${CLICKHOUSE_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}` |
| MinIO root password | `MINIO_ROOT_PASSWORD` | `${MINIO_ROOT_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}` |
| S3 secret key | `S3_SECRET_KEY` | `${S3_SECRET_KEY:-CHANGE_ME_BEFORE_DEPLOY}` |
| JWT secret | `SECRET_KEY` | already `${SECRET_KEY:-dev-secret-key-change-in-production}` — update default |

The `DATABASE_URL` env var embeds the password inline. It must become:
`DATABASE_URL: postgresql+asyncpg://xeter:${POSTGRES_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}@postgres:5432/xeter`

The `minio-init` command hardcodes the password: `mc alias set local http://minio:9000 xeter xeter_dev_password` — this must use the env var too.

---

### 7. S3/MinIO Bucket Policy Documentation

Documentation-only addition to the deployment guide (no code change). Covers:
1. `mc policy set none local/xeter-payloads` to enforce private ACL
2. IAM-style policy JSON granting `s3:GetObject` + `s3:PutObject` only to named service accounts
3. Key rotation runbook: generate new credentials, update env vars, restart affected services (analyser, worker, diagnosticer, presenter)

---

## Data Flow Diagrams

### Refresh Token Flow (new in v1.3)

```
User submits login form
    ↓
Browser → POST /api/login (Next.js origin: localhost:3000)
    ↓ Next.js Route Handler intercepts (not rewrite proxy)
    ↓ server-side fetch
Presenter POST /login
    → verify password
    ← JSON: {session_token: "30min-jwt", refresh_token: "7day-jwt"}
    ↓
Route Handler:
    cookies().set("refresh_token", ..., {httpOnly: true, sameSite: "lax", path: "/api/auth/refresh"})
    returns JSON: {session_token: "30min-jwt"}
    ↓
Browser:
    Zustand stores session_token in memory only (no sessionStorage)
    Browser stores refresh_token in httpOnly cookie (JS cannot read it)

--- 30 minutes later: access token expired ---

Browser API call → 401 from Presenter
    ↓
Zustand interceptor → POST /api/auth/refresh (Next.js origin)
    → Browser sends refresh_token cookie automatically (SameSite=Lax, same origin)
    ↓ Next.js Route Handler reads cookie
    → server-side fetch: POST http://presenter:8000/auth/refresh
      body: {refresh_token: "<cookie value>"}
      ← JSON: {session_token: "new-30min-jwt"}
    ← JSON: {session_token: "new-30min-jwt"}
    ↓
Zustand updates session_token in memory
Original request retried with new token
```

### Worker Write Path (after span_scores RLS)

```
Worker processes span from Redis queue
    ↓
flag_writer.write_flags():
    psycopg2.connect()
    conn.autocommit = False
    SET LOCAL app.current_tenant_id = tenant_id  ← already present
    INSERT INTO flags (...)
    COMMIT
    ↓
score_writer.write_scores():
    psycopg2.connect()
    conn.autocommit = False
    SET LOCAL app.current_tenant_id = tenant_id  ← ADDED in v1.3
    executemany INSERT INTO span_scores (...)
    COMMIT
```

---

## Build Order (Dependencies)

Dependencies flow top-to-bottom. Items on the same level are independent.

```
1. Migration 004
   (span_scores RLS + diagnoses CHECK constraints must exist before code depends on them)
        ↓
2. score_writer.py SET LOCAL addition
   (must land with or after migration 004 — if RLS exists and SET LOCAL absent,
    inserts fail for non-BYPASSRLS users)
        |
3. Presenter deps.py
   (token expiry change + refresh token helpers must exist before new auth route)
        ↓
4. Presenter auth router POST /auth/refresh
   (Presenter endpoint must exist before Next.js calls it)
        ↓
5. Next.js Route Handlers (login + refresh)
   (calls Presenter; Presenter must be updated first)
        ↓
6. auth.ts sessionStorage removal + refresh interceptor
   (last: depends on working cookie-based refresh)

Independent (any order):
   - docker-compose secrets + generate-secrets.sh
   - bcrypt CI test
   - S3 bucket policy documentation
```

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-10k users | Current architecture sufficient. Single Presenter, single Worker, no changes. |
| 10k-100k users | Refresh token revocation becomes important (compromised device use case). Add `refresh_tokens` table with issued_at + revoked_at. |
| 100k+ users | Separate read/write database roles becomes worthwhile. Two DATABASE_URLs (one BYPASSRLS for Worker, one RLS-enforced for Presenter). |

---

## Sources

- PostgreSQL Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- PostgreSQL ALTER TABLE (NOT VALID, VALIDATE CONSTRAINT): https://www.postgresql.org/docs/current/sql-altertable.html
- FastAPI Response Cookies: https://fastapi.tiangolo.com/advanced/response-cookies/
- Next.js cookies() function: https://nextjs.org/docs/app/api-reference/functions/cookies
- Codebase sources verified directly:
  - `xeter/services/presenter/routers/auth.py` — current login implementation
  - `xeter/services/presenter/deps.py` — TOKEN_EXPIRE_HOURS=24, create_session_token
  - `xeter/services/worker/score_writer.py` — no SET LOCAL, context manager pattern
  - `xeter/services/worker/flag_writer.py` — SET LOCAL pattern (reference implementation)
  - `xeter/migrations/versions/002_span_scores.py` — RLS intentionally omitted comment
  - `xeter/services/presenter/routers/spans.py` — CRITICAL comment on span_scores isolation
  - `services/view/src/lib/auth.ts` — sessionStorage usage confirmed
  - `services/view/next.config.ts` — /api/* rewrite rule confirmed
  - `deploy/docker-compose.yml` — hardcoded passwords confirmed

---
*Architecture research for: Xeter v1.3 Security Hardening*
*Researched: 2026-04-27*
