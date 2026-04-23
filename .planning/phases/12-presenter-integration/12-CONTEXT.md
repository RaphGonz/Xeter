# Phase 12: Presenter Integration - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the Presenter service to the Diagnosticer — expose `POST /diagnose` (trigger) and `GET /diagnose/{span_id}` (retrieve) to the frontend, via synchronous HTTP inter-service communication. Storing results and reading them back is handled by the Presenter itself using the shared PostgreSQL `diagnoses` table written by the Diagnosticer in Phase 11.

</domain>

<decisions>
## Implementation Decisions

### Response timing
- Synchronous: Presenter waits for the full diagnosis result before responding to the frontend
- Timeout is configurable via `DIAGNOSTICER_TIMEOUT_SECONDS` env var (should have a sensible default, e.g. 60s)
- Exceeding the timeout → Presenter returns 504 Gateway Timeout
- Diagnosticer URL configured via `DIAGNOSTICER_URL` env var (consistent with Docker Compose service wiring)
- Endpoint path stays as `/diagnose` — keep the existing scaffold path, no versioning or nesting

### Result retrieval pattern
- Presenter reads the `diagnoses` PostgreSQL table directly for GET requests — same DB access pattern used for flags and spans
- No proxy to Diagnosticer for reads; Diagnosticer is only involved in writes (POST /diagnose trigger)
- `GET /diagnose/{span_id}` returns **404** if no diagnosis exists (clean absence signal; frontend uses 404 to know it should trigger diagnosis first)
- Response body contains diagnosis fields only: verdict, severity, affected_field, recommended_fix, diagnosed_at
- Single-span lookup only — no list endpoint in this phase

### Idempotency behavior
- Before forwarding to Diagnosticer, Presenter checks the `diagnoses` table for an existing result
- If diagnosis exists → return it immediately without calling Diagnosticer (no re-diagnosis)
- No force-refresh mechanism in Phase 12 (can be added later if needed)
- Idempotency check lives in a service layer (`DiagnosisService.trigger(span_id)` or equivalent) — keeps the router thin, consistent with existing Presenter patterns

### Error contract
- Diagnosticer unreachable (connection refused, DNS failure) → **503 Service Unavailable**
- Diagnosticer timeout (exceeds `DIAGNOSTICER_TIMEOUT_SECONDS`) → **504 Gateway Timeout**
- Diagnosticer returns an error (LLM failure, provider error) → Wrap with `{error: "diagnosis_failed", detail: "<sanitized message>"}` — do not leak raw provider error strings to the browser
- Tenant guard: Presenter verifies the `span_id` belongs to the authenticated tenant **before** forwarding to Diagnosticer — consistent with how all span-related reads are guarded; Diagnosticer has no session context to enforce this itself

### Claude's Discretion
- HTTP client library choice for inter-service call (httpx is already used in the codebase)
- Exact default value for `DIAGNOSTICER_TIMEOUT_SECONDS`
- Internal module structure for the service layer (where to place `DiagnosisService`)
- How to sanitize Diagnosticer error messages before surfacing them in the structured error response

</decisions>

<specifics>
## Specific Ideas

No specific references — open to standard approaches consistent with existing Presenter patterns.

</specifics>

<deferred>
## Deferred Ideas

- Force-refresh / re-diagnose button — Phase 13 UI option if needed; Phase 12 just returns cached results
- List endpoint for diagnoses (GET /diagnoses with filters) — future phase if a "diagnosed spans" view is added

</deferred>

---

*Phase: 12-presenter-integration*
*Context gathered: 2026-04-23*
