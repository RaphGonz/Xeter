# Roadmap: Xeter

## Overview

Xeter is built bottom-up in strict dependency order: the ClickHouse schema and infrastructure foundation must be locked before any data flows, ingestion must batch writes correctly from day one, and the flagging pipeline delivers the core differentiator before the read path or dashboard are built. Six phases take the project from an empty repo to a validated, shippable v1 — foundation, ingestion, analysis, read path, dashboard, and calibration.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Infrastructure running, schemas locked, multi-tenancy enforced, nothing broken later
- [ ] **Phase 2: Ingestion Path** - Spans flow from SDK through Analyser into ClickHouse and S3 with batched writes
- [ ] **Phase 3: Analysis Path** - Embedding Worker flags tool-call anomalies with configurable, logged similarity scores
- [ ] **Phase 4: Read Path** - Presenter merges ClickHouse and PostgreSQL and serves the full API with Diagnosticer scaffolded
- [ ] **Phase 5: Dashboard** - Developer can log in, see flagged spans, drill into detail, and understand what failed
- [ ] **Phase 6: Validation** - Thresholds calibrated against labelled spans, load tests pass, cross-tenant isolation confirmed

## Phase Details

### Phase 1: Foundation
**Goal**: Infrastructure is running, all schemas are locked with correct primary keys, multi-tenancy is enforced at the data access layer, and no schema decision can break later phases
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, STOR-01, AUTH-01, AUTH-03, AUTH-04, AUTH-05
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts ClickHouse, PostgreSQL, Redis, MinIO, backend, and frontend with no errors
  2. ClickHouse spans table exists with ORDER BY (tenant_id, trace_id, time_begin) and EXPLAIN confirms tenant+trace queries use the primary key index
  3. PostgreSQL migrations run cleanly: tenants, users, api_keys, and flags tables created with correct columns and RLS policies active
  4. DAL rejects any query that omits tenant_id — a test calling DAL without tenant_id returns an error
  5. Developer can register an account (tenant created, API key generated and stored as hash in PostgreSQL)
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — Docker Compose stack, .env.example, Makefile, and Python package scaffold
- [ ] 01-02-PLAN.md — PostgreSQL schema (SQLAlchemy models + Alembic migration + RLS) and ClickHouse spans table DDL
- [ ] 01-03-PLAN.md — Shared DAL: tenant guard, repository classes, API key hashing, RLS session context (TDD)
- [ ] 01-04-PLAN.md — POST /register endpoint, seed script, reset script, and registration integration tests

### Phase 2: Ingestion Path
**Goal**: An instrumented Python agent can emit spans via the SDK, spans arrive at the Analyser, large payloads land in S3, spans are written to ClickHouse in batches, and span IDs are enqueued in Redis for async analysis
**Depends on**: Phase 1
**Requirements**: SDK-01, SDK-02, SDK-03, SDK-04, SDK-05, STOR-02, STOR-04, STOR-05
**Success Criteria** (what must be TRUE):
  1. `pip install xeter-sdk` installs and a 3-line instrumentation snippet emits a span to a local Analyser
  2. Every emitted span includes all required fields (agent_name, agent_model, tool_name, tool_description, tool_arguments, tool_output, prompt, response, raw_response, available_tools_ref, trace_id, parent_span_id, xeter.schema.version); prompt/response/raw_response/available_tools are in S3 with reference keys in ClickHouse; tool_arguments stored inline as JSON in ClickHouse
  3. Analyser rejects spans with a missing or invalid API key with 401
  4. ClickHouse receives spans only via batched INSERT (confirmed by a test that emits 50 spans and observes one or more batch writes, never 50 individual inserts)
  5. A span_id appears in the Redis queue within 200ms of the Analyser returning 200
**Plans**: TBD

