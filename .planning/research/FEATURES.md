# Feature Research

**Domain:** Security hardening — AI observability SaaS (v1.3 milestone)
**Researched:** 2026-04-27
**Confidence:** HIGH (PostgreSQL RLS/BYPASSRLS, bcrypt rounds, MinIO policy), MEDIUM (JWT refresh token rotation patterns), HIGH (docker-compose secrets hygiene)

---

## Context

v1.2 is shipped. This file is scoped to the **v1.3 Security Hardening** milestone:
closing auth gaps, RLS coverage, DB-level validation, secrets hygiene, and
deployment documentation before public launch.

Previously shipped features (ingestion, embedding, flagging, diagnosis, dashboard,
JWT login) are treated as existing dependencies, not features to design.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Any B2B SaaS handling developer production data must have these before launch.
Missing them means security-aware customers will reject the platform in a
security review.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Short-lived access tokens (30 min) | JWTs without expiry are permanent credentials — a leaked token never expires. Any security-conscious buyer will reject a platform with 24-hour (current) or no-expiry tokens | LOW | Change `TOKEN_EXPIRE_HOURS = 24` to `TOKEN_EXPIRE_MINUTES = 30` in `deps.py`. The `jose` library already validates `exp` — no new dependency. |
| httpOnly cookie for refresh token | Refresh tokens in JS-accessible storage (localStorage, memory) are stolen by XSS. httpOnly prevents any JS from reading the cookie. Standard browser security baseline for session tokens. | MEDIUM | FastAPI `response.set_cookie(httponly=True, secure=True, samesite="lax", max_age=604800)`. New `POST /auth/refresh` endpoint required. Access token stays in JSON body for Bearer pattern; refresh token moves to cookie. |
| Refresh token endpoint | Without refresh, 30-min access tokens force re-login every 30 minutes, making the dashboard unusable during long debugging sessions | MEDIUM | `POST /auth/refresh` reads httpOnly cookie, validates token family, issues new access + refresh pair. Requires revocation store (see Anti-Features for why rotation without one is an anti-pattern). Depends on: httpOnly cookie feature. |
| docker-compose secret hygiene | Committed `xeter_dev_password` as a hardcoded inline value means any developer who clones the repo has the same credential. If reused in staging/prod (common mistake), it is a public credential. | LOW | Replace all inline `xeter_dev_password` with `${VAR:-CHANGE_ME_BEFORE_DEPLOY}` expansion. Add `generate-secrets.sh` using `openssl rand -hex 32`. Create root `.gitignore` that excludes `.env`. |
| PostgreSQL CHECK constraints on verdict/severity | `verdict` and `severity` are unconstrained VARCHAR columns in the `diagnoses` table. A LLM hallucination or code bug can write `"CRITICAL"` or `"wrong"` — values neither the frontend nor query logic expects. Data integrity gap. | LOW | `ALTER TABLE diagnoses ADD CONSTRAINT chk_verdict CHECK (verdict IN ('model','architecture','prompt','unknown'))`. Same for severity `IN ('low','medium','high')`. Pure SQL, new Alembic migration, zero Python changes. |

### Differentiators (Competitive Advantage)

