# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- ✅ **v1.1 Analyser Accuracy** — Phases 7–10 (shipped 2026-04-18)
- 📋 **v1.2 Diagnosticer** — Phases 11–13 (in progress)

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

### 📋 v1.2 Diagnosticer (Phases 11–13)

- [x] Phase 11: Diagnosticer Backend (0/4 plans) — not started (completed 2026-04-22)
- [ ] Phase 12: Presenter Integration (0/? plans) — not started
- [ ] Phase 13: Frontend Diagnosis UI (0/? plans) — not started

#### Phase 11: Diagnosticer Backend

**Goal:** Implement core Diagnosticer service — `diagnoses` table + DAL, LLM context assembly, configurable provider/model via env vars, root-cause analysis logic
**Depends on:** Phase 10
**Plans:** 4/4 plans complete

Plans:
- [ ] 11-01-PLAN.md — DB foundation: diagnoses table migration, Diagnosis ORM model, LLM SDK deps
- [ ] 11-02-PLAN.md — LLM provider factory: AnthropicProvider, OpenAIProvider, OllamaProvider
- [ ] 11-03-PLAN.md — DAL + context assembly: DiagnosisRepository, assemble_context()
- [ ] 11-04-PLAN.md — Endpoint wire-up: real POST /diagnose + unit tests

#### Phase 12: Presenter Integration

**Goal:** Wire Presenter to Diagnosticer — trigger endpoint, retrieve endpoint, inter-service communication
**Depends on:** Phase 11
**Plans:** 0 plans

Plans:
- [ ] TBD (run `/gsd:plan-phase 12` to break down)

#### Phase 13: Frontend Diagnosis UI

**Goal:** SpanDetailPanel "Diagnose" button + structured diagnosis display (verdict, severity, affected field, recommended fix)
**Depends on:** Phase 12
**Plans:** 0 plans

Plans:
- [ ] TBD (run `/gsd:plan-phase 13` to break down)

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
| 11. Diagnosticer Backend | 4/4 | Complete    | 2026-04-22 | — |
| 12. Presenter Integration | v1.2 | 0/? | Not started | — |
| 13. Frontend Diagnosis UI | v1.2 | 0/? | Not started | — |
