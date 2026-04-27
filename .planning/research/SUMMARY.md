# Project Research Summary

**Project:** Xeter v1.3 Security Hardening
**Domain:** Auth hardening, RLS completion, DB integrity, secrets hygiene -- existing FastAPI + Next.js 15 AI observability SaaS
**Researched:** 2026-04-27
**Confidence:** HIGH

## Executive Summary

Xeter v1.3 is a security hardening milestone on an already-shipping platform. The work closes six concrete gaps before public launch: permanent JWT credentials, incomplete tenant isolation on span_scores, unconstrained diagnosis values, hardcoded secrets in docker-compose, unasserted MinIO bucket policy, and no CI guard on bcrypt cost factor. None of these require new libraries -- every feature is implementable with the existing dependency set, with the sole change being removal of passlib[bcrypt] which was never imported anywhere. The recommended approach treats these as infrastructure-first changes: migrations and config hygiene go first, then endpoint logic, then frontend integration.

The most significant architectural decision in this milestone is the refresh token design. Features research initially recommended a refresh_tokens DB table with server-side revocation; Architecture research concludes that for the current single-tenant-per-deployment threat model, a long-lived HS256 JWT in an httpOnly cookie with client-side revocation (clear cookie on logout) is sufficient. The Architecture position wins: it avoids a new table, a jti claim, and per-refresh DB writes, while still delivering the primary XSS protection that httpOnly provides. If device-level revocation becomes a requirement (10k+ users scale), a refresh_tokens table can be added in v1.4 without changing the token format. The logout handler must carry an explicit comment acknowledging that stolen refresh tokens remain valid until natural expiry (7 days) -- this is an accepted tradeoff, not an oversight.

The second design resolution: Features research described creating a dedicated xeter_worker BYPASSRLS PostgreSQL role with a separate WORKER_DATABASE_URL. Architecture research identifies that the simpler and equally correct path is modifying score_writer.py to use SET LOCAL app.current_tenant_id inside an explicit transaction -- matching the existing flag_writer.py pattern. This eliminates a new DB role, a new env var, and new docker-compose wiring. Architecture wins. The key risk in this milestone is the interaction between PostgreSQL RLS, FORCE ROW LEVEL SECURITY, and the existing migration role: Pitfalls research confirms that ENABLE ROW LEVEL SECURITY without FORCE leaves the table owner bypassing all policies silently -- migration 004 must add FORCE retroactively to all six existing RLS tables in the same change.

## Key Findings

### Recommended Stack

No new dependencies are required for any v1.3 feature. The existing stack handles everything: python-jose[cryptography] for refresh JWT issuance, fastapi/Starlette Response.set_cookie(httponly=True) for the cookie, SQLAlchemy 2.0 + alembic for the RLS and CHECK constraint migrations, bcrypt directly for the cost factor CI test, and standard POSIX openssl rand for generate-secrets.sh. The only dependency change is a removal: passlib[bcrypt]>=1.7 must be removed from pyproject.toml -- it is never imported anywhere in the codebase, conflicts with Python 3.14+, and was already rejected in PROJECT.md.

**Core technologies (v1.3 relevant):**
- python-jose[cryptography] 3.5.0: Refresh JWT issuance -- same jwt.encode() / jwt.decode() API already used for access tokens; add type: refresh claim and longer exp
- fastapi 0.135.2 / Starlette: response.set_cookie(httponly=True, secure=True, samesite="lax") -- confirmed via official Starlette docs; Cookie() dependency for reading the refresh token server-side
- alembic 1.18.4: Migration 004 -- span_scores RLS + FORCE RLS on all tables + diagnoses CHECK constraints; op.execute(sa.text(...NOT VALID...)) pattern required for live table
- bcrypt 5.0.0: CI test reads cost factor from gensalt() output via salt.split(b"$")[2]; no hashpw call needed
- Migration note: python-jose to PyJWT migration is recommended for v1.4 (near-abandoned library), explicitly out of scope for v1.3

### Expected Features

