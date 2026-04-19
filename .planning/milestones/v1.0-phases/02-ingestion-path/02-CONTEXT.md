# Phase 2: Ingestion Path - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Full pipeline from SDK instrumentation through to storage and queuing: a developer installs `xeter-sdk`, decorates their agent function, and spans flow to the Analyser → S3 (large payload fields) + ClickHouse (batched metadata) + Redis (span ID for async analysis). Auth (API key validation), batching behavior, and SDK ergonomics are all in scope. Dashboard, analysis/flagging, and read path are separate phases.

</domain>

<decisions>
## Implementation Decisions

### SDK API style
- Decorator-based: `@xeter.trace(tool_name="...", prompt_arg="prompt", tools_arg="tools")`
- Developer maps their function's argument names to span fields via decorator params — explicit, no magic
- Works on both `def` and `async def` (SDK auto-detects coroutines)

### SDK configuration
- Configuration via environment variables only: `XETER_ENDPOINT` and `XETER_API_KEY`
- No `xeter.init()` call required — zero-setup beyond setting env vars

### Span sending behavior
- Spans are sent in a background thread (fire-and-forget) — the decorated function returns immediately with no added latency
- On failure (unreachable Analyser, network error): drop the span silently, log a WARNING via the Python `logging` module
- No retry — one attempt, then drop and log
- Agent application is never interrupted or slowed by SDK failures

### S3 payload offload
- These four fields **always** go to S3, unconditionally: `prompt`, `response`, `raw_response`, `available_tools`
- The **Analyser** writes to S3 after receiving the full span — SDK stays thin (no AWS credentials on the client)
- S3 key structure: `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`
  - e.g. `tenant_abc/2026-03/span_uuid/prompt.json`
  - Date-based partitioning enables lifecycle policies and bulk tenant data cleanup
- If S3 write fails: reject the span entirely (5xx to SDK). ClickHouse never gets a span without its S3 payloads — no partial state.

### ClickHouse batching
- Flush trigger: **size OR time**, whichever comes first
- Buffer lives in-memory (in-process queue inside the Analyser) — Redis is reserved for the analysis queue only
- Defaults and env var overrides:
  - `XETER_BATCH_SIZE` (default: 100 spans)
  - `XETER_FLUSH_INTERVAL` (default: 5 seconds)
- Spans lost in an in-flight batch on crash are acceptable — observability data, not transactional

### Redis enqueue
- After a span is written to ClickHouse batch (accepted), its `span_id` is pushed to a Redis queue for the Embedding Worker (Phase 3)
- Enqueue happens after the span is accepted, within the 200ms SLA from the ROADMAP success criteria

### Claude's Discretion
- Exact batch flush implementation (asyncio task, threading, etc.)
- ClickHouse client library choice
- S3 client library choice
- Internal SDK thread pool sizing
- Exact WARNING log message format

</decisions>

<specifics>
## Specific Ideas

- The "3-line snippet" goal from the ROADMAP success criteria should be achievable: set 2 env vars + add 1 decorator
- S3 date partitioning chosen specifically to enable lifecycle/cleanup policies, not just for organization

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-ingestion-path*
*Context gathered: 2026-03-28*
