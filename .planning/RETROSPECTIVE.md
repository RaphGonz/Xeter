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

## Milestone: v1.1 — Analyser Accuracy

**Shipped:** 2026-04-18
**Phases:** 4 (Phases 7–10) | **Plans:** 10 | **Timeline:** 12 days (2026-04-06 → 2026-04-18)

### What Was Built

- Phase 7 (wrong_args): Error-regex priority path + hybrid cosine+BOW on flattened arg values; shared `bow_score`/`hybrid_score` utility; `calibrate.py` per-method isolation
- Phase 8 (wrong_tool): Three-branch `_check_wrong_tool` (called+available, called+no-available, not-called); threshold renamed `wrong_tool_called`; calibrated P=1.0, R=0.5
- Phase 9 (no_tool_used): Simplified rank-based `no_tool_used` (max hybrid score vs available tools); P=1.0, R=0.333 at threshold=0.15
- Phase 10 (unnecessary_tool_call): Social centroid signal flags conversational/phatic prompts where tool call was unnecessary; P=1.0, R=0.667 at threshold=0.25; full-suite mean precision ≥ 95%

### What Worked

- **Error-regex priority path in wrong_args**: firing score=1.0 on obvious API errors without any embedding was the right call — simpler, faster, higher precision
- **Hybrid scoring as shared utility**: `bow_score` + `hybrid_score` in `base.py` gave all four rewritten methods a consistent foundation without duplication
- **Per-method calibration isolation (`--flag-type`)**: being able to calibrate a single flag type in isolation (rather than running the full suite) dramatically shortened the feedback loop
- **Pivoting away from windowed proximity for tool_use_violation**: recognising that SBERT can't encode negation polarity early prevented building a fragile detector
- **Social centroid for unnecessary_tool_call**: simpler conceptually than necessity delta, and calibrated cleanly to P=1.0

### What Was Inefficient

- **Requirements written before pivots were clear**: NOTOOL/EXTOOL requirements were detailed and specific before the approach was validated; the implementation pivoted significantly and the requirements never tracked it
- **Phase 9 and 10 executed without formal plans**: both were handled in a single unplanned summary each; this worked but makes it harder to trace decisions to specific tasks
- **calibrate.py `--verbose` flag was broken mid-milestone**: diagnosing FPs required workarounds; should be fixed before next calibration-heavy milestone

### Patterns Established

- `BINARY_FLAG_TYPES` set in `calibrate.py`: separates threshold-based from rank-based detectors; add future binary detectors here without code changes
- Social centroid fixture (`social_centroid.npy`): precomputed centroid of phatic/conversational prompts; a reusable pattern for prompt-class classification
- Three-branch explicit logic for detector methods: prefer explicit branch per case over combined conditions — tests map 1:1 to branches

### Key Lessons

- Validate the signal before writing detailed requirements — spike the approach first, then spec
- Plans are valuable even for short single-plan phases: they force pre-thinking the approach before execution
- Calibration-first ordering (implement → calibrate → next phase) works well; don't try to calibrate multiple methods at once

### Cost Observations

- Sessions: ~8 across 12 days
- Notable: Phases 9 and 10 were collapsed into single-session executions without formal plans — saved overhead but reduced traceability

---

## Milestone: v1.2 — Diagnosticer

**Shipped:** 2026-04-25
**Phases:** 3 (Phases 11–13) | **Plans:** 8 | **Timeline:** 4 days (2026-04-22 → 2026-04-25)

### What Was Built

- Phase 11 (Diagnosticer Backend): `diagnoses` table (migration 003, RLS, 12 columns), Diagnosis ORM, LLM provider factory (Anthropic/OpenAI/Ollama with lazy imports and structured output), `DiagnosisRepository` DAL, `assemble_context()` with parallel ClickHouse + PostgreSQL + S3 fetch, real POST /diagnose with fail-clean pipeline and 6-test suite
- Phase 12 (Presenter Integration): `DiagnosisService` layer with tenant guard and HTTP error classification (503/504/502), real POST /diagnose and new GET /diagnose/{span_id} router, 10-test suite replacing 4 stale scaffold tests
- Phase 13 (Frontend Diagnosis UI + verification): `DiagnosisCard` sub-component with colored verdict/severity badges and auto-load GET on mount; debugging session that surfaced and fixed 3 integration bugs (missing env vars, wrong S3 bucket, missing auth header)

### What Worked

