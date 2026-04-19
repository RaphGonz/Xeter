# Phase 5: Dashboard - Research

**Researched:** 2026-03-30
**Domain:** Next.js 15 frontend dashboard + Presenter API extension (filtering)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Span list layout**
- Dense table with columns: Status + Flag type, Agent name + Span ID, Similarity score, Relative timestamp
- Status shown as color dot + text label: red "Flagged" (with flag type), green "Clean", grey "Pending" (awaiting analysis)
- Cursor-based pagination with "Load more" button at the bottom — matches the API's cursor pagination

**Filtering experience**
- Top bar above the table: horizontal row of filter dropdowns for flag type, agent name, and time range
- Filters apply instantly on change — no "Apply" button
- Time range presets only: Last 15m, 1h, 6h, 24h, 7d, 30d (no custom date picker)
- Filter state reflected in URL query params for shareability and bookmarkability
- URL params must be validated server-side — no data leakage through URL manipulation (tenant scoping already enforced by API)

**Detail view navigation**
- Side panel slides in from the right when a span row is clicked; span list stays visible but narrowed
- Flag section at top of panel: flag type, similarity score, threshold, triggered fields, and "Request Diagnostic" button inside the flag section
- Below flag section: tabbed S3 payloads (Prompt | Response | Raw Response) — each tab loads content on demand when clicked
- Detail panel shows the COMPLETE span data — not just flag + payloads, but every field: model name, all arguments, tool calls, tokens, latency, everything stored in ClickHouse/PostgreSQL

**Login page**
- Minimal centered form: Xeter branding, email field, password field, login button
- Login errors shown as inline red text below the form ("Invalid email or password")
- Email + password only for this phase

**Navigation & empty states**
- Simple top navigation bar: Xeter logo/name on left, Docs link and user account dropdown (with logout) on right
- Empty span table shown as-is when no spans exist — no special onboarding illustration
- Documentation link lives in the top nav bar

### Claude's Discretion
- Loading skeleton/spinner design
- Exact spacing, typography, and color palette
- Error state handling for API failures
- Side panel width and responsive behavior
- Table sorting behavior (if any)