These go beyond minimum security hygiene — they are meaningful to enterprise buyers
and security reviewers, and distinguish Xeter from hobbyist SaaS.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| span_scores RLS policy | Migration 002 explicitly deferred RLS on `span_scores` ("RLS intentionally omitted"). Currently any DB connection can read all tenants' scores. Closing this gap means tenant isolation is complete across all PostgreSQL tables. | MEDIUM | Enable RLS on `span_scores` + add `tenant_isolation` policy matching migration 001 pattern. Worker inserts must still work — requires Worker BYPASSRLS role below. These two ship together. |
| Worker BYPASSRLS role scoped to insert-only | The worker currently connects as the same `xeter` DB user as Presenter and Analyser — a full-privilege account. Migration 002 says "worker connects as BYPASSRLS role" but this is aspirational; it uses the main DATABASE_URL. | MEDIUM | Create `xeter_worker` role with `BYPASSRLS` attribute. GRANT only `INSERT` on `span_scores` and `flags`. Per PostgreSQL docs (verified): BYPASSRLS bypasses row-level filtering, but GRANT controls table-level access — a role with BYPASSRLS + INSERT-only GRANT **cannot SELECT**. Worker gets its own `WORKER_DATABASE_URL`. |
| bcrypt rounds >= 12 CI enforcement | `bcrypt.gensalt()` defaults to rounds=12 (OWASP minimum). The default is correct but unenforced — a future developer passing `rounds=4` for test speed degrades production security with no CI failure. | LOW | Pytest test: parse cost factor from hash prefix `$2b$<cost>$` and assert `>= 12`. bcrypt hash format makes this trivial without re-hashing. Runs in existing test suite. |
| JWT_SECRET rotation runbook | Many teams rotate secrets only after a breach. A documented dual-secret runbook means rotation is a planned 30-minute operation, not an emergency. | LOW | No code change needed if 30-min access token expiry is in place: (1) generate new SECRET_KEY, (2) accept old + new during 30-min window (or simply accept a 30-min re-login gap), (3) remove old key. Document as ops runbook. |
| MinIO xeter-payloads private bucket assertion | The `minio-init` container only runs `mc mb` (create bucket) without asserting the policy. MinIO denies anonymous access by default, but this is not explicitly enforced or documented — a mis-configured MinIO instance could expose payloads. | LOW | Add `mc anonymous set none local/xeter-payloads` to the `minio-init` command. For cloud (AWS S3) deployments, document the equivalent IAM Deny policy. One line of shell + one paragraph of docs. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Refresh token rotation without a revocation store | Simpler — no extra table, just issue a new token on each request | Without a store, reuse detection is impossible. If an attacker steals a refresh token, they silently compete with the legitimate user forever — the server cannot distinguish them. Rotation without reuse detection is security theater. Auth0 confirms this: token family reuse detection requires server-side state. | Store one row per active session in a `refresh_tokens` table (`family_id`, `token_hash`, `tenant_id`, `expires_at`). On rotation, UPDATE the token_hash. On reuse detection (old token presented), DELETE the family — full invalidation. PostgreSQL already available; no Redis needed. |
| Sliding window refresh token expiry | "Sliding window" (each use extends expiry) feels more user-friendly — sessions stay alive while active | Sliding window requires per-use database writes to extend the expiry timestamp, extending the attack window if a token is stolen. A stolen token keeps getting renewed as long as the attacker uses it. Absolute expiry bounds the damage. | Absolute expiry (7 days). If a user is active beyond 7 days, they re-authenticate once. Predictable, auditable, and safe. |
| Storing refresh tokens in localStorage or React state | Avoids cookie-handling complexity in Next.js frontend | XSS vulnerability. For a platform ingesting LLM traces (which may include adversarial input), XSS risk is elevated. A single DOM injection reads the token from memory. | httpOnly cookie — read only by the server, invisible to JavaScript. Access token in React state (lost on page refresh is acceptable — refresh endpoint re-issues it on next load). |
| BYPASSRLS superuser for all services | One DB user for everything is simpler — fewer credentials to manage | Violates least privilege. If any service (worker, analyser) is compromised, the attacker has full read/write access to all tenant data. The worker is the highest-risk service (it handles external span payloads and runs embedding models). | Dedicated `xeter_worker` role with BYPASSRLS + INSERT-only GRANT. Worker cannot SELECT any tenant's data even if credentials are stolen. |
| PostgreSQL ENUM types for verdict/severity | Stronger type safety than CHECK constraints | ENUM types require `ALTER TYPE ... ADD VALUE` to add new values, which **cannot run inside a transaction** in PostgreSQL. Breaks zero-downtime migrations. Inconsistent with FLAG-03 decision (flag_type is an open string). | CHECK constraint on VARCHAR. Adding a new allowed value is a normal `ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT` inside a transaction. |
| RS256 / JWKS for JWT secret rotation | RS256 with JWKS enables zero-downtime rotation without grace-period coordination | Significant complexity overhead for a single-service deployment: key pair generation, JWKS endpoint, `kid` claim management. Justified when third-party API consumers need to validate tokens. Not justified for internal service-to-service auth. | HS256 + rotation runbook. The 30-min access token window is short enough that a 30-min re-login gap during rotation is acceptable. Migrate to RS256 when/if a public API for third-party consumers is added. |

---

## Feature Dependencies

