# Phase 21: Trace UI - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Add two new pages to the existing dashboard:
- **Traces list page** — shows all traces for the authenticated tenant in a table; clicking a row navigates to the trace detail page
- **Trace detail page** — renders all spans in a collapsible parent/child tree using `parent_span_id`; flag badges on each span; clicking a span navigates to the existing span detail page

Modify the **span detail page** to add a breadcrumb back-link to the parent trace.

No new data fetching architecture — both pages consume the Phase 20 `GET /traces` and `GET /traces/{trace_id}` endpoints. No new flag display logic beyond what already exists on span detail.

</domain>

<decisions>
## Implementation Decisions

### Traces list page — layout
- Table with sortable columns, matching the existing span list style on the dashboard
- Columns: trace_id (truncated), span count, flag count, start time, duration
- `trace_id` column: truncated to first 8 characters with full ID shown on hover (tooltip)
- Click anywhere on the row navigates to the trace detail page
- Empty state: informational text message — "No traces recorded yet" with a brief explanation of what will appear here (not just an empty table)

### Collapsible span tree — behavior
- Default state: all spans expanded on page load
- Visual hierarchy: indentation per depth level + a toggle arrow/chevron on parent spans that rotates on collapse
- Clicking a span row navigates to the existing span detail page (not inline expansion)
- Each span row shows: `tool_name`, duration (computed as `end_time − start_time`), and flag count badge

### Flag badges on spans
- Compact count pill: e.g. "3 flags" — shown inline on each span row after the duration
- Single neutral style — no color variation based on count (no severity semantics)
- Zero-flag spans: show nothing — absence of badge signals zero flags

### Navigation & back-link (span detail)
- Breadcrumb added to the top of the span detail page, above the span title: `Traces › {trace_id[:8]} › {span_id[:8]}`
- Always shown when the span has a `trace_id` — no history-based conditional rendering
- Clicking the `trace_id` segment navigates to `/traces/{trace_id}` (the trace detail page)
- `trace_id` in breadcrumb truncated to first 8 chars, consistent with the list page

### Claude's Discretion
- Exact column widths and responsive breakpoints
- Chevron icon choice and animation style
- Exact typography, spacing, and padding within the tree rows
- Table sorting implementation (client-side vs server-side — server-side not needed given limit=50 default)
- How trace detail page URL is structured (e.g. `/traces/{trace_id}`)

</decisions>

<specifics>
## Specific Ideas

- The span tree should feel like a file explorer tree (VS Code sidebar style) — indentation + chevrons, not lines
- Truncated IDs with tooltip matches the existing span list pattern — use the same component if one exists
- "3 flags" pill should feel like the existing flag count chips elsewhere in the dashboard — match that style

</specifics>

<deferred>
## Deferred Ideas

- Sorting on the traces list by column (user mentioned nothing about this — deferring unless it falls under Claude's Discretion for the table implementation)
- Filtering traces by time range or flag presence — noted in Phase 20 context as deferred
- Inline span detail panel on the trace page (expand-in-place) — not this phase, navigation-based
- Cursor-based pagination for the traces list — deferred from Phase 20

</deferred>

---

*Phase: 21-trace-ui*
*Context gathered: 2026-05-15*