### Deferred Ideas (OUT OF SCOPE)
- SSO / OAuth authentication methods — future phase (login form design doesn't block adding these later)
- Custom date-time range picker for filters — can be added if preset ranges prove insufficient

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | Developer can view a list of spans with flag indicators showing anomaly status | Frontend table component + GET /spans (existing) + filter params (new) |
| DASH-02 | Developer can filter spans by flag type, agent name, and time range | Presenter GET /spans needs 3 new query params; frontend filter bar with nuqs URL state |
| AUTH-02 | Developer can log into the dashboard with email and password | POST /login already exists; frontend login form + JWT token storage in sessionStorage or memory |

</phase_requirements>

---

## Summary

Phase 5 has two distinct work streams: (1) extending the Presenter API with filtering parameters, and (2) scaffolding a Next.js 15 frontend that replaces the Phase 1 static stub. The Presenter's `GET /spans` endpoint currently accepts only `cursor` and `limit` — it needs `flag_type`, `agent_name`, and `from_time`/`to_time` query parameters added before the frontend can implement DASH-02. This is a backend-first dependency: filter params on the API must land before the filter bar on the frontend can be wired.

The frontend is a thin client. There is no business logic in the browser — the dashboard reads from the Presenter REST API and displays what it receives. Token auth uses the existing JWT from `POST /login` (returned as `session_token` in the response body); the frontend stores it in `sessionStorage` (survives tab, cleared on close, no XSS-to-localStorage risk for an internal developer tool). All Presenter API calls use `Authorization: Bearer <token>`. The `GET /spans/{id}` S3 payloads are intentionally loaded on demand when a tab is clicked — this is already spec'd in the API and must be honoured in the frontend by calling `GET /spans/{id}` only when the panel opens (not pre-fetching on row hover).

The standard stack for this frontend is Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui, and `nuqs` for URL search param state. This replaces the Phase 1 `services/view/` stub (static HTML served by `serve`). The Next.js app lives at `services/view/` and is containerised via Docker Compose (already has a `view` service on port 3000).

**Primary recommendation:** Implement Presenter filter params first (backend plan), then the Next.js frontend as three separate plans: login page + auth, span list + filter bar, and detail panel.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | 15.x (latest stable) | App Router, React Server Components, file-system routing | Industry standard for React full-stack; App Router's layout persistence is ideal for split-view dashboards |
| React | 19.x (bundled with Next.js 15) | UI rendering | Bundled with Next.js 15 |
| TypeScript | 5.x | Type safety across components + API client | Required for shadcn/ui, standard for production dashboards |
| Tailwind CSS | v4 | Utility-first CSS | Default with `create-next-app` in 2026; shadcn/ui fully supports v4 |
| shadcn/ui | latest | Unstyled component primitives (Table, Sheet, Tabs, DropdownMenu, Badge) | Most-starred React UI library; radix-ui primitives with Tailwind; 0KB runtime JS |
| nuqs | latest | Type-safe URL search param state management | De-facto standard for Next.js filter state in URL; shallow routing by default |
| Zustand | 5.x | Global auth token state (in-memory, sessionStorage persist) | ~1.2KB, 20M weekly downloads; minimal API; avoids Redux for small state slice |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @tanstack/react-table | v8 | Headless table logic (sorting, pagination helpers) | If dense table needs client-side sort; optional — span list is server-paginated so may not be needed in phase 5 |
| date-fns | v4 | Relative timestamp formatting ("2m ago") | Lightweight, tree-shakeable; for the Relative timestamp column |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Zustand | React Context + useReducer | Context causes full subtree re-renders; Zustand is more surgical; Zustand wins for token state |
| nuqs | Next.js `useSearchParams` + manual state | nuqs adds type-safety, parsing, and shallow routing in one package; manual approach is error-prone |
| shadcn/ui | Headless UI / Radix directly | shadcn includes Tailwind theming out of box; fewer config steps for this project size |
| sessionStorage | httpOnly cookie | httpOnly cookie requires a Next.js API route to set it server-side; adds a BFF pattern; sessionStorage is acceptable for an internal developer tool where the tradeoff is simplicity vs marginal XSS risk |

### Installation
```bash
# From services/view/
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
npx shadcn@latest init
npx shadcn@latest add button card dropdown-menu badge sheet tabs separator table skeleton
npm install nuqs zustand date-fns
```

---

## Architecture Patterns

### Recommended Project Structure
```
services/view/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout — NuqsAdapter + Providers
│   │   ├── page.tsx            # Redirect: / → /login or /spans
│   │   ├── login/
│   │   │   └── page.tsx        # Login form (Client Component)
│   │   └── spans/
│   │       └── page.tsx        # Span list + filter bar + side panel (Client Component)
│   ├── components/
│   │   ├── ui/                 # shadcn generated components (auto-populated by CLI)
│   │   ├── SpanTable.tsx       # Dense table component
│   │   ├── FilterBar.tsx       # Flag type / agent name / time range dropdowns
│   │   ├── StatusDot.tsx       # Color dot + text label
│   │   ├── SpanDetailPanel.tsx # Sheet slide-in panel
│   │   ├── PayloadTabs.tsx     # Tabs (Prompt / Response / Raw Response) — lazy load each
│   │   └── NavBar.tsx          # Top nav: logo + Docs link + user dropdown
│   ├── lib/
│   │   ├── api.ts              # Typed Presenter API client (fetch wrappers)
│   │   ├── auth.ts             # Token get/set/clear in sessionStorage + Zustand store
│   │   └── utils.ts            # cn() helper from shadcn init
│   └── providers.tsx           # NuqsAdapter + Zustand auth provider
├── next.config.ts              # rewrites: /api/* → http://presenter:8000/*
├── package.json
└── Dockerfile                  # Replace Phase 1 stub
```

### Pattern 1: URL Search Param Filter State with nuqs
**What:** Filter values (flag_type, agent_name, time_range) are stored in the URL query string using `nuqs`. Changes to dropdowns immediately update the URL and trigger a re-fetch.
**When to use:** Always for shareable/bookmarkable filter state per the locked decision.
**Example:**
```typescript
// Source: https://nuqs.dev/
import { useQueryState, parseAsString } from 'nuqs'

function FilterBar() {
  const [flagType, setFlagType] = useQueryState('flag_type', parseAsString.withDefault(''))
  const [agentName, setAgentName] = useQueryState('agent_name', parseAsString.withDefault(''))
  const [timeRange, setTimeRange] = useQueryState('time_range', parseAsString.withDefault('1h'))
  // Dropdowns call setters on change — URL updates, no Apply button needed
}
```

### Pattern 2: Next.js Proxy Rewrites for CORS
**What:** `next.config.ts` rewrites `/api/*` to `http://presenter:8000/*` (Docker internal hostname). The browser talks to Next.js on port 3000; Next.js proxies to the Presenter. No CORS headers needed in FastAPI.
**When to use:** Always when Next.js and FastAPI are in the same Docker Compose network. Avoids adding `CORSMiddleware` to the Presenter.
**Example:**
```typescript
// next.config.ts
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.PRESENTER_URL ?? 'http://presenter:8000'}/:path*`,
      },
    ]
  },
}
export default nextConfig
```

### Pattern 3: Session Token in sessionStorage + Zustand
**What:** After `POST /login` succeeds, store the `session_token` in `sessionStorage` (tab-scoped, cleared on close) and in a Zustand store (in-memory for fast reads). Route guard at the `/spans` page reads Zustand store; if null, redirect to `/login`.
**When to use:** Internal developer tool where simplicity > marginal XSS risk from sessionStorage; no BFF (Backend for Frontend) layer required.
**Example:**
```typescript
// lib/auth.ts
import { create } from 'zustand'

