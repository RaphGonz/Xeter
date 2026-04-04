# Retrospective: Xeter

## Milestone: v1.0 — MVP

**Shipped:** 2026-04-04
**Phases:** 6 | **Plans:** 21 | **Timeline:** 12 days (2026-03-23 → 2026-04-04)

### What Was Built

- Phase 1 (Foundation): Docker Compose stack, PostgreSQL schema with RLS, ClickHouse DDL, DAL with tenant guard, tenant registration
- Phase 2 (Ingestion): Python SDK with 12 span fields, Analyser with S3→ClickHouse→Redis locked ingestion pipeline
- Phase 3 (Analysis): BRPOP worker with extensible analyzer registry; ToolCallAnalyzer with 5 embedding dimensions, configurable thresholds, full score logging
- Phase 4 (Read Path): GET /spans with filtering, GET /spans/{id} with lazy S3 fetch, Diagnosticer scaffold (501) proxied from Presenter
- Phase 5 (Dashboard): Next.js 15 app with JWT login, paginated spans table, FilterBar, SpanDetailPanel with payload tabs
- Phase 6 (Validation): Calibration harness with P/R curve and threshold auto-update; cross-tenant isolation tests; E2E smoke test (register → ingest → analyze → retrieve, ~37s)

### What Worked

- **Strict dependency ordering**: building foundation → ingestion → analysis → read → UI prevented rework; nothing was built before its dependencies were locked
- **TDD throughout**: writing failing tests before implementation caught edge cases early (especially in the ingestion and auth layers)
- **Lifespan singleton pattern**: storing all clients (ClickHouse, Redis, S3) on `app.state` made test isolation clean and consistent across services
- **Scaffolding Diagnosticer in v1**: wiring the 501 scaffold in Phase 4 means v1.1 activates LLM without rearchitecting — zero cost now, high value later
- **Score logging regardless of flag outcome**: all similarity scores recorded for every span from day one; calibration in Phase 6 was straightforward because the data was already there
- **Synthetic labelled fixture for calibration**: fixed seed ensured determinism; avoided the sourcing problem of real labelled data

### What Was Inefficient

- **Phase 6 over-engineered initially**: the original plan included load test (500 rps), latency probe, isolation tests, and calibration — replaced with a single E2E smoke test after recognising the full suite was pre-mature for v1
- **ClickHouse CLICKHOUSE_PASSWORD missing from some services**: discovered late in Phase 5 when ClickHouse 25.3 enforced auth for the default user; should be in the base compose template
- **Worker "span not found" race**: the Redis → ClickHouse batcher flush (5s) race was only discovered during E2E validation; retry logic should be in the plan from day one when batching is involved
- **sentence-transformers in all service images**: not isolated to `xeter[ml]` dep until Phase 5; caused unnecessary CUDA/torch bloat in non-ML service images

### Patterns Established

- `app.state` singleton pattern for all long-lived clients (consistent across Analyser, Presenter, View)
- S3-first ingestion ordering: S3 upload → ClickHouse batch add → Redis enqueue (locked sequence, any failure returns 5xx)
- ANALYZERS registry: extensible by append-only — zero modification to existing analyzers
- Two-transaction pattern for tenant bootstrap (RLS requires tenant_id to be set before writing user/key rows)
- Dockerfile model pre-baking: `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer(...)"` in image layer

### Key Lessons

- **Race conditions with async batching**: when Redis queues span_ids and ClickHouse uses a flush interval, the worker will race ahead of the batcher. Always add retry logic when the consumer depends on a batched write being visible.
- **RLS session variable in BYPASSRLS connections**: SET LOCAL is still worth doing even when the user has BYPASSRLS — it's a defensive pattern that costs nothing and prevents future confusion.
- **flag_type as open string from day one**: making this a VARCHAR not an enum in Phase 1 avoided a schema migration when new flag types were added in Phase 3. Enum constraints are premature for extensible categorization.
- **Test isolation via module-level patching**: FastAPI's `dependency_overrides` doesn't cover lifespan startup code. Patching factory functions in the `main.py` module namespace is the correct isolation point.
- **Precision over recall for anomaly detection**: optimising for 80% precision minimises false alarms; a developer who gets false positives stops trusting the tool.

### Cost Observations

- Solo session-based development, no parallelism between phases
- Average plan execution: ~13 min (range 7–17 min)
- Total execution: ~105 min across 8 tracked plans (more were untracked)
- Notable: Phase 6 was restructured mid-execution (overengineered → E2E smoke test) — the pivot saved ~2 days

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Days | LOC | Key Pattern |
|-----------|--------|-------|------|-----|-------------|
| v1.0 MVP | 6 | 21 | 12 | ~12,660 | Bottom-up strict ordering |
