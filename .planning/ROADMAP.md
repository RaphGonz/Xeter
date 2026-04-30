# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- ✅ **v1.2 Diagnosticer** — Phases 11–13 (shipped 2026-04-25)
- 🚧 **v1.3 Security Hardening** — Phases 14–17 (in progress)

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

**Milestone Goal:** Close all pre-launch security gaps — tenant isolation completion, DB-level validation, secrets hygiene, auth hardening, and GDPR data deletion.

- [x] **Phase 14: DB Foundation** — RLS on span_scores, FORCE RLS on all tables, CHECK constraints on diagnoses, S3 tenant key prefix (completed 2026-04-29)
- [x] **Phase 15: Secrets Hygiene** — docker-compose secrets cleanup, generate-secrets.sh, MinIO bucket assertion, bcrypt CI enforcement, passlib removal, Redis AUTH (completed 2026-04-29)
- [ ] **Phase 16: Auth Hardening** — JWT 30-min expiry, hard-fail on missing SECRET_KEY, httpOnly refresh token, JWT_SECRET runbook, internal API key, CORS
- [ ] **Phase 17: GDPR Data Deletion** — delete_tenant.py covering ClickHouse, PostgreSQL, S3, and documented Redis flush

## Phase Details

### Phase 14: DB Foundation
**Goal**: All PostgreSQL tables have enforced tenant isolation, domain-valid diagnosis values, and S3 payloads are structurally scoped to tenant
**Depends on**: Phase 13 (v1.2 complete)
**Requirements**: DB-01, DB-02, DB-03, S3-01
**Success Criteria** (what must be TRUE):
  1. Developer can write a span_scores row as worker and verify it is only visible to the correct tenant — the tenant_isolation RLS policy exists on span_scores and score_writer.py uses SET LOCAL inside an explicit transaction
  2. Developer can confirm no table owner can silently bypass RLS — SELECT relforcerowsecurity FROM pg_class WHERE relname IN ('spans','flags','span_scores','diagnoses','tenants','api_keys') returns t for all six rows
  3. Developer can trust verdict and severity columns reject unexpected values — INSERT with verdict='undetermined' or severity='critical' raises a constraint violation after VALIDATE CONSTRAINT runs
  4. Migration 004 applies cleanly from zero (fresh alembic upgrade) and idempotently (second run exits without error)
  5. All S3 payload keys for new spans use `{tenant_id}/{span_id}/...` prefix; Presenter S3 fetch asserts the key belongs to the requesting tenant before returning content; a unit test fetching a span key as the wrong tenant returns 403
  6. Diagnosticer LLM provider code only emits verdict values in `('model','architecture','prompt','unknown')` and severity values in `('low','medium','high')`; pre-flight violation query against existing `diagnoses` rows returns zero results before `VALIDATE CONSTRAINT` runs
  7. An integration test connects to PostgreSQL without calling `set_config` and asserts `SELECT COUNT(*) FROM span_scores` returns 0 even when rows exist — confirming RLS silent-empty behavior is detected, not invisible
**Plans**: 3 plans

Plans:
- [ ] 14-01-PLAN.md — Fix provider Literals + pre-flight audit script (DB-03 prerequisite)
- [ ] 14-02-PLAN.md — Presenter S3 tenant-prefix assertion + unit tests (S3-01)
- [ ] 14-03-PLAN.md — Migration 004 + score_writer SET LOCAL + unit tests (DB-01, DB-02, DB-03)

### Phase 15: Secrets Hygiene
**Goal**: Secrets cannot be accidentally committed, the deployment stack uses safe defaults, and Redis is authenticated
**Depends on**: Phase 13 (can execute independently of Phase 14 and 16)
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, DB-04
**Success Criteria** (what must be TRUE):
  1. Developer running git add .env sees it blocked — root .gitignore contains .env; docker-compose references env vars with CHANGE_ME_BEFORE_DEPLOY as the documented-insecure default
  2. Operator can run bash generate-secrets.sh and receive a valid .env file with random secrets in one step — the script uses openssl rand -hex 32 for all secret values and includes a git-tracking guard
  3. MinIO xeter-payloads bucket denies anonymous reads on every docker-compose up — minio-init container runs mc anonymous set none and the deployment guide documents the equivalent mc policy set and S3 IAM JSON for cloud
  4. CI fails if bcrypt cost factor drops below 12 — a test reads the hash prefix and asserts $2b$12$; all test fixtures that call bcrypt.hashpw use rounds=4 with session scope
  5. passlib[bcrypt] does not appear in pyproject.toml or any import
  6. Redis requires password authentication — REDIS_PASSWORD env var in docker-compose with no :- fallback; unauthenticated redis-cli ping to the Redis container returns NOAUTH Authentication required
  7. minio-init mc alias set command string references ${MINIO_ROOT_PASSWORD}, not a hardcoded literal