```
[httpOnly refresh token cookie]
    └──requires──> [Refresh token endpoint (POST /auth/refresh)]
                       └──requires──> [Refresh tokens table (revocation store)]
                                          └──requires──> [Short-lived access token (30 min expiry)]

[span_scores RLS policy]
    └──requires──> [Worker BYPASSRLS role (xeter_worker)]
                       └──requires──> [Separate WORKER_DATABASE_URL env var]
                                          └──requires──> [docker-compose secret hygiene update]
                                                             └──requires──> [generate-secrets.sh adds WORKER_DATABASE_PASSWORD]

[bcrypt CI enforcement]
    └──standalone──> [No new dependencies; test reads hash prefix]

[CHECK constraints (verdict/severity)]
    └──standalone──> [New Alembic migration; no Python service changes]

[JWT_SECRET rotation runbook]
    └──enhances──> [Short-lived access token (30 min window makes rotation safe without code changes)]

[MinIO private bucket assertion]
    └──standalone──> [One mc command in minio-init; no service changes]
```

### Dependency Notes

- **Refresh token requires access token expiry shortening first.** A 24-hour access token makes refresh tokens useless — the access token outlives any attack window where the refresh mechanism matters. The 30-min expiry is the prerequisite that makes the refresh architecture meaningful.
- **span_scores RLS requires worker BYPASSRLS role in the same deployment.** Adding RLS to span_scores without a scoped worker role breaks worker inserts. These two features must land in the same Alembic migration and docker-compose update — never one without the other.
- **Worker BYPASSRLS requires docker-compose secret hygiene update.** A new `WORKER_DATABASE_URL` env var must be wired in docker-compose. The `generate-secrets.sh` script must generate the worker DB password, so secret hygiene and worker role creation are naturally bundled.
- **CHECK constraints are fully standalone.** Pure SQL in a migration, no ordering dependency on other v1.3 features.
- **bcrypt CI test is fully standalone.** Five-line pytest test, no new dependencies.
- **MinIO documentation is fully standalone.** One shell line in docker-compose, one paragraph in ops docs.

---

## Implementation Details Per Feature

### 1. JWT 30 Min Expiry + Refresh Token + httpOnly Cookie

**Current state (`deps.py`):**
- `TOKEN_EXPIRE_HOURS = 24` — 24-hour access tokens
- No refresh mechanism. No cookie. Token issued in JSON body only.

**Target state:**

Access token: Change constant to `TOKEN_EXPIRE_MINUTES = 30`. `timedelta(minutes=TOKEN_EXPIRE_MINUTES)`.

Refresh token revocation store — new `refresh_tokens` table (Alembic migration 004 or 005):
```sql
CREATE TABLE refresh_tokens (
    family_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash TEXT NOT NULL,        -- SHA-256 of the raw refresh token string
    tenant_id  UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
-- No RLS needed: only the backend (as superuser) reads/writes this table.
-- One row per active session. On rotation: UPDATE token_hash. On reuse: DELETE row.
```

`POST /auth/refresh` logic:
1. Read refresh token from httpOnly cookie.
2. Look up `family_id` by token hash in `refresh_tokens`.
3. If row not found: token was revoked or never issued → 401.
4. If token hash does not match stored hash: reuse detected → DELETE row (full family invalidation) → 401.
5. If expired: DELETE row → 401.
6. On valid token: generate new access token + new refresh token. UPDATE `token_hash` in DB. Set new cookie. Return new access token in body.

Cookie parameters:
- `httponly=True` — blocks JS access
- `secure=True` in production (HTTPS), `False` in local dev (HTTP)
- `samesite="lax"` — CSRF protection without breaking cross-origin flows
- `max_age=604800` — 7-day absolute expiry (seconds)

Login changes: on successful login, set httpOnly cookie in addition to returning access token in body.

**MEDIUM complexity:** New table, new endpoint, cookie handling on server side, Next.js frontend must let the browser handle the cookie automatically (no manual cookie header — `credentials: "include"` on fetch calls to `/auth/refresh`).

---

### 2. JWT_SECRET Rotation Runbook

**Dual-secret strategy for HS256 without code changes (using 30-min access token window):**