**Must have (table stakes -- all required before public launch):**
- JWT 30-minute access token expiry -- change TOKEN_EXPIRE_HOURS = 24 to TOKEN_EXPIRE_MINUTES = 30 in deps.py
- httpOnly refresh token cookie + POST /auth/refresh endpoint -- XSS token theft prevention; cookie set by Next.js Route Handler (not Presenter directly, due to Next.js rewrite stripping upstream Set-Cookie headers)
- docker-compose secrets hygiene -- replace 12+ xeter_dev_password literals with ${VAR:-CHANGE_ME_BEFORE_DEPLOY}; add generate-secrets.sh; create root .gitignore
- PostgreSQL CHECK constraints on verdict/severity in diagnoses -- data integrity guard against LLM hallucinations writing unexpected enum values

**Should have (differentiators that complete tenant isolation):**
- span_scores RLS policy + score_writer.py SET LOCAL -- closes the documented "RLS intentionally omitted" gap in migration 002; the table comment in spans.py explicitly flags this as the sole isolation mechanism
- FORCE ROW LEVEL SECURITY on all existing RLS tables -- retroactive fix; without it the migration role owner bypasses all tenant policies silently
- bcrypt rounds >= 12 CI enforcement -- regression guard; gensalt() defaults are already correct; test prevents future rounds=4 test-speed shortcuts from reaching production

**P2 (include in v1.3, not a hard launch blocker):**
- JWT_SECRET rotation runbook -- operational readiness doc; Option A (30-min re-login gap) requires zero code with 30-min access token expiry in place
- MinIO xeter-payloads private bucket assertion -- add mc anonymous set none local/xeter-payloads to minio-init; document IAM equivalent for cloud deployments

**Defer to v1.4+:**
- Rate limiting on /auth/login and /auth/refresh -- brute-force protection; relevant post-launch
- Explicit logout endpoint with DB revocation -- session ends naturally on expiry; add when device-level revocation is a requirement
- python-jose to PyJWT migration
- RS256 / JWKS -- only relevant when third-party API consumers exist
- Argon2id migration from bcrypt
- Per-service MinIO IAM service accounts (current shared credential is acceptable for solo-dev SaaS)

**Conflict resolution -- refresh token revocation store:**
Features recommended a refresh_tokens table. Architecture rules it out for v1.3 as over-engineered for the current threat model. The refresh token is a long-lived HS256 JWT; revocation is client-side (cookie cleared on logout). Pitfall 2 documents the stolen-token risk accurately -- this is an accepted gap, bounded by 7-day absolute expiry.

**Conflict resolution -- Worker BYPASSRLS role:**
Features recommended a dedicated xeter_worker DB role + WORKER_DATABASE_URL. Architecture rules it out for v1.3 in favor of adding SET LOCAL app.current_tenant_id to score_writer.py (same pattern as flag_writer.py). The two-role approach remains the right v1.4 path if Worker ever has SELECT requirements.

### Architecture Approach

The v1.3 architecture adds two new files (Next.js Route Handlers for login and refresh), modifies five existing files, and introduces one new Alembic migration (004). The only structural pattern change is in the auth cookie flow: the Presenter never sets cookies directly -- it returns both tokens in JSON; the Next.js Route Handler at app/api/login/route.ts sets the httpOnly cookie using cookies().set() from the Next.js App Router API. This is required because Next.js rewrites strip upstream Set-Cookie headers, so FastAPI cookies would be silently discarded.

**Modified/new components:**

1. services/view/src/app/api/login/route.ts (NEW) -- Login Route Handler; calls Presenter, receives {session_token, refresh_token} in JSON body, sets httpOnly refresh cookie on browser-facing response
2. services/view/src/app/api/auth/refresh/route.ts (NEW) -- Refresh Route Handler; reads httpOnly cookie, calls POST http://presenter:8000/auth/refresh with token in request body, returns new access token in JSON
3. xeter/services/presenter/routers/auth.py (MODIFIED) -- Add POST /auth/refresh route; read token from request body (not cookie); validate and return new access token
4. xeter/services/presenter/deps.py (MODIFIED) -- TOKEN_EXPIRE_MINUTES = 30; add create_refresh_token(); access token stays Bearer pattern
5. services/view/src/lib/auth.ts (MODIFIED) -- Remove sessionStorage; access token in Zustand memory only; add 401 interceptor that calls /api/auth/refresh
6. xeter/services/worker/score_writer.py (MODIFIED) -- Add explicit transaction + SET LOCAL app.current_tenant_id matching flag_writer.py pattern
7. xeter/migrations/versions/004_security.py (NEW) -- ENABLE ROW LEVEL SECURITY on span_scores + tenant_isolation policy; FORCE ROW LEVEL SECURITY retroactively on all 6 existing RLS tables; CHECK constraints on diagnoses verdict/severity using NOT VALID pattern
8. deploy/docker-compose.yml (MODIFIED) -- Replace all xeter_dev_password literals; update minio-init to add mc anonymous set none
9. deploy/generate-secrets.sh (NEW) -- openssl rand -hex 32 for all secrets; git-tracking guard check
10. xeter/pyproject.toml (MODIFIED) -- Remove passlib[bcrypt]>=1.7

