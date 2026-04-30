# Requirements: Xeter

**Defined:** 2026-04-27
**Core Value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## v1.3 Requirements

Requirements for v1.3 Security Hardening. Each maps to roadmap phases.

### Database Security

- [ ] **DB-01**: Developer can rely on span_scores rows being tenant-isolated — RLS tenant_isolation policy added; score_writer.py uses SET LOCAL in transaction (matching flag_writer.py pattern)
- [ ] **DB-02**: Developer can rely on all RLS policies being enforced even for the table owner role — FORCE ROW LEVEL SECURITY added retroactively to all existing RLS tables
- [ ] **DB-03**: Developer can trust verdict and severity values are domain-valid at DB level — CHECK constraints added via NOT VALID + VALIDATE CONSTRAINT two-step, with pre-flight violation query before VALIDATE
- [x] **DB-04**: Project has no dead passlib[bcrypt] dependency — removed from pyproject.toml

### Data Isolation

- [x] **S3-01**: All S3 payload keys are prefixed with the tenant ID — key format is `{tenant_id}/{span_id}/prompt` (and `/response`, `/raw_response`, `/available_tools`); Presenter asserts the fetched key starts with the requesting tenant's ID before returning content; a unit test confirms a cross-tenant key fetch returns 403

### Authentication

- [x] **AUTH-01**: Session tokens expire after 30 minutes; server hard-fails on startup if SECRET_KEY env var is unset (no silent fallback to dev key)
- [ ] **AUTH-02**: User can silently refresh an expired access token via httpOnly refresh token cookie — Presenter POST /auth/refresh endpoint; Next.js Route Handlers for /api/login and /api/auth/refresh; sessionStorage removed from auth.ts
- [ ] **AUTH-03**: Operator has a documented JWT_SECRET rotation runbook covering dual-secret window and service restart sequence
- [x] **AUTH-04**: Presenter-to-Diagnosticer calls are authenticated by a static internal API key — `INTERNAL_API_KEY` env var (required, no fallback) present in both services; Presenter includes it as `X-Internal-Api-Key` request header; Diagnosticer middleware rejects any request missing or providing a wrong value with 401

### Operations & Secrets

- [x] **OPS-01**: Developer cannot accidentally commit secrets — root .gitignore excludes .env; docker-compose uses env var refs with CHANGE_ME_BEFORE_DEPLOY defaults
- [x] **OPS-02**: Operator can generate a valid random .env in one command via generate-secrets.sh (uses openssl rand)
- [x] **OPS-03**: xeter-payloads MinIO bucket is asserted private on every startup (mc anonymous set none in minio-init container); deployment guide documents mc policy set and S3 IAM JSON
- [x] **OPS-04**: CI fails if bcrypt cost factor drops below 12; test fixtures use rounds=4 with session scope to avoid CI slowdown
- [x] **OPS-05**: Redis requires password authentication — `REDIS_PASSWORD` env var in docker-compose with no `:-` fallback; Redis started with `--requirepass ${REDIS_PASSWORD}`; an unauthenticated `redis-cli ping` returns `NOAUTH Authentication required`

### GDPR & Data Retention

- [ ] **GDPR-01**: Operator can delete all data for a given tenant in one command — `delete_tenant.py --tenant-id <id>` shows a dry-run summary of affected rows and S3 objects by default; `--confirm` flag required to execute; deletion covers ClickHouse spans (`ALTER TABLE spans DELETE WHERE tenant_id = :id`), all PostgreSQL tables (`flags`, `span_scores`, `diagnoses`, `users`, `api_keys`, `tenants`), all S3 objects under `{tenant_id}/` prefix, and a documented Redis key flush procedure; script is idempotent

## Future Requirements

### Authentication

- **AUTH-F01**: Refresh token revocation store — server-side blacklist for stolen token detection (deferred; httpOnly cookie + client-side clear sufficient for v1.3 threat model)
- **AUTH-F02**: python-jose → PyJWT migration — python-jose is near-abandoned; migrate before it becomes a CVE liability (v1.4)

### SDK

- **SDK-F01**: TypeScript/Node.js SDK for instrumenting JS-based agents (deferred to v1.4+)

### Access Control

- **ACL-F01**: Per-service MinIO IAM service accounts (deferred; single bucket policy sufficient for v1.3)

### Data Isolation

- **DB-F01**: ClickHouse per-service read-only users and row-level policies — ClickHouse cannot enforce tenant isolation at the DB layer; create a read-only ClickHouse user per service scoped to the `xeter` database and document this as an architectural constraint requiring ClickHouse Cloud row policies for full enforcement (deferred; Python DAL + integration test is the v1.3 enforcement layer)

### Operations

- **OPS-F01**: Rate limiting on Analyser ingestion — per-API-key sliding window using Redis; configurable `RATE_LIMIT_SPANS_PER_MINUTE` env var; HTTP 429 with `Retry-After` header; maximum payload size rejection before S3 touch (deferred to v1.4; B2B customer set mitigates runaway-agent risk for v1.3)
- **OPS-F02**: Per-tenant Redis queue keys — replace global `analysis_queue` list with `analysis_queue:{tenant_id}` keys; Worker pops in round-robin across tenant queues to prevent starvation (deferred to v1.4; Worker refactor independent from v1.3 security surface)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Prompt management / versioning | Competes with Langfuse on their home turf; not our moat |
| LLM cost attribution / billing analytics | General observability breadth, not diagnosis |
| Multi-model A/B comparison | Established players own this |
| LLM-as-a-judge eval pipelines | HoneyHive and LangSmith have mature offerings |
| On-premise distribution | SaaS only per constraints |
| Clerk auth migration | Schema supports it; deferred to when multi-member tenants are needed |
| Refresh token DB revocation table | httpOnly cookie + client-side clear is sufficient for current threat model |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 14 | Pending |
| DB-02 | Phase 14 | Pending |
| DB-03 | Phase 14 | Pending |
| S3-01 | Phase 14 | Complete |
| DB-04 | Phase 15 | Complete |
| OPS-01 | Phase 15 | Complete |
| OPS-02 | Phase 15 | Complete |
| OPS-03 | Phase 15 | Complete |
| OPS-04 | Phase 15 | Complete |
| OPS-05 | Phase 15 | Complete |
| AUTH-01 | Phase 16 | Complete |
| AUTH-02 | Phase 16 | Pending |
| AUTH-03 | Phase 16 | Pending |
| AUTH-04 | Phase 16 | Complete |
| GDPR-01 | Phase 17 | Pending |

**Coverage:**
- v1.3 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-27*
*Last updated: 2026-04-27 — traceability updated after v1.3 roadmap creation*
