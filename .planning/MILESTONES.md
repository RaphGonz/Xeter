# Milestones

## v1.0 MVP (Shipped: 2026-04-04)

**Phases completed:** 6 phases (Phases 1–6), 21 plans
**Timeline:** 2026-03-23 → 2026-04-04 (12 days)
**Code:** ~12,660 LOC (10,400 Python + 2,255 TypeScript), 219 files

**Key accomplishments:**
- Shipped a working end-to-end AI agent observability platform from empty repo in 12 days
- Python SDK instruments agent code and emits OTel spans with 12 fields to the Analyser
- Analyser ingests spans into ClickHouse (batched) + S3 (large payloads) + Redis (async queue)
- Embedding Worker flags tool-call anomalies across 5 dimensions with configurable thresholds and full score logging
- Presenter API serves filtered span lists, span detail with lazy S3 payload fetch, multi-tenant isolation via RLS
- Next.js 15 dashboard with login, span list, FilterBar, and SpanDetailPanel with flag scores and payload tabs
- E2E smoke test passes: register → ingest → worker analysis → span retrieval (~37s end-to-end)

**Archive:**
- Roadmap: `.planning/milestones/v1.0-ROADMAP.md`
- Requirements: `.planning/milestones/v1.0-REQUIREMENTS.md`

---

## v1.1 Analyser Accuracy (Shipped: 2026-04-18)

**Phases completed:** 4 phases (Phases 7–10), 10 plans
**Timeline:** 2026-04-06 → 2026-04-18 (12 days)
**Code:** ~11,148 LOC Python (down from v1.0 due to analyzer rewrite; TypeScript unchanged)

**Key accomplishments:**
- `_check_wrong_args` rewritten with two-path detection: error-regex priority (no embedding) + hybrid cosine+BOW on flattened arg values; `low_confidence` flag removed
- Shared `bow_score` + `hybrid_score` utility functions added to `base.py` (HYBRID-01) — foundation for all v1.1 similarity rewrites
- `calibrate.py` extended with `--flag-type` isolation CLI arg and `BINARY_FLAG_TYPES` set for non-threshold detectors
- `_check_wrong_tool` rewritten with three-branch logic (tool called + tools available, tool called + no tools available, no tool called); threshold renamed `wrong_tool_called`
- `_check_no_tool` simplified to `no_tool_used`: rank-based detector, P=1.000, R=0.333 at threshold=0.15
- `_check_excessive_tool` replaced by `unnecessary_tool_call`: social centroid signal flags tool calls on conversational prompts; P=1.000, R=0.667 at threshold=0.25
- Full calibration suite: all 4 methods calibrated with P/R benchmarks; full-suite mean precision ≥ 95%

**Known scope changes (accepted pivots):**
- `tool_use_violation` (windowed proximity detection) deferred — `no_tool_used` covers the priority case cleanly
- `excessive_tool` necessity-delta approach replaced by social centroid — simpler, calibrated better

**Archive:**
- Roadmap: `.planning/milestones/v1.1-ROADMAP.md`
- Requirements: `.planning/milestones/v1.1-REQUIREMENTS.md`

---


## v1.2 Diagnosticer (Shipped: 2026-04-25)

**Phases completed:** 3 phases (Phases 11–13), 8 plans
**Timeline:** 2026-04-22 → 2026-04-25 (4 days)
**Code:** ~13,398 LOC Python + 2,619 TypeScript; 112 tests passing

**Key accomplishments:**
- PostgreSQL `diagnoses` table (migration 003) with 12-column schema, RLS tenant isolation, and Diagnosis ORM model — foundation for all Diagnosticer plans
- Async LLM provider factory supporting Anthropic (forced tool_choice), OpenAI (strict function calling), and Ollama (format= schema) — typed `DiagnosisResult` returned, no free-text parsing
- `assemble_context()` pulls ClickHouse span + PostgreSQL flags + S3 payloads in parallel (5s timeout) into a single LLM-ready prompt string
- Real POST /diagnose endpoint replacing 501 scaffold: fail-clean pipeline (assemble → diagnose → persist), error mapping (ValueError→404, LLMError→502, ParseError→422), 6-test suite
- `DiagnosisService` in Presenter with ClickHouse tenant guard, HTTP error classification (503/504/502), and re-read-from-DB pattern; GET /diagnose/{span_id} polling endpoint added
- SpanDetailPanel `DiagnosisCard` with auto-load GET on mount, colored verdict/severity badges, affected field + recommended fix display, always-enabled Diagnose button