1. Generate new `SECRET_KEY`: `openssl rand -hex 32`.
2. **Option A (zero-code, 30-min re-login gap):** Update `SECRET_KEY` env var and redeploy. All existing access tokens (max 30 min) expire naturally. Users re-authenticate once. Refresh tokens remain valid if their family rows exist in `refresh_tokens` — but since refresh tokens are validated by DB lookup (not JWT decode), they survive the secret rotation without issues.
3. **Option B (dual-decode, zero re-login):** Temporarily modify `verify_session_token()` to try decoding with `SECRET_KEY_NEW` first, fall back to `SECRET_KEY_OLD` on failure. After 30 min, remove the fallback.

Runbook steps (Option A, recommended for solo-dev SaaS):
```
1. openssl rand -hex 32 → new_secret
2. Update SECRET_KEY in .env (or secrets manager)
3. Redeploy presenter and diagnosticer services
4. Wait 30 minutes (existing access tokens expire)
5. No further action needed — refresh tokens are DB-validated, not JWT-validated
```

**LOW complexity:** Pure documentation. No code change unless dual-decode fallback is desired.

---

### 3. span_scores RLS + Worker BYPASSRLS Role

**Current state:**
- `span_scores` has no RLS (migration 002 comment: "RLS intentionally omitted")
- Worker connects as the same `xeter` DB user as all other services — full privileges
- `score_writer.py` comment says "BYPASSRLS role" but this is aspirational

**Target state (SQL — run via migration or init script before migration 004):**
```sql
-- 1. Create the scoped worker role
CREATE ROLE xeter_worker WITH LOGIN PASSWORD 'CHANGE_ME' BYPASSRLS;

-- 2. Grant only INSERT on tables the worker writes to
GRANT INSERT ON span_scores TO xeter_worker;
GRANT INSERT ON flags TO xeter_worker;

-- 3. Enable RLS on span_scores
ALTER TABLE span_scores ENABLE ROW LEVEL SECURITY;

-- 4. Add tenant isolation policy (same pattern as migration 001)
CREATE POLICY tenant_isolation ON span_scores
    USING (tenant_id::text = current_setting('app.current_tenant_id', true));
```

**Verified mechanic (PostgreSQL 16 docs, HIGH confidence):**
BYPASSRLS bypasses the row-filtering layer. GRANT controls the table-privilege layer (above RLS). A role with `BYPASSRLS` + `INSERT`-only GRANT:
- CAN INSERT (bypasses RLS row filter; GRANT allows INSERT)
- CANNOT SELECT (GRANT denied at table level; never reaches RLS)

This is the correct least-privilege pattern for a write-only worker.

**Alternative (no BYPASSRLS):** Add a `FOR INSERT WITH CHECK (true)` policy on `span_scores` for the `xeter_worker` role instead of using BYPASSRLS. This avoids the BYPASSRLS attribute but requires the worker to set `app.current_tenant_id` before each insert (currently it does not). BYPASSRLS is simpler for the worker's existing insert pattern.

**docker-compose change:**
```yaml
worker:
  environment:
    WORKER_DATABASE_URL: postgresql+asyncpg://xeter_worker:${WORKER_DATABASE_PASSWORD:-CHANGE_ME}@postgres:5432/xeter
```

Worker `score_writer.py` and `flag_writer.py` must read `WORKER_DATABASE_URL` (falling back to `DATABASE_URL` for local dev compatibility).

**MEDIUM complexity:** New DB role, migration, two env var changes, `score_writer.py` and `flag_writer.py` DSN source change.

---

### 4. CHECK Constraints (verdict + severity)

**Current state:** `verdict VARCHAR NOT NULL`, `severity VARCHAR NOT NULL` in migration 003. No constraint on allowed values. A LLM hallucination or parse bug could write arbitrary strings.

**Migration (004 or combined with RLS migration):**
```sql
ALTER TABLE diagnoses
    ADD CONSTRAINT chk_verdict
        CHECK (verdict IN ('model', 'architecture', 'prompt', 'unknown')),
    ADD CONSTRAINT chk_severity
        CHECK (severity IN ('low', 'medium', 'high'));
```

**Note on existing data:** If `diagnoses` rows with non-conforming values exist (e.g., from early seed data), the migration fails. Pre-check:
```sql
SELECT DISTINCT verdict FROM diagnoses WHERE verdict NOT IN ('model','architecture','prompt','unknown');
```
Delete or update outliers before running the migration.

