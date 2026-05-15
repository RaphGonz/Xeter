# Phase 20: Trace API - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Add two read-only REST endpoints to the Presenter:
- `GET /traces` — paginated list of traces for the authenticated tenant
- `GET /traces/{trace_id}` — full trace detail with all spans, flags, and scores

Both endpoints enforce tenant RLS. Data is assembled from ClickHouse (spans) and PostgreSQL (flags, scores). No write operations, no filtering UI, no trace creation — that is out of scope for this phase.

</domain>

<decisions>
## Implementation Decisions

### List endpoint — response shape
- Wrapped envelope: `{traces: [...], total: N, limit: N, offset: N}`
- Each trace item: `trace_id`, `span_count`, `flag_count`, `start_time`, `duration`
  - `start_time`: min span start_time across the trace
  - `duration`: max span end_time minus min span start_time
- No `score_count` in the list — flag_count only
- Sort order: most recent first (`DESC` by `start_time`)

### List endpoint — pagination
- Limit + offset: `?limit=50&offset=0`
- Default limit: 50, max limit: 100 (reject or clamp above 100)
- No filtering parameters this phase (no time range, no flag presence filter)

### Detail endpoint — response shape
- Top-level `trace` object: `{trace_id, start_time, duration, flags: [...]}` — trace-level flags (span_id = NULL) live here
- `spans` key: flat array of span objects, sorted by `start_time` ASC, `parent_span_id` preserved for the UI to build the tree
- Each span: `span_id`, `parent_span_id`, `tool_name`, `model`, `start_time`, `end_time`, `input_tokens`, `output_tokens`, `flags: [...]`, `scores: [...]`
- Flags and scores embedded inline on each span object

### Error & edge cases
- Cross-tenant access: **404 Not Found** (stealth — do not reveal trace existence)
- Error payload: match existing Presenter error format (whatever `detail`/`error` shape is in use)
- Trace exists in PostgreSQL but no spans in ClickHouse yet: `200 {"trace": {...}, "spans": []}` — not an error, spans may be in flight
- Tenant has zero traces: `200 {"traces": [], "total": 0, "limit": 50, "offset": 0}`

### Claude's Discretion
- Exact SQL/ClickHouse queries for assembling spans and joining flags/scores
- Whether `duration` is stored or computed on read
- How `start_time` at the trace level is derived (query-time aggregation vs stored)
- Index strategy for the ClickHouse span query

</decisions>

<specifics>
## Specific Ideas

- Trace-level flags (span_id = NULL, introduced in Phase 19) must be surfaced — they live on the top-level `trace` object in the detail response, not on any span
- Detail response deliberately leaves tree assembly to the frontend (Phase 21) — the API returns a flat array with `parent_span_id` intact

</specifics>

<deferred>
## Deferred Ideas

- Time range filtering (`?from=&to=`) — useful but deferred until usage patterns emerge post-Phase 21
- Flag presence filter (`?has_flags=true`) — same rationale
- Cursor-based pagination — add when offset pagination shows performance limits

</deferred>

---

*Phase: 20-trace-api*
*Context gathered: 2026-05-15*
