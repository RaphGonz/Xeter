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

**Phases completed:** 10 phases, 29 plans, 8 tasks

**Key accomplishments:**
- (none recorded)

---

