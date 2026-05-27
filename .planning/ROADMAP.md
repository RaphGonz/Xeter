# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- ✅ **v1.2 Diagnosticer** — Phases 11–13 (shipped 2026-04-25)
- ✅ **v1.3 Security Hardening** — Phases 14–17 (shipped 2026-05-02)
- ✅ **v1.4 Trace Hierarchy + TraceAnalyzer Foundation** — Phases 18–21 (shipped 2026-05-15)
- 🔄 **v1.5 Silent Failure Detection** — Phases 22–27 (in progress)

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

<details>
<summary>✅ v1.4 Trace Hierarchy + TraceAnalyzer Foundation (Phases 18–21) — SHIPPED 2026-05-15</summary>

- [x] Phase 18: Cleanup + BaseAnalyzer Refactor (2/2 plans) — completed 2026-05-14
- [x] Phase 19: TraceAnalyzer Scaffold + DB Migration (3/3 plans) — completed 2026-05-14
- [x] Phase 20: Trace API (2/2 plans) — completed 2026-05-15
- [x] Phase 21: Trace UI (4/4 plans) — completed 2026-05-15

See `.planning/milestones/v1.4-ROADMAP.md` for full phase details.

</details>

### v1.5 Silent Failure Detection (Phases 22–27)

- [x] **Phase 22: Bug Fixes** — Fix idle-flush and trace score persistence (gates all trace-level checks)
- [x] **Phase 23: Infrastructure** — calibrate.py multi-analyzer, new deps, SpanData schema fields (completed 2026-05-20)
- [x] **Phase 24: Structural Span Checks** — OutputSchemaAnalyzer with heuristic/deterministic checks; zero embedding calls (completed 2026-05-21)
- [x] **Phase 25: Semantic Span + Structural Trace Checks** — Embedding-based span checks and first wave of trace checks (completed 2026-05-24)
- [x] **Phase 26: Best-Effort Proxy Checks** — Remaining trace checks; best-effort heuristics; precision floors verified (completed 2026-05-26)
- [ ] **Phase 27: Calibration Pass** — All 18 new flag types calibrated; recall floor and full-suite precision verified

## Phase Details

### Phase 22: Bug Fixes

**Goal**: Worker reliably flushes and scores idle traces, so trace-level checks can fire in test and production conditions
**Depends on**: Nothing (first v1.5 phase; gates all trace analysis)
**Requirements**: INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):

  1. A test that sends exactly N spans and stops receives trace-level flags from the worker (idle trace flushed via BRPOP timeout, not just on next span arrival)
  2. After each trace flush, `span_scores` contains rows for trace-level metrics (flush_scores called; calibration dataset can include trace-level data)
  3. The worker does not silently drop traces that are the last item in the queue with no subsequent span

**Plans**: 2 plans
Plans:

- [x] 22-01-PLAN.md — DB migration 006 (span_scores nullable span_id) + write_scores type update
- [x] 22-02-PLAN.md — Extract _flush_stale_traces, wire both call sites, add 4 tests

### Phase 23: Infrastructure

**Goal**: Worker has the dependencies, schema fields, and calibration tooling required to implement every v1.5 check
**Depends on**: Phase 22
**Requirements**: INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):

  1. `calibrate.py --flag-type <new_type>` routes to the correct analyzer class and produces a threshold for that class's method (multi-analyzer support active)
  2. Hill-climb in calibrate.py rejects degenerate P=1.0, R=0.0 convergence — a R < 0.10 result causes the run to fail with an explicit recall-floor error
  3. Worker environment imports `jsonschema`, `tiktoken`, and `rapidfuzz` without error
  4. `SpanData.expected_output_schema` field is populated from ClickHouse when a span carries it; absent on spans that don't
  5. `SpanData.parent_span_id` field is populated from ClickHouse when a span carries it; absent on spans that don't

**Plans**: 3 plans
Plans:

