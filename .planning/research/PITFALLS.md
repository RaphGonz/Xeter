# Pitfalls Research

**Domain:** AI agent observability / debugging platform (ClickHouse + PostgreSQL + S3 + Redis + vector embeddings)
**Researched:** 2026-03-27
**Confidence:** MEDIUM-HIGH (critical pitfalls verified across multiple sources including Langfuse post-mortem and ClickHouse official docs; embedding threshold pitfalls MEDIUM — domain-specific data scarce)

---

## Critical Pitfalls

### Pitfall 1: Embedding Threshold Hardcoded Without Domain Calibration

**What goes wrong:**
A cosine similarity threshold is picked arbitrarily (e.g., 0.7) based on general NLP benchmarks and shipped without calibration against actual agent tool-call spans. The threshold is optimal for one domain but catastrophically wrong for another: legal document similarity at 0.7 is weak; social media similarity at 0.7 is strong. Optimal thresholds vary from 0.334 to 0.867 across domains in published benchmarks. For Xeter's specific comparison (prompt↔tool_name, prompt↔tool_description, prompt↔response), there is no off-the-shelf threshold that works — calibration against real agent spans is mandatory.

**Why it happens:**
The developer ships what works in toy examples during development, then optimises only when users complain. By that time, false positives have eroded trust and users have stopped trusting the flags entirely.

**How to avoid:**
- Design the threshold as a configuration parameter from day one — never hardcode it in business logic.
- Log every similarity score computed, including scores for spans that are NOT flagged, so a calibration dataset accumulates automatically.
- Build a calibration harness in the foundation phase: a small labelled dataset of known-good and known-bad spans that can be run against candidate thresholds to produce precision/recall curves.
- Do not claim the flagging is reliable until threshold calibration has been run against at least 200 real labelled spans.

**Warning signs:**
- User reports that the dashboard is "noisy" (too many false positives) or "silent" (flags nothing obvious).
- Score distribution plots show all scores clustering near 0.5 — the model is not discriminating.
- Calibration dataset is empty or never evaluated.

**Phase to address:**
Foundation / ingestion phase — threshold must be a first-class config from the first sprint, and score logging infrastructure must exist before any real users onboard.

---

### Pitfall 2: ClickHouse Sorting Key Locked in Wrong Order

**What goes wrong:**
The ClickHouse `spans` table is created with a poorly chosen ORDER BY (e.g., `ORDER BY span_id` or `ORDER BY time_begin`). Because ClickHouse uses the primary key as its sparse index, a wrong choice means every query for a specific tenant or trace requires a full table scan. Worse: **you cannot change a sorting key on an existing table**. The only fix is a full table rebuild — migrating potentially millions of rows into a new table.

**Why it happens:**
Developers familiar with PostgreSQL treat ClickHouse primary keys like PostgreSQL primary keys (point-lookup indexes). ClickHouse primary keys work completely differently — they are sparse, ordered indexes optimised for range scans, not point lookups. The correct key for Xeter's access patterns is `(tenant_id, trace_id, time_begin)` because every query is scoped by tenant and most are scoped by trace.

**How to avoid:**
- Establish the ORDER BY as `(tenant_id, trace_id, time_begin)` in the first schema migration. This directly reflects the query pattern: tenant-scoped, trace-grouped, time-ordered.
- Never use a high-cardinality monotonically-increasing field (like a UUID `span_id` or millisecond timestamp alone) as the sort key.
- Add `span_id` as a secondary index (skip index or a data skipping index) if point lookups on span_id are needed; do not put it in ORDER BY.
- Verify query plans in the first week of development with `EXPLAIN` on representative queries before any data is loaded.

**Warning signs:**
- Queries slow down linearly with table size even for single-tenant, single-trace lookups.
- `EXPLAIN` shows full table scans (`rows_read` equals total row count).
- Schema was designed without consulting ClickHouse access pattern documentation.

**Phase to address:**
Foundation / storage schema phase — ORDER BY must be the first design decision before the first migration is written.

---

### Pitfall 3: High-Frequency Small Inserts Causing "Too Many Parts" Failure