**Archive:**
- Roadmap: `.planning/milestones/v1.2-ROADMAP.md`

---


## v1.3 Security Hardening (Shipped: 2026-05-02)

**Phases completed:** 4 phases (Phases 14–17), 12 plans
**Timeline:** 2026-04-27 → 2026-04-30 (3 days)
**Code:** ~14,500 LOC Python + 3,000 TypeScript; 78 files changed (+11,019 / -1,239 lines)

**Key accomplishments:**
- PostgreSQL tenant isolation completed: span_scores RLS policy added; FORCE RLS enforced on all 7 tables; score_writer.py uses SET LOCAL in explicit transaction (mirrors flag_writer.py pattern)
- DB-level domain validation: CHECK constraints on `diagnoses.verdict` and `diagnoses.severity` added via NOT VALID + pre-flight audit script (zero-downtime migration); provider Literals aligned before migration
- S3 tenant-prefix assertion: Presenter rejects cross-tenant key fetch with HTTP 403 before calling GetObject — defence-in-depth independent of ClickHouse tenant filter
- Secrets hardening: root .gitignore, one-command generate-secrets.sh with shared-password reuse pattern, no `:-` fallbacks for secrets in docker-compose, Redis requirepass enforced, MinIO bucket asserted private on every startup
- Full auth hardening: JWT 30-min expiry, SECRET_KEY hard-fail on startup (both services), INTERNAL_API_KEY service trust boundary via middleware, httpOnly refresh token with silent 401 interceptor in Next.js, JWT_SECRET rotation runbook
- GDPR Art. 17: delete_tenant.py dry-run + --confirm covering ClickHouse async mutation, FK-ordered PostgreSQL DELETEs, S3 paginated batch delete, and documented Redis flush procedure

**Tech debt (no blockers):**
- Dead `verify_session_token()` in `diagnosticer/main.py` (lines 78–94) — never wired to any `Depends()`, should be removed before v1.4
- Stale "NO PostgreSQL RLS" comment in `spans.py` lines 9/442 — stale after migration 004 added RLS
- `delete_tenant.py --confirm` completion message omits Redis store from output (runbook covers it)
- Phase 13 (v1.2) missing VERIFICATION.md — should be addressed when archiving v1.2 phases

**Archive:**
- Roadmap: `.planning/milestones/v1.3-ROADMAP.md`
- Requirements: `.planning/milestones/v1.3-REQUIREMENTS.md`
- Audit: `.planning/milestones/v1.3-MILESTONE-AUDIT.md`

---


## v1.4 Trace Hierarchy + TraceAnalyzer Foundation (Shipped: 2026-05-15)

**Phases completed:** 4 phases (Phases 18–21), 11 plans
**Timeline:** 2026-05-14 → 2026-05-15 (2 days)
**Code:** 57 files changed (+6,772 / -129 lines)

**Key accomplishments:**
- Eliminated v1.3 tech debt: dead `verify_session_token()` removed from Diagnosticer, stale "NO RLS" comments corrected, all `os.environ.get()` defaults annotated `[safe-default]`/`[must-set-in-prod]` across 9 service files
- Refactored monolithic `BaseAnalyzer` into 3-class hierarchy: generic root + `BaseSpanAnalyzer` + `BaseTraceAnalyzer`; `ToolCallAnalyzer` re-parented — extensible contract for future trace-level checks
- `TraceAnalyzer(BaseTraceAnalyzer)` scaffold wired into worker with flush-timeout trigger (WORKER_TRACE_FLUSH_TIMEOUT_S, default 30s); `flags.span_id` made nullable via migration 005 to support trace-level flags
- `GET /traces` and `GET /traces/{trace_id}` FastAPI endpoints with two-phase 404 logic (CH then PG), no-spans-yet 200 case, and belt-and-suspenders tenant isolation; 14-test suite passing
- Traces list page (TraceTable + auth-guarded layout) and collapsible SpanTree trace detail view shipped in Next.js dashboard; breadcrumb with `?span=` URL deep-link auto-opens SpanDetailPanel on back-navigation; human browser tests verified