**Consistency with FLAG-03:** VARCHAR + CHECK rather than PostgreSQL ENUM. Adding `'critical'` to severity in the future requires only updating the CHECK constraint inside a transaction — no `ALTER TYPE ... ADD VALUE` which PostgreSQL cannot run transactionally.

**LOW complexity:** Pure SQL migration. Zero Python changes. Standalone dependency.

---

### 5. bcrypt Rounds >= 12 CI Enforcement

**Current state:**
- `bcrypt.gensalt()` called without `rounds` argument in `auth.py`, `api_keys.py`, `seed.py`
- Python's `bcrypt` library defaults to `rounds=12` (OWASP minimum)
- No CI guard exists — a future `bcrypt.gensalt(rounds=4)` for test speed would silently degrade security

**OWASP guidance (HIGH confidence):** Minimum work factor for bcrypt is 10 globally; 12 is the recommended floor for new systems. The Python `bcrypt` library default matches this.

**Test implementation:**
```python
def test_bcrypt_cost_factor_at_least_12():
    """Cost factor is encoded in the hash: $2b$<cost>$<salt><hash>."""
    import bcrypt
    hashed = bcrypt.hashpw(b"test-password", bcrypt.gensalt())
    cost_factor = int(hashed.decode().split("$")[2])
    assert cost_factor >= 12, f"bcrypt cost {cost_factor} below OWASP minimum of 12"
```

The bcrypt hash format `$2b$12$...` makes cost factor extraction trivial without re-hashing. Add to `test_security_invariants.py` or inline in `test_auth_login.py`.

**LOW complexity:** 5-line test. No new dependencies.

---

### 6. docker-compose CHANGE_ME + generate-secrets.sh

**Current state:**
- Hardcoded `xeter_dev_password` in docker-compose.yml for postgres, clickhouse, minio
- `SECRET_KEY` already uses `${SECRET_KEY:-dev-secret-key-change-in-production}` (correct pattern)
- Root `.gitignore` does not exist — `.env` is not excluded from git
- No `generate-secrets.sh`

**Target state:**

`docker-compose.yml` replacements:
```yaml
postgres:
  environment:
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}

clickhouse:
  environment:
    CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}

minio:
  environment:
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-CHANGE_ME_BEFORE_DEPLOY}
```

`generate-secrets.sh`:
```bash
#!/usr/bin/env bash
# Generates random secrets for a new deployment environment.
# Usage: bash generate-secrets.sh > .env
set -euo pipefail
echo "POSTGRES_PASSWORD=$(openssl rand -hex 32)"
echo "CLICKHOUSE_PASSWORD=$(openssl rand -hex 32)"
echo "MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "WORKER_DATABASE_PASSWORD=$(openssl rand -hex 32)"
```

Root `.gitignore` (must be created — currently absent):
```
.env
*.env.local
```

`CHANGE_ME_BEFORE_DEPLOY` as the fallback (not `xeter_dev_password`) makes it immediately obvious in logs/config dumps that secrets have not been rotated.

**LOW complexity:** Sed-pattern replacements in docker-compose, one shell script, one `.gitignore`.

---

### 7. MinIO xeter-payloads Private Bucket Policy

**Current state:**
- `minio-init` container: `mc mb local/xeter-payloads --ignore-existing` only
- No explicit policy assertion
- MinIO denies anonymous access by default, but this is not enforced or documented

**Target state:**

Add to `minio-init` command (idempotent, safe to re-run):
```sh
mc anonymous set none local/xeter-payloads
```
Per MinIO mc documentation (HIGH confidence): `none` removes all anonymous access policies. This is the equivalent of "private ACL" in S3 terminology.

Full `minio-init` command after change:
```sh
mc alias set local http://minio:9000 xeter ${MINIO_ROOT_PASSWORD} \
  && mc mb local/xeter-payloads --ignore-existing \
  && mc anonymous set none local/xeter-payloads
```