**Plans**: 3 plans

Plans:
- [ ] 15-01-PLAN.md — Root .gitignore + generate-secrets.sh + .env.example update (OPS-01, OPS-02)
- [ ] 15-02-PLAN.md — docker-compose hardening: Redis --requirepass, MinIO mc anonymous set none, all env var wiring (OPS-03, OPS-05)
- [ ] 15-03-PLAN.md — Remove passlib + bcrypt cost-factor CI test + test fixture rounds=4 (OPS-04, DB-04)

### Phase 16: Auth Hardening
**Goal**: Session tokens expire promptly, refresh is seamless and XSS-safe, internal service calls are authenticated, and the SECRET_KEY rotation procedure is documented
**Depends on**: Phase 14 (schema ready), Phase 15 (SECRET_KEY hard-fail in place before refresh flow)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04
**Success Criteria** (what must be TRUE):
  1. Developer starting the Presenter without SECRET_KEY set sees a startup exception — os.environ["SECRET_KEY"] raises KeyError; no :- fallback exists in docker-compose for SECRET_KEY
  2. Access tokens expire after 30 minutes — TOKEN_EXPIRE_MINUTES = 30 in deps.py; a test that decodes a freshly issued token confirms exp - iat = 1800 seconds
  3. User whose access token has expired can continue using the dashboard without re-logging in — Next.js 401 interceptor calls /api/auth/refresh, the Route Handler reads the httpOnly cookie and returns a new session_token in JSON, and the original request retries transparently
  4. Operator has a written runbook that describes how to rotate JWT_SECRET with zero code changes — the runbook covers the 30-minute re-login gap, the dual-secret window option, and the service restart sequence
  5. Presenter includes X-Internal-Api-Key: ${INTERNAL_API_KEY} on every HTTP call to Diagnosticer; Diagnosticer middleware returns 401 on any request missing or providing a wrong value; INTERNAL_API_KEY is a required env var (KeyError on startup) in both services
  6. CORSMiddleware is present in Presenter with allow_credentials=True and explicit allow_origins (never "*"); cookie secure and samesite settings are driven by an ENVIRONMENT env var — dev: secure=False, samesite="lax"; prod: secure=True, samesite="strict"
  7. services/view test files are audited for window.sessionStorage mocks before auth.ts change lands; test suite passes after sessionStorage removal
**Plans**: 5 plans

Plans:
- [ ] 16-01-PLAN.md — Python backend hard-fail: SECRET_KEY + INTERNAL_API_KEY + 30min expiry + Diagnosticer middleware (AUTH-01, AUTH-04)
- [ ] 16-02-PLAN.md — JWT rotation runbook (AUTH-03)
- [ ] 16-03-PLAN.md — Presenter refresh endpoint + CORS + diagnosis_service INTERNAL_API_KEY + docker-compose wiring (AUTH-02, AUTH-04)
- [ ] 16-04-PLAN.md — Fix test suite for hard-fail env vars + new response shapes (AUTH-01, AUTH-04)
- [ ] 16-05-PLAN.md — Next.js Route Handlers + auth.ts sessionStorage removal + api.ts 401 interceptor (AUTH-02)

### Phase 17: GDPR Data Deletion
**Goal**: All data for a given tenant can be fully deleted in one operator command
**Depends on**: Phase 14 (S3 prefix required for complete deletion by tenant prefix), Phase 16 (full v1.3 in place before deletion tooling is shipped)
**Requirements**: GDPR-01
**Success Criteria** (what must be TRUE):
  1. delete_tenant.py --tenant-id <id> prints a dry-run summary by default showing counts of rows and S3 objects that would be deleted; --confirm flag required to execute
  2. Deletion covers all four data stores: ClickHouse (ALTER TABLE spans DELETE WHERE tenant_id = :id), PostgreSQL (flags, span_scores, diagnoses, users, api_keys, tenants), S3 (all objects under {tenant_id}/ prefix via aws s3 rm --recursive), and a documented Redis key flush procedure
  3. Script is idempotent — running it twice on the same tenant produces no error and no additional side effects
  4. GDPR Art. 17 deletion procedure is documented in the deployment guide with the exact command and expected output
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
| 14. DB Foundation | v1.3 | 3/3 | Complete | 2026-04-29 |
| 15. Secrets Hygiene | v1.3 | 3/3 | Complete | 2026-04-29 |
| 16. Auth Hardening | 4/5 | In Progress|  | - |
| 17. GDPR Data Deletion | v1.3 | 0/TBD | Not started | - |