- [x] 23-01-PLAN.md — New deps (pyproject.toml + Dockerfile) + SpanData fields + span_fetcher + calibrate.py build_span_data
- [x] 23-02-PLAN.md — expected_output_schema ingest pipeline (SpanPayload, SPAN_COLUMNS, ingest row, DDL, ALTER, SDK)
- [x] 23-03-PLAN.md — calibrate.py FLAG_TYPE_TO_ANALYZER_CLASS registry + recall floor check

### Phase 24: Structural Span Checks

**Goal**: System detects output schema violations, truncated outputs, type errors, and token overflow at the span level using only deterministic/heuristic signals — no embedding calls
**Depends on**: Phase 23
**Requirements**: SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, CTX-01
**Success Criteria** (what must be TRUE):

  1. A span with `expected_output_schema` set and a free-text `response` (no JSON / no tool_use block) receives an `output_schema_violation` flag
  2. A span whose `tool_arguments` passes JSON parse but fails the `required` validator in `expected_output_schema` receives a `required_fields_missing` flag
  3. A span with `finish_reason=length` or an unclosed JSON delimiter in its response receives an `output_truncated` flag
  4. A span whose `tool_arguments` contains a type violation (e.g., number-as-string) against `expected_output_schema` receives a `type_coercion_error` flag
  5. A span whose prompt token count (tiktoken cl100k_base) exceeds the configured threshold receives a `context_overflow` flag
**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 24-01-PLAN.md — Failing test scaffold for OutputSchemaAnalyzer (RED) — 31 tests covering 5 checks

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 24-02-PLAN.md — Implement OutputSchemaAnalyzer with 5 deterministic checks (GREEN)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 24-03-PLAN.md — Wire OutputSchemaAnalyzer into worker main.py + calibrate.py registries; update routing tests

### Phase 25: Semantic Span + Structural Trace Checks

**Goal**: System detects stale context and missing detail at the span level via embeddings, and detects step repetition, termination loops, context propagation failure, and history loss at the trace level via rapidfuzz/spaCy/embeddings
**Depends on**: Phase 24
**Requirements**: CTX-02, CTX-04, TRACE-01, TRACE-02, TRACE-03, TRACE-04
**Success Criteria** (what must be TRUE):

  1. A span whose prompt closely matches a prior span's `tool_output` in the same trace receives a `stale_context` flag marked `low_confidence: true`; a span with fresh tool output does not
  2. A span whose `response` semantically fails to cover entities explicitly requested in the `prompt` receives a `missing_details` flag
  3. A trace containing two spans with near-duplicate `(tool_name, tool_arguments)` pairs receives a `step_repetition` flag on the trace
  4. A trace where the same tool is called N+ times in sequence without a distinct exit receives a `termination_loop` flag on the trace
  5. A trace where a later span's prompt is missing key information from an earlier span's `tool_output` receives a `context_propagation_failure` flag on the trace
  6. A trace where a later span's prompt is semantically disconnected from the centroid of earlier prompts receives a `history_loss` flag on the trace

**Plans**: 5 plans
Plans:
**Wave 1** *(parallel — no dependencies)*

- [x] 25-01-PLAN.md — RED test scaffold for SemanticSpanAnalyzer._check_missing_details (10 tests)
- [x] 25-02-PLAN.md — RED test scaffold for TraceAnalyzer 5 checks (22 tests)

**Wave 2** *(blocked on 25-01)*

- [x] 25-03-PLAN.md — GREEN: implement SemanticSpanAnalyzer with _check_missing_details (CTX-04)

**Wave 3** *(blocked on 25-02 + 25-03)*

- [x] 25-04-PLAN.md — GREEN: implement TraceAnalyzer with 5 _check_*() methods (CTX-02, TRACE-01–04)

**Wave 4** *(blocked on 25-03 + 25-04)*

- [x] 25-05-PLAN.md — Wire SemanticSpanAnalyzer + TraceAnalyzer into main.py + calibrate.py; fix TraceAnalyzer evaluation path; 6 new routing tests

### Phase 26: Best-Effort Proxy Checks