**What goes wrong:**
Each INSERT to ClickHouse creates one or more data parts on disk. Background merge processes merge parts over time, but if inserts arrive faster than merges can consolidate them, the active part count exceeds ClickHouse's threshold (default 300 per partition), and all subsequent inserts fail with `DB::Exception: Too many parts`. This is not theoretical — a production ClickHouse deployment storing OpenTelemetry spans at 100k-200k spans/sec triggered this error repeatedly.

**Why it happens:**
The ingestion code inserts one span per INSERT call (following a REST-style request/response model) rather than batching. This pattern is natural when coming from PostgreSQL, where single-row inserts are cheap.

**How to avoid:**
- Buffer spans in the Redis queue before writing to ClickHouse. The embedding worker that reads from Redis should batch spans before inserting: aim for 1,000–100,000 rows per INSERT.
- Alternatively, enable ClickHouse async inserts (`async_insert=1`) server-side. This moves batching responsibility to ClickHouse but requires `wait_for_async_insert=1` to confirm disk persistence.
- Do NOT allow the Analyser to write individual spans directly to ClickHouse per ingestion request — even at low volumes, this creates a scaling ceiling.
- Monitor `system.parts` table — alert when active parts per partition exceed 200.

**Warning signs:**
- `Too many parts` errors appearing in ClickHouse logs.
- Insert latency rising over time.
- `system.merges` shows merge queue backing up.

**Phase to address:**
Ingestion pipeline phase — batched write path must be designed before any write code is written. The Redis queue exists specifically to enable this; use it.

---

### Pitfall 4: Span Lost on ClickHouse Insert Failure With No Recovery Path

**What goes wrong:**
The arc42 doc acknowledges: "If ClickHouse span insert fails: span lost; SDK must retry or accept loss." If the ingestion path writes directly to ClickHouse without durability, and ClickHouse is temporarily down (restart, migration, Too Many Parts error), spans are silently dropped. Users see gaps in their trace data, cannot reproduce bugs, and lose trust in the platform.

**Why it happens:**
Engineers treat storage as reliable and don't build durability into the write path. Redis is used as a queue for async flagging, but not as a durable buffer for writes — meaning the write-to-ClickHouse path has no replay.

