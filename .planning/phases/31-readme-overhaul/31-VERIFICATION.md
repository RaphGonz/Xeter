---
phase: 31-readme-overhaul
verified: 2026-05-31T10:00:00Z
status: gaps_found
score: 8/10 must-haves verified
overrides_applied: 0
gaps:
  - truth: "A developer can copy Quick Start commands verbatim and reach a working dashboard (no manual migration/seed step)"
    status: partial
    reason: "The git clone command contains a literal placeholder `<repo-url>` that was never substituted with an actual repository URL. A developer copying this command verbatim gets a git clone error. All subsequent commands (cp .env.example, generate-secrets.sh, docker compose up) are correct and verbatim-copyable."
    artifacts:
      - path: "README.md"
        issue: "Line 24: `git clone <repo-url> && cd Xeter` — `<repo-url>` is an unsubstituted placeholder"
    missing:
      - "Replace `<repo-url>` with the actual GitHub repository URL (e.g., https://github.com/RaphGonz/Xeter)"
  - truth: "The Performance section covers exactly the two levers specified in D-P-01"
    status: failed
    reason: "ROADMAP.md Success Criterion #5 specifies 'all five performance tuning levers' and REQUIREMENTS.md DOCS-07 lists Redis queue sizing, disabling unused analyzers, and ClickHouse retention policy as required. The Performance section only documents 2 levers. This is an intentional descoping decision documented in CONTEXT.md D-P-01 through D-P-03 (user authorized narrowing to real levers only). Requires an override to accept."
    artifacts:
      - path: "README.md"
        issue: "Performance section documents only 2 levers; ROADMAP SC #5 and REQUIREMENTS.md DOCS-07 specify 5 items"
    missing:
      - "Either add a verification override accepting the 2-lever scope (recommended — the 3 omitted items do not exist in codebase), OR update ROADMAP.md and REQUIREMENTS.md to reflect the descoped scope."
---

# Phase 31: README Overhaul Verification Report

**Phase Goal:** Any developer can find Xeter, understand what it does, deploy it locally, instrument their agent, and understand every detection check — without reading source code
**Verified:** 2026-05-31T10:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The banner image, tagline, and license badge appear at the very top of the rendered page | VERIFIED | README.md line 1: `![Xeter](assets/logo+typo.png)`; line 3: tagline; line 5: `img.shields.io` badge linked to LICENSE |
| 2 | A developer can copy Quick Start commands verbatim and reach a working dashboard (no manual migration/seed step) | PARTIAL | `generate-secrets.sh`, `docker compose -f deploy/docker-compose.yml up --build`, health check, seeded credentials all present — but `git clone <repo-url>` uses an unsubstituted placeholder on line 24 |
| 3 | Seeded credentials are shown explicitly so the developer knows what to log in with | VERIFIED | README.md lines 31–38: email `dev@example.com`, password `dev_password_local`, API key `dev-api-key-local` — matches seed.py constants exactly |
| 4 | The SDK section contains a complete, copy-pasteable instrumentation example | VERIFIED | `pip install xeter-sdk`, `XETER_ENDPOINT`, `XETER_API_KEY`, and full `@xeter.trace(...)` decorator example with all 6 parameters present |
| 5 | All 24 flag types appear in a single detection checks table with class, description, threshold type, and default | VERIFIED | Detection Checks table has exactly 24 rows; all columns present; all 11 binary flags correctly classified; all tunable defaults match calibrate.py DEFAULT_THRESHOLDS |
| 6 | The Calibration section covers the full workflow end-to-end | VERIFIED | 4-step workflow: `--reset`, add fixture spans, `--flag-type <type>`, apply `WORKER_THRESHOLD_<FLAG_TYPE_UPPER>` to docker-compose + restart worker |
| 7 | The Pluggable LLM section lists all three providers and all required env vars | VERIFIED | Anthropic, OpenAI, Ollama providers listed; all 5 env vars present: `DIAGNOSTICER_PROVIDER`, `DIAGNOSTICER_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`; Ollama `host.docker.internal` note included |
| 8 | The Performance section covers exactly the two levers specified in D-P-01 | FAILED | Section documents exactly 2 levers (`WORKER_TRACE_FLUSH_TIMEOUT_S` and embedder model swap) per user decision D-P-01. However ROADMAP.md SC #5 says "all five performance tuning levers" and REQUIREMENTS.md DOCS-07 lists 5 items — the scope mismatch requires an override |
| 9 | The Project Status and Documentation sections are removed entirely | VERIFIED | `grep '## Project Status' README.md` → no match; `grep '## Documentation' README.md` → no match |
| 10 | Running docker compose up applies migrations and seeds dev data automatically — no separate CLI commands needed | VERIFIED | `db-init` service present in docker-compose.yml; chaining `alembic upgrade head && python -m xeter.scripts.seed`; `restart: "no"`; all 4 app services depend on `db-init: condition: service_completed_successfully` |

