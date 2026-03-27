# Feature Research

**Domain:** AI agent observability and debugging platform (tool-call failure diagnosis)
**Researched:** 2026-03-27
**Confidence:** MEDIUM-HIGH (competitor product pages verified; some differentiator claims from aggregator articles cross-checked against official docs)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Span/trace ingestion via SDK | Every competitor offers an instrumentation SDK; without one there is no product | MEDIUM | Xeter uses Python SDK emitting OTel spans — already scoped |
| Span list view with filtering | Users need to find specific traces fast; a raw data dump is useless | MEDIUM | Filter by time, status, flag type, tenant; Langfuse and LangSmith both do this as baseline |
| Span detail view | Users must see the full context of a single execution: inputs, outputs, tool arguments, response | MEDIUM | Include prompt, tool_name, tool_args, raw_response, latency, model; Langfuse/LangSmith both show this |
| Tool call capture (name, args, result) | Tool calls are the primary unit of failure for agent workflows; any tool that misses them is useless for agent debugging | LOW | OTel GenAI semantic conventions standardize the schema; this is Xeter's core data |
| Token and latency metadata | Users expect to see how long things took and how many tokens were consumed per call | LOW | Standard OTel attributes; low effort to capture and store in ClickHouse |
| Error/exception capture | Users need to see when a tool returned an error or threw an exception; silent failures are invisible otherwise | LOW | HTTP errors, JSON parse failures, tool return errors — all must be captured |
| Multi-tenancy with API key auth | B2B SaaS users assume their data is isolated; any shared-tenant leak is a trust-destroying incident | HIGH | Row-level isolation via tenant_id; API key per tenant for SDK ingestion — already scoped |
| Dashboard login / auth | Users need a protected interface; unauthenticated dashboards are a non-starter for any real deployment | MEDIUM | Email/password first (Path A); already scoped |
| Retention and data persistence | Traces must persist long enough to be useful; ephemeral storage breaks debugging workflows | MEDIUM | ClickHouse for spans, PostgreSQL for flags — already scoped; retention policy TBD |
| OpenTelemetry compatibility | By 2026, OTel is the industry standard for instrumentation; tools that don't accept OTel spans require custom SDKs that developers won't adopt | MEDIUM | Xeter ingests OTel spans — already decided |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required for entry, but create switching costs and justify adoption over Langfuse.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Automated tool-call flag types (wrong_tool, no_tool, excessive_tool, parsing_error) | No competitor automatically categorizes *why* a tool call failed — they show the trace, you infer the cause; Xeter names the failure type explicitly | HIGH | Vector similarity between prompt and tool fields; requires embedding worker + ClickHouse flag storage — core Xeter differentiator |
| Root-cause attribution (model / architecture / prompt) | The market gap identified in positioning: every existing tool shows *that* something failed, none say *why*; developers spend hours manually correlating | HIGH | LLM-powered Diagnosticer service (Milestone 2); v1 scaffolds it; this is Xeter's stated core value |
| Heuristic flag scoring with confidence score | A flag without a confidence score forces the developer to decide if it's noise; a scored flag lets them triage instantly | MEDIUM | Cosine similarity score stored with each flag; threshold calibration is a correctness risk (R-03) |
| Flag detail view showing which field triggered the flag | Knowing *which* mismatch caused the flag (prompt vs tool_description vs response) is actionable; just saying "wrong tool" is not | MEDIUM | Requires storing flag.detail as a structured object — already scoped |
| Lazy-loaded large payload display | Prompt and response text can be hundreds of KB; loading it all at page load bloats the UI and slows the dashboard; lazy retrieval from S3 makes the span detail snappy | MEDIUM | S3 reference keys in ClickHouse; retrieve on demand — already scoped |
| Single-framework-agnostic SDK (works with any agent) | Langfuse and Phoenix are framework-agnostic but don't diagnose; LangSmith diagnoses but only for LangChain; Xeter diagnoses for any stack | MEDIUM | OTel-native SDK; minimal instrumentation surface — already scoped |
| Append-only immutable span storage | Defenders of data integrity: once a span is written, it can never be edited or deleted, making audit trails trustworthy | LOW | ClickHouse append-only model — already scoped; a trust signal worth communicating |
| Session/conversation grouping | Multi-turn agent workflows need trace grouping to see a full session, not just isolated spans | MEDIUM | Langfuse does this well; Xeter should support trace_id / session_id correlation — not yet scoped |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a solo developer or for the product's focus.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| LLM-as-a-judge evaluation (v1) | Developers want automated quality scores; competitors offer it | Requires significant infrastructure (eval dataset, judge model, scoring pipeline); adds scope before core diagnosis is validated; risks becoming a worse version of Langfuse's eval suite | Defer to v2; v1 heuristic flags are the differentiator; LLM Diagnosticer (Milestone 2) delivers this more surgically |
| Real-time SSE push for flag updates | Feels more "live" and reactive | Adds persistent connection management, reconnection logic, and server complexity; polling or manual refresh is adequate for debugging workflows which are not time-critical at sub-second granularity | Polling or manual refresh for v1; SSE deferred per PROJECT.md |
| Trace tree visualization (full agent graph) | Arize Phoenix's agent graph is compelling; LangSmith's hierarchical trace tree is the industry reference | Building a robust tree renderer for arbitrary nested spans is a significant frontend effort; v1 can deliver value with a flat span list + flags; premature tree view competes with Phoenix on their strength | Ship flat span list + flag indicators first; add trace tree in v1.x after validating the flag diagnosis loop |
| Prompt playground | Developers want to iterate prompts without leaving the tool | Requires prompt version management, diff views, execution against a live model, and response comparison — scope of a separate product category; Langfuse and LangSmith do this well; duplicating it without their scale is a trap | Link out to the user's existing prompt tooling; don't build it |
| Built-in LLM cost attribution | Teams want per-user or per-feature cost breakdowns | Requires per-model pricing tables that go stale, token count attribution logic, and billing integrations; high maintenance burden; Helicone and dedicated cost tools do this better | Capture token counts in span metadata so users can build cost queries; don't own the cost analytics layer |
| Alerting and notification system (v1) | Users will immediately ask for Slack/PagerDuty alerts when flag rates spike | Requires threshold configuration UI, alert rule storage, notification delivery infrastructure (email/Slack webhooks), and false-positive management — significant scope; Langfuse doesn't have this yet and users are requesting it | Defer; v1 is for debugging not monitoring; design flag schema so alerting can be layered on top later |
| TypeScript SDK | Many web developers and Next.js users want TS support | Python SDK must be stable and battle-tested first; TS SDK doubles SDK maintenance burden; splitting focus before Python SDK is proven is a risk | Python SDK first; TS SDK as v1.1 per AD-18 |
| Multi-model comparison / A-B testing | Sophisticated users want to compare GPT-4o vs Claude on same inputs | Requires experiment management, dataset storage, side-by-side diff UI — a separate product surface; Braintrust and LangSmith own this | Out of scope; stay focused on diagnosis of individual failures |

