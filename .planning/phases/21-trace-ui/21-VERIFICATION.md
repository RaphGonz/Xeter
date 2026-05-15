---
phase: 21-trace-ui
verified: 2026-05-15T14:00:00Z
status: human_needed
score: 8/8 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 7/8
  gaps_closed:
    - "From any span detail view, the user can navigate back to the parent trace detail page with the span highlighted or scrolled into view"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Navigate to /traces/{trace_id}, click a span row to open SpanDetailPanel, click the breadcrumb trace_id link"
    expected: "Browser navigates to /traces/{trace_id}?span={span_id} and SpanDetailPanel reopens for the same span automatically"
    why_human: "useState(spanFromUrl) initialiser cannot be observed statically; Sheet open/closed state is runtime behavior"
  - test: "On /traces/{trace_id}, toggle a parent span chevron to collapse, then click again to expand"
    expected: "Children hide on collapse, reappear on expand; chevron rotates 90 degrees; clicking the row (not chevron) opens SpanDetailPanel without triggering collapse"
    why_human: "Runtime event propagation and DOM animation cannot be verified statically"
  - test: "With no traces recorded, navigate to /traces"
    expected: "'No traces recorded yet' message with descriptive subtext — not a blank or broken table"
    why_human: "Requires a tenant with no trace data"
---

# Phase 21: Trace UI Verification Report