### Phase 3: Analysis Path
**Goal**: The Embedding Worker processes queued span IDs, computes cosine similarities, classifies tool-call anomalies into flag types, and writes flags to PostgreSQL with similarity scores logged for every span regardless of whether it was flagged
**Depends on**: Phase 2
**Requirements**: FLAG-01, FLAG-02, FLAG-03, FLAG-04, FLAG-05, FLAG-06, FLAG-07, FLAG-08, FLAG-09, FLAG-10, FLAG-11, FLAG-12, STOR-03
**Success Criteria** (what must be TRUE):
  1. A span with a clearly mismatched tool call (e.g., prompt asks to send email, tool is a database query) produces a wrong_tool flag in PostgreSQL with a score and detail JSON including ranked candidate tools from available_tools
  2. A clean span produces no flag row but still has similarity scores logged (score logging confirmed in the spans or a dedicated scores table)
  3. Similarity thresholds are read from config, not hardcoded — changing the config value changes which spans get flagged without a code change
  4. Adding a second analyzer (even a stub) to the registry causes the pipeline to dispatch each span to both analyzers without modifying the first analyzer
  5. flag_type column in PostgreSQL is a VARCHAR/text column and accepts an arbitrary string value (not an enum constraint)
  6. A span with mismatched tool_arguments (e.g., prompt asks to email Alice, tool_arguments contains Bob's address) produces a wrong_tool_args flag with a low-confidence score in the detail JSON
**Plans**: TBD

### Phase 4: Read Path
**Goal**: The Presenter API serves span lists with flag indicators, span detail with lazy S3 payload loading, and proxies to a scaffolded Diagnosticer that returns a 501 placeholder — all queries scoped by tenant
**Depends on**: Phase 3
**Requirements**: STOR-03, DASH-03, DASH-04, DASH-05, INFR-02
**Success Criteria** (what must be TRUE):
  1. GET /spans returns a list of spans with flag indicators and similarity score overlays without fetching any S3 payload content
  2. GET /spans/{id} returns span detail including flag details and lazy-loads prompt/response/raw_response from S3 only on that single request
  3. POST /diagnose forwards the request to the Diagnosticer scaffold and returns a 501 with a placeholder body
  4. All Presenter endpoints return 401 for requests missing a valid session token
  5. Authenticated Tenant A cannot retrieve Tenant B spans — GET /spans returns zero Tenant B rows when called with Tenant A credentials
**Plans**: TBD

### Phase 5: Dashboard
**Goal**: A developer can log in, view the span list filtered by flag type and time, drill into a span to see flag details and S3 payloads, and see the Diagnosticer entry point — with no business logic in the frontend
**Depends on**: Phase 4
**Requirements**: DASH-01, DASH-02, AUTH-02
**Success Criteria** (what must be TRUE):
  1. Developer navigates to the app, enters email and password, and reaches the span list without an error
  2. Span list shows flag badges on flagged spans and similarity score overlays; unanalysed spans show a "pending" status distinct from "clean"
  3. Developer can filter the span list by flag type, agent name, and time range and the list updates without a page reload
  4. Clicking a span opens the detail view showing which fields triggered the flag, the similarity score, and the configured threshold; prompt/response/raw_response load on demand, not on page load
  5. Detail view shows a "Request Diagnostic" button that calls POST /diagnose and displays the 501 placeholder response
**Plans**: TBD

### Phase 6: Validation
**Goal**: Embedding thresholds are calibrated against labelled spans, critical infrastructure invariants are confirmed under load, and the system is ready to trust before being presented to users
**Depends on**: Phase 5
**Requirements**: (no new requirements — this phase validates all prior requirements against real runtime behaviour)
**Success Criteria** (what must be TRUE):
  1. Calibration harness runs against 200+ labelled spans and produces a precision/recall curve; threshold config is updated to the calibrated value with a documented rationale
  2. Load test at 500 spans/second sustained for 60 seconds completes without ClickHouse "Too Many Parts" errors
  3. Cross-tenant isolation integration test authenticates as Tenant A and confirms zero Tenant B rows in every API response
  4. End-to-end latency from SDK emit to flag row in PostgreSQL is confirmed below 5 seconds at normal load (ingestion <200ms, worker processing <4.8s)
  5. Every span emitted by the SDK carries xeter.schema.version and all similarity scores are present in the score log for every processed span
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/4 | Not started | - |
| 2. Ingestion Path | 0/TBD | Not started | - |
| 3. Analysis Path | 0/TBD | Not started | - |
| 4. Read Path | 0/TBD | Not started | - |
| 5. Dashboard | 0/TBD | Not started | - |
| 6. Validation | 0/TBD | Not started | - |