- **Fail-clean pipeline design**: enforcing assemble → diagnose → persist in strict order — with explicit error mapping at each step — made the Diagnosticer correct-by-construction and easy to test
- **Provider abstraction with lazy imports**: factory pattern meant adding/switching providers required zero changes to calling code; Ollama works without anthropic installed
- **Re-read-from-DB after Diagnosticer write**: Presenter owns the response schema, Diagnosticer owns the write — clean separation; avoids parsing the HTTP body
- **Parallel context assembly**: `asyncio.gather` for S3 fetches with `asyncio.wait_for` timeout meant LLM gets maximum context with bounded latency
- **`autouse` fixture for lifespan isolation**: patching `get_async_engine` at module level before `TestClient` creates the app was the correct isolation point — without it, every test hits real PostgreSQL during lifespan startup
- **Structured output via vendor tool/function calling**: Anthropic forced tool_choice + OpenAI strict=True + Ollama format= schema eliminated the free-text parsing failure mode entirely

### What Was Inefficient

- **Missing env vars in docker-compose**: `DIAGNOSTICER_PROVIDER`, `DIAGNOSTICER_MODEL`, `ANTHROPIC_API_KEY` were not added to the Diagnosticer service block when the service was scaffolded in v1.0 — discovered as 500 errors in Plan 13-02 debugging; should be wired at the same time as the real endpoint
- **S3 bucket name mismatch in seed script**: `seed_spans.py` was uploading to `xeter-spans` but Presenter reads from `xeter-payloads` — surfaced only during visual E2E verification; a smoke test for seed data visibility would catch this earlier
- **Auth forwarding discovered late**: Presenter was not forwarding the bearer token to Diagnosticer — caused 401s only during live E2E testing, not unit tests; cross-service auth contracts need explicit unit test coverage

### Patterns Established

- **Two-location patch pattern**: service-level tests patch `diagnosis_service.DiagnosisRepository`; router-level tests patch `routers.diagnose.DiagnosisRepository` — the right module to patch is where the name is imported, not where it's defined
- **Verification plan as integration testbed**: Plan 13-02 ("visual verification") was where all integration bugs surfaced — this is the correct use of a verification plan; the pattern holds from v1.0
- **Bearer token forwarding for service-to-service**: Presenter passes `request.headers.get("authorization")` directly to downstream services; shared SECRET_KEY validates — simple and sufficient for single-tenant SaaS

### Key Lessons

- Wire all env vars at the same commit that activates the feature — not at scaffold time, not at verification time
- Cross-service auth (token forwarding) requires an integration test, not just unit tests; a unit-mocked call to Diagnosticer will never catch a missing auth header
- The "verification" plan is the most valuable plan in a cross-service phase — budget time for it; it will find things unit tests can't

### Cost Observations

- 4 days, 3 phases, 8 plans — fastest milestone yet
- Average plan execution: ~10 min (range 5–14 min)
- Plan 13-02 was mostly debugging (~1.5 hours); the implementation plans themselves were clean

---

## Milestone: v1.3 — Security Hardening

**Shipped:** 2026-05-02
**Phases:** 4 (Phases 14–17) | **Plans:** 12 | **Timeline:** 3 days (2026-04-27 → 2026-04-30)

### What Was Built

- Phase 14 (DB Foundation): Provider Literals aligned to DB vocabulary; pre-flight audit script (exit 0/1 pattern); migration 004 with FORCE RLS on all 7 tables, span_scores tenant_isolation policy, score_writer SET LOCAL, and diagnoses CHECK constraints via NOT VALID + VALIDATE; S3 tenant-prefix assertion with 403 guard
- Phase 15 (Secrets Hygiene): Root .gitignore, generate-secrets.sh with shared-password reuse pattern, .env.example with 13 CHANGE_ME_BEFORE_DEPLOY fields; Redis --requirepass, MinIO mc anonymous set none on every up, no :- fallbacks for any secret; passlib removed; bcrypt cost-factor CI guard
- Phase 16 (Auth Hardening): SECRET_KEY + INTERNAL_API_KEY hard-fail startup in both services; InternalApiKeyMiddleware on Diagnosticer; 30-min JWT expiry; POST /auth/refresh + httpOnly cookie via Next.js Route Handler; 401 interceptor with single retry; CORS with env-var origin list; JWT_SECRET rotation runbook
- Phase 17 (GDPR Data Deletion): delete_tenant.py with dry-run + --confirm gate; ClickHouse async mutation; FK-ordered PostgreSQL DELETEs; S3 paginated batch delete; documented Redis flush procedure; GDPR_DELETION_RUNBOOK.md

