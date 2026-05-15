---
phase: 20-trace-api
verified: 2026-05-15T10:00:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
---

# Phase 20: trace-api Verification Report

**Phase Goal:** Add GET /traces and GET /traces/{trace_id} endpoints to the Presenter with tenant RLS, assembling trace data from ClickHouse (spans) and PostgreSQL (flags, scores)
**Verified:** 2026-05-15T10:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /traces returns {traces: [...], total, limit, offset} with trace_id, span_count, flag_count, start_time, duration per item | VERIFIED | traces.py lines 135–218; TraceListResponse + TraceListItem models; ClickHouse aggregation + PG flag count merge |
| 2 | GET /traces/{trace_id} returns {trace: {trace_id, start_time, duration, flags}, spans: [...]} with flat spans sorted by time_begin ASC | VERIFIED | traces.py lines 226–399; ORDER BY time_begin ASC in CH query; SpanInTrace assembled per span |
| 3 | Cross-tenant GET /traces/{trace_id} returns 404 (stealth, no 403) | VERIFIED | Two-phase existence check: WHERE tenant_id filters applied to both CH and PG; both return empty for other tenant's trace_id; raises 404 with error=not_found |
| 4 | Tenant A cannot retrieve traces belonging to Tenant B via either endpoint | VERIFIED | All CH queries: WHERE tenant_id = %(tenant_id)s; all PG queries: Flag.tenant_id == tenant_id; verified by test_list_traces_tenant_isolation and test_get_trace_detail_cross_tenant_404 |
| 5 | GET /traces with no traces returns 200 {traces: [], total: 0, limit: 50, offset: 0} | VERIFIED | traces.py line 183: early return when CH rows empty; test_list_traces_empty passes |
| 6 | GET /traces/{trace_id} with trace_id that has no spans yet returns 200 {trace: {...}, spans: []} | VERIFIED | Two-phase check: zero CH rows triggers PG existence probe; if flag exists returns 200 with spans=[]; test_get_trace_detail_no_spans_yet passes |
| 7 | GET /traces returns 401 when Authorization header missing | VERIFIED | verify_session_token dependency raises 401; test_list_traces_missing_auth passes |
| 8 | GET /traces/{trace_id} returns 401 when Authorization header missing | VERIFIED | test_get_trace_detail_missing_auth passes |
| 9 | Trace-level flags (span_id=None) appear on trace.flags, not on any span | VERIFIED | traces.py lines 339–348: flag.span_id is None check routes to trace_flags_list; test_get_trace_detail_trace_level_flags passes |
| 10 | Span-level flags appear inline on the correct span object | VERIFIED | traces.py lines 339–348: flags_by_span dict; test_get_trace_detail_span_level_flags passes |
| 11 | GET /traces accepts limit (1-100, default 50) and offset (default 0) | VERIFIED | traces.py line 141: Query(default=50, ge=1, le=100) and Query(default=0, ge=0); test_list_traces_pagination_params verifies params forwarded to CH |
| 12 | scores appear inline on correct span | VERIFIED | traces.py lines 350–355; test_get_trace_detail_scores_inline passes |
| 13 | GET /traces/{trace_id} returns 404 when both CH and PG have no record for (tenant_id, trace_id) | VERIFIED | traces.py lines 272–279; test_get_trace_detail_not_found passes |
| 14 | traces router registered on FastAPI app | VERIFIED | main.py line 55: app.include_router(traces.router, prefix="", tags=["traces"]); import on line 21 |
| 15 | All 14 unit tests pass, no regressions in presenter suite | VERIFIED | pytest: 14/14 new tests pass; 51/51 total presenter tests pass |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `xeter/services/presenter/routers/traces.py` | GET /traces and GET /traces/{trace_id} FastAPI router with response models | VERIFIED | 400 lines; exports router, TraceListResponse, TraceDetailResponse, TraceObject, SpanInTrace, TraceFlagItem, ScoreItem, TraceListItem; both handlers fully implemented |
| `xeter/services/presenter/main.py` | traces router registered on the FastAPI app | VERIFIED | Line 21: imports traces; line 55: app.include_router(traces.router, ...) |
| `xeter/tests/presenter/test_traces.py` | Unit tests for both endpoints | VERIFIED | 581 lines; 14 tests collected and passing; covers all specified scenarios |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `routers/traces.py` | ClickHouse spans table | asyncio.to_thread(ch_client.query, ...) | VERIFIED | list_traces: ch_client.query called with WHERE tenant_id = %(tenant_id)s on spans table; get_trace_detail: same pattern with trace_id filter |
| `routers/traces.py` | xeter/shared/models.Flag | session.execute(select(Flag).where(...)) | VERIFIED | list_traces: text() query on flags table with tenant_id; get_trace_detail: select(Flag).where(Flag.tenant_id == tenant_id, ...) — lines 264, 283, 316 |
| `main.py` | `routers/traces.py` | app.include_router(traces.router) | VERIFIED | main.py line 21 imports traces; line 55: app.include_router(traces.router, prefix="", tags=["traces"]) |
| `test_traces.py` | traces.router | dependency_overrides[verify_session_token] + TestClient | VERIFIED | Line 136: app.dependency_overrides[get_ch_client]; line 137: verify_session_token; line 138: get_session; TestClient used in every test |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TRACE-01 | 20-01, 20-02 | Operator can list all traces for their tenant via GET /traces — response includes trace_id, span count, flag count, time_begin, time_end per trace; results ordered by time_begin descending; scoped to authenticated tenant via RLS | SATISFIED | TraceListResponse with all required fields; ORDER BY start_time DESC in CH query; tenant_id filter on all queries; 6 list-endpoint tests cover the contract |
| TRACE-02 | 20-01, 20-02 | Operator can fetch a full trace via GET /traces/{trace_id} — response includes all spans in the trace with their flags and scores, assembled from ClickHouse (spans) + PostgreSQL (flags, scores); returns 404 if trace_id not found or belongs to another tenant | SATISFIED | TraceDetailResponse with TraceObject + list[SpanInTrace]; flags from PG joined per span; scores from span_scores joined per span; two-phase 404 for not-found and cross-tenant stealth; 8 detail-endpoint tests cover the contract |

