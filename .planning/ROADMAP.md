# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- ✅ **v1.2 Diagnosticer** — Phases 11–13 (shipped 2026-04-25)
- ✅ **v1.3 Security Hardening** — Phases 14–17 (shipped 2026-05-02)
- 🚧 **v1.4 Trace Hierarchy + TraceAnalyzer Foundation** — Phases 18–21 (in progress)

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

<details>
<summary>✅ v1.3 Security Hardening (Phases 14–17) — SHIPPED 2026-05-02</summary>

- [x] Phase 14: DB Foundation (3/3 plans) — completed 2026-04-29
- [x] Phase 15: Secrets Hygiene (3/3 plans) — completed 2026-04-29
- [x] Phase 16: Auth Hardening (5/5 plans) — completed 2026-04-30
- [x] Phase 17: GDPR Data Deletion (1/1 plan) — completed 2026-04-30

See `.planning/milestones/v1.3-ROADMAP.md` for full phase details.

</details>

### 🚧 v1.4 Trace Hierarchy + TraceAnalyzer Foundation (In Progress)

**Milestone Goal:** Remove v1.3 tech debt, introduce the 3-class analyzer hierarchy (BaseSpanAnalyzer + BaseTraceAnalyzer), scaffold TraceAnalyzer into the worker, extend the flags schema for trace-level flags, and expose trace-level data via API and dashboard UI.

- [ ] **Phase 18: Cleanup + BaseAnalyzer Refactor** — Remove v1.3 dead code and restructure analyzer hierarchy into generic root + BaseSpanAnalyzer + BaseTraceAnalyzer
- [ ] **Phase 19: TraceAnalyzer Scaffold + DB Migration** — Wire TraceAnalyzer into worker with flush-timeout trigger; extend flags table schema for trace-level flags
- [ ] **Phase 20: Trace API** — Add GET /traces and GET /traces/{trace_id} endpoints with tenant RLS, assembling data from ClickHouse and PostgreSQL
- [ ] **Phase 21: Trace UI** — Add Traces list page and collapsible trace detail tree to dashboard; back-navigation from span detail

## Phase Details

### Phase 18: Cleanup + BaseAnalyzer Refactor
**Goal**: Remove v1.3 tech debt and refactor BaseAnalyzer into the 3-class hierarchy (generic root + BaseSpanAnalyzer + BaseTraceAnalyzer); no new behavior, only cleanup and restructuring
**Depends on**: Phase 17 (v1.3 complete)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, TANA-01
**Success Criteria** (what must be TRUE):
  1. Dead `verify_session_token()` is absent from `diagnosticer/main.py` and all tests pass
  2. Stale "NO PostgreSQL RLS" comments are absent from `spans.py`
  3. All env var defaults have been audited and any unsafe fallbacks removed or documented
  4. `BaseAnalyzer`, `BaseSpanAnalyzer`, and `BaseTraceAnalyzer` exist as distinct classes; `ToolCallAnalyzer` inherits from `BaseSpanAnalyzer`; existing analyzer tests pass unchanged
**Plans**: TBD

### Phase 19: TraceAnalyzer Scaffold + DB Migration
**Goal**: Wire a TraceAnalyzer scaffold into the worker with a flush-timeout trigger; extend the flags table so span_id is nullable and trace_id is non-nullable, with backfill of existing rows
**Depends on**: Phase 18
**Requirements**: TANA-02, TANA-03, TANA-04
**Success Criteria** (what must be TRUE):
  1. Worker accumulates spans by trace_id and triggers TraceAnalyzer after the flush timeout elapses with no new spans for that trace
  2. TraceAnalyzer scaffold runs without error and produces no flags (no checks implemented yet)
  3. flags table migration applies cleanly: span_id is nullable, trace_id is non-nullable, and all pre-existing rows have trace_id backfilled from the ClickHouse span record
  4. All existing flag-write and flag-read paths continue to function correctly after the schema change
**Plans**: TBD

### Phase 20: Trace API
**Goal**: Add GET /traces and GET /traces/{trace_id} endpoints to the Presenter with tenant RLS, assembling trace data from ClickHouse (spans) and PostgreSQL (flags, scores)
**Depends on**: Phase 19
**Requirements**: TRACE-01, TRACE-02
**Success Criteria** (what must be TRUE):
  1. GET /traces returns a list of traces for the authenticated tenant, each with trace_id, span count, and flag count
  2. GET /traces/{trace_id} returns the full trace: all spans in hierarchy order with their flags and scores; cross-tenant requests are rejected
  3. Both endpoints enforce tenant RLS — a request authenticated as tenant A cannot retrieve traces belonging to tenant B
**Plans**: TBD

### Phase 21: Trace UI
**Goal**: Add a Traces list page and a collapsible trace detail tree to the dashboard; enable back-navigation from span detail to parent trace
**Depends on**: Phase 20
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. Dashboard has a Traces list page showing all traces for the tenant with span and flag counts
  2. Trace detail page renders spans as a collapsible parent/child tree using parent_span_id, with flag badges on each span
  3. From any span detail view, the user can navigate back to the parent trace detail page
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
| 16. Auth Hardening | v1.3 | 5/5 | Complete | 2026-04-30 |
| 17. GDPR Data Deletion | v1.3 | 1/1 | Complete | 2026-04-30 |
| 18. Cleanup + BaseAnalyzer Refactor | v1.4 | 0/TBD | Not started | - |
| 19. TraceAnalyzer Scaffold + DB Migration | v1.4 | 0/TBD | Not started | - |
| 20. Trace API | v1.4 | 0/TBD | Not started | - |
| 21. Trace UI | v1.4 | 0/TBD | Not started | - |