**Phase Goal:** Add a Traces list page and a collapsible trace detail tree to the dashboard; enable back-navigation from span detail to parent trace with the span highlighted or pre-selected on arrival.
**Verified:** 2026-05-15T14:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (Plan 04 closed UI-03 span highlight gap)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dashboard has a Traces list page showing all traces with span and flag counts | VERIFIED | /traces/page.tsx fetches `listTraces()` and renders `TraceTable` with span_count and flag_count columns; 87 lines |
| 2 | Traces list page is accessible from main navigation | VERIFIED | NavBar.tsx line 39: `href="/traces"` Traces link present in left nav group |
| 3 | Trace detail page renders spans as a collapsible parent/child tree using parent_span_id | VERIFIED | SpanTree.tsx: `buildTree()` maps spans by `parent_span_id`; orphaned spans treated as roots; 163 lines |
| 4 | All spans are expanded by default on page load | VERIFIED | SpanTree.tsx line 128: `useState<Set<string>>(new Set())` — empty collapsed set; no span collapsed on mount |
| 5 | Parent spans have a chevron toggle that collapses/expands subtree with propagation stopped | VERIFIED | SpanTree.tsx lines 74-78: `e.stopPropagation()` + `onToggle(span.span_id)` called; `hasChildren` guard on render |
| 6 | Each span row shows tool_name (or model fallback), duration, and flag count badge | VERIFIED | SpanTree.tsx lines 91-104: `span.tool_name ?? span.model`, `formatDuration()`, conditional flag badge hidden at 0 |
| 7 | Clicking a span row opens SpanDetailPanel | VERIFIED | traces/[trace_id]/page.tsx lines 102-112: SpanTree `onSpanClick` sets `selectedSpanId`; SpanDetailPanel renders with `open={selectedSpanId !== null}` |
| 8 | From span detail, back-navigation to parent trace reopens that span in the panel | VERIFIED | SpanDetailPanel.tsx line 259: breadcrumb href is `/traces/${detail.trace_id}?span=${detail.span_id}`; traces/[trace_id]/page.tsx lines 21-31: `useSearchParams().get('span')` initialises `selectedSpanId` |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/view/src/lib/api.ts` | Trace types + listTraces(), getTraceDetail() | VERIFIED | TraceFlagItem, ScoreItem, SpanInTrace, TraceObject, TraceDetailResponse, TraceListItem, TraceListResponse, listTraces, getTraceDetail all exported at lines 196-269 |
| `services/view/src/components/TraceTable.tsx` | Trace list table, min 40 lines | VERIFIED | 68 lines; shadcn Table with 5 columns; cursor-pointer rows; router.push to /traces/{trace_id} |
| `services/view/src/app/traces/page.tsx` | Traces list page, min 60 lines | VERIFIED | 87 lines; listTraces() import + call; loading skeleton; empty state "No traces recorded yet"; error handling; auth redirect |
| `services/view/src/app/traces/layout.tsx` | Auth-guarded layout with NavBar | VERIFIED | 30 lines; useHydrateAuth + useAuthStore hydration gate + useEffect redirect; wraps NavBar |
| `services/view/src/components/NavBar.tsx` | Traces nav link added | VERIFIED | href="/traces" at line 39; href="/spans" at line 33; both present in left nav group |
| `services/view/src/components/SpanTree.tsx` | Collapsible span tree, min 80 lines | VERIFIED | 163 lines; buildTree(), SpanRow, formatDuration(), collapsed Set state, ChevronRight from lucide-react |
| `services/view/src/app/traces/[trace_id]/page.tsx` | Trace detail page, min 60 lines | VERIFIED | 115 lines; getTraceDetail() import + call; useSearchParams + spanFromUrl; SpanTree + SpanDetailPanel wired |
| `services/view/src/components/SpanDetailPanel.tsx` | Breadcrumb with ?span= deep-link | VERIFIED | Line 259: `href={\`/traces/${detail.trace_id}?span=${detail.span_id}\`}` — full span context in URL |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| traces/page.tsx | api.ts:listTraces() | import + call | WIRED | `import { listTraces } from '@/lib/api'` + `listTraces(token, { limit: 50 })` |
| TraceTable.tsx | /traces/{trace_id} | router.push on row click | WIRED | `router.push(\`/traces/${trace.trace_id}\`)` at line 33 |
| NavBar.tsx | /traces | Link href | WIRED | `href="/traces"` at line 39 |
| traces/[trace_id]/page.tsx | api.ts:getTraceDetail() | import + call | WIRED | `import { getTraceDetail } from '@/lib/api'` + `getTraceDetail(token, traceId)` |
| SpanTree.tsx | SpanDetailPanel via onSpanClick | prop callback | WIRED | SpanRow `onClick={() => onSpanClick(span.span_id)`; page passes `onSpanClick={(id) => setSelectedSpanId(id)}` |
| SpanTree.tsx | SpanInTrace.parent_span_id | tree-building logic | WIRED | buildTree() maps spans by parent_span_id; resolvedKey orphan-safe logic at line 27 |
| SpanDetailPanel.tsx | /traces/{trace_id}?span={span_id} | Link breadcrumb | WIRED | href includes `?span=${detail.span_id}` at line 259 |
| traces/[trace_id]/page.tsx | selectedSpanId state | useSearchParams().get('span') initialiser | WIRED | Lines 21-22: `const searchParams = useSearchParams()` + `const spanFromUrl = searchParams.get('span')`; line 31: `useState<string \| null>(spanFromUrl)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| UI-01 | 21-01-PLAN.md | Traces list page with span count, flag count, time range; accessible from nav | SATISFIED | /traces page + NavBar Traces link + TraceTable with all required columns; confirmed in codebase |
| UI-02 | 21-02-PLAN.md | Trace detail page renders collapsible span tree using parent_span_id; flag badges on each span | SATISFIED | SpanTree.tsx builds tree from parent_span_id; flag badges hidden at 0; chevron toggle functional |
| UI-03 | 21-03-PLAN.md + 21-04-PLAN.md | Span detail view has back-to-trace link navigating with span highlighted/scrolled into view | SATISFIED | Breadcrumb href includes ?span= param; trace detail page reads useSearchParams().get('span') and initialises selectedSpanId — panel auto-opens on arrival |

No orphaned requirements. All three IDs declared in plans map to REQUIREMENTS.md and are confirmed satisfied in code.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| traces/page.tsx | 49 | `return null` | Info | Legitimate auth hydration guard — matches spans/page.tsx pattern |
| traces/layout.tsx | 20-22 | `return null` | Info | Legitimate auth hydration guard — matches spans/layout.tsx pattern |
| traces/[trace_id]/page.tsx | 57 | `return null` | Info | Legitimate auth hydration guard |

No blockers or warnings. All `return null` instances are intentional auth hydration gates matching the established project pattern.

### Human Verification Required

#### 1. Span auto-open on back-navigation (UI-03)

**Test:** Navigate to /traces/{trace_id}, click a span row to open SpanDetailPanel, then click the breadcrumb trace_id link (e.g. `a1b2c3d4`).
**Expected:** Browser navigates to /traces/{trace_id}?span={span_id} and SpanDetailPanel slides open for the same span immediately on page load.
**Why human:** useState(spanFromUrl) initialiser behaviour and Sheet animation cannot be verified statically.

#### 2. Collapsible tree interaction

**Test:** On /traces/{trace_id} with a multi-level trace, click a parent span chevron to collapse, then click again to expand. Also click the row area (not the chevron) on a parent span.
**Expected:** Subtree hides on collapse and reappears on expand. Chevron rotates. Clicking the row (not chevron) opens SpanDetailPanel without triggering collapse.
**Why human:** Runtime event propagation and DOM state cannot be verified statically.

#### 3. Empty state on /traces

**Test:** With no traces in the system, navigate to /traces.
**Expected:** "No traces recorded yet" message with subtext about agent runs — not a blank or broken table.
**Why human:** Requires a tenant with no trace data.

### Re-Verification Summary

The one gap from the initial verification is now closed. Plan 04 made two targeted edits:

1. `SpanDetailPanel.tsx` breadcrumb href changed from `/traces/${detail.trace_id}` to `/traces/${detail.trace_id}?span=${detail.span_id}` (commit 998760c).
2. `traces/[trace_id]/page.tsx` now imports `useSearchParams`, reads `.get('span')`, and initialises `selectedSpanId` from that value (commit 030a308).

Both commits are verified in git history. TypeScript compiles with zero errors across the entire view service. All 8 must-have truths are satisfied in the codebase. The three pending items are runtime/visual behaviors that require human testing — no automated check can confirm the Sheet animation fires correctly or that the collapse toggle does not double-fire on row click.

---

_Verified: 2026-05-15T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
