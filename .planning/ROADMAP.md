# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- ✅ **v1.2 Diagnosticer** — Phases 11–13 (shipped 2026-04-25)
- ✅ **v1.3 Security Hardening** — Phases 14–17 (shipped 2026-05-02)
- ✅ **v1.4 Trace Hierarchy + TraceAnalyzer Foundation** — Phases 18–21 (shipped 2026-05-15)
- ✅ **v1.5 Silent Failure Detection** — Phases 22–28 (shipped 2026-05-30)
- **v1.6 Release** — Phases 29–31 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–6) — SHIPPED 2026-04-04</summary>

- [x] Phase 1: Foundation (4/4 plans) — completed 2026-03-27
- [x] Phase 2: Ingestion Path (3/3 plans) — completed 2026-03-28
- [x] Phase 3: Analysis Path (4/4 plans) — completed 2026-03-28
- [x] Phase 4: Read Path (3/3 plans) — completed 2026-03-30
- [x] Phase 5: Dashboard (4/4 plans) — completed 2026-03-31
- [x] Phase 6: Validation (3/3 plans) — completed 2026-04-04

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.1 Analyser Accuracy (Phases 7–10) — SHIPPED 2026-04-18</summary>

- [x] Phase 7: wrong_args Rewrite (5/5 plans) — completed 2026-04-06
- [x] Phase 8: wrong_tool Rewrite (3/3 plans) — completed 2026-04-18
- [x] Phase 9: no_tool_used + wrong_tool_choice (1/1 plan) — completed 2026-04-18
- [x] Phase 10: unnecessary_tool_call (1/1 plan) — completed 2026-04-18

See `.planning/milestones/v1.1-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.2 Diagnosticer (Phases 11–13) — SHIPPED 2026-04-25</summary>

- [x] Phase 11: Diagnosticer Backend (4/4 plans) — completed 2026-04-22
- [x] Phase 12: Presenter Integration (2/2 plans) — completed 2026-04-23
- [x] Phase 13: Frontend Diagnosis UI (2/2 plans) — completed 2026-04-25

See `.planning/milestones/v1.2-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.3 Security Hardening (Phases 14–17) — SHIPPED 2026-05-02</summary>

- [x] Phase 14: DB Foundation (3/3 plans) — completed 2026-04-29
- [x] Phase 15: Secrets Hygiene (3/3 plans) — completed 2026-04-29
- [x] Phase 16: Auth Hardening (5/5 plans) — completed 2026-04-30
- [x] Phase 17: GDPR Data Deletion (1/1 plan) — completed 2026-04-30

See `.planning/milestones/v1.3-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.4 Trace Hierarchy + TraceAnalyzer Foundation (Phases 18–21) — SHIPPED 2026-05-15</summary>

- [x] Phase 18: Cleanup + BaseAnalyzer Refactor (2/2 plans) — completed 2026-05-14
- [x] Phase 19: TraceAnalyzer Scaffold + DB Migration (3/3 plans) — completed 2026-05-14
- [x] Phase 20: Trace API (2/2 plans) — completed 2026-05-15
- [x] Phase 21: Trace UI (4/4 plans) — completed 2026-05-15

See `.planning/milestones/v1.4-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.5 Silent Failure Detection (Phases 22–28) — SHIPPED 2026-05-30</summary>

- [x] Phase 22: Bug Fixes (2/2 plans) — completed 2026-05-19
- [x] Phase 23: Infrastructure (3/3 plans) — completed 2026-05-20
- [x] Phase 24: Structural Span Checks (3/3 plans) — completed 2026-05-21
- [x] Phase 25: Semantic Span + Structural Trace Checks (5/5 plans) — completed 2026-05-24
- [x] Phase 26: Best-Effort Proxy Checks (3/3 plans) — completed 2026-05-26
- [x] Phase 27: Calibration Pass (3/3 plans) — completed 2026-05-30
- [x] Phase 28: Precision Improvements (4/4 plans) — completed 2026-05-30