interface AuthStore {
  token: string | null
  setToken: (t: string) => void
  clearToken: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  token: typeof window !== 'undefined' ? sessionStorage.getItem('xeter_token') : null,
  setToken: (t) => { sessionStorage.setItem('xeter_token', t); set({ token: t }) },
  clearToken: () => { sessionStorage.removeItem('xeter_token'); set({ token: null }) },
}))
```

### Pattern 4: On-Demand S3 Payload via Span Detail Fetch
**What:** The detail panel does NOT pre-fetch span detail on row click. It calls `GET /spans/{id}` (which internally fetches S3 payloads) only when the panel opens. Each S3 tab (Prompt, Response, Raw Response) receives the content already present in the response — no second fetch per tab. The "on demand" aspect is panel-level (not tab-level), matching the API behaviour.
**Note:** The `GET /spans/{id}` endpoint already fetches all three S3 payloads together in one call (see `_fetch_all_s3_payloads`). Tab switching is just local state — no additional network requests.
**When to use:** Always — matches the API contract and prevents eager S3 fetches on the list view.

### Anti-Patterns to Avoid
- **Pre-fetching span detail on row hover:** Do not call `GET /spans/{id}` until the panel actually opens. S3 fetches are expensive.
- **Filter state in component state only:** Filters MUST be in URL params (nuqs). Component-only state breaks shareability.
- **Direct fetch to `http://presenter:8000` from browser:** Always proxy through Next.js rewrites. Browser → presenter direct would need CORS middleware.
- **localStorage for JWT:** Use sessionStorage. This is an internal tool; localStorage persists indefinitely and is accessible to any same-origin JS.
- **Calling `GET /spans` on every keystroke:** Filters are dropdowns with discrete values — no debounce needed. nuqs triggers re-fetch on dropdown change.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL search param sync | Custom useState + router.push | nuqs | nuqs handles serialisation, deserialisation, shallow routing, and TypeScript types |
| Slide-out panel | Custom modal/drawer | shadcn Sheet (side="right") | Built on Radix Dialog: focus trap, aria-modal, keyboard dismiss — all free |
| Tabbed content | Custom tab state + CSS | shadcn Tabs | Accessible ARIA roles, keyboard navigation |
| Status badge | Custom color classes | shadcn Badge + Tailwind variant | Consistent with the design system |
| Table structure | Raw `<table>` markup | shadcn Table components | Semantic HTML + Tailwind + responsive behaviour |
| Relative timestamps | Custom date math | date-fns `formatDistanceToNow` | Handles edge cases (just now, future dates, locales) |

**Key insight:** shadcn/ui components are copied into the project (not a runtime dep) — they are customisable without fighting an opinionated library.

---

## Common Pitfalls

