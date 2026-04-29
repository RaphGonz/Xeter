---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Security Hardening
status: unknown
last_updated: "2026-04-29T13:21:45Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-27)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** v1.3 Security Hardening — Phase 15: Secrets Hygiene

## Current Position

Phase: 15 of 16 (Secrets Hygiene) — COMPLETE
Plan: 3 of 3 complete (15-01 .env.example, 15-02 docker-compose hardening, 15-03 passlib removal + bcrypt CI guard)
Status: Phase 15 complete — ready for Phase 16
Last activity: 2026-04-29 — 15-03 complete: passlib[bcrypt] removed, bcrypt>=4.0 direct dep, CI cost-factor test added, session-scoped rounds=4 fixture in auth tests

Progress: [████░░░░░░] ~40% (v1.3 — Phase 15 complete)

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
- 15-02: No :- fallbacks for secrets in docker-compose.yml — fail-loud at startup if var unset (intentional)
- 15-02: mc anonymous set none runs on every docker compose up via minio-init (idempotent bucket privacy)
- 15-03: Replaced passlib[bcrypt]>=1.7 with direct bcrypt>=4.0 — removes dead supply-chain dep (DB-04)
- 15-03: rounds=4 in test fixtures only; cost-factor test uses unparameterised gensalt() to assert production minimum (OPS-04)

### Pending Todos

None.

### Blockers/Concerns

- Phase 16 depends on Phase 14 landing first (span_scores RLS must exist before score_writer.py SET LOCAL is meaningful)
- Before running VALIDATE CONSTRAINT in Phase 14: run xeter/scripts/preflight_diagnoses_audit.py — existing v1.2 data may violate new constraints

## Session Continuity

Last session: 2026-04-29 — Phase 15 complete: 15-03 done (passlib removed, bcrypt CI cost-factor guard added, session-scoped fixture in auth tests).
Stopped at: 15-03 execution complete
Next: /gsd:execute-phase 16