**Build order constraint (hard dependencies):**
Migration 004 must exist before score_writer.py changes are deployed. Presenter deps.py changes must exist before the /auth/refresh route. Presenter route must exist before Next.js Route Handlers call it. auth.ts sessionStorage removal is last (depends on working cookie refresh).

### Critical Pitfalls

1. **Next.js rewrites strip upstream Set-Cookie headers** -- The Presenter cannot set httpOnly cookies directly; the cookie must be set by a Next.js Route Handler using cookies().set(). A direct FastAPI response.set_cookie() will succeed in curl and be silently discarded by the browser.

2. **ENABLE ROW LEVEL SECURITY without FORCE leaves table owner unrestricted** -- The migration role owns all tables. Every existing migration (001-003) uses only ENABLE. Migration 004 must add ALTER TABLE ... FORCE ROW LEVEL SECURITY for all six RLS tables. Verify with SELECT relforcerowsecurity FROM pg_class -- must be t for all.

3. **CHECK constraint migration blocks writes on live diagnoses table** -- Standard op.create_check_constraint() acquires ACCESS EXCLUSIVE lock and scans all rows. Use ALTER TABLE ... ADD CONSTRAINT ... NOT VALID in the migration (instantaneous), then VALIDATE CONSTRAINT manually after a pre-flight violation query. Existing v1.2 data may include verdict='undetermined' and severity='critical' -- both violate the proposed constraints.

4. **Secrets env var fallback silently uses weak defaults** -- os.environ.get("SECRET_KEY", "dev-secret-key") and docker-compose :- patterns are two layers of silent fallback. Change to os.environ["SECRET_KEY"] (raises KeyError on startup) and ${SECRET_KEY} (no fallback, docker-compose fails loudly). The .gitignore entry for .env must exist before generate-secrets.sh is run.

5. **bcrypt module-level hash in test_auth_login.py accumulates CI time at rounds=12** -- Line 32 of test_auth_login.py calls bcrypt.hashpw() at module scope. At rounds=12 this adds 300-600ms per import. Move all test bcrypt calls to scope="session" fixtures using rounds=4. The CI enforcement test verifies the hash prefix $2b$12$ only; it never calls hashpw with production cost.

6. **/auth/refresh must return access token in JSON body, not only as a cookie** -- If the endpoint returns only a cookie, Next.js 15 Client Components cannot read it (httpOnly blocks document.cookie). The 401 interceptor reads response.json().session_token from the refresh response body.

## Implications for Roadmap

The six security features group naturally into three phases based on hard dependencies and deployment risk. All are P1 for v1.3 launch.

### Phase 1: Database Foundation
**Rationale:** Migration 004 must exist before any code that depends on RLS or constraints is deployed. Applying it first, independently, means it can be run on production before any service code changes, eliminating the race condition where services deploy against an old schema.

**Delivers:**
- span_scores ENABLE ROW LEVEL SECURITY + tenant_isolation policy
- FORCE ROW LEVEL SECURITY retroactively on all 6 existing RLS tables
- diagnoses CHECK constraints on verdict/severity (NOT VALID; VALIDATE run manually after data audit)
- passlib[bcrypt] removed from pyproject.toml

**Addresses:** Table stakes (data integrity), differentiator (tenant isolation completion)

**Avoids:**
- Table owner RLS bypass -- add FORCE in same migration as ENABLE
- Blocking writes on live diagnoses -- use NOT VALID pattern; pre-flight violation query required before VALIDATE

**Research flag:** Standard Alembic and PostgreSQL patterns. No phase research needed. Pre-flight SQL for existing constraint violations must be run manually before VALIDATE.

---

### Phase 2: Secrets Hygiene + Worker RLS Wiring
**Rationale:** Can deploy independently from auth changes. Bundled together because docker-compose and score_writer.py changes both touch deployment configuration, and the bcrypt fixture refactor should precede adding more auth tests in Phase 3.