AWS S3 equivalent (for production/cloud deployments — documentation only):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::xeter-payloads",
        "arn:aws:s3:::xeter-payloads/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::ACCOUNT_ID:user/xeter-service"
        }
      }
    }
  ]
}
```

**LOW complexity:** One line in docker-compose minio-init, one paragraph in deployment docs.

---

## MVP Definition

### Launch With (v1.3 — all features required)

Security hardening is binary. Shipping partial security improvements creates a false sense of security — if any of these gaps are open, a security review will fail.

- [ ] JWT 30 min access token expiry — eliminates permanent-credential exposure
- [ ] Refresh token endpoint + httpOnly cookie + revocation store — closes XSS token theft vector
- [ ] docker-compose CHANGE_ME_BEFORE_DEPLOY + generate-secrets.sh + root .gitignore — closes committed-secrets risk
- [ ] span_scores RLS policy — completes tenant isolation across all PostgreSQL tables
- [ ] Worker xeter_worker BYPASSRLS role + WORKER_DATABASE_URL — closes cross-tenant read via worker
- [ ] CHECK constraints on verdict/severity — closes data integrity gap
- [ ] bcrypt rounds >= 12 CI test — regression guard in place
- [ ] JWT_SECRET rotation runbook — operational readiness documented
- [ ] MinIO xeter-payloads private bucket documented + mc command asserted — closes S3 config gap

### Add After Validation (v1.4+)

- [ ] Rate limiting on `POST /auth/login` and `POST /auth/refresh` — brute-force protection; important but post-launch for a solo-dev SaaS
- [ ] Explicit logout endpoint (invalidates refresh token family) — UX polish; session ends naturally on expiry without it
- [ ] RS256 / JWKS key rotation — only relevant when third-party API consumers exist

### Future Consideration (v2+)

- [ ] Argon2id migration from bcrypt — OWASP's preferred algorithm; worth migrating when multi-region deployment justifies the operational complexity
- [ ] Clerk migration for multi-member tenant auth — already deferred in PROJECT.md

---

## Feature Prioritization Matrix

| Feature | Security Value | Implementation Cost | Priority |
|---------|---------------|---------------------|----------|
| JWT 30 min access token expiry | HIGH | LOW | P1 |
| httpOnly refresh token + endpoint + revocation store | HIGH | MEDIUM | P1 |
| docker-compose CHANGE_ME + generate-secrets.sh | HIGH | LOW | P1 |
| span_scores RLS + xeter_worker BYPASSRLS role | HIGH | MEDIUM | P1 |
| CHECK constraints (verdict/severity) | MEDIUM | LOW | P1 |
| bcrypt rounds >= 12 CI test | MEDIUM | LOW | P1 |
| JWT_SECRET rotation runbook | MEDIUM | LOW | P2 |
| MinIO private bucket assertion + documentation | MEDIUM | LOW | P2 |

**Priority key:** P1 = blocking for v1.3 launch, P2 = include in v1.3 but not a hard blocker

---

## Sources

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — bcrypt minimum work factor is 10 globally; 12 recommended for new systems. HIGH confidence.
- [PostgreSQL 16 Role Attributes](https://www.postgresql.org/docs/16/role-attributes.html) — BYPASSRLS attribute definition and creation syntax. HIGH confidence.
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — BYPASSRLS + GRANT interaction: BYPASSRLS bypasses row-level filtering; GRANT controls table-level access; both apply independently. HIGH confidence.
- [Auth0: Refresh Tokens — What Are They and When to Use Them](https://auth0.com/blog/refresh-tokens-what-are-they-and-when-to-use-them/) — token family reuse detection strategy; invalidate entire family on reuse detection. MEDIUM confidence.
- [Implement Refresh Token Reuse Detection Without DB Bloat](https://dev.to/alvaromrveiga/implement-refresh-token-automatic-reuse-detection-without-cluttering-your-database-lb) — store one row per active token family (family_id + token_hash); UPDATE on rotation, DELETE on reuse. MEDIUM confidence.
- [MinIO mc anonymous set documentation](https://docs.min.io/enterprise/aistor-object-store/reference/cli/mc-anonymous/mc-anonymous-set/) — `none` removes all anonymous access policies. HIGH confidence.
- [pyca/bcrypt on PyPI](https://pypi.org/project/bcrypt/) — `gensalt()` defaults to rounds=12. HIGH confidence.
- Codebase direct review: `deps.py`, `routers/auth.py`, `migrations/002_span_scores.py`, `migrations/003_diagnoses.py`, `services/worker/score_writer.py`, `deploy/docker-compose.yml`, `.env.example`

---
*Feature research for: Xeter v1.3 Security Hardening*
*Researched: 2026-04-27*