No orphaned requirements — TRACE-01 and TRACE-02 are the only requirement IDs mapped to Phase 20 in REQUIREMENTS.md, and both are claimed by plans 20-01 and 20-02.

---

### Anti-Patterns Found

No anti-patterns detected. Scan of `traces.py`, `main.py`, `test_traces.py`:

- No TODO/FIXME/HACK/PLACEHOLDER comments
- No `return null` / `return {}` / empty stub handlers
- No console.log-only implementations (Python; no structlog calls replacing real logic)
- No static return values bypassing database queries
- All handlers perform real ClickHouse and PostgreSQL query sequences before returning responses

---

### Human Verification Required

None required. All goal-critical behaviors were verified programmatically:

- Route registration: confirmed via FastAPI app.routes inspection (pytest)
- Tenant isolation: confirmed via CH query param assertions in test_list_traces_tenant_isolation
- Two-phase 404 logic: confirmed via mock side_effect sequencing in test_get_trace_detail_not_found and test_get_trace_detail_no_spans_yet
- Flag separation (trace-level vs span-level): confirmed via test_get_trace_detail_trace_level_flags and test_get_trace_detail_span_level_flags
- All 14 tests executed and pass in CI-equivalent environment

The only items that would benefit from human review in a full integration environment are end-to-end behavior against real ClickHouse and PostgreSQL instances — those are out of scope for this phase's unit-test contract.

---

### Gaps Summary

No gaps. All must-haves are verified.

---

_Verified: 2026-05-15T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