**Delivers:**
- All xeter_dev_password literals replaced in docker-compose.yml
- generate-secrets.sh with git-tracking guard
- Root .gitignore with .env entry
- SECRET_KEY hard-fail on missing env var (os.environ["SECRET_KEY"], no :- fallback in docker-compose)
- score_writer.py explicit transaction + SET LOCAL app.current_tenant_id
- MinIO mc anonymous set none added to minio-init command
- MinIO bucket policy documentation in deployment guide
- bcrypt rounds >= 12 CI test + module-level bcrypt fixture refactor in test suite

**Addresses:** Table stakes (secrets hygiene), P2 (MinIO bucket assertion), differentiator (bcrypt CI enforcement)

**Avoids:**
- .env committed to git -- create .gitignore before writing generate-secrets.sh
- Silent :- fallback defaults for security-critical env vars
- Worker score_writer.py failing on RLS policies -- SET LOCAL must land with or after migration 004
- bcrypt CI slowdown -- fixture refactor ships in same PR as cost factor test

**Research flag:** Standard patterns. No phase research needed.

---

### Phase 3: JWT Hardening + Refresh Token Flow
**Rationale:** Most complex phase; requires coordination across Presenter (Python), Next.js (TypeScript), and browser cookie behavior. Must come after Phase 1 (schema ready) and Phase 2 (secrets hygiene, so SECRET_KEY is properly set). The Next.js Route Handler pattern must be implemented correctly from the start -- retrofitting after a direct-Presenter-cookie implementation is costly.

**Delivers:**
- TOKEN_EXPIRE_MINUTES = 30 in deps.py
- create_refresh_token() helper in deps.py (HS256 JWT, 7-day exp, type: refresh claim)
- POST /auth/refresh on Presenter -- reads refresh token from request body, returns new access token in JSON
- app/api/login/route.ts -- Next.js Route Handler that sets httpOnly cookie
- app/api/auth/refresh/route.ts -- Next.js Route Handler that reads cookie and calls Presenter
- auth.ts -- remove sessionStorage; access token in Zustand memory only; 401 interceptor with refresh retry
- JWT_SECRET rotation runbook (Option A: 30-min re-login gap, zero code)

**Addresses:** Table stakes (JWT expiry, refresh token, httpOnly cookie)

**Avoids:**
- Set-Cookie stripped by Next.js rewrite -- Route Handler pattern, not direct Presenter cookie
- Access token in sessionStorage -- Zustand memory only after this phase
- /auth/refresh returning only cookies -- must return {session_token, expires_in: 1800} in JSON body
- Revocation theater -- logout clears cookie; gap (stolen tokens valid 7 days) is explicitly documented in handler comment as accepted v1.3 tradeoff

**Research flag:** Next.js App Router cookies() API and Route Handler interaction with rewrites is the one non-obvious integration. Architecture covers it completely. No additional research needed, but the first implementation task must be a manual browser test verifying the cookie is attached on the refresh call before any other frontend logic is built on top of it.

---

### Phase Ordering Rationale

- Phase 1 first because the schema is a hard prerequisite for Phase 2 score_writer.py change (RLS must exist before SET LOCAL is meaningful).
- Phase 2 before Phase 3 because SECRET_KEY hard-fail must be in place before the refresh token flow depends on it, and the bcrypt fixture refactor must precede adding more auth tests in Phase 3.
- Phase 3 last because it touches the most files across two services and the frontend simultaneously.
- The three phases can be code-reviewed and deployed independently, reducing blast radius if any phase needs rollback.

### Research Flags

Phases with standard patterns -- no additional phase research needed:
- **Phase 1 (Database Foundation):** Alembic migrations and PostgreSQL RLS are well-documented. The NOT VALID pattern is covered in depth in ARCHITECTURE.md. Only non-standard step is the manual pre-flight violation query before VALIDATE.
- **Phase 2 (Secrets Hygiene + Worker):** Pure config and one Python pattern change. All patterns documented in existing codebase (flag_writer.py is the reference implementation).