---

## Feature Dependencies

```
[OTel Span Ingestion (SDK)]
    └──requires──> [API Key Auth + Multi-tenancy]
    └──requires──> [ClickHouse span storage]
                       └──requires──> [S3 large payload storage]
                       └──requires──> [Redis ingestion queue]

[Span List View]
    └──requires──> [OTel Span Ingestion]
    └──requires──> [Dashboard Auth (login)]

[Span Detail View]
    └──requires──> [Span List View]
    └──requires──> [S3 lazy payload retrieval]

[Heuristic Flag Types (wrong_tool, no_tool, etc.)]
    └──requires──> [OTel Span Ingestion]
    └──requires──> [Embedding worker + vector similarity]
    └──requires──> [PostgreSQL flag storage]

[Flag Detail in Span View]
    └──requires──> [Heuristic Flag Types]
    └──requires──> [Span Detail View]

[Root Cause Attribution (model/arch/prompt)]
    └──requires──> [Heuristic Flag Types]
    └──requires──> [LLM Diagnosticer service (Milestone 2)]

[Alerting]
    └──requires──> [Heuristic Flag Types]
    └──requires──> [Flag rate aggregation (not yet designed)]

[Trace Tree Visualization]
    └──requires──> [Span Ingestion with parent_span_id]
    └──requires──> [Frontend tree renderer (significant effort)]
    └──enhances──> [Span List View]

[Session/Conversation Grouping]
    └──requires──> [session_id on spans]
    └──enhances──> [Span List View]
```

### Dependency Notes

