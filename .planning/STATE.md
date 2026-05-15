---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Trace Hierarchy + TraceAnalyzer Foundation
status: unknown
last_updated: "2026-05-15T09:52:51.296Z"
progress:
  total_phases: 10
  completed_phases: 10
  total_plans: 27
  completed_plans: 27
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12)

**Core value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.
**Current focus:** Phase 21 — Trace UI

## Current Position

Phase: 21 of 21 (Trace UI)
Plan: 21-03 complete (3 of N plans in phase 21)
Status: In progress — phase 21 plan 03 complete
Last activity: 2026-05-15 — 21-03 breadcrumb in SpanDetailPanel: Traces › {trace_id[:8]} › {span_id[:8]} with clickable trace_id link to /traces/{trace_id}

Progress: [███░░░░░░░] ~30%

## Accumulated Context

All decisions logged in PROJECT.md Key Decisions table.

### Key Decisions (v1.4)

- Option B hierarchy: BaseAnalyzer (generic root) → BaseSpanAnalyzer + BaseTraceAnalyzer; ToolCallAnalyzer moves to BaseSpanAnalyzer
- TraceAnalyzer scaffold in v1.4 (no checks yet); actual checks land in v1.5
- Worker flush timeout triggers TraceAnalyzer — configurable window (WORKER_TRACE_FLUSH_TIMEOUT_S, default 30s), not per-span
- flags table extended: span_id nullable, trace_id non-nullable — supports both span-level and trace-level flags
- v1.5 will cover 20 new checks across B/C/D/E/F/G/H categories (see documentation/silent_failures_ai_agents.md)
- BaseAnalyzer root keeps name abstract property but no analyze() — each subclass defines its own analyze() signature (18-02)
- BaseTraceAnalyzer added as stub in 18-02; Phase 19 provides concrete TraceAnalyzer implementation
- TraceAnalyzer scaffold (19-01): analyze() returns [] unconditionally; name="trace_analyzer"; v1.5 adds B/C/D/E/F/G/H checks

### Key Decisions (v1.4 continued — 19-03)

- process_span() returns SpanData (Option A): minimal extension; existing callers ignore return value
- Flush loop evicts trace from buffer unconditionally (finally block) — prevents unbounded buffer growth on TraceAnalyzer error
- WORKER_TRACE_FLUSH_TIMEOUT_S default 30s; configurable per deployment

### Key Decisions (v1.4 continued — 19-02)

- Migration 005: span_id DROP NOT NULL (trace-level flags have no single span); trace_id backfill is a no-op (already NOT NULL since migration 001)
- Flag.span_id: Mapped[str | None] with nullable=True in ORM model; write_flags() span_id param: str | None
- psycopg2 None -> SQL NULL automatically; _INSERT_SQL string unchanged

### Key Decisions (v1.4 continued — 20-01)

- GET /traces and GET /traces/{trace_id} implemented with two-phase 404 (CH then PG): no-spans-yet returns 200 with spans=[]
- Cross-tenant stealth 404 via WHERE tenant_id on both CH and PG — requesting tenant's filter makes other tenant data invisible
- Trace-level flags (span_id IS NULL) on trace.flags; span-level flags inline on SpanInTrace
- PG queries sequential on shared AsyncSession (concurrent execute causes IllegalStateChangeError)
- TRACE-01 and TRACE-02 satisfied

### Key Decisions (v1.4 continued — 20-02)

- CH side_effect list simulates asyncio.gather two-query pattern in tests (list + count calls in order)
- Missing-auth tests retain get_session and get_ch_client overrides while removing verify_session_token — FastAPI resolves all deps concurrently before raising 401
- No-spans-yet test exercises both PG calls (existence probe + trace-level flags fetch) via side_effect; asserts 200 and spans==[]

### Key Decisions (v1.4 continued — 21-03)

- SpanDetailPanel breadcrumb always shown (trace_id non-nullable on SpanDetail — no conditional); old "trace: {full trace_id}" paragraph removed
- Breadcrumb Link uses onClick stopPropagation to prevent Sheet drawer from intercepting click

### Key Decisions (v1.4 continued — 21-01)

- trace_id displayed as 8-char truncation with full ID in title tooltip (vs 20-char for span_id in SpanTable)
- NavBar now has explicit Spans link alongside new Traces link; brand "Xeter" still points to /spans
- flag_count=0 renders em-dash instead of "0 flags" badge for visual clarity
- TracesLayout mirrors SpansLayout exactly — hydration gate + useEffect redirect pattern

### Key Decisions (v1.4 continued — 18-01)

- verify_session_token deleted from diagnosticer/main.py — InternalApiKeyMiddleware is the sole auth boundary; JWT auth was dead code
- Env var safety annotation pattern established: [safe-default] and [must-set-in-prod] inline tags on all os.environ.get() calls across 9 service files
- span_scores belt-and-suspenders (RLS + explicit WHERE) confirmed intentional; stale "NO RLS" comments corrected

### Pending Todos

None — audit env var defaults (2026-04-24) resolved by CLEAN-03 in 18-01

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-05-15 — 21-03 complete. Breadcrumb added to SpanDetailPanel: Traces › {trace_id[:8]} › {span_id[:8]}, clickable trace_id navigates to /traces/{full trace_id}; zero TS errors.
Stopped at: 21-03-PLAN.md complete
Next: Phase 21 remaining plans