**Goal**: System surfaces best-effort heuristic flags for agent handoff failures and verification absence at the trace level, with precision floors verified before each check ships
**Depends on**: Phase 25
**Requirements**: TRACE-05, TRACE-06, TRACE-07, TRACE-08, TRACE-09, TRACE-10
**Success Criteria** (what must be TRUE):

  1. A trace with an unexpected agent-name transition (given a configured `AGENT_ROUTING_GRAPH`) receives a `wrong_agent_handoff` flag marked `low_confidence: true`; a trace with no configured graph produces no flag
  2. A trace where an agent's `response` contains named entities not present in the next span's `prompt` receives an `information_withholding` flag
  3. A trace with an abrupt embedding-cosine drop below the reset threshold mid-trace receives a `conversation_reset` flag marked `low_confidence: true`
  4. A trace where a span proceeds on a disjunctive prompt (contains "or"/"either"/"which") with no question mark in its `response` receives a `clarification_skipped` flag marked `low_confidence: true`
  5. A completed trace with no verification-keyword tool call receives a `no_verification` flag
  6. A trace that has a verification span (no_verification not fired) but covers fewer output entities than were produced receives an `incomplete_verification` flag; `no_verification` and `incomplete_verification` never both fire on the same trace

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 26-01-PLAN.md — RED test scaffold for all 6 Phase 26 _check_*() methods (30+ failing tests)

**Wave 2** *(blocked on 26-01)*

- [x] 26-02-PLAN.md — GREEN: implement all 6 _check_*() methods in TraceAnalyzer + __init__ update + _VERIFICATION_KEYWORDS + analyze() mutual-exclusion

**Wave 3** *(blocked on 26-02)*

- [x] 26-03-PLAN.md — Wire: main.py THRESHOLDS + AGENT_ROUTING_GRAPH parsing + TraceAnalyzer routing_graph kwarg + calibrate.py registrations + 6 routing tests

### Phase 27: Calibration Pass

**Goal**: All 18 new flag types have calibrated thresholds, recall floors are enforced, and full-suite mean precision meets the 95% target
**Depends on**: Phase 26
**Requirements**: CAL-01
**Success Criteria** (what must be TRUE):

  1. Every new flag type has a key in `THRESHOLDS` (or is registered in `BINARY_FLAG_TYPES`) and `calibrate.py --flag-type <type>` completes without error for each
  2. No new flag type calibrates to R < 0.10 (recall floor enforced by hill-climb; any violation is a build error)
  3. Full-suite mean precision across all flag types (old + new) is ≥ 95% as reported by calibrate.py
  4. The calibration report identifies which of the 18 new checks are binary (no threshold sweep) versus threshold-tuned

**Plans**: 3 plans

**Wave 1**

- [x] 27-01-PLAN.md — Extend fixture generator for 17 new types + grouped trace evaluation in calibrate.py

**Wave 2** *(blocked on 27-01 completion)*

- [ ] 27-02-PLAN.md — Run per-type calibration, classify Phase 26 binary types, write calibrated_thresholds.json

**Wave 3** *(blocked on 27-02 completion)*

- [ ] 27-03-PLAN.md — Full-suite run, mean precision verification, docker-compose patch, final commit

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
| 18. Cleanup + BaseAnalyzer Refactor | v1.4 | 2/2 | Complete | 2026-05-14 |
| 19. TraceAnalyzer Scaffold + DB Migration | v1.4 | 3/3 | Complete | 2026-05-14 |
| 20. Trace API | v1.4 | 2/2 | Complete | 2026-05-15 |
| 21. Trace UI | v1.4 | 4/4 | Complete | 2026-05-15 |
| 22. Bug Fixes | v1.5 | 2/2 | Complete | 2026-05-19 |
| 23. Infrastructure | v1.5 | 3/3 | Complete   | 2026-05-20 |
| 24. Structural Span Checks | v1.5 | 3/3 | Complete | 2026-05-21 |
| 25. Semantic Span + Structural Trace Checks | v1.5 | 5/5 | Complete | 2026-05-24 |
| 26. Best-Effort Proxy Checks | v1.5 | 3/3 | Complete   | 2026-05-26 |
| 27. Calibration Pass | v1.5 | 1/3 | In progress | - |
