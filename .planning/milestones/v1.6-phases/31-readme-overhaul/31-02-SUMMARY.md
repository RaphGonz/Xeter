---
phase: 31-readme-overhaul
plan: "02"
subsystem: docs
tags: [readme, documentation, public-facing, v1.6, sdk, detection-checks, calibration]

requires:
  - phase: 31-readme-overhaul
    plan: "01"
    provides: db-init init container in deploy/docker-compose.yml

provides:
  - README.md rewritten as definitive v1.6 public-facing developer documentation
  - All 11 sections per D-S-01: banner, TOC, quick start, SDK, detection checks, calibration, pluggable LLM, performance, architecture, multi-tenancy+auth, license
  - 24-row detection checks table sourced directly from FLAG_TYPE_TO_ANALYZER_CLASS registry

affects: [README.md, onboarding, public-release]

tech-stack:
  added: []
  patterns:
    - "Single-source-of-truth: FLAG_TYPE_TO_ANALYZER_CLASS + BINARY_FLAG_TYPES + DEFAULT_THRESHOLDS drive the detection table directly"

key-files:
  created: []
  modified:
    - README.md

key-decisions:
  - "Wrote full README in one atomic Write operation covering all 11 sections — one commit covers both Task 1 and Task 2 since they modify the same file"
  - "Kept dev-api-key-local visible in Quick Start per threat model T-31-02-01 (dev-only, explicitly labeled)"
  - "Architecture section cross-references port table from Quick Start section to avoid duplicating content — both sections include the table for standalone readability"
  - "TOC uses 9 entries (excludes Table of Contents itself) — 11 total document sections per D-S-01"

duration: 11min
completed: 2026-05-31
---

# Phase 31 Plan 02: README Overhaul Summary

**README.md rewritten as the definitive public-facing v1.6 developer document — all 11 sections, 24-flag detection table, Quick Start with seeded credentials, no deferred content**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-31T06:52:25Z
- **Completed:** 2026-05-31T07:03:25Z
- **Tasks:** 2 (written as one atomic README rewrite)
- **Files modified:** 1

## Accomplishments

### Task 1: Sections 1-5

- **Section 1 (Banner + tagline + badge):** `![Xeter](assets/logo+typo.png)` as first line, tagline sentence, GPL-3.0 + Commons Clause shield badge linked to LICENSE
- **Section 2 (Table of Contents):** 9 auto-linked GitHub anchor entries in D-S-01 order
- **Section 3 (Quick Start):** 4-command sequence (git clone, cp .env.example, ./generate-secrets.sh, docker compose up --build); explicit seeded credentials block (email: dev@example.com, API key: dev-api-key-local); health check; ports table; dev commands table (migrate/seed rows removed — handled automatically by db-init)
- **Section 4 (SDK):** pip install xeter-sdk; XETER_ENDPOINT + XETER_API_KEY env vars; full @xeter.trace decorator example with all 6 parameters; fire-and-forget note
- **Section 5 (Detection Checks):** WORKER_THRESHOLD_* note; 24-row flat table sourced from FLAG_TYPE_TO_ANALYZER_CLASS; columns: Flag type, Analyzer class, Description, Threshold type, Default threshold; binary flags show `—`; context_overflow shows `8000 tokens`

### Task 2: Sections 6-11

