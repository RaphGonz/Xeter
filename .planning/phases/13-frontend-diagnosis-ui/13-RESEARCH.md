# Phase 13: Frontend Diagnosis UI - Research

**Researched:** 2026-04-24
**Domain:** React/Next.js UI — structured diagnosis display inside SpanDetailPanel
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Persisted result behavior**
- Auto-load on open: when the panel opens for a flagged span, fire `GET /diagnose/{span_id}`; if a diagnosis exists, show it immediately without requiring a click
- Re-run on button click: clicking "Diagnose" always POSTs to `/diagnose`, overwrites the stored result, updates the display — no confirmation step
- Button stays visible above the result card at all times (even after a result loads)

**Verdict/severity visual treatment**
- Verdict (model / architecture / prompt): colored badge — visually prominent, scannable at a glance, consistent with the existing flag badge pattern
- Severity: colored badge on the same row as the verdict badge (e.g., `[model] [critical]`)
- Affected field + recommended fix: MetaRow-style rows below the badge row — label + value, consistent with the span metadata section

**Loading and error states**
- Loading state: skeleton placeholder where the result card will appear, with a small note "Analyzing… (this may take a few seconds)" — sets expectations for the 5–15s LLM latency
- Error state: inline red error box below the Diagnose button (same position as diagError in current scaffold); button stays enabled so the user can retry without re-opening the panel

**Diagnosis display layout**
- Result lives inside `FlagSection`, below the flags list — keeps diagnosis visually linked to the flags that triggered it
- Diagnose button sits below the flags list, just above where the result card appears: see flags → click Diagnose → see result
- Result renders as a nested card inside the FlagSection red border card

### Claude's Discretion
- Exact badge color mapping (verdict → color, severity → color) — use red/orange/yellow/zinc as appropriate to signal severity
- Whether to add a subtle timestamp ("Diagnosed 2 minutes ago") on the result card
- Exact skeleton height/shape

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

Phase 13 is a focused UI change to `SpanDetailPanel.tsx` and `api.ts`. The backend already provides two endpoints (`POST /diagnose` and `GET /diagnose/{span_id}`) that return a structured `DiagnosisResponse` with verdict, severity, affected_field, recommended_fix, and diagnosed_at. The frontend scaffold currently stores the result as a plain string (`status: message`) — this phase replaces that string with a typed response and renders it as a proper card with colored badges and MetaRow fields.

The work breaks into three pieces: (1) update `api.ts` — replace the scaffold `DiagnoseResponse` type and add a typed `getDiagnosis` GET call; (2) update `FlagSection` state — replace `diagResult: string | null` with `diagResult: DiagnosisResponse | null`, add `diagAutoLoaded` state, and trigger the GET on mount; (3) render — add `DiagnosisCard` sub-component inside `FlagSection` that shows badges, MetaRow fields, and the skeleton/error states.

No new packages are required. The project already has Tailwind v4 (with `tw-animate-css`), shadcn UI components (`Badge`, `Skeleton`, `Card` family), `date-fns` v4 (for optional "diagnosed X minutes ago"), and `lucide-react` v1.7.0. All rendering stays within the existing `'use client'` file pattern established by the codebase.

**Primary recommendation:** Make all changes in two files only — `services/view/src/lib/api.ts` and `services/view/src/components/SpanDetailPanel.tsx`. Introduce a `DiagnosisCard` sub-component inside the same file as `FlagSection` to keep the diff contained.

---

## Standard Stack

### Core (already installed — no installs needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | 16.2.1 | App framework (`'use client'` component model) | Project standard |
| React | 19.2.4 | Component model, `useState`/`useEffect` hooks | Project standard |
| Tailwind CSS | 4.x | Utility-first styling | Project standard |
| shadcn Badge | already present | Colored badge component (CVA-based) | Used for existing flag badges |
| shadcn Skeleton | already present | Loading placeholder | Used in `LoadingSkeleton` already |
| shadcn Card family | already present | Nested card structure | Available for diagnosis card |
| date-fns | 4.1.0 | `formatDistanceToNow` for timestamp | Already installed |
| lucide-react | 1.7.0 | Icon library if needed | Already installed |
| clsx / tailwind-merge | present | Class merging via `cn()` | Project standard via `@/lib/utils` |