### Pitfall 1: Presenter API Missing Filter Params
**What goes wrong:** Frontend filter bar sends `?flag_type=wrong_tool` but `GET /spans` ignores it — ClickHouse query has no WHERE clause for it. Filters appear to work (no errors) but return unfiltered data.
**Why it happens:** The existing `GET /spans` only accepts `cursor` and `limit`. DASH-02 requires adding `flag_type`, `agent_name`, `from_time`, `to_time` to both the router and the ClickHouse query.
**How to avoid:** Implement Presenter filter extension as a separate backend plan BEFORE the frontend filter bar plan.
**Warning signs:** Filter dropdown changes don't change the span count.

### Pitfall 2: Next.js `useSearchParams` Without NuqsAdapter
**What goes wrong:** `nuqs` hooks throw an error in the App Router because `useSearchParams` requires a Suspense boundary and the NuqsAdapter wrapping.
**Why it happens:** Next.js App Router requires Suspense around `useSearchParams` usage; nuqs provides an adapter that handles this.
**How to avoid:** Wrap root layout in `<NuqsAdapter>` from `nuqs/adapters/next/app`. Every filter component then works without individual Suspense wrapping.

### Pitfall 3: Hydration Mismatch from sessionStorage Read
**What goes wrong:** Zustand store initialises `token` from `sessionStorage` on the server (where `window` is undefined) → hydration mismatch error.
**Why it happens:** Next.js renders components on both server and browser; `sessionStorage` doesn't exist server-side.
**How to avoid:** Guard the sessionStorage read: `typeof window !== 'undefined' ? sessionStorage.getItem('xeter_token') : null`. Pattern already shown in Code Examples.

### Pitfall 4: Duplicate S3 Fetches
**What goes wrong:** Each tab click in the detail panel triggers `GET /spans/{id}` again, causing repeated S3 fetches.
**Why it happens:** Misunderstanding the API design. The `GET /spans/{id}` already returns all three S3 payloads in one response — tab switching needs no network call.
**How to avoid:** Fetch `GET /spans/{id}` once when the panel opens; store the result in local state; tabs just render from that stored result.

### Pitfall 5: Docker Compose View Service Uses Old Stub Dockerfile
**What goes wrong:** `docker-compose up` still runs the Phase 1 `serve` stub instead of the Next.js app.
**Why it happens:** The Phase 1 Dockerfile runs `npm install -g serve && CMD ["serve", ...]`. Phase 5 must replace this with a proper `npm run dev` / `npm run build && npm run start` Dockerfile.
**How to avoid:** Rewrite `services/view/Dockerfile` as part of the frontend scaffold plan.

### Pitfall 6: nuqs and Next.js SSR — Filter Params Not Available on First Render
**What goes wrong:** SSR renders the page with no filter params, then client hydrates with URL params — causes a flicker.
**Why it happens:** nuqs with shallow routing (default) only updates client-side.
**How to avoid:** The `/spans` page should be a pure Client Component (`'use client'`). No server-side span fetching — all data fetching is client-side via the API proxy. This also simplifies auth guard (redirect if token missing).

---

## Code Examples

Verified patterns from official sources:

### Presenter API Client (lib/api.ts)
```typescript
// All API calls go through /api/* (rewrites → presenter:8000)
const BASE = '/api'

export async function login(email: string, password: string) {
  const res = await fetch(`${BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error('Invalid email or password')
  return res.json() as Promise<{ session_token: string }>
}

export async function listSpans(token: string, params: SpanListParams) {
  const url = new URL(`${BASE}/spans`, window.location.origin)
  if (params.flag_type) url.searchParams.set('flag_type', params.flag_type)
  if (params.agent_name) url.searchParams.set('agent_name', params.agent_name)
  if (params.from_time) url.searchParams.set('from_time', params.from_time)
  if (params.to_time) url.searchParams.set('to_time', params.to_time)
  if (params.cursor) url.searchParams.set('cursor', params.cursor)
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (res.status === 401) { /* clear token, redirect to login */ }
  return res.json()
}

