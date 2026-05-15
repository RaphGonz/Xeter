---
phase: 21-trace-ui
verified: 2026-05-15T12:50:00Z
status: gaps_found
score: 7/8 must-haves verified
gaps:
  - truth: "From any span detail view, the user can navigate back to the parent trace detail page with the span highlighted or scrolled into view"
    status: partial
    reason: "Breadcrumb navigates to /traces/{trace_id} but no span highlight or scroll-to is implemented. REQUIREMENTS.md UI-03 specifies 'with the span highlighted or scrolled into view'. The plan scoped this down to plain navigation without documenting the deviation from the requirement."
    artifacts:
      - path: "services/view/src/app/traces/[trace_id]/page.tsx"
        issue: "Does not accept a span_id query param or URL hash; no auto-scroll/highlight logic present"
      - path: "services/view/src/components/SpanDetailPanel.tsx"
        issue: "Breadcrumb href is /traces/{trace_id} with no span anchor; e.g. no ?span_id= or #span-id appended"
    missing:
      - "Breadcrumb link should include span context in URL: href={`/traces/${detail.trace_id}?span=${detail.span_id}`} or a hash anchor"
      - "Trace detail page should read the span param from useSearchParams() and either auto-open SpanDetailPanel for that span or scroll its row into view"
human_verification:
  - test: "Navigate to /traces, click a trace row, then click a span row to open SpanDetailPanel, then click the breadcrumb trace_id link"
    expected: "Browser navigates to /traces/{trace_id} and either opens the span detail panel for that span or scrolls/highlights the span row in the tree"
    why_human: "Cannot verify auto-scroll, visual highlight, or panel auto-open behavior programmatically"
  - test: "Verify collapsible tree behavior: on /traces/{trace_id}, toggle a parent span chevron to collapse, then click again to expand"
    expected: "Children hide on collapse, reappear on expand; chevron rotates; row click still fires correctly and does not double-fire when clicking chevron area"
    why_human: "Runtime event propagation and DOM state cannot be verified statically"
---

# Phase 21: Trace UI Verification Report

**Phase Goal:** Add a Traces UI — list page (/traces) and detail page (/traces/{trace_id}) — that lets operators navigate and inspect traces in the dashboard.
**Verified:** 2026-05-15T12:50:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dashboard has a Traces list page showing all traces with span and flag counts | VERIFIED | /traces/page.tsx fetches listTraces() and renders TraceTable with span_count and flag_count columns |
| 2 | Traces list page is accessible from main navigation | VERIFIED | NavBar.tsx line 38-43: `<Link href="/traces">Traces</Link>` present |
| 3 | Trace detail page renders spans as a collapsible parent/child tree using parent_span_id | VERIFIED | SpanTree.tsx: buildTree() constructs Map-bucketed parent/child nodes from parent_span_id; roots rendered recursively |
| 4 | All spans are expanded by default on page load | VERIFIED | SpanTree.tsx line 128: `useState<Set<string>>(new Set())` — empty collapsed set on mount |
| 5 | Parent spans have a chevron toggle that collapses/expands subtree with propagation stopped | VERIFIED | SpanTree.tsx lines 74-78: stopPropagation + onToggle called; hasChildren guard on render |
| 6 | Each span row shows tool_name (or model fallback), duration, and flag count badge | VERIFIED | SpanTree.tsx lines 91-104: `span.tool_name ?? span.model`, formatDuration(), conditional flag badge |
| 7 | Clicking a span row opens the existing SpanDetailPanel | VERIFIED | traces/[trace_id]/page.tsx lines 102-109: SpanTree onSpanClick sets selectedSpanId; SpanDetailPanel renders with open prop |
| 8 | From any span detail view, the user can navigate back to the parent trace with span highlighted | FAILED | Breadcrumb href is `/traces/${detail.trace_id}` — no span anchor or query param; UI-03 requires "with the span highlighted or scrolled into view" |

