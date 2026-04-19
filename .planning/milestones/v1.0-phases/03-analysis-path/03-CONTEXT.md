# Phase 3: Analysis Path - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

The Embedding Worker processes queued span IDs, computes cosine similarities, classifies tool-call anomalies into flag types, and writes flags to PostgreSQL with similarity scores logged for every span. This phase builds ONE concrete analyzer (ToolCallAnalyzer) plus the shared infrastructure (worker loop, base class, registry) that makes adding future analyzers trivial.

Creating analyzers for other failure categories (B–H from the silent failures taxonomy) is explicitly out of scope — the extensibility pattern is built here, the other analyzers are not.

</domain>

<decisions>
## Implementation Decisions

### Extensibility — core design principle
- This is a prototype / reference implementation, not a final product
- The goal is one working analyzer built on a pattern that is obviously copyable and extensible
- `BaseAnalyzer` is the template: provides `embed()`, `compare()`, `log_score()` helpers; subclasses override `analyze(span) → list[Flag]`
- To add a new analyzer later (e.g. OutputAnalyzer for B-category failures): copy ToolCallAnalyzer, rename it, override `analyze()` — nothing else changes
- ANALYZERS list in `worker/main.py` is the registry: `ANALYZERS = [ToolCallAnalyzer(config)]` — to add a new one, import it and append

### ToolCallAnalyzer structure
- One class, multiple private methods: `_check_wrong_tool()`, `_check_no_tool()`, `_check_excessive_tool()`, `_check_parsing_error()`, `_check_wrong_args()` — all called from `analyze()`
- To add a new check within the tool-call domain: add a private method and call it from `analyze()`
- Score logging is explicit and visible inside the analyzer via `self.log_score(metric, value)` — not hidden in the pipeline

### Embedding provider
- sentence-transformers, local (no API key, no network call, works offline)
- Model: `all-MiniLM-L6-v2` (384-dim, ~80MB, fast)
- Model loaded once at worker startup and kept in memory
- Base class exposes `embed(text)` and `compare(a, b)` — subclasses call these helpers directly
- Tool embeddings (from `available_tools` fetched via S3) cached in-memory keyed by content hash to avoid re-embedding identical tool lists across spans

### Score storage
- `span_scores` table in PostgreSQL — one row per metric: `(span_id, analyzer_name, metric_name, score)`
- Scores persisted for every span (flagged or not) to enable threshold calibration in Phase 6
- Flags table in PostgreSQL for flagged spans only — existing schema from Phase 1
- Both tables linked to spans by `span_id` UUID

### Worker architecture
- Separate Docker service — own container in docker-compose, independent lifecycle from the Analyser
- Consumes span IDs from Redis via BLPOP loop (blocking pop with timeout, immediate reaction to new spans)
- On span processing failure: log error with span_id and reason, skip span, continue loop — no retry, no dead-letter queue

### Claude's Discretion
- Exact Flag dataclass/namedtuple structure returned by `analyze()`
- BLPOP timeout value
- Exact column names and indexes on `span_scores` table
- How worker startup/shutdown is handled (signal handling, graceful drain)

</decisions>

<specifics>
## Specific Ideas

- User explicitly wants the base class and ToolCallAnalyzer to serve as a readable, copyable template — code clarity and obviousness matter more than abstraction elegance
- The silent failures taxonomy (documentation/silent_failures_ai_agents.md) defines the failure types: Phase 3 covers A1–A7 (Tool Use Failures); B–H are deferred to future analyzers
- FLAG-10 rationale: scores logged for every span (not just flagged) to support threshold calibration in Phase 6 — user confirmed this after understanding the reason

</specifics>

<deferred>
## Deferred Ideas

- OutputAnalyzer (B1–B4: schema, missing fields, truncation, type coercion) — future phase
- ReasoningAnalyzer (C1–C5: derailment, premature termination, step repetition) — future phase
- ContextAnalyzer (D1–D5), InstructionAnalyzer (E1–E3), MultiAgentAnalyzer (F1–F6), VerificationAnalyzer (G1–G3), OutputContentAnalyzer (H1–H3) — future phases

</deferred>

---

*Phase: 03-analysis-path*
*Context gathered: 2026-03-28*
