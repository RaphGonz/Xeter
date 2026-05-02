# Xeter

## What This Is

Xeter is a B2B SaaS observability platform that debugs AI agent tool-calling failures. It ingests OpenTelemetry spans from instrumented agent code via a Python SDK, applies heuristic analysis (vector similarity between prompt and tool fields) to flag anomalous tool calls, and exposes a dashboard where developers can see what went wrong and why. Unlike existing tools that show traces, Xeter isolates root cause — model, architecture, or prompt — via on-demand LLM diagnosis.

v1.0 shipped: full pipeline from SDK to dashboard running locally via Docker Compose. v1.1 shipped: all four analyser check methods rewritten with research-backed implementations. v1.2 shipped: LLM-powered Diagnosticer active end-to-end. v1.3 shipped: full security hardening — tenant isolation, auth hardening, secrets hygiene, and GDPR deletion.

## Core Value

When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Python SDK that instruments agent code and emits OTel spans to the Analyser — v1.0
- ✓ Analyser receives spans, stores them in ClickHouse (batched), S3 (large payloads), and enqueues for async embedding analysis — v1.0
- ✓ Heuristic flagging: vector similarity across 5 dimensions; flag types: wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error — v1.0
- ✓ Flags stored as append-only rows in PostgreSQL with score and detail; flag_type is open string (no enum) — v1.0
- ✓ Large text payloads stored in S3 with reference keys in ClickHouse; tool_arguments inline as JSON — v1.0
- ✓ Redis queue decoupling ingestion from embedding workers — v1.0
- ✓ Dashboard: span list with flag indicators, filtering by flag_type/agent_name/time range — v1.0
- ✓ Dashboard: span detail with flag details, similarity scores, and lazy-loaded S3 payload content — v1.0
- ✓ Auth: API key per tenant for SDK ingestion; email/password login for dashboard — v1.0
- ✓ Multi-tenancy: tenant_id on all tables, RLS in PostgreSQL, tenant guard in DAL — v1.0
- ✓ Diagnosticer service scaffolded (501 placeholder, wired to Presenter) — v1.0
- ✓ Docker Compose for local development (ClickHouse, PostgreSQL, Redis, MinIO, backend, frontend) — v1.0
- ✓ `_check_wrong_args` rewritten with error-regex priority path + hybrid cosine+BOW on flattened arg values — v1.1
- ✓ `_check_wrong_tool` rewritten with three-branch logic (called+available, called+no-available, not-called); threshold key `wrong_tool_called` — v1.1
- ✓ `_check_no_tool` → `no_tool_used`: rank-based, flags when prompt overlaps with available tools and none called — v1.1
- ✓ `_check_excessive_tool` → `unnecessary_tool_call`: social centroid signal flags tool calls on conversational/phatic prompts — v1.1
- ✓ Shared hybrid scoring utility (`bow_score` + `hybrid_score`) in `base.py` (HYBRID-01) — v1.1
- ✓ `calibrate.py` per-method isolation (`--flag-type`) and `BINARY_FLAG_TYPES` for non-threshold detectors — v1.1
- ✓ LLM-powered Diagnosticer: on-demand root cause analysis per span — verdict (model/architecture/prompt) + severity + affected field + recommended fix — v1.2
- ✓ Configurable LLM provider + model via env vars (Anthropic / OpenAI / Ollama) — v1.2
- ✓ Diagnosis results stored in PostgreSQL (`diagnoses` table with RLS) and rendered in SpanDetailPanel (DiagnosisCard with auto-load) — v1.2
- ✓ span_scores RLS policy (tenant_isolation); FORCE RLS on all 7 PostgreSQL tables; score_writer SET LOCAL in explicit transaction — v1.3
- ✓ diagnoses CHECK constraints: verdict IN ('model','architecture','prompt','unknown'), severity IN ('low','medium','high') — v1.3
- ✓ S3 payload keys scoped to tenant prefix ({tenant_id}/...); Presenter asserts key ownership before serving content (403 on cross-tenant) — v1.3
- ✓ passlib removed; bcrypt CI cost-factor guard (≥12); test fixtures use rounds=4 session-scoped — v1.3
- ✓ Secrets hygiene: root .gitignore, generate-secrets.sh one-command .env, no :- fallbacks for secrets in docker-compose — v1.3
- ✓ MinIO xeter-payloads bucket asserted private (mc anonymous set none) on every docker-compose up — v1.3
- ✓ Redis requirepass enforced; REDIS_PASSWORD with no :- fallback — v1.3
- ✓ JWT 30-min expiry; SECRET_KEY hard-fail on startup in Presenter and Diagnosticer (no dev-key fallback) — v1.3
- ✓ httpOnly refresh token; silent 401 interceptor in Next.js api.ts; Route Handler owns cookie lifecycle — v1.3
- ✓ JWT_SECRET rotation runbook (docs/JWT_ROTATION_RUNBOOK.md) covering dual-secret window and service restart sequence — v1.3
- ✓ INTERNAL_API_KEY hard-fail + InternalApiKeyMiddleware on Diagnosticer; service trust boundary established — v1.3
- ✓ GDPR Art. 17: delete_tenant.py dry-run + --confirm, covering ClickHouse / PostgreSQL / S3 / Redis — v1.3

