# Phase 4: Read Path - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

The Presenter API serves span lists with flag indicators, span detail with lazy S3 payload loading, and proxies to a scaffolded Diagnosticer that returns a 501 placeholder. All queries are scoped by tenant. No dashboard UI in this phase — API only.

</domain>

<decisions>
## Implementation Decisions

### Span list response shape
- Cursor-based pagination (opaque token for next/prev)
- Default sort order: newest first
- Inline flag summary per span: `[{type, score}]` — dashboard renders badges without a second call
- Fields per span: span_id, agent_name, model, timestamp, status, duration_ms, plus flags array

### Lazy S3 loading behavior
- GET /spans/{id} always fetches S3 payloads (prompt, response, raw_response) — no opt-in query param
- Content returned inline in JSON response, not pre-signed URLs
- Block until S3 fetch completes, with a 5-second timeout
- On timeout or S3 failure, return a full error response (not partial data)

### Diagnosticer scaffold
- Separate service from day one: own Dockerfile, own container, own docker-compose entry
- Presenter proxies POST /diagnose to the Diagnosticer service
- Request body: `{span_id, flags: [...]}`
- Diagnosticer fetches its own data from ClickHouse/S3/PostgreSQL (needs DB access wired up)
- 501 response body: `{status: "not_implemented", message: "Diagnosticer not yet available", span_id: "..."}`
- DB/S3 connections wired in docker-compose even though the scaffold only returns 501 — ready for v2 LLM integration

### Error & auth responses
- Simple JSON error format: `{error: "not_found", message: "Span not found", status: 404}`
- Cross-tenant access returns 404 (not 403) — no information leakage about other tenants' spans
- Generic 401 for all auth failures: `{error: "unauthorized", message: "Invalid or missing session token"}` — no distinction between expired, malformed, or missing
- No rate limiting in this phase — defer to Phase 6 (Validation) if needed

### Claude's Discretion
- Exact cursor encoding strategy
- Internal routing/proxy mechanism between Presenter and Diagnosticer
- ClickHouse query optimization for span list
- S3 client configuration and retry strategy within the 5s timeout

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-read-path*
*Context gathered: 2026-03-30*