export async function getSpanDetail(token: string, spanId: string) {
  const res = await fetch(`${BASE}/spans/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`Span fetch failed: ${res.status}`)
  return res.json()
}

export async function diagnose(token: string, spanId: string, flags: unknown[]) {
  const res = await fetch(`${BASE}/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ span_id: spanId, flags }),
  })
  return res.json()
}
```

### nuqs Filter Hook
```typescript
// Source: https://nuqs.dev/
import { useQueryState, parseAsString } from 'nuqs'

const TIME_RANGE_PRESETS = ['15m', '1h', '6h', '24h', '7d', '30d'] as const

export function useSpanFilters() {
  const [flagType, setFlagType] = useQueryState('flag_type', parseAsString.withDefault(''))
  const [agentName, setAgentName] = useQueryState('agent_name', parseAsString.withDefault(''))
  const [timeRange, setTimeRange] = useQueryState('time_range', parseAsString.withDefault('1h'))
  return { flagType, setFlagType, agentName, setAgentName, timeRange, setTimeRange }
}
```

### Next.js Rewrite Config (next.config.ts)
```typescript
// Source: https://nextjs.org/docs/app/api-reference/next-config-js/rewrites
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.PRESENTER_URL ?? 'http://presenter:8000'}/:path*`,
      },
    ]
  },
}
export default nextConfig
```

### Presenter GET /spans Filter Extension (backend)
```python
# Extend existing GET /spans in xeter/services/presenter/routers/spans.py
@router.get("/spans", response_model=SpanListResponse)
async def list_spans(
    request: Request,
    tenant_id: Annotated[str, Depends(verify_session_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    flag_type: str | None = Query(default=None),     # NEW: filter by flag type
    agent_name: str | None = Query(default=None),    # NEW: filter by agent name
    from_time: str | None = Query(default=None),     # NEW: ISO timestamp lower bound
    to_time: str | None = Query(default=None),       # NEW: ISO timestamp upper bound
) -> SpanListResponse:
    # flag_type filter requires a JOIN or subquery: only return span_ids that
    # have a flag row matching flag_type. Implemented as an IN subquery on spans
    # where span_id in (SELECT span_id FROM flags WHERE tenant_id=? AND flag_type=?).
    # agent_name + time range added as WHERE clauses on the ClickHouse query directly.
```

**Note:** `flag_type` filtering is applied in PostgreSQL (flags table) — collect matching span_ids first, then add `AND span_id IN (...)` to the ClickHouse query. `agent_name` and `from_time`/`to_time` filter directly on ClickHouse columns.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pages Router + getServerSideProps | App Router + React Server Components | Next.js 13+ (stable Next.js 15) | Server components reduce JS bundle; layouts don't remount on navigation |
| Tailwind CSS v3 (tailwind.config.js) | Tailwind CSS v4 (CSS-first @theme) | Tailwind v4 GA (2025) | No config file required; automatic content detection |
| react-query v4 | TanStack Query v5 | 2023–2024 | Unified package name; improved TypeScript inference |
| Redux / MobX for global state | Zustand v5 | 2024–present | ~1.2KB vs ~50KB; no boilerplate; dominates market in 2026 |
| Custom URL state (router.push) | nuqs | 2023–present | Type-safe, shallow by default, works with App Router Suspense |

**Deprecated/outdated:**
- `next/router` (Pages Router): Replaced by `next/navigation` in App Router
- `getServerSideProps` / `getStaticProps`: Replaced by async Server Components
- `pages/` directory: Still works but App Router is the recommended path for new projects

---

## Open Questions

1. **Should `GET /spans/{id}` be called per-panel-open or only on tab click?**
   - What we know: The API fetches all S3 payloads in one call; the panel shows complete span data including non-S3 fields immediately.
   - What's unclear: Whether to call `GET /spans/{id}` immediately on panel open (shows S3 content pre-loaded when user clicks first tab) vs lazy-call only on first tab click (avoids S3 fetch if user closes panel without viewing payloads).
   - Recommendation: Call `GET /spans/{id}` immediately on panel open. The CONTEXT.md says "each tab loads content on demand when clicked" — interpret this as the panel-level trigger (row click = panel open = detail fetch). The tab switching itself is local state. This matches the API's single-call design.