**Score:** 8/10 truths verified (2 gaps — 1 PARTIAL, 1 FAILED)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `README.md` | Public-facing developer documentation for v1.6 | VERIFIED | 278 lines; all 11 sections present; first line is banner image |
| `README.md` | Contains `assets/logo+typo.png` | VERIFIED | Line 1 |
| `README.md` | Contains `generate-secrets.sh` | VERIFIED | Line 27 in Quick Start |
| `README.md` | Contains `WORKER_THRESHOLD_` | VERIFIED | 3 occurrences: Detection Checks intro, Calibration step 4 example |
| `deploy/docker-compose.yml` | `db-init` service definition | VERIFIED | Lines 84–97; uses presenter Dockerfile; `restart: "no"` |
| `assets/logo+typo.png` | Banner image file | VERIFIED | File exists at repo root |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| README.md Quick Start | deploy/docker-compose.yml db-init | `docker compose up` — no separate migrate/seed step | VERIFIED | README line 30: "Migrations and seed data run automatically via the `db-init` init container"; docker-compose.yml has db-init service with postgres dependency |
| README.md Detection Checks table | xeter/scripts/calibrate.py FLAG_TYPE_TO_ANALYZER_CLASS | 24-row table sourced from calibrate.py registry | VERIFIED | All 24 flag types, analyzer classes, binary/tunable classifications, and DEFAULT_THRESHOLDS values match calibrate.py exactly |
| db-init | worker / presenter / analyser / diagnosticer | `depends_on` condition: service_completed_successfully | VERIFIED | All 4 services have `db-init: condition: service_completed_successfully` confirmed by Python yaml parse |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces documentation (README.md) and infrastructure config (docker-compose.yml). No dynamic data rendering.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| docker-compose.yml YAML is valid | `python -c "import yaml; yaml.safe_load(open('deploy/docker-compose.yml'))"` | Parsed without error | PASS |
| db-init service has correct structure | `python -c "..."` (yaml parse) | `restart: no`, `depends_on: [postgres]`, all 4 app services have `db-init: condition: service_completed_successfully` | PASS |
| Detection table row count | `python` parse of README.md | 24 rows | PASS |
| All binary/tunable classifications correct | `python` comparison vs BINARY_FLAG_TYPES set | 0 mismatches | PASS |
| All default thresholds match calibrate.py | `python` comparison vs DEFAULT_THRESHOLDS dict | 0 mismatches | PASS |

### Probe Execution

No probe scripts defined for this phase. Phase type is documentation + infra config. Step 7c: SKIPPED (no probe scripts).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LICENSE-03 | 31-02 | README displays license badge linked to LICENSE file | SATISFIED | `img.shields.io` badge on line 5, `(LICENSE)` link present |
| DOCS-01 | 31-02 | README banner + tagline at top | SATISFIED | `![Xeter](assets/logo+typo.png)` line 1; tagline line 3 |
| DOCS-02 | 31-01, 31-02 | Quick Start with exact commands | PARTIAL | `generate-secrets.sh`, `docker compose up` present; seeded credentials shown; health check shown. Gap: `git clone <repo-url>` placeholder not substituted |
| DOCS-03 | 31-02 | SDK section with decorator, env vars, example | SATISFIED | Install, `XETER_ENDPOINT`, `XETER_API_KEY`, `@xeter.trace` decorator all present |
| DOCS-04 | 31-02 | Detection Checks table — 24 flag types | SATISFIED | 24-row table; all columns correct; sources verified against calibrate.py |
| DOCS-05 | 31-02 | Calibration section — full workflow | SATISFIED | 4-step workflow including `--reset`, fixture spans, `--flag-type`, env var application |
| DOCS-06 | 31-02 | Pluggable LLM — 3 providers + env vars | SATISFIED | All 3 providers and all 5 env vars documented; Ollama note present |
| DOCS-07 | 31-02 | Performance section — 5 items per REQUIREMENTS.md | PARTIAL | 2 levers documented (WORKER_TRACE_FLUSH_TIMEOUT_S + embedder swap). 3 items omitted: Redis queue sizing, disable unused analyzers, ClickHouse retention. User explicitly authorized this descoping in DISCUSSION-LOG.md and CONTEXT.md D-P-01/D-P-02/D-P-03. ROADMAP SC #5 still says "five levers" and was not updated. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| README.md | 24 | `<repo-url>` unsubstituted placeholder | WARNING | Developer cannot copy git clone command verbatim; Quick Start is broken at step 1 |