### Active

<!-- v1.4 candidates — define requirements in /gsd:new-milestone -->

- [ ] python-jose → PyJWT migration — python-jose near-abandoned; migrate before CVE liability (AUTH-F02)
- [ ] Refresh token revocation store — server-side blacklist for stolen token detection (AUTH-F01)
- [ ] Rate limiting on Analyser ingestion — per-API-key sliding window, Redis, 429 with Retry-After (OPS-F01)
- [ ] TypeScript/Node.js SDK for instrumenting JS-based agents (SDK-F01)

### Out of Scope

<!-- Explicit boundaries — reviewed after v1.2. -->

- Prompt management / versioning — competes with Langfuse on their home turf; not our moat
- LLM cost attribution / billing analytics — general observability breadth, not diagnosis
- Multi-model A/B comparison — established players own this
- LLM-as-a-judge eval pipelines — HoneyHive and LangSmith have mature offerings
- On-premise distribution — SaaS only per constraints
- Clerk auth migration — future; schema supports it, deferred to when multi-member tenants are needed
- TypeScript SDK — deferred to v1.4+; Python SDK covers current customer base
- Per-service MinIO IAM accounts — single bucket policy sufficient for current threat model (ACL-F01)
- ClickHouse per-service read-only users + row policies — Python DAL is the v1.3 enforcement layer (DB-F01)
- Per-tenant Redis queue keys — Worker refactor independent from current priorities (OPS-F02)

## Context

- v1.0 shipped 2026-04-04, v1.1 shipped 2026-04-18, v1.2 shipped 2026-04-25, v1.3 shipped 2026-05-02: full pipeline + LLM diagnosis + security hardening running locally via Docker Compose
- ~14,500 LOC Python + 3,000 TypeScript; flag types: `wrong_tool_called`, `wrong_tool_args`, `no_tool_used`, `unnecessary_tool_call`, `tool_not_available`, `parsing_error`, `response_anomaly`
- Tech stack: Python 3.12, FastAPI, ClickHouse, PostgreSQL (RLS + CHECK constraints), Redis (requirepass), MinIO (S3, private ACL), Next.js 15, sentence-transformers (all-MiniLM-L6-v2), Anthropic/OpenAI/Ollama (Diagnosticer)
- Architecture: Analyser (ingestion) → Redis queue → Worker (embedding+flagging) → Presenter (read/auth/diagnosis trigger) → Diagnosticer (LLM root cause) → View (Next.js)
- Calibration: precision target 80%; `wrong_tool_called` is binary (no threshold sweep); full-suite mean precision ≥ 95%
- Main adversary: Langfuse — open-source, self-hostable, but doesn't diagnose root cause
- Solo developer; Python primary language; 112+ tests passing

## Constraints