2. **time_range filter: ISO range vs relative label in the URL?**
   - What we know: Presets are "Last 15m, 1h, 6h, 24h, 7d, 30d". The Presenter needs `from_time`/`to_time` as ISO timestamps.
   - What's unclear: Whether to store the preset label ("1h") in the URL and convert to ISO at call time, or store the ISO timestamps.
   - Recommendation: Store the preset label ("1h") in the URL (human-readable, shareable). Convert to `from_time`/`to_time` ISO at call time in `lib/api.ts`. This also avoids stale shared links ("6h ago" is always relative to now, not to when the link was created).

3. **Does the view Dockerfile need multi-stage build?**
   - What we know: Docker Compose already has a `view` service on port 3000.
   - What's unclear: Whether to use a single-stage (`npm run dev` for local) or multi-stage (build + `npm start`) Dockerfile.
   - Recommendation: Single-stage with `npm run dev` for Phase 5 (consistent with other services using `--reload`). Production build optimisation is Phase 6+ scope.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x + pytest-asyncio 0.24.0 (already installed) |
| Config file | `xeter/pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `pytest xeter/tests/presenter/ -x -q` |
| Full suite command | `pytest xeter/tests/ -x -q` |

**Note:** Frontend testing (Jest/Playwright) is NOT in scope for Phase 5. The nyquist validation criteria are met with backend tests for the API extension + manual smoke test of the UI. The CONTEXT.md does not specify frontend test coverage, and the project has no existing frontend test infrastructure.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | GET /spans returns flagged/clean/pending spans with flag badges | unit (already exists) | `pytest xeter/tests/presenter/test_spans_list.py -x` | ✅ |
| DASH-02 | GET /spans filters by flag_type, agent_name, from_time, to_time | unit (new) | `pytest xeter/tests/presenter/test_spans_list_filters.py -x` | ❌ Wave 0 |
| AUTH-02 | POST /login returns session_token; frontend login form works | unit (already exists for backend); manual for UI | `pytest xeter/tests/presenter/test_auth_login.py -x` | ✅ (backend); manual (UI) |

### Sampling Rate
- **Per task commit:** `pytest xeter/tests/presenter/ -x -q`
- **Per wave merge:** `pytest xeter/tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `xeter/tests/presenter/test_spans_list_filters.py` — covers DASH-02 filter params (flag_type, agent_name, from_time/to_time)

*(All other test infrastructure exists.)*

---

## Sources

### Primary (HIGH confidence)
- [Next.js App Router Docs](https://nextjs.org/docs/app) — App Router patterns, rewrites config, cookies, useSearchParams
- [shadcn/ui Tailwind v4 Docs](https://ui.shadcn.com/docs/tailwind-v4) — Tailwind v4 compatibility, component install
- [nuqs official docs](https://nuqs.dev/) — URL search param state management, NuqsAdapter, shallow routing
- [shadcn Sheet component](https://ui.shadcn.com/docs/components/radix/sheet) — Side panel implementation

### Secondary (MEDIUM confidence)
- [Next.js 15.x stable (March 2026)](https://www.abhs.in/blog/nextjs-current-version-march-2026-stable-release-whats-new) — Confirmed 15.x is current stable; 16 exists but 15 is the last known stable
- [Zustand v5 npm](https://www.npmjs.com/package/zustand) — v5.0.12 current, 20M weekly downloads, confirmed market leader
- [nuqs + Next.js App Router guide](https://medium.com/@Jaimayal/how-to-properly-manage-search-params-in-nextjs-app-router-leverage-the-power-of-nuqs-the-right-way-9f7238cff76a) — NuqsAdapter requirement, shallow routing default

### Tertiary (LOW confidence)
- WebSearch consensus on sessionStorage vs localStorage vs httpOnly cookie for internal tools — multiple sources agree sessionStorage is acceptable for internal dashboards without a BFF

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Next.js 15, shadcn/ui, nuqs, Zustand all verified with official docs and npm
- Architecture: HIGH — API filter gap identified by reading actual source code; proxy rewrite pattern from Next.js official docs
- Pitfalls: HIGH — hydration mismatch and NuqsAdapter gaps are documented in official nuqs/Next.js docs; S3 fetch behaviour from reading actual Presenter source
- Frontend testing scope: MEDIUM — no existing frontend test infrastructure; decision to use manual smoke test for UI is a judgment call

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable stack; Next.js releases are rapid but App Router patterns are stable)
