# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- ✅ **v1.2 Diagnosticer** — Phases 11–13 (shipped 2026-04-25)
- 🚧 **v1.3 Security Hardening** — Phases 14–16 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–6) — SHIPPED 2026-04-04</summary>

- [x] Phase 1: Foundation (4/4 plans) — completed 2026-03-27
- [x] Phase 2: Ingestion Path (3/3 plans) — completed 2026-03-28
- [x] Phase 3: Analysis Path (4/4 plans) — completed 2026-03-28
- [x] Phase 4: Read Path (3/3 plans) — completed 2026-03-30
- [x] Phase 5: Dashboard (4/4 plans) — completed 2026-03-31
- [x] Phase 6: Validation (3/3 plans) — completed 2026-04-04

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.1 Analyser Accuracy (Phases 7–10) — SHIPPED 2026-04-18</summary>

- [x] Phase 7: wrong_args Rewrite (5/5 plans) — completed 2026-04-06
- [x] Phase 8: wrong_tool Rewrite (3/3 plans) — completed 2026-04-18
- [x] Phase 9: no_tool_used + wrong_tool_choice (1/1 plan) — completed 2026-04-18
- [x] Phase 10: unnecessary_tool_call (1/1 plan) — completed 2026-04-18

See `.planning/milestones/v1.1-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.2 Diagnosticer (Phases 11–13) — SHIPPED 2026-04-25</summary>

- [x] Phase 11: Diagnosticer Backend (4/4 plans) — completed 2026-04-22
- [x] Phase 12: Presenter Integration (2/2 plans) — completed 2026-04-23
- [x] Phase 13: Frontend Diagnosis UI (2/2 plans) — completed 2026-04-25

See `.planning/milestones/v1.2-ROADMAP.md` for full phase details.

</details>

### 🚧 v1.3 Security Hardening (In Progress)

**Milestone Goal:** Close all pre-launch security gaps — tenant isolation completion, DB-level validation, secrets hygiene, and auth hardening.

- [ ] **Phase 14: DB Foundation** — RLS on span_scores, FORCE RLS on all tables, CHECK constraints on diagnoses
- [ ] **Phase 15: Secrets Hygiene** — docker-compose secrets cleanup, generate-secrets.sh, MinIO bucket assertion, bcrypt CI enforcement, passlib removal
- [ ] **Phase 16: Auth Hardening** — JWT 30-min expiry, hard-fail on missing SECRET_KEY, httpOnly refresh token, JWT_SECRET runbook

## Phase Details

### Phase 14: DB Foundation
**Goal**: All PostgreSQL tables have enforced tenant isolation and domain-valid diagnosis values
**Depends on**: Phase 13 (v1.2 complete)
**Requirements**: DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. Developer can write a span_scores row as worker and verify it is only visible to the correct tenant — the tenant_isolation RLS policy exists on span_scores and score_writer.py uses SET LOCAL inside an explicit transaction
  2. Developer can confirm no table owner can silently bypass RLS — SELECT relforcerowsecurity FROM pg_class WHERE relname IN ('spans','flags','span_scores','diagnoses','tenants','api_keys') returns t for all six rows
  3. Developer can trust verdict and severity columns reject unexpected values — INSERT with verdict='undetermined' or severity='critical' raises a constraint violation after VALIDATE CONSTRAINT runs
  4. Migration 004 applies cleanly from zero (fresh alembic upgrade) and idempotently (second run exits without error)
**Plans**: TBD

### Phase 15: Secrets Hygiene
**Goal**: Secrets cannot be accidentally committed and the deployment stack uses safe defaults
**Depends on**: Phase 13 (can execute independently of Phase 14 and 16)
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, DB-04
**Success Criteria** (what must be TRUE):
  1. Developer running git add .env sees it blocked — root .gitignore contains .env; docker-compose references env vars with CHANGE_ME_BEFORE_DEPLOY as the documented-insecure default
  2. Operator can run bash generate-secrets.sh and receive a valid .env file with random secrets in one step — the script uses openssl rand -hex 32 for all secret values and includes a git-tracking guard
  3. MinIO xeter-payloads bucket denies anonymous reads on every docker-compose up — minio-init container runs mc anonymous set none and the deployment guide documents the equivalent mc policy set and S3 IAM JSON for cloud
  4. CI fails if bcrypt cost factor drops below 12 — a test reads the hash prefix and asserts $2b$12$; all test fixtures that call bcrypt.hashpw use rounds=4 with session scope
  5. passlib[bcrypt] does not appear in pyproject.toml or any import
**Plans**: TBD

### Phase 16: Auth Hardening
**Goal**: Session tokens expire promptly, refresh is seamless and XSS-safe, and the SECRET_KEY rotation procedure is documented
**Depends on**: Phase 14 (schema ready), Phase 15 (SECRET_KEY hard-fail in place before refresh flow)
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. Developer starting the Presenter without SECRET_KEY set sees a startup exception — os.environ["SECRET_KEY"] raises KeyError; no :- fallback exists in docker-compose for SECRET_KEY
  2. Access tokens expire after 30 minutes — TOKEN_EXPIRE_MINUTES = 30 in deps.py; a test that decodes a freshly issued token confirms exp - iat = 1800 seconds
  3. User whose access token has expired can continue using the dashboard without re-logging in — Next.js 401 interceptor calls /api/auth/refresh, the Route Handler reads the httpOnly cookie and returns a new session_token in JSON, and the original request retries transparently
  4. Operator has a written runbook that describes how to rotate JWT_SECRET with zero code changes — the runbook covers the 30-minute re-login gap, the dual-secret window option, and the service restart sequence
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 4/4 | Complete | 2026-03-27 |
| 2. Ingestion Path | v1.0 | 3/3 | Complete | 2026-03-28 |
| 3. Analysis Path | v1.0 | 4/4 | Complete | 2026-03-28 |
| 4. Read Path | v1.0 | 3/3 | Complete | 2026-03-30 |
| 5. Dashboard | v1.0 | 4/4 | Complete | 2026-03-31 |
| 6. Validation | v1.0 | 3/3 | Complete | 2026-04-04 |
| 7. wrong_args Rewrite | v1.1 | 5/5 | Complete | 2026-04-06 |
| 8. wrong_tool Rewrite | v1.1 | 3/3 | Complete | 2026-04-18 |
| 9. no_tool_used + wrong_tool_choice | v1.1 | 1/1 | Complete | 2026-04-18 |
| 10. unnecessary_tool_call | v1.1 | 1/1 | Complete | 2026-04-18 |
| 11. Diagnosticer Backend | v1.2 | 4/4 | Complete | 2026-04-22 |
| 12. Presenter Integration | v1.2 | 2/2 | Complete | 2026-04-23 |
| 13. Frontend Diagnosis UI | v1.2 | 2/2 | Complete | 2026-04-25 |
| 14. DB Foundation | v1.3 | 0/TBD | Not started | - |
| 15. Secrets Hygiene | v1.3 | 0/TBD | Not started | - |
| 16. Auth Hardening | v1.3 | 0/TBD | Not started | - |