- **Heuristic flag types require embedding worker:** Flags are computed asynchronously from ingestion; the Redis queue decouples these so ingestion latency stays low (AD-01).
- **Root cause attribution requires Diagnosticer (Milestone 2):** The LLM-powered explanation of *why* a flag happened is the highest-value differentiator but depends on stable flag data from Milestone 1.
- **Alerting requires flag rate aggregation:** Flag-rate alerts need time-windowed aggregation queries over ClickHouse; this is a non-trivial query design problem best deferred until flag quality is validated.
- **Trace tree conflicts with v1 scope:** The parent_span_id field should be captured in v1 spans so tree view can be added later without schema migration — but the renderer itself is deferred.
- **Session grouping is not in v1 scope but session_id should be captured:** Same as trace tree — capture the field, render later.

---

## MVP Definition

### Launch With (v1 — Milestone 1)

Minimum viable product — what's needed to validate the core hypothesis that heuristic flagging delivers diagnostic value.

- [ ] Python SDK that instruments agent code and emits OTel spans — without this there is no product
- [ ] Span ingestion API with API key auth and multi-tenancy — required for any real usage
- [ ] ClickHouse span storage + S3 large payload storage — required for span list and detail views
- [ ] Redis queue + async embedding worker — required for flag computation without blocking ingestion
- [ ] Heuristic flag types: wrong_tool, no_tool, excessive_tool, parsing_error with cosine similarity scores — the core differentiator
- [ ] PostgreSQL flag storage (append-only, with score and detail fields) — required for flag rendering
- [ ] Span list view with flag indicators and filtering — required for users to find failures
- [ ] Span detail view with flag details and lazy-loaded S3 payloads — required to understand a failure
- [ ] Dashboard login (email/password) — required for any real deployment
- [ ] Diagnosticer service scaffolded (wired but not functional) — required so Milestone 2 doesn't require rearchitecting

### Add After Validation (v1.x)

Features to add once the core flag-diagnosis loop is working and trusted.

- [ ] Session/conversation grouping — add when users report difficulty tracking multi-turn agent workflows
- [ ] Trace tree visualization — add when span list + flags is validated and users ask for deeper visual navigation
- [ ] TypeScript SDK — add when Python SDK is stable and TS demand is confirmed (AD-18)
- [ ] Alerting / Slack notifications — add when users move from debugging to monitoring (flag rate stabilizes)
- [ ] Flag threshold calibration UI — add when false positive rate becomes a reported pain point

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] LLM-powered Diagnosticer active (Milestone 2) — the model/arch/prompt attribution layer; highest strategic value but depends on stable Milestone 1 data
- [ ] Prompt management and versioning — defer; Langfuse does this; don't compete until diagnosis is proven
- [ ] LLM-as-a-judge evaluation pipeline — defer; requires dataset infrastructure; not the diagnosis differentiator
- [ ] LLM cost attribution and reporting — defer; high maintenance; not Xeter's moat
- [ ] Multi-model A-B experiment comparison — defer; separate product surface

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Python SDK (OTel spans) | HIGH | MEDIUM | P1 |
| API key auth + multi-tenancy | HIGH | MEDIUM | P1 |
| Span ingestion + ClickHouse storage | HIGH | MEDIUM | P1 |
| Heuristic flag types (wrong_tool, etc.) | HIGH | HIGH | P1 |
| Span list view + flag indicators | HIGH | MEDIUM | P1 |
| Span detail view + S3 lazy load | HIGH | MEDIUM | P1 |
| Dashboard login | HIGH | LOW | P1 |
| Flag detail (which field triggered) | HIGH | LOW | P1 |
| Token + latency metadata capture | MEDIUM | LOW | P1 |
| Redis queue + async embedding worker | HIGH | MEDIUM | P1 |
| Diagnosticer scaffold (wired, inactive) | MEDIUM | LOW | P1 |
| Session/conversation grouping | MEDIUM | MEDIUM | P2 |
| Trace tree visualization | MEDIUM | HIGH | P2 |
| TypeScript SDK | MEDIUM | MEDIUM | P2 |
| Alerting / notifications | MEDIUM | HIGH | P2 |
| Flag threshold calibration UI | MEDIUM | MEDIUM | P2 |
| LLM Diagnosticer active (root cause) | HIGH | HIGH | P2 |
| Prompt playground | LOW | HIGH | P3 |
| LLM cost attribution | LOW | MEDIUM | P3 |
| LLM-as-a-judge eval pipeline | LOW | HIGH | P3 |
| Multi-model A-B experiment comparison | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v1 launch
- P2: Should have, add in v1.x or Milestone 2
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | Langfuse | LangSmith | Arize Phoenix | HoneyHive | Xeter (our approach) |
|---------|----------|-----------|---------------|-----------|---------------------|
| Span/trace ingestion | Yes (OTel + own SDK) | Yes (own SDK, 13+ frameworks) | Yes (OTel) | Yes (OTel) | Yes (OTel via Python SDK) |
| Tool call capture | Yes (named observation type) | Yes (automatic per run) | Yes (span attributes) | Yes (tool step monitoring) | Yes (OTel semantic conventions) |
| Span list view | Yes | Yes | Yes | Yes | Yes (v1) |
| Span detail view | Yes | Yes | Yes | Yes | Yes (v1) |
| Trace tree / agent graph | Partial (nested observations) | Yes (hierarchical runs) | Yes (Agent Graph viz) | Yes | Deferred to v1.x |
| Session grouping | Yes | Yes (threads) | Yes | Yes | Deferred to v1.x |
| Token + cost tracking | Yes | Yes | Yes | Yes | Token metadata only (no cost) |
| Automated flag types for tool failures | No | No | No | Partial (Tool Use Accuracy evaluator, not automatic) | Yes — core differentiator |
| Root cause attribution (model/arch/prompt) | No | No | No | No | Milestone 2 (LLM Diagnosticer) |
| Heuristic similarity score per flag | No | No | No | No | Yes (cosine similarity, confidence score) |
| LLM-as-a-judge evaluation | Yes | Yes | Yes | Yes | Deferred to v2 |
| Prompt management | Yes | Yes | No (basic) | No | Not planned |
| Alerting | Roadmap only (as of March 2026) | Yes | Partial | No native | Deferred to v1.x |
| Multi-tenancy | Yes (self-hosted; cloud plans) | Yes (cloud; BYOC at enterprise) | Yes (cloud plans) | Yes (enterprise) | Yes (row-level isolation, v1) |
| Open-source / self-hostable | Yes (fully open-source) | Enterprise only | Yes (fully open-source) | Enterprise only | SaaS only (v1) |
| Framework-agnostic | Yes | LangChain-native (others via SDK) | Yes | Yes | Yes |