**Installation:** None — all dependencies are already installed.

### Badge Variants Available

The existing `badge.tsx` uses CVA with these built-in variants:
- `default` — primary (dark) background
- `secondary` — light gray
- `destructive` — red-tinted (currently used for flag badges)
- `outline` — border only, no background
- `ghost` — hover-only
- `link` — underline

For custom badge colors (verdict/severity), use `className` override with Tailwind utilities on top of the `outline` or `default` base. The component accepts `className` and passes it through `cn()`, so arbitrary color overrides work cleanly.

---

## Architecture Patterns

### Recommended File Changes

```
services/view/src/
├── lib/
│   └── api.ts                    # 2 changes: update DiagnoseResponse type, add getDiagnosis()
└── components/
    └── SpanDetailPanel.tsx       # Main work: FlagSection state + DiagnosisCard sub-component
```

No new files. No new routes. No new stores.

### Pattern 1: Typed API Response Replacement

**What:** Replace the scaffold `DiagnoseResponse` with the real backend shape, and add a GET function.

**Backend `DiagnosisResponse` (authoritative, from `diagnosis_service.py`):**
```typescript
// Mirrors xeter/services/presenter/diagnosis_service.py DiagnosisResponse
export interface DiagnosisResponse {
  diagnosis_id: string
  span_id: string
  verdict: string        // "model" | "architecture" | "prompt" — stored as string, not enum
  severity: string       // "critical" | "high" | "medium" | "low" — stored as string
  affected_field: string | null
  recommended_fix: string | null   // maps from DB field "fix"
  diagnosed_at: string             // ISO 8601 string
}

// GET /diagnose/{span_id} — returns 404 if no diagnosis exists
export async function getDiagnosis(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>(`/api/diagnose/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// POST /diagnose — update body type: remove flags field (backend no longer accepts it)
export async function diagnose(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>('/api/diagnose', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ span_id: spanId }),
  })
}
```

**Key change in `diagnose()`:** the `flags` parameter is removed. The backend `DiagnoseRequest` only accepts `{ span_id: string }` (flags field was removed in Phase 12, Plan 01).

### Pattern 2: Auto-Load on FlagSection Mount

**What:** Fire `GET /diagnose/{span_id}` when `FlagSection` mounts, show existing diagnosis if found. 404 = no diagnosis yet (not an error to show).

**When to use:** Panel opens for a flagged span.

```typescript
// Inside FlagSection
const [diagResult, setDiagResult] = useState<DiagnosisResponse | null>(null)
const [diagLoading, setDiagLoading] = useState(false)
const [diagError, setDiagError] = useState<string | null>(null)

