# Phase 5: Dashboard - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Developer-facing dashboard where a user can log in with email/password, view a list of spans with flag indicators and similarity scores, filter spans by flag type / agent name / time range, drill into a span to see full details and S3 payloads, and trigger a diagnostic request. No business logic in the frontend — the dashboard is a thin client over the Presenter API.

</domain>

<decisions>
## Implementation Decisions

### Span list layout
- Dense table with columns: Status + Flag type, Agent name + Span ID, Similarity score, Relative timestamp
- Status shown as color dot + text label: red "Flagged" (with flag type), green "Clean", grey "Pending" (awaiting analysis)
- Cursor-based pagination with "Load more" button at the bottom — matches the API's cursor pagination

### Filtering experience
- Top bar above the table: horizontal row of filter dropdowns for flag type, agent name, and time range
- Filters apply instantly on change — no "Apply" button
- Time range presets only: Last 15m, 1h, 6h, 24h, 7d, 30d (no custom date picker)
- Filter state reflected in URL query params for shareability and bookmarkability
- URL params must be validated server-side — no data leakage through URL manipulation (tenant scoping already enforced by API)

### Detail view navigation
- Side panel slides in from the right when a span row is clicked; span list stays visible but narrowed
- Flag section at top of panel: flag type, similarity score, threshold, triggered fields, and "Request Diagnostic" button inside the flag section
- Below flag section: tabbed S3 payloads (Prompt | Response | Raw Response) — each tab loads content on demand when clicked
- Detail panel shows the COMPLETE span data — not just flag + payloads, but every field: model name, all arguments, tool calls, tokens, latency, everything stored in ClickHouse/PostgreSQL

### Login page
- Minimal centered form: Xeter branding, email field, password field, login button
- Login errors shown as inline red text below the form ("Invalid email or password")
- Email + password only for this phase

### Navigation & empty states
- Simple top navigation bar: Xeter logo/name on left, Docs link and user account dropdown (with logout) on right
- Empty span table shown as-is when no spans exist — no special onboarding illustration
- Documentation link lives in the top nav bar

### Claude's Discretion
- Loading skeleton/spinner design
- Exact spacing, typography, and color palette
- Error state handling for API failures
- Side panel width and responsive behavior
- Table sorting behavior (if any)

</decisions>

<specifics>
## Specific Ideas

- Detail panel should feel like Sentry/Datadog span inspection — dense, information-rich, developer-oriented
- The span table should prioritize scannability — developers need to quickly spot flagged spans
- "Request Diagnostic" button greyed out for clean/pending spans
- Diagnostic response (currently 501 placeholder) displayed inline after clicking the button

</specifics>

<deferred>
## Deferred Ideas

- SSO / OAuth authentication methods — future phase (login form design doesn't block adding these later)
- Custom date-time range picker for filters — can be added if preset ranges prove insufficient

</deferred>

---

*Phase: 05-dashboard*
*Context gathered: 2026-03-30*