See `.planning/milestones/v1.5-ROADMAP.md` for full phase details.

</details>

### v1.6 Release (Phases 29–31)

- [x] **Phase 29: License, Assets & Cleanup** — Apply GPL-3.0 + Commons Clause, move assets, delete dev artifacts (completed 2026-05-30)
- [x] **Phase 30: Diagnosticer Prompt** — Extract and rewrite the diagnosticer prompt with system message + CoT scaffold (completed 2026-05-31)
- [ ] **Phase 31: README Overhaul** — Comprehensive public README covering all 24 checks, install, SDK, calibration, LLM config, optimization

## Phase Details

*(All v1.0–v1.5 phase details archived to their respective milestone ROADMAP files.)*

### Phase 29: License, Assets & Cleanup

**Goal**: Repo is legally licensed and clean for public release — LICENSE file present, SPDX headers in source, assets folder organized, and dead dev artifacts deleted
**Depends on**: Nothing (first v1.6 phase; all tasks are independent file operations)
**Requirements**: LICENSE-01, LICENSE-02, ASSETS-01, CLEAN-01, CLEAN-02
**Success Criteria** (what must be TRUE):
  1. A `LICENSE` file exists at repo root containing GPL-3.0 full text followed by the Commons Clause 1.0 addendum; `grep "Commons Clause"` in the file returns a match
  2. Every top-level Python source file across analyser, presenter, worker, diagnosticer, and SDK has an SPDX header line at the top (`SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0`)
  3. `assets/logo+typo.png` exists; `logo+typo.png` no longer exists at repo root; `.gitignore` and any path references reflect the new location
  4. `check_tier4.py` is absent from the repo root (deleted, not just moved)
  5. `VALIDATION-REPORT.md` is absent from the repo root (deleted, not just moved)
**Plans**: 3 plans
Plans:
- [x] 29-01-PLAN.md � Write GPL-3.0 + Commons Clause LICENSE file at repo root
- [x] 29-02-PLAN.md � Create assets/, move logo, delete check_tier4.py and VALIDATION-REPORT.md
- [x] 29-03-PLAN.md � Add SPDX headers to all substantive Python source files

### Phase 30: Diagnosticer Prompt

**Goal**: The diagnosticer prompt is a maintainable, human-readable file with structured reasoning guidance — not a raw string buried in Python source
**Depends on**: Phase 29
**Requirements**: DIAG-01, DIAG-02
**Success Criteria** (what must be TRUE):
  1. `xeter/services/diagnosticer/prompt.md` exists and contains the complete prompt text (system message section, CoT scaffold, verdict decision criteria for all four verdicts, severity calibration guidance)
  2. `context_assembly.py:_format_context()` no longer contains an inline prompt string — it reads `prompt.md` at import time and performs span-data substitution from that template
  3. The system message section clearly frames the diagnosticer's role (root-cause analysis, not general Q&A)
  4. The chain-of-thought scaffold walks through each flag before reaching a verdict, with explicit decision criteria distinguishing `model`, `architecture`, `prompt`, and `unknown`
**Plans**: 2 plans
Plans:
- [x] 30-01-PLAN.md — Extract prompt f-string into prompt.md, read at import + format_map substitution, add test_context_assembly.py (DIAG-01)
- [x] 30-02-PLAN.md — Rewrite prompt.md with system message, CoT scaffold, four-verdict criteria, severity calibration + content tests (DIAG-02)

### Phase 31: README Overhaul