- **Tech stack**: Python backend + Python SDK primary; ClickHouse + PostgreSQL + S3 + Redis for storage
- **Solo developer**: Single maintainer — scope must stay tight; progressive building is essential
- **SaaS only**: No on-premise distribution
- **Correctness over speed**: False positive flags erode trust — threshold calibration is critical
- **View has no logic**: All business logic in backend services per AD-04

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| A4 approach (A3 first) | Best global pattern across all evaluation matrices; A3 is natural first milestone | ✓ Good — shipped cleanly as v1.0 |
| ClickHouse for spans | OLAP, append-only, proven at scale by competitors (Langfuse, LangSmith) | ✓ Good — no issues at dev scale |
| PostgreSQL for flags/diagnostics/auth | Low volume, mutable, relational; append-only pattern | ✓ Good — RLS works as designed |
| S3 for large payloads | Prevents row bloat in ClickHouse; lazy retrieval preferred | ✓ Good — lazy-load UX works well |
| Redis for ingestion queue | Decouples ingestion from embedding; standard worker pattern | ✓ Good — BRPOP FIFO ordering solid |
| Async flagging | Span ingestion must not be blocked by embedding computation (AD-01) | ✓ Good — ~37s E2E is acceptable |
| Diagnosticer as separate service | LLM calls are slow and on-demand; isolation allows independent scaling (AD-02) | ✓ Good — scaffold in v1 painless |
| REST for Presenter | REST for queries/actions; SSE deferred to v1.1 | ✓ Good — sufficient for v1 |
| Email/password auth first, Clerk later | Zero external dependency for early development; schema supports migration (AD-14) | ✓ Good — JWT works cleanly |
| Scaffold Diagnosticer in v1 | Wired but inactive — enables progressive building without rearchitecting later | ✓ Good — POST /diagnose proxy ready |
| flag_type as open string (not enum) | New analyzer categories must not require schema migrations (FLAG-03) | ✓ Good — validated during Phase 3 |
| ClickHouse ORDER BY (tenant_id, trace_id, time_begin) | One-way door — set before any data flows | ✓ Good — query performance confirmed |
| bcrypt directly instead of passlib | passlib 1.7.4 incompatible with Python 3.14 + current bcrypt | ✓ Good — works cleanly |
| Worker Dockerfile pre-bakes sentence-transformers model | Avoids 80MB runtime download on first span | ✓ Good — image startup fast |
| wrong_tool_args excluded from P/R calibration | Low-confidence by design; terse JSON produces unreliable cosine similarity | ✓ Good — calibration more meaningful |
| BRPOP with 5s retry backoff in worker | Race: Redis delivers span_id before ClickHouse batcher flush (5s interval) | ✓ Good — fixed silent "span not found" |
| Skip `tool_use_violation` windowed proximity approach | `no_tool_used` covers the priority case cleanly; proximity detection adds complexity for marginal gain | ✓ Good — simpler and calibrated well |
| Social centroid for `unnecessary_tool_call` | Necessity-delta approach was theoretically sound but hard to calibrate; social centroid is interpretable and P=1.0 | ✓ Good — R=0.667 at threshold=0.25 |
| Three-branch logic for `wrong_tool_called` | Old AND-gate suppressed high-score wrong-tool spans; three explicit branches cover all cases | ✓ Good — logic is explicit, tests cover all branches |
| String (not PG enum) for verdict/severity | Avoids migration pain when adding new values; consistent with FLAG-03 pattern | ✓ Good — no enum migrations needed |
| Fail-clean Diagnosticer pipeline | assemble → diagnose → persist strictly in order; no DB row written unless LLM parse succeeds | ✓ Good — prevents phantom diagnosis rows |
| Presenter re-reads from DB after Diagnosticer write | Presenter owns the response schema; avoids parsing Diagnosticer HTTP body | ✓ Good — clean separation of concerns |
| Auth token forwarding to Diagnosticer | Presenter forwards bearer token; shared SECRET_KEY validates — simple, no separate service auth | ✓ Good — sufficient for single-tenant deployment |
| Re-diagnosis always overwrites (no idempotency) | Every Diagnose click triggers fresh LLM call; diagnoses table is append-only so history preserved | ✓ Good — UX is simple, history intact |
| getDiagnosis 404 suppressed in frontend | No prior diagnosis is normal initial state; surfacing 404 would confuse users | ✓ Good — clean UX on first visit |
| LLM provider lazy imports in factory | Only selected provider SDK imported at runtime — avoids ImportError when other SDKs absent | ✓ Good — Ollama works without anthropic installed |
| Structured output via vendor tool/function calling | No free-text parsing; Anthropic tool_choice force, OpenAI strict=True, Ollama format= schema | ✓ Good — eliminated free-text parsing failure mode |
| SET LOCAL for RLS in score_writer | No BYPASSRLS role; app.current_tenant_id SET LOCAL in explicit transaction mirrors flag_writer.py | ✓ Good — consistent writer pattern, simpler than a BYPASSRLS grant |
| httpOnly cookie via Next.js Route Handler | Presenter rewrites strip upstream Set-Cookie; Route Handler owns cookie lifecycle cleanly | ✓ Good — no Presenter direct cookie writes, clean boundary |
| CHECK constraints with NOT VALID + pre-flight audit | Avoids ACCESS EXCLUSIVE lock; pre-flight script exits non-zero if violating rows exist before VALIDATE | ✓ Good — zero-downtime constraint migration pattern, reusable |
| INTERNAL_API_KEY middleware + hard-fail startup | Explicit service trust boundary; dead verify_session_token in Diagnosticer is tech debt (never wired to Depends()) | ⚠ Revisit — remove dead verify_session_token before v1.4 |
| GDPR Redis flush as documented procedure | analysis_queue is global; automated LREM unsafe (FLUSHDB prohibited); runbook covers operator steps | ✓ Good — accepted v1.3 tradeoff, documented in GDPR_DELETION_RUNBOOK.md |

---
*Last updated: 2026-05-02 after v1.3 Security Hardening milestone*