Phase that warrants careful step-by-step verification (not additional research):
- **Phase 3 (JWT Hardening):** The Next.js Route Handler cookie-setting pattern is the one genuinely non-obvious integration. Architecture covers it completely. First sub-task must be a real browser verification that the httpOnly cookie is present on the refresh request before building additional frontend logic on top of it.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All claims verified against PyPI and official docs 2026-04-27; no new dependencies; single removal (passlib) confirmed by codebase grep |
| Features | HIGH | PostgreSQL RLS/BYPASSRLS/FORCE patterns verified against official PostgreSQL 16 docs. Refresh token revocation gap explicitly accepted, not a research uncertainty |
| Architecture | HIGH | All patterns verified against actual codebase files with line-level specificity. Next.js Route Handler cookie pattern verified against Next.js App Router docs |
| Pitfalls | HIGH | 10 pitfalls documented with direct codebase evidence (file paths, line numbers). PostgreSQL behavior verified against official docs |

**Overall confidence:** HIGH

### Gaps to Address

- **Existing diagnoses data audit:** Before running VALIDATE CONSTRAINT for verdict/severity, a pre-flight query must be run against the production database. Architecture documents that undetermined (verdict) and critical (severity) may appear in existing rows -- both violate the proposed constraints. The migration uses NOT VALID so it is non-blocking, but VALIDATE will fail until data is cleaned. Diagnosticer provider code must also be updated to only emit values in the allowed sets.
- **minio-init env var reference:** docker-compose minio-init currently hardcodes the MinIO password in the mc alias set command string. When secrets hygiene replaces it, the command string must also reference ${MINIO_ROOT_PASSWORD} -- easy to miss since it is not in an environment: block.
- **sessionStorage removal regression test:** Removing sessionStorage from auth.ts may break any frontend test that mocks window.sessionStorage. Audit services/view test files before Phase 3 lands.

## Sources

### Primary (HIGH confidence)
- Starlette Response.set_cookie() docs (https://www.starlette.dev/responses/#set-cookie) -- httponly, secure, samesite parameter signatures confirmed
- PyPI: bcrypt 5.0.0 (https://pypi.org/project/bcrypt/) -- gensalt() default rounds=12; hash format $2b$<rounds>$...
- PostgreSQL 16: Row Security Policies (https://www.postgresql.org/docs/current/ddl-rowsecurity.html) -- BYPASSRLS, FORCE ROW LEVEL SECURITY semantics
- PostgreSQL 16: ALTER TABLE (https://www.postgresql.org/docs/current/sql-altertable.html) -- NOT VALID, VALIDATE CONSTRAINT, lock behavior
- FastAPI: Cookie params (https://fastapi.tiangolo.com/tutorial/cookie-params/) -- Cookie() dependency pattern
- Next.js: cookies() function (https://nextjs.org/docs/app/api-reference/functions/cookies) -- Route Handler cookie API
- MinIO mc anonymous set (https://docs.min.io/enterprise/aistor-object-store/reference/cli/mc-anonymous/mc-anonymous-set/) -- none removes all anonymous access policies
- OWASP Password Storage Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) -- bcrypt minimum work factor 10; recommended 12 for new systems
- Codebase direct inspection: presenter/deps.py, presenter/routers/auth.py, worker/score_writer.py, worker/flag_writer.py, migrations/001_initial.py, migrations/002_span_scores.py, migrations/003_diagnoses.py, deploy/docker-compose.yml, services/view/src/lib/auth.ts, services/view/next.config.ts, tests/presenter/test_auth_login.py

### Secondary (MEDIUM confidence)
- FastAPI discussion #11345 (https://github.com/fastapi/fastapi/discussions/11345) -- python-jose near-abandoned; PyJWT recommended for v1.4
- Auth0: Refresh Tokens -- token family reuse detection (https://auth0.com/blog/refresh-tokens-what-are-they-and-when-to-use-them/) -- revocation store patterns (deferred to v1.4)
- Squawk: constraint-missing-not-valid (https://squawkhq.com/docs/constraint-missing-not-valid) -- NOT VALID migration pattern for live tables
- Common Postgres RLS footguns -- Bytebase (https://www.bytebase.com/blog/postgres-row-level-security-footguns/) -- FORCE ROW LEVEL SECURITY necessity

### Tertiary (LOW confidence -- implementation caution advised)
- Chrome 80 SameSite=None impact on localhost (https://medium.com/swlh/how-the-new-chrome-80-cookie-rule-samesite-none-secure-affects-web-development-c06380220ced) -- cross-port cookie behavior; moot under Next.js Route Handler pattern but relevant if implementation deviates from Architecture recommendation

---
*Research completed: 2026-04-27*
*Ready for roadmap: yes*