**How to avoid:**
- Use S3 as the event store (Langfuse's exact lesson): write spans to S3 first, then asynchronously to ClickHouse. If ClickHouse fails, replay from S3. Redis holds only references and processing state.
- At minimum, write spans to the Redis queue before acknowledging the SDK request. If ClickHouse insert fails, the item remains in the queue for retry.
- Make span inserts idempotent: use `span_id` as the deduplication key (ClickHouse supports insert deduplication by block hash natively, but designing idempotent inserts explicitly is safer).

**Warning signs:**
- Trace views show gaps in span timelines.
- No retry/dead-letter mechanism exists in the ingestion queue.
- ClickHouse insert errors are logged but not acted upon.

**Phase to address:**
Ingestion pipeline phase — define durability contract before writing any insert code.

---

### Pitfall 5: Cross-Store Inconsistency Between ClickHouse and PostgreSQL Flags

**What goes wrong:**
A span is written to ClickHouse but the async flagging worker fails before writing the flag to PostgreSQL. The span appears in the dashboard as "unflagged" even though it should have flags. Worse: a partial write results in a flag row in PostgreSQL referencing a `span_id` that does not yet exist in ClickHouse (if span write also failed). The two stores drift apart silently.

**Why it happens:**
There is no distributed transaction across ClickHouse and PostgreSQL. Engineers assume that because both writes succeed in the happy path, the system is consistent. The unhappy path is never tested.

**How to avoid:**
- Accept eventual consistency explicitly: the span list view shows "flagging pending" state until flags arrive. Never imply synchronous flagging.
- Design the flag worker to be idempotent: running it twice on the same span_id is safe.
- Use a processing-state field in Redis (or a `flagging_status` column in PostgreSQL) to track whether async processing completed. Dashboard queries check this status.
- Write integration tests that kill the flag worker mid-run and verify the system recovers correctly on restart.

**Warning signs:**
- Flag worker has no retry logic — failed jobs disappear silently.
- Dashboard shows unflagged spans that users know should be flagged.
- No "flagging pending" state visible in the UI.

**Phase to address:**
Async flagging phase — consistency model must be designed explicitly, not assumed to work.

---

### Pitfall 6: OTel GenAI Semantic Conventions Churn Breaking the SDK

**What goes wrong:**
The SDK emits spans using OpenTelemetry GenAI semantic conventions. Those conventions are currently **experimental** and have already had breaking changes (version 1.37.0 introduced breaking changes to the GenAI convention). If the SDK hardcodes attribute names from the convention without versioning, a convention update forces a full SDK release cycle to stay compatible, causing customer instrumentation to break silently when their OTel SDK version diverges from Xeter's SDK version.

**Why it happens:**
The GenAI semantic conventions are new and fast-moving. Developers treat them as stable because they are "official" — but experimental status means breaking changes are allowed without deprecation cycles.

**How to avoid:**
- Define Xeter's own stable span schema independently of OTel's GenAI conventions. The OTel conventions inform the design but Xeter owns the contract.
- Map between OTel convention attribute names and Xeter's internal schema in a single adapter layer (one file). When conventions change, only the adapter changes.
- Version the SDK's span format explicitly (`xeter.schema.version` attribute). The Analyser can handle multiple schema versions.
- Do not rely on OTel GenAI agent framework conventions (still in discussion as of March 2026) for anything critical.

**Warning signs:**
- OTel semantic-conventions GitHub releases show GenAI changes.
- SDK attributes are scattered across multiple files with no central convention mapping.
- No schema version field in emitted spans.

**Phase to address:**
SDK foundation phase — schema versioning must be designed into the SDK before any customers instrument their agents.

---

### Pitfall 7: tenant_id Missing From a Query Causing Cross-Tenant Data Leak

**What goes wrong:**
One query in the Presenter or Analyser omits `WHERE tenant_id = $tenant_id`. This is the most catastrophic correctness bug in a multi-tenant SaaS: Tenant A sees Tenant B's data. It is guaranteed to happen eventually if tenant_id scoping is enforced purely by developer discipline on every query, especially as the codebase grows.

**Why it happens:**
PostgreSQL RLS (row-level security) is not configured, so the database does not enforce tenant isolation — the application layer does. Application-layer enforcement is reliable only if every query goes through a single accessor function that injects tenant_id automatically. As soon as a developer writes a raw query or adds a new endpoint, the filter is easy to forget.

**How to avoid:**
- Build a data access layer (DAL) in the Presenter that is the only code that writes SQL. All queries go through this layer. Tenant ID injection happens in the DAL, not at the call site.
- Enable PostgreSQL Row Level Security on all `flags`, `diagnostics`, `users`, and `api_keys` tables as a defense-in-depth measure (belt and suspenders — the DAL AND the DB enforce isolation).
- For ClickHouse, create row policies scoped to the application-level user that inject `tenant_id` filtering.
- Write integration tests that authenticate as Tenant A and verify Tenant B's data is never returned under any endpoint.

**Warning signs:**
- Raw SQL strings scattered across service layers rather than in a single DAL.
- No integration tests verifying cross-tenant isolation.
- PostgreSQL RLS is disabled (default).

**Phase to address:**
Multi-tenancy / auth phase — RLS and DAL must be built before any customer data is stored.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode embedding threshold at 0.7 | Ship faster | Flags never calibrated to domain; users stop trusting them | Never — threshold must be config from day one |
| Single-row inserts to ClickHouse | Simple ingestion code | "Too many parts" failures under load; forced architectural change | Never — Redis queue exists to batch writes |
| Skip tenant_id in one query | Faster development | Cross-tenant data leak in production | Never |
| Embed model hardcoded (`all-MiniLM-L6-v2`) | Avoids decision | Model may underperform on agent tool-call semantics; forced reembedding of all historical spans to switch | Acceptable in v1 if documented and configurable via env var |
| S3 payload fetch on span list view (eager) | Simpler code | Every list view makes N S3 requests; latency 10-100x worse | Never for list views — lazy/on-demand only |
| ClickHouse sorting key with only `time_begin` | Quick schema | All tenant/trace queries do full table scans; no fix without rebuild | Never |
| Skip processing-state tracking for async flags | Simpler worker | No way to detect or recover from partial flag writes | Never in production |
| Skip schema versioning in SDK | Faster v1 | Convention changes break all customer instrumentation silently | Never — one field, one adapter file, solved in an hour |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ClickHouse inserts | One INSERT per span (REST-style) | Buffer in Redis queue, INSERT in batches of 1,000+ rows |
| ClickHouse schema changes | `ALTER TABLE ADD COLUMN` assumed free | Adding columns to `MergeTree` tables is cheap; changing `ORDER BY` requires full table rebuild — design ORDER BY once and lock it |
| S3 + ClickHouse `_ref` fields | Fetch S3 content on every ClickHouse row read | Fetch S3 content only on span detail view (lazy); list views never touch S3 |
| Redis queue + worker | Worker acks job before processing completes | Ack only after PostgreSQL flag write succeeds; use visibility timeout / lease pattern |
| PostgreSQL cross-store FK | Foreign key from `flags.span_id` → ClickHouse `spans.span_id` | FK cannot cross databases — enforce referential integrity in application layer; document explicitly |
| OTel OTLP endpoint | Expose plain HTTP for OTLP without auth | All OTLP ingestion endpoints must validate API key before accepting payload |
| sentence-transformers model | Use `all-MiniLM-L6-v2` without normalisation check | Verify model ends with `Normalize` layer; if yes, use dot product (not cosine) to avoid double-normalisation overhead |
| MinIO (local S3) | Different error codes than AWS S3 | Use boto3 with endpoint_url override; test all error paths against MinIO in CI, not just AWS |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Single-row ClickHouse inserts | "Too many parts" errors; insert latency grows | Batch writes through Redis queue | ~100 inserts/second sustained |
| Eager S3 fetch on span list | Dashboard list view takes 5-30 seconds | Lazy load S3 content only on detail view | ~50 spans per page |
| Embedding computed synchronously on ingestion | Ingestion endpoint latency spikes >1 second | Async: enqueue span, return 202, compute embedding in worker | First production agent sending >10 spans/second |
| Uncached embeddings per request | Embedding same prompt text repeatedly | Cache embeddings in Redis with TTL keyed by content hash | When same prompt appears >2x across spans |
| Presenter merging ClickHouse + PostgreSQL sequentially | Detail view latency = sum of both query times | Parallelise both queries using `asyncio.gather()` | Always — should be default |
| `ORDER BY non_primary_key LIMIT N` in ClickHouse | Full table scan for every paginated query | Ensure ORDER BY in list queries uses primary key prefix (`tenant_id, trace_id, time_begin`) | First query on non-trivial dataset |
| Nullable columns in ClickHouse | Query performance degrades; storage increases | Use empty string defaults instead of Nullable(String) | Schema design time |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| API key stored in plaintext in `api_keys` table | Key theft from DB dump compromises all customer ingestion | Store only `bcrypt` hash; plaintext shown once on creation, never stored |
| Tenant ID taken from request body rather than authenticated session | Tenant impersonation: attacker sets `tenant_id` to any value | Derive `tenant_id` from authenticated API key at validation time; never trust client-supplied tenant_id |
| OTLP endpoint unauthenticated | Anyone can flood the ingestion pipeline with garbage spans | Validate API key on every OTLP/HTTP request before touching ClickHouse or Redis |
| S3 presigned URLs with long expiry given to frontend | URL cached by browser; expired key still works via role rotation | Set presigned URL expiry to 15 minutes; generate fresh URL per detail view request |
| LLM prompt injection via span content | Attacker crafts span content to manipulate the Diagnosticer's LLM reasoning | Sanitise or delimit span content in Diagnosticer prompts; treat span content as untrusted user input in the prompt template |
| Cross-tenant data leak via missing tenant_id filter | Tenant A reads Tenant B's flags/diagnostics | DAL enforces tenant_id on all queries; PostgreSQL RLS as second layer |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Flag with no explanation of why it fired | User sees "wrong_tool" flag but cannot understand what triggered it | Always surface `detail` JSON in the flag: which fields were compared, what the similarity score was, what the threshold was |
| Unflagged span with no "analysed" status | User cannot distinguish "clean span" from "analysis not yet run" | Show explicit `pending / analysed / flagged` status on every span |
| Threshold set too low — all spans flagged | User ignores all flags; platform becomes noise | Default threshold should err toward low recall (few false positives); let users tune sensitivity upward |
| LLM diagnostic response displayed as raw JSON | Confusing to non-ML developers | Structure the `diagnostics.result` schema from the start: `root_cause` (model/architecture/prompt), `evidence` (list), `recommendation` (string) |
| Dashboard loads all S3 payload content on page load | Page takes 10+ seconds with 50 spans | Always lazy-load S3 content; show placeholder until user expands span detail |

---

## "Looks Done But Isn't" Checklist

- [ ] **Embedding threshold:** Verify the threshold is loaded from config (not hardcoded), and that score logging is in place to enable future calibration.
- [ ] **ClickHouse ORDER BY:** Verify `SHOW CREATE TABLE spans` shows `ORDER BY (tenant_id, trace_id, time_begin)` — not timestamp alone or span_id.
- [ ] **Insert batching:** Verify the write path reads from Redis queue in batches, not one span at a time. Load test: 500 spans/second for 60 seconds — no "Too many parts" errors.
- [ ] **Tenant isolation:** Verify with an integration test: create two tenants, insert spans for both, authenticate as Tenant A, call every endpoint — confirm zero Tenant B spans returned.
- [ ] **Flag worker idempotency:** Kill the flag worker mid-run. Restart it. Verify no duplicate flags, no missing flags.
- [ ] **S3 lazy load:** Verify span list endpoint makes zero S3 calls. Verify detail endpoint makes exactly one S3 call per ref field.
- [ ] **SDK schema versioning:** Verify every emitted span includes a `xeter.schema.version` attribute.
- [ ] **API key hashing:** Verify the `api_keys` table contains only `key_hash` — no plaintext. Verify a raw SQL dump of the table cannot be used to authenticate.
- [ ] **Async flag vs sync ingestion:** Verify the ingestion endpoint returns 200/202 before any embedding computation starts. Load test confirms ingestion latency stays under 100ms even with embedding worker running.
- [ ] **Error handling when ClickHouse is down:** Verify the Analyser returns a retryable error (not 500 drop) when ClickHouse is unreachable. Verify Redis queue retains the span for retry.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong ClickHouse ORDER BY in production | HIGH | Create new table with correct ORDER BY; INSERT INTO new_table SELECT * FROM old_table; atomically swap using RENAME TABLE; downtime window required |
| Hardcoded threshold eroding trust | MEDIUM | Add threshold config param; expose per-tenant threshold override in dashboard settings; re-run flagging analysis on historical spans using score log (requires score log to have been populated) |
| Cross-tenant data leak discovered | CRITICAL | Immediate: rotate all API keys; audit all affected queries; deploy fix; notify affected tenants per legal obligation |
| Span loss during ClickHouse downtime | MEDIUM | If Redis queue still contains un-acked spans: replay from queue after ClickHouse recovery. If queue was also lost: data is gone — post-mortem, add S3 durability layer |
| OTel convention breaking change breaks SDK | MEDIUM | Release SDK patch with adapter update; bump `xeter.schema.version`; Analyser handles both versions for one release cycle |
| Embedding model change invalidating historical scores | MEDIUM | Re-embed all historical spans using new model; historical flags become stale — either recompute or mark as "legacy scoring" |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Embedding threshold hardcoded | Foundation / ingestion schema | Threshold value read from config; score logging confirmed active |
| Wrong ClickHouse ORDER BY | Storage schema design | `SHOW CREATE TABLE spans` checked before any data loaded |
| Small inserts / too many parts | Ingestion pipeline | Load test at 500 spans/sec shows no part errors; batch size logged |
| Span loss on ClickHouse failure | Ingestion pipeline | Kill ClickHouse mid-test; restart; verify spans replay from queue |
| Cross-store flag inconsistency | Async flagging pipeline | Kill flag worker mid-run; verify recovery; integration test |
| OTel convention churn breaking SDK | SDK design phase | `xeter.schema.version` in every span; adapter layer in one file |
| Cross-tenant data leak | Multi-tenancy / auth phase | Integration test: Tenant A cannot read Tenant B data via any endpoint |
| S3 eager fetch on list view | Presenter / API phase | Confirmed zero S3 calls on span list endpoint; profile under load |
| Nullable ClickHouse columns | Storage schema design | Schema review: no `Nullable()` columns in `spans` table |
| Solo developer scope creep | Every phase | Phase scope locked at phase start; no feature additions mid-phase |

---

## Solo Developer Scope Warning

This is a five-service system (Analyser, Presenter, Diagnosticer, SDK, View) backed by four storage technologies (ClickHouse, PostgreSQL, S3, Redis). The highest risk for a solo developer is not any individual technical pitfall — it is building too much in parallel, leaving multiple half-finished components, and never having a shippable artifact.

**Mitigation:**
- Each phase must ship one end-to-end vertical slice, not multiple partial components.
- The Diagnosticer is scaffolded but inactive in v1 — this is correct. Resist activating it early.
- Lock phase scope before writing the first line of code in that phase. Any feature not in the phase scope is deferred, not "quick to add."
- The TypeScript SDK lags Python by one release cycle (AD-18). Do not start TypeScript SDK until Python SDK is stable and tested.

---

## Sources

- [Langfuse v3 Infrastructure Evolution Post-Mortem](https://langfuse.com/blog/2024-12-langfuse-v3-infrastructure-evolution) — MEDIUM confidence (first-party post-mortem, highly relevant)
- [ClickHouse: The Good, The Bad, and The Ugly (DEV Community)](https://dev.to/lindesvard/clickhouse-the-good-the-bad-and-the-ugly-2pi7) — MEDIUM confidence (practitioner experience)
- [13 Common ClickHouse Getting Started Mistakes (Official ClickHouse Blog)](https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse) — HIGH confidence (official documentation)
- [ClickHouse Lessons Learned: Too Many Parts (Official Docs)](https://clickhouse.com/docs/tips-and-tricks/too-many-parts) — HIGH confidence (official documentation)
- [Six Months with ClickHouse at CloudQuery](https://www.cloudquery.io/blog/six-months-with-clickhouse-at-cloudquery) — MEDIUM confidence (practitioner post-mortem)
- [AI Agent Observability — Evolving Standards (OpenTelemetry Blog 2025)](https://opentelemetry.io/blog/2025/ai-agent-observability/) — HIGH confidence (official OTel blog)
- [OTel GenAI Semantic Conventions (Official Docs)](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — HIGH confidence (official documentation, verified experimental status)
- [Multi-Tenant Leakage: When Row-Level Security Fails (Medium 2026)](https://medium.com/@instatunnel/multi-tenant-leakage-when-row-level-security-fails-in-saas-da25f40c788c) — LOW confidence (single source, unverified)
- [Top 5 Sentence Transformer Embedding Mistakes (AITUDE)](https://www.aitude.com/top-5-sentence-transformer-embedding-mistakes-and-their-easy-fixes-for-better-nlp-results/) — MEDIUM confidence (aligns with sbert.net documentation patterns)
- [Semantic Textual Similarity — sentence-transformers docs (sbert.net)](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) — HIGH confidence (official library documentation)
- [Xeter arc42 Architecture Document](documentation/xeter-arc42.md) — Risks R-01 through R-08 used as primary input

---
*Pitfalls research for: AI agent observability / debugging platform (Xeter)*
*Researched: 2026-03-27*
