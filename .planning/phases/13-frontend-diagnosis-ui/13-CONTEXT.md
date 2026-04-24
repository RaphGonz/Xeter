# Phase 13: Frontend Diagnosis UI - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the scaffold "Request Diagnostic" button result (plain `status: message` string) in `SpanDetailPanel.tsx` with a real structured diagnosis display — verdict, severity, affected field, and recommended fix. The button and `FlagSection` component already exist; the work is updating API types, fetch logic (GET on open + POST on click), and the result rendering inside `FlagSection`.

</domain>

<decisions>
## Implementation Decisions

### Persisted result behavior
- Auto-load on open: when the panel opens for a flagged span, fire `GET /diagnose/{span_id}`; if a diagnosis exists, show it immediately without requiring a click
- Re-run on button click: clicking "Diagnose" always POSTs to `/diagnose`, overwrites the stored result, updates the display — no confirmation step
- Button stays visible above the result card at all times (even after a result loads)

### Verdict/severity visual treatment
- Verdict (model / architecture / prompt): colored badge — visually prominent, scannable at a glance, consistent with the existing flag badge pattern
- Severity: colored badge on the same row as the verdict badge (e.g., `[model] [critical]`)
- Affected field + recommended fix: MetaRow-style rows below the badge row — label + value, consistent with the span metadata section

### Loading and error states
- Loading state: skeleton placeholder where the result card will appear, with a small note "Analyzing… (this may take a few seconds)" — sets expectations for the 5–15s LLM latency
- Error state: inline red error box below the Diagnose button (same position as diagError in current scaffold); button stays enabled so the user can retry without re-opening the panel

### Diagnosis display layout
- Result lives inside `FlagSection`, below the flags list — keeps diagnosis visually linked to the flags that triggered it
- Diagnose button sits below the flags list, just above where the result card appears: see flags → click Diagnose → see result
- Result renders as a nested card inside the FlagSection red border card

### Claude's Discretion
- Exact badge color mapping (verdict → color, severity → color) — use red/orange/yellow/zinc as appropriate to signal severity
- Whether to add a subtle timestamp ("Diagnosed 2 minutes ago") on the result card
- Exact skeleton height/shape

</decisions>

<specifics>
## Specific Ideas

- Layout mockup selected by user:
  ```
  ┌─ Flags ─────────────────────────────────────┐
  │  [wrong_tool_called] score: 0.8712          │
  │  { detail... }                              │
  │                                             │
  │  [Diagnose]                                 │
  │  ┌─ Diagnosis ──────────────────────────┐   │
  │  │ [model] [critical]                   │   │
  │  │ Affected: tool_name                  │   │
  │  │ Fix: Switch to a model...            │   │
  │  └──────────────────────────────────────┘   │
  └─────────────────────────────────────────────┘
  ```

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-frontend-diagnosis-ui*
*Context gathered: 2026-04-24*
