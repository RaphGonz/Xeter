---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Security Hardening
status: unknown
last_updated: "2026-04-30T07:26:14Z"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 14
  completed_plans: 14
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-27)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.3 Security Hardening — Phase 16: Auth Hardening

## Current Position

Phase: 16 of 16 (Auth Hardening) — IN PROGRESS
Plan: 4 of 5 complete (16-01 SECRET_KEY hard-fails; 16-02 JWT_SECRET rotation runbook; 16-03 refresh token + INTERNAL_API_KEY + CORS; 16-04 test suite fixes)
Status: 16-04 complete — ready for 16-05
Last activity: 2026-04-30 — 16-04 complete: conftest.py env defaults, test_auth_login refresh_token assertions, test_diagnose_endpoint InternalApiKeyMiddleware tests, test_diagnose X-Internal-Api-Key header assertions

Progress: [████████░░] ~80% (v1.3 — Phase 16 plan 04 complete)

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

### Pending Todos

None.

### Blockers/Concerns

- Phase 16 depends on Phase 14 landing first (span_scores RLS must exist before score_writer.py SET LOCAL is meaningful)
- Before running VALIDATE CONSTRAINT in Phase 14: run xeter/scripts/preflight_diagnoses_audit.py — existing v1.2 data may violate new constraints

## Session Continuity

Last session: 2026-04-30 — 16-04 complete: conftest.py setdefault SECRET_KEY/INTERNAL_API_KEY, test_auth_login refresh_token assertion, test_diagnose_endpoint InternalApiKeyMiddleware tests (missing/wrong/correct key), test_diagnose X-Internal-Api-Key forwarding assertion. 44 presenter+diagnosticer tests pass.
Stopped at: Completed 16-04-PLAN.md
Next: /gsd:execute-phase 16 (plan 05 remaining — frontend)