No TBD/FIXME/XXX debt markers found in README.md or deploy/docker-compose.yml.

### DOCS-07 Scope Discrepancy — Override Recommendation

REQUIREMENTS.md DOCS-07 and ROADMAP.md SC #5 specify three items not present in the Performance section:
- Redis queue sizing
- Disabling unused analyzers via env flag
- ClickHouse retention policy

The user's explicit decision (DISCUSSION-LOG.md lines 65–76, CONTEXT.md D-P-01/D-P-02/D-P-03) was to scope the Performance section to "only the tunes that are actually present in the code." The "disable unused analyzers" env flag does not exist in the codebase (confirmed in DISCUSSION-LOG.md: "Checked codebase for 'disable unused analyzers' env flag — does not exist"). The ClickHouse retention and Redis queue sizing items are also not implemented.

**This is an intentional deviation.** To accept it, add an override to VERIFICATION.md frontmatter and update REQUIREMENTS.md / ROADMAP.md SC #5 to reflect the actual scope:

```yaml
overrides:
  - must_have: "The Performance section covers all five performance tuning levers per DOCS-07"
    reason: "User decision D-P-01 scoped Performance section to 2 real levers only (WORKER_TRACE_FLUSH_TIMEOUT_S + embedder model swap). Three items in DOCS-07/ROADMAP SC #5 (Redis queue sizing, disable unused analyzers, ClickHouse retention) do not exist in the codebase. Documented in CONTEXT.md and DISCUSSION-LOG.md."
    accepted_by: "{your name}"
    accepted_at: "{ISO timestamp}"
```

### Human Verification Required

#### 1. Banner image renders correctly on GitHub

**Test:** Open the GitHub repository page and verify the banner image renders (not a broken image placeholder).
**Expected:** `assets/logo+typo.png` displays as the first visible element on the README page.
**Why human:** Cannot verify image rendering programmatically from the codebase; requires GitHub page load.

#### 2. All anchor links in Table of Contents resolve correctly

**Test:** Click each of the 9 TOC links in the rendered GitHub README.
**Expected:** Each link scrolls to the corresponding section heading. Pay special attention to `## Multi-Tenancy & Auth` (the anchor includes the `&` character which can cause rendering issues).
**Why human:** GitHub anchor generation for headings with special characters requires visual/interactive verification.

### Gaps Summary

Two gaps found:

**Gap 1 — PARTIAL (WARNING): `<repo-url>` placeholder in Quick Start git clone command**

The Quick Start section at README.md line 24 contains `git clone <repo-url> && cd Xeter`. This is an unsubstituted placeholder. A developer who has never seen the repo cannot find the URL from the README alone, and the command will fail if copied verbatim. Fix: replace `<repo-url>` with the actual repository URL.

**Gap 2 — FAILED (requires override OR scope update): DOCS-07 and ROADMAP SC #5 claim 5 performance levers; README documents 2**

The Performance section correctly documents the only 2 real performance levers in the codebase. The 3 omitted items (Redis queue sizing, disable unused analyzers, ClickHouse retention) do not exist. This is a documented user decision. The gap is that ROADMAP.md SC #5 and REQUIREMENTS.md DOCS-07 were not updated to reflect the descoping decision. Resolution options:
1. Add an override (fastest — documents the accepted deviation)
2. Update ROADMAP.md SC #5 and REQUIREMENTS.md DOCS-07 to match what was built (cleaner audit trail for v1.6 milestone)

---

_Verified: 2026-05-31T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