**Score:** 7/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/view/src/lib/api.ts` | TraceListItem, TraceDetailResponse, SpanInTrace, TraceFlagItem, TraceObject types + listTraces(), getTraceDetail() | VERIFIED | All 7 interfaces and 2 functions exported; confirmed at lines 196-268 |
| `services/view/src/components/TraceTable.tsx` | Trace list table, min 40 lines | VERIFIED | 68 lines; shadcn Table with 5 columns; cursor-pointer rows; router.push to /traces/{trace_id} |
| `services/view/src/app/traces/page.tsx` | Traces list page — fetches + renders TraceTable, min 60 lines | VERIFIED | 86 lines; listTraces() import + call; loading skeleton; empty state; error handling; auth redirect |
| `services/view/src/app/traces/layout.tsx` | Auth-guarded layout with NavBar | VERIFIED | 30 lines; useHydrateAuth + useAuthStore hydration gate + useEffect redirect to /login; wraps NavBar |
| `services/view/src/components/NavBar.tsx` | Traces nav link added | VERIFIED | href="/traces" present at line 39; href="/spans" also present |
| `services/view/src/components/SpanTree.tsx` | Collapsible span tree component, min 80 lines | VERIFIED | 162 lines; buildTree(), SpanRow, formatDuration(), collapsed Set state, chevron ChevronRight from lucide-react |
| `services/view/src/app/traces/[trace_id]/page.tsx` | Trace detail page — fetches trace, renders SpanTree + SpanDetailPanel, min 60 lines | VERIFIED | 113 lines; getTraceDetail() import + call; trace metadata header; SpanTree + SpanDetailPanel wired |
| `services/view/src/components/SpanDetailPanel.tsx` | Breadcrumb added above SheetTitle; contains traces/ | PARTIAL | Breadcrumb present at lines 254-267; navigates to /traces/{trace_id} but no span anchor/query param for highlight |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| traces/page.tsx | api.ts:listTraces() | import + call | WIRED | `import { listTraces } from '@/lib/api'` + `listTraces(token, { limit: 50 })` |
| TraceTable.tsx | /traces/{trace_id} | router.push on row click | WIRED | `router.push(\`/traces/${trace.trace_id}\`)` at line 33 |
| NavBar.tsx | /traces | Link href | WIRED | `href="/traces"` at line 39 |
| traces/[trace_id]/page.tsx | api.ts:getTraceDetail() | import + call | WIRED | `import { getTraceDetail } from '@/lib/api'` + `getTraceDetail(token, traceId)` |
| SpanTree.tsx | SpanDetailPanel via onSpanClick | prop callback | WIRED | SpanRow `onClick={() => onSpanClick(span.span_id)`; page passes `onSpanClick={(id) => setSelectedSpanId(id)}` |
| SpanTree.tsx | SpanInTrace.parent_span_id | tree-building logic | WIRED | buildTree() maps spans by parent_span_id; resolvedKey logic at line 27 |
| SpanDetailPanel.tsx | /traces/{trace_id} | Link breadcrumb | PARTIAL | href navigates correctly; span highlight/scroll context missing from URL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| UI-01 | 21-01-PLAN.md | Traces list page with span count, flag count, time range; accessible from nav | SATISFIED | /traces page + NavBar link + TraceTable with all required columns confirmed |
| UI-02 | 21-02-PLAN.md | Trace detail page renders collapsible span tree using parent_span_id; flag badges on each span | SATISFIED | SpanTree.tsx builds tree from parent_span_id; flag badges hidden at 0; chevron toggle functional |
| UI-03 | 21-03-PLAN.md | Span detail view has back-to-trace link navigating to /traces/{trace_id} with span highlighted/scrolled | PARTIAL | Breadcrumb navigates to /traces/{trace_id} — navigation link present but "span highlighted or scrolled into view" clause of the requirement is not implemented |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| traces/page.tsx | 49 | `return null` | Info | Legitimate auth hydration guard — matches spans/page.tsx pattern |
| traces/layout.tsx | 21 | `return null` | Info | Legitimate auth hydration guard — matches spans/layout.tsx pattern |
| traces/[trace_id]/page.tsx | 55 | `return null` | Info | Legitimate auth hydration guard |

No blockers or warnings found. All `return null` occurrences are intentional auth hydration gates matching the established pattern.

### Human Verification Required

#### 1. Back-navigation span context

**Test:** From /spans or /traces/{trace_id}, click a span row to open SpanDetailPanel. Click the breadcrumb trace_id (e.g. `a1b2c3d4`). Observe what happens at /traces/{trace_id}.
**Expected per UI-03:** The span that was open in the panel should be highlighted or the tree should scroll to it.
**Actual:** Browser navigates to /traces/{trace_id} with no span pre-selected. SpanDetailPanel is closed. No scroll or highlight occurs.
**Why human:** Visual and navigation state cannot be verified statically.

#### 2. Collapsible tree interaction

**Test:** On /traces/{trace_id} with a multi-level trace, click a parent span's chevron to collapse, then click it again to expand.
**Expected:** Subtree hides on collapse and reappears on expand. Clicking the row (not the chevron) opens SpanDetailPanel without triggering collapse.
**Why human:** Runtime event propagation and DOM animation cannot be verified statically.

#### 3. Empty state and loading skeleton on /traces

**Test:** With no traces in the system, navigate to /traces.
**Expected:** "No traces recorded yet" message with descriptive subtext — not a blank or broken table.
**Why human:** Requires a tenant with no trace data.

### Gaps Summary

One gap blocks full UI-03 compliance. The breadcrumb in SpanDetailPanel correctly navigates from a span detail view to the parent trace detail page, satisfying the "back to trace" navigation intent. However, REQUIREMENTS.md UI-03 specifies the destination should show "the span highlighted or scrolled into view." The trace detail page (`/traces/[trace_id]/page.tsx`) does not accept a span identity from the URL (no `searchParams`, no `#hash`), so the returning user lands on the trace detail page with no span pre-selected.

The plan scoped UI-03 to plain navigation (plan truth: "Clicking the trace_id segment in the breadcrumb navigates to /traces/{trace_id}") without documenting that the highlight/scroll clause was intentionally deferred. This is a partial implementation of the requirement.

The fix is two-step: (1) append `?span={detail.span_id}` to the breadcrumb href in SpanDetailPanel; (2) read that param in the trace detail page via `useSearchParams()` and either auto-open SpanDetailPanel for that span_id or visually highlight the row.

All other truths, artifacts, and key links are fully verified. TypeScript compiles with zero errors. All 6 documented commits exist in git history.

---

_Verified: 2026-05-15T12:50:00Z_
_Verifier: Claude (gsd-verifier)_