- **Section 6 (Calibration):** 4-step workflow: --reset, add fixture spans, --flag-type <type>, apply WORKER_THRESHOLD_<FLAG_TYPE_UPPER> to docker-compose.yml + restart worker; note on binary vs tunable flag types
- **Section 7 (Pluggable LLM):** 3 providers (Anthropic default, OpenAI, Ollama); env vars table: DIAGNOSTICER_PROVIDER, DIAGNOSTICER_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL; Ollama Docker note (host.docker.internal for macOS/Windows)
- **Section 8 (Performance):** 2 levers only per D-P-01: WORKER_TRACE_FLUSH_TIMEOUT_S (default 30, lower/higher trade-off explained) + embedder model swap (all-MiniLM-L6-v2 default, paraphrase-MiniLM-L3-v2 smaller, all-mpnet-base-v2 larger)
- **Section 9 (Architecture):** Verbatim ASCII diagram; service descriptions updated to include db-init; storage descriptions; ports table repeated for standalone readability
- **Section 10 (Multi-Tenancy & Auth):** Existing RLS prose + JWT/API key auth prose, updated with 30-min JWT expiry and silent refresh note
- **Section 11 (License):** GPL-3.0 + Commons Clause prose with link to LICENSE file; no full license text in README

## Task Commits

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1+2 | Rewrite README.md — all 11 sections for v1.6 public release | `8ff65b7` | README.md |

## Files Created/Modified

- `README.md` — complete rewrite; 202 additions, 108 deletions; all 11 sections per D-S-01

## Decisions Made

- Wrote all 11 sections in one atomic Write operation — both Task 1 and Task 2 modify the same file, so one commit is the correct atomic unit
- Dev credentials shown explicitly in Quick Start per D-QS-03; labeled dev-only per T-31-02-01 threat mitigations
- `wrong_tool_choice` listed as binary in the detection table — it's in BINARY_FLAG_TYPES in calibrate.py (even though the flag name differs from `wrong_tool_called`; the public-facing flag_type is `wrong_tool_choice`)
- `context_overflow` listed as binary with `8000 tokens` default — it has a value in DEFAULT_THRESHOLDS but is in BINARY_FLAG_TYPES; the plan explicitly states "For binary flags that appear in DEFAULT_THRESHOLDS with value 1.0, show `—`. For context_overflow, show `8000 tokens`."

## Deviations from Plan

None — plan executed exactly as written. Both Task 1 and Task 2 completed in a single README write because the file content was designed as a complete unit; the two-task split in the plan describes logical sections, not separate file writes.

## Requirements Satisfied

| Requirement | Section | Status |
|-------------|---------|--------|
| LICENSE-03 | Section 1 (badge) + Section 11 (prose) | Satisfied |
| DOCS-01 | Section 1 (banner + tagline) | Satisfied |
| DOCS-02 | Section 3 (Quick Start) | Satisfied |
| DOCS-03 | Section 4 (SDK) | Satisfied |
| DOCS-04 | Section 5 (Detection Checks table) | Satisfied |
| DOCS-05 | Section 6 (Calibration workflow) | Satisfied |
| DOCS-06 | Section 7 (Pluggable LLM) | Satisfied |
| DOCS-07 | Section 8 (Performance) | Satisfied |

## Known Stubs

None — all sections are fully implemented with real data from source files. No placeholder content.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. README.md is a documentation-only change. Dev credentials shown are dev-only fixed values per seed.py — not production keys (T-31-02-01 mitigated by explicit dev-only label in Quick Start).

## Self-Check: PASSED

- `README.md` present: FOUND
- First line is `![Xeter](assets/logo+typo.png)`: VERIFIED
- 24 analyzer class mentions in detection table: VERIFIED (grep count = 24)
- All 11 section headings present: VERIFIED
- `generate-secrets.sh` in Quick Start: VERIFIED
- `dev-api-key-local` in Quick Start credentials block: VERIFIED
- `WORKER_THRESHOLD_` in detection checks: VERIFIED
- `WORKER_TRACE_FLUSH_TIMEOUT_S` in performance: VERIFIED
- `all-MiniLM-L6-v2` in performance: VERIFIED
- `## Project Status` absent: VERIFIED (not found)
- `## Documentation` section absent: VERIFIED (not found)
- `Commons Clause` in license section: VERIFIED
- Commit `8ff65b7` exists: VERIFIED

---
*Phase: 31-readme-overhaul*
*Completed: 2026-05-31*
