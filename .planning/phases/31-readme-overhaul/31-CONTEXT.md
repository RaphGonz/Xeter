# Phase 31: README Overhaul - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite the existing `README.md` to be the definitive public-facing document for Xeter v1.6. A developer who has never seen the repo can find it, understand what it does, deploy it locally, instrument their agent, and understand all 24 detection checks — without reading source code. Also adds a migrate+seed init container to `deploy/docker-compose.yml` so setup is fully self-contained.

</domain>

<decisions>
## Implementation Decisions

### Quick Start Flow
- **D-QS-01**: Add a migrate+seed init container service to `deploy/docker-compose.yml`. It runs `alembic upgrade head` followed by `python -m xeter.scripts.seed`, with `depends_on: [postgres]` and `condition: service_completed_successfully`. The service exits after completion; other services depend on it to ensure migrations run first.
- **D-QS-02**: Init container runs both migrate AND seed by default. Seed is already idempotent — re-running on an existing DB is safe.
- **D-QS-03**: README Quick Start section shows the seeded credentials explicitly: tenant name `dev`, API key `dev-api-key-local`, dashboard at `http://localhost:3000`. Developer doesn't need to read `seed.py` to know what to use.
- **D-QS-04**: Quick Start flow: `generate-secrets.sh && docker compose up` — done. No separate migration or seed commands needed after this change.

### Flag Table Format
- **D-FT-01**: Single flat table for all 24 flags. Rows are ordered by analyzer class (ToolCall first, then OutputSchema, then SemanticSpan, then Trace). No subsection headers — one table.
- **D-FT-02**: One-liner description per flag. Terse — enough to understand the check's intent without reading source.
- **D-FT-03**: Table columns: `Flag type` | `Analyzer class` | `Description` | `Threshold type` | `Default threshold`. For binary flags, "Default threshold" column shows `—` (no continuous threshold).

### Performance & Optimization Section
- **D-P-01**: Keep the Performance section but scope it to 2 real levers only — do not invent tuning knobs that don't exist.
  - **`WORKER_TRACE_FLUSH_TIMEOUT_S`** (default: 30s) — seconds of inactivity before a trace is flushed for analysis. Lower = faster analysis, less context per trace. Higher = more span context per trace, higher latency.
  - **Embedder model swap** — `EMBEDDER_URL` in docker-compose points to the embedder service. Swap the sentence-transformers model (`all-MiniLM-L6-v2` default) for a smaller/faster model to reduce embedding latency at the cost of detection accuracy.
- **D-P-02**: Do NOT add a "disable unused analyzers" env flag — this feature does not exist in the codebase. No scope creep.
- **D-P-03**: No ClickHouse retention section — out of scope for this phase.

### README Structure
- **D-S-01**: Full restructure for developer-first flow. Order:
  1. Banner (`assets/logo+typo.png`) + one-sentence tagline + license badge
  2. Table of contents (auto-linked anchors)
  3. Quick Start (generate-secrets.sh → docker compose up → seeded credentials)
  4. SDK (install + `@xeter_sdk.trace` decorator + env vars + minimal example)
  5. Detection Checks (24-flag table)
  6. Calibration (DOCS-05 scope: reset thresholds → add fixture spans → calibrate.py → apply to docker-compose)
  7. Pluggable LLM (DOCS-06 scope: 3 providers + env vars + Ollama note)
  8. Performance (2 levers per D-P-01)
  9. Architecture (updated ASCII diagram + service descriptions)
  10. Multi-Tenancy & Auth (existing content, updated)
  11. License section (GPL-3.0 + Commons Clause summary, links to LICENSE file)
- **D-S-02**: Remove the "Project Status" section entirely. The banner communicates release state; a changelog-style section doesn't belong in a public README.
- **D-S-03**: Include a TOC with auto-linked GitHub anchors, placed immediately after the banner/tagline.
- **D-S-04**: Remove the outdated "Documentation" section at the bottom (it references arc42 docs that are dev-internal; the README should be self-contained for public users).