**Goal**: Any developer can find Xeter, understand what it does, deploy it locally, instrument their agent, and understand every detection check — without reading source code
**Depends on**: Phase 30 (banner path and prompt file must exist before README references them)
**Requirements**: LICENSE-03, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06, DOCS-07
**Success Criteria** (what must be TRUE):
  1. README renders a banner (`assets/logo+typo.png`), a one-sentence tagline, and a license badge linked to the LICENSE file — visible at the top of the GitHub repo page
  2. A developer who has never seen the repo can run `generate-secrets.sh && docker compose up` and reach a healthy dashboard using only the README Quick Start section (all exact commands present, no steps omitted)
  3. The SDK section shows a complete, copy-pasteable instrumentation example including install command, `@xeter_sdk.trace` decorator usage, and the two required env vars (`XETER_ENDPOINT`, `XETER_API_KEY`)
  4. The Detection Checks section contains a table listing all 24 flag types with analyzer class, description, threshold type (binary / tunable), and default threshold value — a developer can determine the check's behavior without reading source
  5. The Calibration, Pluggable LLM, and Performance sections each cover their topic completely: calibration workflow, all three LLM provider env vars, and all five performance tuning levers
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 4/4 | Complete | 2026-03-27 |
| 2. Ingestion Path | v1.0 | 3/3 | Complete | 2026-03-28 |
| 3. Analysis Path | v1.0 | 4/4 | Complete | 2026-03-28 |
| 4. Read Path | v1.0 | 3/3 | Complete | 2026-03-30 |
| 5. Dashboard | v1.0 | 4/4 | Complete | 2026-03-31 |
| 6. Validation | v1.0 | 3/3 | Complete | 2026-04-04 |
| 7. wrong_args Rewrite | v1.1 | 5/5 | Complete | 2026-04-06 |
| 8. wrong_tool Rewrite | v1.1 | 3/3 | Complete | 2026-04-18 |
| 9. no_tool_used + wrong_tool_choice | v1.1 | 1/1 | Complete | 2026-04-18 |
| 10. unnecessary_tool_call | v1.1 | 1/1 | Complete | 2026-04-18 |
| 11. Diagnosticer Backend | v1.2 | 4/4 | Complete | 2026-04-22 |
| 12. Presenter Integration | v1.2 | 2/2 | Complete | 2026-04-23 |
| 13. Frontend Diagnosis UI | v1.2 | 2/2 | Complete | 2026-04-25 |
| 14. DB Foundation | v1.3 | 3/3 | Complete | 2026-04-29 |
| 15. Secrets Hygiene | v1.3 | 3/3 | Complete | 2026-04-29 |
| 16. Auth Hardening | v1.3 | 5/5 | Complete | 2026-04-30 |
| 17. GDPR Data Deletion | v1.3 | 1/1 | Complete | 2026-04-30 |
| 18. Cleanup + BaseAnalyzer Refactor | v1.4 | 2/2 | Complete | 2026-05-14 |
| 19. TraceAnalyzer Scaffold + DB Migration | v1.4 | 3/3 | Complete | 2026-05-14 |
| 20. Trace API | v1.4 | 2/2 | Complete | 2026-05-15 |
| 21. Trace UI | v1.4 | 4/4 | Complete | 2026-05-15 |
| 22. Bug Fixes | v1.5 | 2/2 | Complete | 2026-05-19 |
| 23. Infrastructure | v1.5 | 3/3 | Complete | 2026-05-20 |
| 24. Structural Span Checks | v1.5 | 3/3 | Complete | 2026-05-21 |
| 25. Semantic Span + Structural Trace Checks | v1.5 | 5/5 | Complete | 2026-05-24 |
| 26. Best-Effort Proxy Checks | v1.5 | 3/3 | Complete | 2026-05-26 |
| 27. Calibration Pass | v1.5 | 3/3 | Complete | 2026-05-30 |
| 28. Precision Improvements | v1.5 | 4/4 | Complete | 2026-05-30 |
| 29. License, Assets & Cleanup | v1.6 | 3/3 | Complete    | 2026-05-30 |
| 30. Diagnosticer Prompt | v1.6 | 2/2 | Complete    | 2026-05-31 |
| 31. README Overhaul | v1.6 | 0/TBD | Not started | - |
