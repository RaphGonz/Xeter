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