**Tech debt (no blockers):**
- `useSearchParams()` in `traces/[trace_id]/page.tsx` runs without explicit Suspense boundary — acceptable because `use(params)` makes page dynamically rendered; human verification confirmed correct in production build

**Archive:**
- Roadmap: `.planning/milestones/v1.4-ROADMAP.md`
- Requirements: `.planning/milestones/v1.4-REQUIREMENTS.md`
- Audit: `.planning/milestones/v1.4-MILESTONE-AUDIT.md`

---


## v1.5 Silent Failure Detection (Shipped: 2026-05-30)

**Phases completed:** 7 phases (Phases 22–28), 23 plans
**Timeline:** 2026-05-18 → 2026-05-30 (12 days)
**Code:** 235+ tests passing; ~15,000+ LOC Python; 24 flag types active

**Key accomplishments:**
- Worker idle-flush gap closed (Phase 22) — BRPOP timeout triggers trace analysis; trace score persistence confirmed
- calibrate.py multi-analyzer routing and recall floor (R ≥ 0.10) enforcement — foundation for all new check types (Phase 23)
- OutputSchemaAnalyzer: 5 deterministic span checks (output_schema_violation, required_fields_missing, output_truncated, type_coercion_error, context_overflow) — all P=1.0 R=1.0, zero embedding calls (Phase 24)
- SemanticSpanAnalyzer + TraceAnalyzer: 6 embedding/heuristic checks (stale_context, missing_details, step_repetition, termination_loop, context_propagation_failure, history_loss) (Phase 25)
- 6 best-effort proxy trace checks (wrong_agent_handoff, information_withholding, conversation_reset, clarification_skipped, no_verification, incomplete_verification) — no_verification + incomplete_verification mutually exclusive (Phase 26)
- Full calibration: all 24 flag types calibrated; 11 BINARY_FLAG_TYPES; mean precision 0.947; deploy/docker-compose.yml patched with all WORKER_THRESHOLD_* values (Phases 27–28)
- Precision improvements: 14 flag types fixed across 4 plans; key rewrites: information_withholding → binary, step_repetition → binary exact-match, wrong_tool_args → tool-relevance guard (Phase 28)

**Known scope changes (accepted):**
- CTX-03 (prompt_injection) permanently removed — insufficient OTel signal without LLM-in-the-loop
- history_loss P=0.5 accepted — architectural cross-contamination with conversation_reset; deferred to v1.6+

**Archive:**
- Roadmap: `.planning/milestones/v1.5-ROADMAP.md`
- Requirements: `.planning/milestones/v1.5-REQUIREMENTS.md`

---


## v1.6 Release (Shipped: 2026-05-31)

**Phases completed:** 3 phases (Phases 29–31), 7 plans
**Timeline:** 2026-05-30 → 2026-05-31 (2 days)
**Code:** 123 files changed, +4,620 / -240 lines

**Key accomplishments:**
- GPL-3.0 + Commons Clause `LICENSE` file (35 KB) created at repo root — prohibits selling Xeter-as-a-service; SPDX headers added to all 90 substantive Python source files
- `assets/` directory created; `logo+typo.png` moved from root; dead dev artifacts (`check_tier4.py`, `VALIDATION-REPORT.md`) deleted
- Diagnosticer prompt extracted from inline f-string in `context_assembly.py` into `prompt.md`, read at import via `Path(__file__).parent`, substituted via `format_map` — 5 tests pass (DIAG-01)
- `prompt.md` rewritten with structured system message, four-verdict decision criteria (model/architecture/prompt/unknown), severity calibration (high/medium/low), and chain-of-thought scaffold — 9 diagnosticer tests pass (DIAG-02)
- `db-init` one-shot init container added to `docker-compose.yml` — runs `alembic upgrade head` + seed before app services start
- `README.md` fully rewritten as public-facing v1.6 developer document — all 11 sections: banner, Quick Start, SDK, 24-flag detection table, calibration workflow, pluggable LLM config, performance levers, architecture, multi-tenancy, license

**Archive:**
- Roadmap: `.planning/milestones/v1.6-ROADMAP.md`
- Requirements: `.planning/milestones/v1.6-REQUIREMENTS.md`

---