---

## Sources

- Langfuse official docs: https://langfuse.com/docs/observability/overview (HIGH confidence — official documentation)
- Langfuse observation types: https://langfuse.com/docs/observability/features/observation-types (HIGH confidence — official documentation)
- Langfuse roadmap (alerting status): https://github.com/orgs/langfuse/discussions/3997 and https://github.com/orgs/langfuse/discussions/10147 (MEDIUM confidence — GitHub discussions, reflects current product state)
- LangSmith agent observability: https://www.langchain.com/langsmith/observability (MEDIUM confidence — official marketing page)
- LangSmith agent debugging blog: https://blog.langchain.com/debugging-deep-agents-with-langsmith/ (MEDIUM confidence — official blog)
- Arize Phoenix GitHub: https://github.com/Arize-ai/phoenix (HIGH confidence — official source)
- Arize blog on common agent failures: https://arize.com/blog/common-ai-agent-failures/ (MEDIUM confidence — vendor blog, field analysis)
- HoneyHive observability: https://www.honeyhive.ai/observability (MEDIUM confidence — official product page)
- HoneyHive evaluators: https://docs.honeyhive.ai/evaluators/introduction (MEDIUM confidence — official docs)
- Braintrust buyer's guide 2026: https://www.braintrust.dev/articles/best-ai-observability-tools-2026 (MEDIUM confidence — vendor-authored but cross-referenced)
- Galileo root cause analysis tools: https://galileo.ai/blog/best-ai-agent-debugging-root-cause-analysis-tools (MEDIUM confidence — vendor blog, cross-referenced)
- Maxim AI top 5 platforms 2026: https://www.getmaxim.ai/articles/top-5-ai-agent-observability-platforms-in-2026/ (LOW confidence — vendor aggregator)
- OTel AI agent observability standards: https://opentelemetry.io/blog/2025/ai-agent-observability/ (HIGH confidence — official OTel blog)

---
*Feature research for: AI agent observability / tool-call debugging platform (Xeter)*
*Researched: 2026-03-27*