useEffect(() => {
  // Auto-load existing diagnosis on mount
  let cancelled = false
  async function loadExisting() {
    setDiagLoading(true)
    try {
      const result = await getDiagnosis(token, spanId)
      if (!cancelled) setDiagResult(result)
    } catch (err) {
      const msg = err instanceof Error ? err.message : ''
      // 404 = no diagnosis yet — expected, not an error to surface
      if (!cancelled && !msg.includes('404') && !msg.includes('HTTP 404')) {
        setDiagError(msg)
      }
    } finally {
      if (!cancelled) setDiagLoading(false)
    }
  }
  loadExisting()
  return () => { cancelled = true }
}, [spanId, token])
```

**Critical:** Use a `cancelled` flag to prevent setState calls on unmounted component when the panel closes before the fetch resolves.

### Pattern 3: DiagnosisCard Sub-Component

**What:** Renders the structured result inside `FlagSection`. Uses colored badges for verdict/severity, MetaRow-style rows for fields/fix.

**Verdict color mapping (Claude's discretion):**
- `"model"` → orange tones (`bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-400`)
- `"architecture"` → yellow tones (`bg-yellow-100 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-400`)
- `"prompt"` → blue tones (`bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400`)

**Severity color mapping (Claude's discretion):**
- `"critical"` → destructive red (matches `variant="destructive"` pattern)
- `"high"` → orange
- `"medium"` → yellow/amber
- `"low"` → zinc/muted

```typescript
function DiagnosisCard({ result }: { result: DiagnosisResponse }) {
  // Color maps for verdict and severity
  const verdictColors: Record<string, string> = {
    model: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-400 dark:border-orange-800',
    architecture: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
    prompt: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  }
  const severityColors: Record<string, string> = {
    critical: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
    high: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-400 dark:border-orange-800',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
    low: 'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700',
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      {/* Badge row */}
      <div className="flex items-center gap-2 mb-2">
        <Badge className={cn('border', verdictColors[result.verdict] ?? '')}>
          {result.verdict}
        </Badge>
        <Badge className={cn('border', severityColors[result.severity] ?? '')}>
          {result.severity}
        </Badge>
      </div>
      {/* MetaRow-style fields */}
      <dl>
        {result.affected_field && (
          <MetaRow label="Affected field" value={result.affected_field} />
        )}
        {result.recommended_fix && (
          <MetaRow label="Fix" value={result.recommended_fix} />
        )}
      </dl>
      {/* Optional timestamp */}
      <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
        Diagnosed {formatDistanceToNow(new Date(result.diagnosed_at), { addSuffix: true })}
      </p>
    </div>
  )
}
```

### Pattern 4: Skeleton for Diagnosis Loading State

**What:** Replace the old "Requesting…" button-disabled state with a skeleton card + note.

```typescript
{diagLoading && (
  <div className="mt-2 space-y-2">
    <Skeleton className="h-8 w-full" />
    <Skeleton className="h-4 w-3/4" />
    <p className="text-xs text-zinc-400 dark:text-zinc-500">
      Analyzing… (this may take a few seconds)
    </p>
  </div>
)}
```

The button stays **enabled** during loading (per user decision: button always visible, POST always overwrites). The `disabled={diagLoading}` in the scaffold should be removed.

### Pattern 5: FlagSection Layout Order

```
FlagSection (red border card)
├── "Flags" heading
├── flags.map() — flag badges + score + detail
├── [Diagnose] button           ← always visible, never disabled by result
├── diagError box               ← inline red box if error (stays after retry attempt)
├── diagLoading skeleton        ← shown while loading
└── DiagnosisCard               ← shown when diagResult !== null
```

### Anti-Patterns to Avoid

- **Don't reuse the `diagnose()` call for auto-load:** The GET and POST are semantically distinct. GET = read existing, POST = trigger new. Conflating them breaks the "no side effects on open" contract.
- **Don't disable the Diagnose button during loading:** User decision says button stays enabled at all times. The skeleton communicates loading state instead.
- **Don't show 404 as an error:** The GET 404 means "no diagnosis yet" — this is the expected state for spans that have never been diagnosed. Surface it as nothing (empty state, no card).
- **Don't pass `flags` in POST body:** The backend's `DiagnoseRequest` no longer has a `flags` field (removed in Phase 12). Sending it would be ignored but signals a stale API assumption.
- **Don't use `useEffect` with missing deps:** The auto-load `useEffect` depends on `[spanId, token]`. FlagSection mounts fresh each time the panel opens because `SpanDetailPanel` conditionally renders it (`detail.status === 'flagged'`), so mount = panel open.
- **Don't import from `date-fns` root in Next.js 16:** Use named imports from the specific function file or the package root with tree-shaking. The correct import is `import { formatDistanceToNow } from 'date-fns'` — the package ships ESM properly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Colored badges | Custom `<span>` with inline styles | shadcn `Badge` + `className` override | CVA handles variant merging; `cn()` handles dark mode |
| Timestamp display | Custom date formatter | `date-fns` `formatDistanceToNow` | Already installed; handles all edge cases |
| Loading placeholder | CSS animation from scratch | shadcn `Skeleton` (already used in file) | Consistent with `LoadingSkeleton` above |
| Nested card styling | Custom card markup | Plain `<div>` with Tailwind or shadcn `Card` | Project already uses both patterns; plain div is simpler for a nested card |
| API error parsing | Custom error parsing | Existing `request<T>()` in `api.ts` | Already throws `Error` with `body.message ?? HTTP ${status}` |

**Key insight:** The project's `request<T>()` helper already handles error body parsing and throws a typed `Error`. Callers just catch and check `err.message` — the 404 detection is `msg.includes('404')` or `msg.includes('HTTP 404')`.

---

## Common Pitfalls

### Pitfall 1: Stale DiagnosisResponse when panel reopens for different span

**What goes wrong:** `diagResult` from a previous span persists briefly when a new span opens the panel.

**Why it happens:** `FlagSection` unmounts and remounts when `spanId` changes (because `SpanDetailPanel` conditionally renders it), so state resets to `null` automatically. But if the component identity is preserved (same React tree position), old state could flash.

**How to avoid:** `FlagSection` receives `spanId` as a prop — if React ever deduplicates renders, add a `key={spanId}` on `FlagSection` in `SpanDetailPanel`. This forces remount on span change and resets all state cleanly.

**Warning signs:** Diagnosis card for span A briefly flashes when opening span B.

### Pitfall 2: Cancellation race on fast panel close

**What goes wrong:** Panel opens, GET fires, user immediately closes panel → setState called on unmounted component → React warning.

**Why it happens:** Async fetch resolves after component unmounts.

**How to avoid:** Use the `cancelled` boolean flag pattern in `useEffect` cleanup (shown in Pattern 2). This is simpler than `AbortController` for this use case and avoids the abort-handling complexity.

**Warning signs:** React "Can't perform a state update on an unmounted component" warning in console.

### Pitfall 3: Badge className override fighting CVA defaults

**What goes wrong:** Custom color classes are overridden by CVA's variant classes because they have the same specificity.

**Why it happens:** The badge component applies `cn(badgeVariants({ variant }), className)` — `className` comes AFTER, so it wins. This is correct. The risk is using a CVA variant that sets background and also passing a custom background — the custom one wins due to order, which is correct.

**How to avoid:** Pass `className` only (no `variant` prop, or use `variant="outline"` as a neutral base). For fully custom-colored badges, use `variant="outline"` plus custom className to avoid background conflict.

**Warning signs:** Badge shows wrong color in one mode (light vs dark).

### Pitfall 4: `diagnose()` signature mismatch after removing `flags`

**What goes wrong:** `handleDiagnose` in `FlagSection` currently calls `diagnose(token, spanId, flags)` — after updating the function signature, the call site fails to compile if `flags` arg is left in.

**Why it happens:** The scaffold was written before Phase 12 removed `flags` from the backend request.

**How to avoid:** Update both the `diagnose()` function signature in `api.ts` AND the call site in `FlagSection.handleDiagnose()` in the same diff.

**Warning signs:** TypeScript compile error: "Expected 2 arguments, but got 3."

### Pitfall 5: Next.js 16 — verify any new API usage

**What goes wrong:** Next.js 16.2.1 is not the version from training data. The project AGENTS.md explicitly warns: "This version has breaking changes — APIs, conventions, and file structure may all differ from your training data."

**Why it happens:** Training knowledge lag.

**How to avoid:** Phase 13 changes stay within existing patterns (`'use client'`, `useState`, `useEffect`, standard React) — no new Next.js-specific APIs are needed. If any Next.js API beyond these is needed, read `node_modules/next/dist/docs/` first.

**Warning signs:** Any import from `next/...` that isn't already present in the file.

---

## Code Examples

### Auto-load pattern (complete useEffect)

```typescript
// Source: project pattern — mirrors existing getSpanDetail useEffect in SpanDetailPanel
useEffect(() => {
  let cancelled = false
  async function loadExisting() {
    setDiagLoading(true)
    setDiagError(null)
    try {
      const result = await getDiagnosis(token, spanId)
      if (!cancelled) setDiagResult(result)
    } catch (err) {
      const msg = err instanceof Error ? err.message : ''
      if (!cancelled && !msg.includes('404') && !msg.includes('HTTP 404')) {
        setDiagError(msg)
      }
    } finally {
      if (!cancelled) setDiagLoading(false)
    }
  }
  loadExisting()
  return () => { cancelled = true }
}, [spanId, token])
```

### Re-run (POST) handler — updated signature

```typescript
async function handleDiagnose() {
  setDiagLoading(true)
  setDiagResult(null)
  setDiagError(null)
  try {
    const result = await diagnose(token, spanId)  // no flags arg
    setDiagResult(result)
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Diagnostic request failed'
    setDiagError(msg)
  } finally {
    setDiagLoading(false)
  }
}
```

### FlagSection JSX layout (bottom section)

```typescript
<div className="mt-3 space-y-2">
  <Button
    size="sm"
    variant="outline"
    onClick={handleDiagnose}
    // NOTE: button is NOT disabled during loading — user decision
  >
    {diagLoading ? 'Analyzing…' : 'Diagnose'}
  </Button>

  {diagError && (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
      {diagError}
    </div>
  )}

  {diagLoading && (
    <div className="space-y-2">
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <p className="text-xs text-zinc-400 dark:text-zinc-500">
        Analyzing… (this may take a few seconds)
      </p>
    </div>
  )}

  {!diagLoading && diagResult && (
    <DiagnosisCard result={diagResult} />
  )}