### What Worked

- **Pre-flight audit pattern**: aligning provider Literals before running VALIDATE CONSTRAINT (Phase 14-01) meant migration 004 ran clean the first time — no rollback needed
- **Strict no-:- rule in docker-compose**: enforcing hard-fail for all secrets eliminated the entire class of "silently deployed dev credentials" bugs before they could manifest
- **Next.js Route Handler for cookie lifecycle**: recognising that Presenter's proxy rewrites strip Set-Cookie and routing cookie ownership to the Route Handler was the right call — clean boundary, no Presenter cookie writes
- **Dry-run-first GDPR pattern**: delete_tenant.py defaulting to read-only with --confirm required made the deletion safe to run speculatively; operators can audit before committing
- **Phase dependency discipline**: Phase 14 → 15 → 16 → 17 execution order was respected strictly — checking spans.py RLS existed before score_writer SET LOCAL was meaningful

### What Was Inefficient

- **STATE.md frontmatter shows stale counts (7 phases, 20 plans)**: the state tracker carried forward phase counts from v1.2 phases; milestone-scoped tracking needs a reset point at milestone boundary
- **Dead verify_session_token in Diagnosticer**: created during 16-01 for backwards-compat with existing test overrides, but was never wired to Depends() — a TODO was noted but not addressed before milestone close; requires cleanup in v1.4
- **generate-secrets.sh missing vars discovered at audit**: INTERNAL_API_KEY, S3_ENDPOINT_URL, ENVIRONMENT, CORS_ALLOW_ORIGINS were missing from the initial implementation; found and fixed during audit, not during Phase 15 execution — better integration tests for the script would have caught this

### Patterns Established

- **Pre-flight audit script**: `exit 0 = safe to migrate, exit 1 = violations with repair SQL` — reusable for any future NOT VALID constraint migration
- **Route Handler cookie boundary**: Next.js Route Handler owns httpOnly cookie lifecycle; Presenter never writes cookies directly
- **GDPR dry-run-first**: operator deletion scripts always default read-only; --confirm required to execute; completion message lists all stores touched
- **No :- fallbacks convention**: all security-critical env vars in docker-compose use `${VAR}` with no :- fallback — fail-loud on startup

### Key Lessons

- Wire all env vars for a feature in the same commit that activates it — not at scaffold time or verification time (same lesson as v1.2, still recurring)
- Integration tests for infra scripts (generate-secrets.sh output, .gitignore coverage) would catch gaps before audit phase
- Dead code that requires env var provisioning (verify_session_token needing SECRET_KEY) is a hidden operational cost — remove it at the same PR that makes it dead

### Cost Observations

- 3 days, 4 phases, 12 plans — fastest milestone to date per-plan (avg ~15 min/plan)
- 58 commits across 78 files
- Audit discovered and fixed generate-secrets.sh gaps inline — saved a gap-closure phase

---

## Milestone: v1.4 — Trace Hierarchy + TraceAnalyzer Foundation

**Shipped:** 2026-05-15
**Phases:** 4 (Phases 18–21) | **Plans:** 11 | **Timeline:** 2 days (2026-05-14 → 2026-05-15)

### What Was Built

- Phase 18 (Cleanup + BaseAnalyzer Refactor): Deleted dead `verify_session_token()` from Diagnosticer (InternalApiKeyMiddleware is sole auth boundary); corrected stale "NO RLS" comments post-migration-004; annotated all `os.environ.get()` defaults with `[safe-default]`/`[must-set-in-prod]` across 9 files; split `BaseAnalyzer` into 3-class hierarchy (generic root + `BaseSpanAnalyzer` + `BaseTraceAnalyzer`); `ToolCallAnalyzer` re-parented
- Phase 19 (TraceAnalyzer Scaffold + DB Migration): Concrete `TraceAnalyzer(BaseTraceAnalyzer)` scaffold with stub `analyze() → []`; Alembic migration 005 (flags.span_id nullable); worker trace buffer accumulates SpanData by trace_id; flush-timeout invokes TraceAnalyzer after WORKER_TRACE_FLUSH_TIMEOUT_S inactivity
- Phase 20 (Trace API): `GET /traces` (concurrent CH aggregation + asyncio.gather) and `GET /traces/{trace_id}` (two-phase 404, no-spans-yet 200, trace-level flags via span_id IS NULL); 14-test suite; 51 presenter tests passing
- Phase 21 (Trace UI): Traces list page + auth-guarded layout; NavBar Spans + Traces links; collapsible SpanTree with buildTree O(n) from parent_span_id; SpanDetailPanel breadcrumb with `?span=` URL deep-link; useState(spanFromUrl) initialiser auto-opens panel on back-navigation; human browser tests verified

