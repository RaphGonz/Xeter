# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Phase 1 — Foundation

## Current Position

Phase: 1 of 6 (Foundation)
Plan: 3 of 4 in current phase
Status: In progress
Last activity: 2026-03-27 — Completed Plan 03 (DAL tenant guard + repository layer + TDD tests)

Progress: [███░░░░░░░] 12%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~14 min
- Total execution time: ~0.7 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3 completed | 43 min | ~14 min |

**Recent Trend:**
- Last 5 plans: 01-01 (15 min), 01-02 (14 min), 01-03 (14 min)
- Trend: Consistent

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Foundation: ClickHouse ORDER BY (tenant_id, trace_id, time_begin) is a one-way door — must be set and verified in Phase 1 before any data is written
- Foundation: DAL (data access layer) enforces tenant_id injection — no call-site filtering; PostgreSQL RLS is defence-in-depth
- Ingestion: ClickHouse writes are batched via Redis queue — single-row inserts are forbidden from day one (Too Many Parts risk)
- Analysis: Embedding thresholds are first-class config from day one; all similarity scores logged regardless of flag outcome (calibration dataset)
- Read Path: Diagnosticer is scaffolded in Phase 4 returning 501 — wired now so Milestone 2 activates without rearchitecting
- 01-01: Removed obsolete docker-compose 'version' key — Docker Compose v2 deprecates it, causes CI log noise
- 01-01: Used pytest-asyncio==0.24.0 instead of plan-specified 1.3.0 (1.3.0 does not exist; package uses 0.x versioning)
- 01-01: View stub uses static 'serve' server in Phase 1 — Next.js scaffolded in a later plan
- 01-02: flag_type is String (VARCHAR) not PostgreSQL enum — allows new flag types without schema migrations (FLAG-03)
- 01-02: RLS uses current_setting('app.current_tenant_id', true) with true to avoid errors when variable unset during migrations
- 01-02: ClickHouse ORDER BY (tenant_id, trace_id, time_begin) set and locked as one-way door before any data flows
- 01-03: bcrypt used directly instead of passlib CryptContext — passlib 1.7.4 incompatible with Python 3.14 + current bcrypt
- 01-03: require_tenant() raises at Python boundary before any DB call — RLS is defence-in-depth only
- 01-03: TenantRepository.create() has no guard — bootstrap-level, tenant does not exist yet when creating

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3: Embedding threshold initial default is unknown — no published benchmarks for agent tool-call cosine similarity exist. Treat initial value as hypothesis; calibrate in Phase 6 against 200+ labelled spans.
- Phase 6: Labelled dataset sourcing not yet specified — may need a research spike before executing calibration harness.

## Session Continuity

Last session: 2026-03-27
Stopped at: Completed 01-03-PLAN.md — DAL tenant guard + repository layer + TDD tests
Resume file: None
