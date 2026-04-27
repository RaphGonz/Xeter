# Requirements: Xeter

**Defined:** 2026-04-27
**Core Value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## v1.3 Requirements

Requirements for v1.3 Security Hardening. Each maps to roadmap phases.

### Database Security

- [ ] **DB-01**: Developer can rely on span_scores rows being tenant-isolated — RLS tenant_isolation policy added; score_writer.py uses SET LOCAL in transaction (matching flag_writer.py pattern)
- [ ] **DB-02**: Developer can rely on all RLS policies being enforced even for the table owner role — FORCE ROW LEVEL SECURITY added retroactively to all existing RLS tables
- [ ] **DB-03**: Developer can trust verdict and severity values are domain-valid at DB level — CHECK constraints added via NOT VALID + VALIDATE CONSTRAINT two-step, with pre-flight violation query before VALIDATE
- [ ] **DB-04**: Project has no dead passlib[bcrypt] dependency — removed from pyproject.toml

### Authentication

- [ ] **AUTH-01**: Session tokens expire after 30 minutes; server hard-fails on startup if SECRET_KEY env var is unset (no silent fallback to dev key)
- [ ] **AUTH-02**: User can silently refresh an expired access token via httpOnly refresh token cookie — Presenter POST /auth/refresh endpoint; Next.js Route Handlers for /api/login and /api/auth/refresh; sessionStorage removed from auth.ts
- [ ] **AUTH-03**: Operator has a documented JWT_SECRET rotation runbook covering dual-secret window and service restart sequence

### Operations & Secrets

- [ ] **OPS-01**: Developer cannot accidentally commit secrets — root .gitignore excludes .env; docker-compose uses env var refs with CHANGE_ME_BEFORE_DEPLOY defaults
- [ ] **OPS-02**: Operator can generate a valid random .env in one command via generate-secrets.sh (uses openssl rand)
- [ ] **OPS-03**: xeter-payloads MinIO bucket is asserted private on every startup (mc anonymous set none in minio-init container); deployment guide documents mc policy set and S3 IAM JSON
- [ ] **OPS-04**: CI fails if bcrypt cost factor drops below 12; test fixtures use rounds=4 with session scope to avoid CI slowdown

## Future Requirements

### Authentication

- **AUTH-F01**: Refresh token revocation store — server-side blacklist for stolen token detection (deferred; httpOnly cookie + client-side clear sufficient for v1.3 threat model)
- **AUTH-F02**: python-jose → PyJWT migration — python-jose is near-abandoned; migrate before it becomes a CVE liability (v1.4)

### SDK

- **SDK-F01**: TypeScript/Node.js SDK for instrumenting JS-based agents (deferred to v1.4+)

### Access Control

- **ACL-F01**: Per-service MinIO IAM service accounts (deferred; single bucket policy sufficient for v1.3)

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
| DB-04 | Phase 15 | Pending |
| OPS-01 | Phase 15 | Pending |
| OPS-02 | Phase 15 | Pending |
| OPS-03 | Phase 15 | Pending |
| OPS-04 | Phase 15 | Pending |
| AUTH-01 | Phase 16 | Pending |
| AUTH-02 | Phase 16 | Pending |
| AUTH-03 | Phase 16 | Pending |

**Coverage:**
- v1.3 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-27*
*Last updated: 2026-04-27 — traceability updated after v1.3 roadmap creation*
