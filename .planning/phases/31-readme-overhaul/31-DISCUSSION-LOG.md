# Phase 31: README Overhaul - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 31-readme-overhaul
**Areas discussed:** Quick Start flow, Flag table format, Performance levers, README structure

---

## Quick Start Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Add init container to compose | migrate+seed service runs before other services; developer runs `generate-secrets.sh && docker compose up` and is done | ✓ |
| Keep multi-step, show all commands | README lists separate alembic and seed steps after compose up | |
| Hybrid: compose up + one post-up block | compose up then a single docker compose run block | |

**Sub-question: migrate only, or migrate + seed?**

| Option | Description | Selected |
|--------|-------------|----------|
| Migrate + seed by default | Dev tenant + API key created automatically | ✓ |
| Migrate only, seed separately | Seed kept as a separate optional command | |

**Sub-question: show seeded credentials?**

| Option | Description | Selected |
|--------|-------------|----------|
| Show the seeded credentials | README shows tenant dev, API key dev-api-key-local, localhost:3000 | ✓ |
| Just point to localhost:3000 | Developer figures out credentials themselves | |

**User's choice:** Add init container (migrate+seed), show credentials
**Notes:** Seed is idempotent — re-runs on an existing DB are safe, no guard needed.

---

## Flag Table Format

| Option | Description | Selected |
|--------|-------------|----------|
| Grouped by analyzer class | 4 subsections with their own tables | |
| One flat table, alphabetical | All 24 in a single alphabetical table | |
| One flat table, ordered by analyzer class | Single table, rows grouped by class | ✓ |

**Sub-question: description depth per flag?**

| Option | Description | Selected |
|--------|-------------|----------|
| One-liner | Terse; developer reads source for details | ✓ |
| Two sentences | Detection logic + what it signals; makes table very wide | |
| Just flag name + threshold type + default | Minimal; no prose description | |

**User's choice:** Single flat table ordered by analyzer class, one-liner descriptions
**Notes:** Columns: flag type | analyzer class | description | threshold type (binary/tunable) | default threshold. Binary flags show `—` for default threshold.

---

## Performance Levers

**Initial question:** User was asked what the "5 performance tuning levers" from the roadmap success criteria meant.
**User response:** "I don't even know what that means" — the success criteria wording was auto-generated; user hadn't considered this section.

**Resolution:** Read REQUIREMENTS.md DOCS-07, which specifies: embedding model swap, WORKER_TRACE_FLUSH_TIMEOUT_S, Redis queue sizing, disabling unused analyzers via env flag, ClickHouse retention policy.

**Follow-up:** Checked codebase for "disable unused analyzers" env flag — does not exist (no output from grep).

| Option | Description | Selected |
|--------|-------------|----------|
| Just WORKER_TRACE_FLUSH_TIMEOUT_S + embedder model | Short section; 2 real levers that actually exist | ✓ |
| Drop the section entirely | No Performance section at all | |
| Expand to include ClickHouse TTL | Add retention hint; would need CH schema work | |

**User's choice:** Keep performance section, scope to 2 real levers only
**Notes:** User's exact words: "Make it a section at the end, deep, and only include the tunes that are actually present in the code." No disable-analyzer env flag (doesn't exist); no ClickHouse retention (out of scope).

---

## README Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Restructure for developer-first flow | Banner → TOC → Quick Start → SDK → Detection Checks → Calibration → Pluggable LLM → Performance → Architecture → Multi-Tenancy/Auth → License | ✓ |
| Keep current order, add missing sections at end | Append new sections after existing ones | |
| Add TOC at top, keep section order | Minimal change with navigation | |

**Sub-question: Project Status section?**

| Option | Description | Selected |
|--------|-------------|----------|
| Remove it | Public READMEs don't need changelog sections | ✓ |
| Update it to reflect v1.6 | Keep as a quick changelog for maturity evaluation | |
| Replace with a short Roadmap note | "v1.6 released — v1.7 will add TypeScript SDK" | |

**Sub-question: TOC?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, auto-linked TOC near the top | GitHub-rendered anchor links | ✓ |
| No TOC | Developer scrolls or uses Ctrl+F | |
| You decide | Claude picks based on final README length | |

**User's choice:** Full restructure, remove Project Status, include TOC
**Notes:** Also agreed to remove the "Documentation" section (arc42 links are dev-internal).

---

## Claude's Discretion

- Exact wording of each flag's one-liner description (source from code/tests for accuracy)
- Calibration section command examples (DOCS-05 scope)
- Architecture prose (update existing ASCII + service descriptions)
- License badge exact format (img.shields.io)
- Whether Dev Commands table gets a `<details>` collapse or stays flat

## Deferred Ideas

- "Disable unused analyzers" env flag — doesn't exist; not adding it to scope
- ClickHouse retention policy documentation — out of scope v1.6
- TypeScript SDK documentation — SDK doesn't exist yet (v1.7+)
- Arc42 architecture docs update — dev-internal