</div>
```

### Updated getDiagnosis in api.ts

```typescript
// Source: backend contract — xeter/services/presenter/routers/diagnose.py

export interface DiagnosisResponse {
  diagnosis_id: string
  span_id: string
  verdict: string
  severity: string
  affected_field: string | null
  recommended_fix: string | null
  diagnosed_at: string
}

// GET — returns existing diagnosis or throws on 404
export async function getDiagnosis(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>(`/api/diagnose/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// POST — triggers new diagnosis, always overwrites
export async function diagnose(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>('/api/diagnose', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ span_id: spanId }),
  })
}
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `diagResult: string \| null` holding `"status: message"` | `diagResult: DiagnosisResponse \| null` holding typed backend shape | Enables structured rendering |
| `diagnose(token, spanId, flags)` with flags arg | `diagnose(token, spanId)` — no flags | Matches backend contract post-Phase 12 |
| Button disabled during loading | Button always enabled; skeleton communicates loading | User requirement |
| No GET on open | `getDiagnosis()` fires in `useEffect` on mount | Auto-loads persisted results |
| Plain string display | `DiagnosisCard` with colored badges + MetaRow | Structured, scannable output |

---

## Open Questions

1. **Should the Diagnose button label change to "Re-diagnose" after a result loads?**
   - What we know: user said "button stays visible above the result at all times"
   - What's unclear: whether the label should change to signal a re-run vs initial run
   - Recommendation: Claude's discretion — use "Diagnose" always for simplicity; the presence of the result card makes the re-run intent clear

2. **Does `FlagSection` need `key={spanId}` in its parent?**
   - What we know: `FlagSection` is conditionally rendered inside `SpanDetailPanel` and receives `spanId` as prop
   - What's unclear: whether React will reuse the component instance across panel open/close cycles
   - Recommendation: Add `key={spanId}` as a safety measure — zero-cost, prevents any state persistence edge case

3. **`formatDistanceToNow` import path in date-fns v4**
   - What we know: date-fns 4.1.0 is installed; `formatDistanceToNow.js` exists in package root
   - What's unclear: whether the import style `import { formatDistanceToNow } from 'date-fns'` works correctly with Next.js 16 tree-shaking
   - Recommendation: Use `import { formatDistanceToNow } from 'date-fns'` — this is the standard ESM import that date-fns v4 supports. If timestamp is omitted (Claude's discretion), this question becomes moot.

---

## Sources

### Primary (HIGH confidence)
- Direct file read: `xeter/services/presenter/diagnosis_service.py` — authoritative `DiagnosisResponse` field list
- Direct file read: `xeter/services/presenter/routers/diagnose.py` — endpoint behavior, 404 contract, DiagnoseRequest shape
- Direct file read: `services/view/src/components/SpanDetailPanel.tsx` — current scaffold state, `MetaRow`, `FlagSection`, badge patterns
- Direct file read: `services/view/src/lib/api.ts` — existing `request<T>()` helper, `diagnose()` signature, error format
- Direct file read: `services/view/src/components/ui/badge.tsx` — CVA variants available, className override chain
- Direct file read: `services/view/package.json` — exact versions of all dependencies

### Secondary (MEDIUM confidence)
- `services/view/src/app/globals.css` + `src/components/ui/card.tsx` — Tailwind v4 setup, design tokens, available `cn()` utilities

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- API contract (DiagnosisResponse shape): HIGH — read directly from Python source
- Component patterns: HIGH — read directly from existing TSX files
- Badge color mapping: MEDIUM — Claude's discretion per CONTEXT.md; specific oklch values need visual testing
- date-fns import compatibility: MEDIUM — package exists, ESM export confirmed by file listing, but not run-tested

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (stable stack — no active churn in Next.js 16 or Tailwind 4 APIs at this date)
