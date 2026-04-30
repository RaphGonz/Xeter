---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Security Hardening
status: unknown
last_updated: "2026-04-30T12:32:10.476Z"
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 20
  completed_plans: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-27)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.3 Security Hardening — COMPLETE (Phase 17: GDPR Data Deletion done)

## Current Position

Phase: 17 of 17 (GDPR Data Deletion) — COMPLETE
Plan: 1 of 1 complete (17-01 GDPR Art. 17 delete_tenant.py + runbook)
Status: Phase 17 complete — all v1.3 security hardening requirements done
Last activity: 2026-04-30 — 17-01 complete: delete_tenant.py (302 lines) with dry-run + --confirm gate, GDPR_DELETION_RUNBOOK.md (216 lines), GDPR-01 satisfied

Progress: [██████████] 100% (v1.3 — all phases complete)

## Accumulated Context

All decisions logged in PROJECT.md Key Decisions table.
v1.0–v1.2 retrospective in RETROSPECTIVE.md.

### Key Decisions (v1.3)

- Worker RLS: SET LOCAL app.current_tenant_id in explicit transaction (score_writer.py) — no separate BYPASSRLS role
- Refresh token: long-lived HS256 JWT in httpOnly cookie; no DB revocation table (accepted v1.3 tradeoff)
- httpOnly cookie set by Next.js Route Handler, not Presenter directly (Next.js rewrites strip upstream Set-Cookie)
- CHECK constraints: NOT VALID migration + manual VALIDATE after pre-flight data audit (avoids ACCESS EXCLUSIVE lock)
- 14-01: Provider vocabulary aligned BEFORE migration runs — ensures no new bad rows in window before VALIDATE CONSTRAINT; preflight_diagnoses_audit.py exits 0/1 with repair SQL
- S3-01 guard: key.startswith(f"{tenant_id}/") check before GetObject raises HTTP 403 — defence-in-depth independent of ClickHouse tenant filter
- 15-01: Shared passwords (PG_PASS, REDIS_PASS, MINIO_PASS) pre-generated into shell vars before heredoc in generate-secrets.sh — prevents DATABASE_URL/POSTGRES_URL from receiving different passwords
- 15-01: ANTHROPIC_API_KEY and OPENAI_API_KEY intentionally left as CHANGE_ME_BEFORE_DEPLOY in generate-secrets.sh — require manual operator input
- 15-02: No :- fallbacks for secrets in docker-compose.yml — fail-loud at startup if var unset (intentional)
- 15-02: mc anonymous set none runs on every docker compose up via minio-init (idempotent bucket privacy)
- 15-03: Replaced passlib[bcrypt]>=1.7 with direct bcrypt>=4.0 — removes dead supply-chain dep (DB-04)
- 15-03: rounds=4 in test fixtures only; cost-factor test uses unparameterised gensalt() to assert production minimum (OPS-04)
- 16-01: SECRET_KEY uses os.environ[] hard-fail in both presenter and diagnosticer — eliminates dev-key silently deployed to production (AUTH-01)
- 16-01: TOKEN_EXPIRE_MINUTES=30 replaces TOKEN_EXPIRE_HOURS=24 — access tokens now 30-minute lifetime
- 16-01: InternalApiKeyMiddleware on diagnosticer establishes service trust boundary — Presenter must pass X-Internal-Api-Key (AUTH-04)
- 16-01: verify_session_token kept in diagnosticer for backwards compat with existing test dependency_overrides
- 16-02: Recommend Option A (30-minute gap) for v1.3 — no temporary code changes; Option B documented for hard zero-re-auth requirements only
- 16-02: python-jose HS256 requires manual try/except decode loop for dual-secret window — no built-in multi-secret support (unlike RS256 JWKS)
- 16-02: Restart sequence is Diagnosticer-first — avoids window where Presenter issues new-key tokens that Diagnosticer still rejects
- 16-03: POST /auth/refresh is stateless — no DB revocation table; refresh token revocation deferred to AUTH-F01 (accepted v1.3 tradeoff)
- 16-03: CORS_ALLOW_ORIGINS env var split on comma at startup — supports multi-origin without code change; never wildcard with allow_credentials=True
- 16-03: auth_header parameter removed from DiagnosisService.trigger(); Presenter now sends X-Internal-Api-Key + X-Tenant-Id to Diagnosticer (AUTH-04 complete)
- 16-04: conftest.py setdefault before imports — prevents KeyError at pytest collection; test_diagnose_endpoint uses X-Internal-Api-Key not verify_session_token overrides
- 16-05: auth.ts hydrate() sets hydrated:true immediately (no storage read) — eliminates infinite redirect loop on page reload; token comes from 401 interceptor retry
- 16-05: 401 interceptor retries exactly once — no loop; on failed refresh, clears token and throws HTTP 401 so redirect fires
- 16-05: refresh_token stripped at Route Handler boundary — only session_token reaches browser JS
- 17-01: Redis flush for GDPR is documented procedure only — analysis_queue is global; no automated per-tenant LREM (FLUSHDB prohibited)
- 17-01: ClickHouse ALTER TABLE spans DELETE is async MergeTree mutation — script submits and returns; verify after 30s via dry-run re-run
- 17-01: PostgreSQL GDPR deletion uses single autocommit=False connection with commit() after all 7 DELETEs in FK order (span_scores → diagnostics → diagnoses → flags → api_keys → users → tenants)
- 17-01: delete_tenant.py idempotent by construction — no tenant-existence pre-check; DELETE WHERE on absent rows is no-op

### Pending Todos

None.

### Blockers/Concerns

- Phase 16 depends on Phase 14 landing first (span_scores RLS must exist before score_writer.py SET LOCAL is meaningful)
- Before running VALIDATE CONSTRAINT in Phase 14: run xeter/scripts/preflight_diagnoses_audit.py — existing v1.2 data may violate new constraints

## Session Continuity

Last session: 2026-04-30 — 17-01 complete: delete_tenant.py GDPR Art. 17 script + GDPR_DELETION_RUNBOOK.md. GDPR-01 satisfied. Phase 17 complete. v1.3 milestone fully reached.
Stopped at: Completed 17-01-PLAN.md
Next: v1.3 Security Hardening milestone complete — all requirements satisfied