### What Worked

- **Clearing v1.3 tech debt first (Phase 18)**: starting the milestone with cleanup instead of new features left the codebase in a clean state before adding complexity; env var annotations are embedded in code as future-proof documentation
- **Scaffold-first for TraceAnalyzer**: shipping a stub `analyze() → []` with full infrastructure (flush-timeout, nullable span_id, buffer eviction) meant the API and UI could be built without any trace-level flag data — v1.5 can add real checks with zero rearchitecting
- **Two-phase 404 for trace detail**: the CH-then-PG fallback pattern correctly handles the race where flags may exist before ClickHouse has flushed spans — discovered during planning, not during debugging
- **useState initialiser for span deep-link**: using `useState(spanFromUrl)` instead of a `useEffect` was the right call — synchronous, no re-render cycle, clean
- **Human browser verification for UI-03 deep-link**: caught that the disputed Suspense issue was a non-issue in practice — better than shipping with an open audit flag

### What Was Inefficient

- **Archived roadmap plan checkboxes wrong ([ ] instead of [x])**: CLI's milestone-complete command archived the ROADMAP.md snapshot before plans were marked complete in the roadmap (plans section checkboxes were still `[ ]` from the template); required manual post-archive fix — CLI should mark plans complete before archiving
- **STATE.md phase/plan counts wrong in CLI**: gsd-tools counted cumulative phases (11) and plans (31) instead of milestone-scoped (4 / 11); required manual correction of STATE.md and MILESTONES.md
- **19-01-SUMMARY.md frontmatter requirements-completed field was empty despite TANA-02 being verified**: doc gap noted in audit; requirements_completed field not populated at plan write time; low-cost fix is to fill this field at plan completion

### Patterns Established

- **Env var safety annotation pattern**: every `os.environ.get()` in service files now carries `[safe-default]` or `[must-set-in-prod]` inline comment — production deployment checklist embedded in the code
- **Trace-level flag write**: `write_flags(span_id=None, trace_id=..., ...)` — span_id=None denotes trace-level; span-level writes unchanged
- **Buffer eviction finally block**: trace evicted from both `trace_buffer` and `trace_last_seen` unconditionally in finally, even on TraceAnalyzer error — prevents unbounded growth
- **SpanTree buildTree pattern**: `Map<string|null, SpanInTrace[]>` bucketing by parent_span_id (null = root) in O(n) — reusable pattern for any tree UI component

### Key Lessons

- **The audit file is worth reading before milestone-complete**: the v1.4 audit flagged the Suspense boundary concern before close; human browser verification resolved it definitively — don't proceed blind on audit tech_debt items, verify them
- **Infrastructure before analysis**: scaffolding TraceAnalyzer with an empty analyze() was the correct v1.4 decision — the buffer, schema, API, and UI are all load-bearing; real checks are additive
- **CLI milestone archive should mark phase plans complete**: the current CLI archives the roadmap before updating plan status, leaving checkboxes in wrong state in the archive

### Cost Observations

- 2 days, 4 phases, 11 plans, 42 commits — fastest milestone by day count
- Average plan: ~11 min (range 5–18 min)
- Phase 18-01 (env var audit) was the longest at 18 min; Phase 21-03 (breadcrumb) was the shortest at 5 min

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Days | LOC | Key Pattern |
|-----------|--------|-------|------|-----|-------------|
| v1.0 MVP | 6 | 21 | 12 | ~12,660 | Bottom-up strict ordering |
| v1.1 Analyser Accuracy | 4 | 10 | 12 | ~11,148 Py | One method at a time, calibrate before next |
| v1.2 Diagnosticer | 3 | 8 | 4 | ~16,017 (+4,869) | Fail-clean service activation; verification plan as integration testbed |
| v1.3 Security Hardening | 4 | 12 | 3 | ~14,500 Py + 3,000 TS | Pre-flight audit before migration; hard-fail secrets; Route Handler cookie boundary |
| v1.4 Trace Hierarchy | 4 | 11 | 2 | +6,772 / -129 lines | Cleanup-first; scaffold-then-checks; URL-driven UI state |