### Claude's Discretion
- Exact wording of each flag's one-liner description (pull from source/tests for accuracy).
- Calibration section command examples — use DOCS-05 scope (reset thresholds, add fixture spans, `calibrate.py --flag-type <type>`, apply output to `docker-compose.yml` via `WORKER_THRESHOLD_*`).
- Prose for Architecture section (update the existing ASCII diagram and service descriptions to reflect v1.6 state).
- License badge format: use standard `img.shields.io` GitHub badge format.
- Whether to use an inline `<details>` block for Dev Commands table or keep it flat.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of truth for flag types and thresholds
- `xeter/scripts/calibrate.py` lines 91–161 — `FLAG_TYPE_TO_ANALYZER_CLASS` (all 24 flags, mapped to analyzer class), `BINARY_FLAG_TYPES` (11 binary types), `DEFAULT_THRESHOLDS` (default threshold values per flag). This is the single source of truth for the detection checks table.

### Docker Compose and env vars
- `deploy/docker-compose.yml` — current service definitions, WORKER_THRESHOLD_* env vars, EMBEDDER_URL; the init container (migrate+seed) needs to be added here.
- `xeter/services/worker/main.py` lines 80–86 — `WORKER_TRACE_FLUSH_TIMEOUT_S` and `WORKER_AGENT_ROUTING_GRAPH` env var definitions with defaults.

### Quick Start setup scripts
- `generate-secrets.sh` — exact script that generates .env secrets; README Quick Start must reference this exactly.
- `xeter/scripts/seed.py` (or `xeter/scripts/seed/` — confirm path) — seed script; init container runs this.
- `xeter/migrations/alembic.ini` — alembic config used by migration commands.

### Requirements
- `.planning/REQUIREMENTS.md` — DOCS-01 through DOCS-07 and LICENSE-03 define the required sections and their exact scope. Planner must satisfy each requirement.

### Assets
- `assets/logo+typo.png` — banner image; confirmed exists at this path (moved in Phase 29).

### Existing README (to be overwritten)
- `README.md` — existing content to reuse/update where still accurate: architecture ASCII diagram, port table, multi-tenancy/auth descriptions, SDK decorator example skeleton.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `README.md` (existing) — architecture ASCII diagram, port table, multi-tenancy prose, auth prose, SDK decorator example — all reusable with updates.
- `calibrate.py` lines 91–161 — complete flag type data: name, class, binary/tunable classification, default threshold. Pull this directly into the detection checks table without manual lookup.
- `generate-secrets.sh` — 7-var secret generation; content is the exact Quick Start step 1.

### Established Patterns
- Docker Compose service format uses `depends_on: service: condition:` syntax (check existing services for `condition: service_healthy` pattern to mirror for the init container).
- All `WORKER_THRESHOLD_*` env vars follow `WORKER_THRESHOLD_<FLAG_TYPE_UPPER>` naming convention and are already set in `deploy/docker-compose.yml` with calibrated values.

### Integration Points
- `deploy/docker-compose.yml` — init container is a new service added here; must run before `worker`, `presenter`, `analyser` services start.
- The seed script is idempotent — calling it on an already-seeded DB is safe; no guard needed.

</code_context>

<specifics>
## Specific Ideas

- Banner line: `![Xeter](assets/logo+typo.png)` as the very first line of README, then one-sentence tagline, then license badge on the same or next line.
- License badge: `[![License: GPL-3.0 + Commons Clause](https://img.shields.io/badge/License-GPL--3.0%20%2B%20Commons%20Clause-blue)](LICENSE)` (confirm exact badge text).
- Seeded credentials block in Quick Start: after compose up, show `Dashboard: http://localhost:3000 — Email: dev@example.com / API key: dev-api-key-local` (confirm actual seed values from seed.py).
- Detection Checks table header note: mention that all thresholds are set via `WORKER_THRESHOLD_*` env vars in `docker-compose.yml` — so developers know where to tune without reading the calibration section first.

</specifics>

<deferred>
## Deferred Ideas

- "Disable unused analyzers" via env flag — doesn't exist, not adding it (D-P-02).
- ClickHouse retention policy documentation — out of scope for v1.6.
- Arc42 architecture docs update — dev-internal; not part of the public README overhaul.
- TypeScript SDK documentation — TypeScript SDK doesn't exist yet (deferred to v1.7+).

</deferred>

---

*Phase: 31-readme-overhaul*
*Context gathered: 2026-05-31*
