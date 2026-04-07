# Roadmap: Xeter

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-04)
- 🚧 **v1.1 Analyser Accuracy** — Phases 7–10 (in progress)

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

### 🚧 v1.1 Analyser Accuracy (In Progress)

**Milestone Goal:** Replace the four conceptually-wrong heuristic check methods in ToolCallAnalyzer with research-backed implementations — one method at a time. Each phase ends with a per-method calibration run that must pass P/R benchmarks before the next phase begins.

- [x] **Phase 7: wrong_args Rewrite** - `_check_wrong_args` redesigned with output-error priority + flattened embedding, calibration infra updated, and hybrid scoring utility in place
- [ ] **Phase 8: wrong_tool Rewrite** - `_check_wrong_tool` redesigned with two-gate logic (rank floor + gap), calibrated against P/R benchmark
- [ ] **Phase 9: no_tool + tool_use_violation Split** - `_check_no_tool` redesigned against available_tools; `_check_tool_use_violation` extracted as keyword-regex-only method, both calibrated
- [ ] **Phase 10: excessive_tool Rewrite** - `_check_excessive_tool` redesigned with necessity delta signal, calibrated against P/R benchmark

## Phase Details

### Phase 7: wrong_args Rewrite
**Goal**: `_check_wrong_args` produces trustworthy flags backed by output error patterns and correctly-embedded argument values; shared hybrid scoring utility exists for all subsequent phases; calibration script supports binary flags and per-method runs
**Depends on**: Phase 6 (v1.0 complete — ToolCallAnalyzer and calibrate.py exist)
**Requirements**: HYBRID-01, ARGS-01, ARGS-02, ARGS-03, ARGS-04, ARGS-05, ARGS-06, CAL-01, CAL-02
**Success Criteria** (what must be TRUE):
  1. A span with a tool_output containing an error pattern (e.g., "invalid argument", HTTP 4xx) is flagged as `wrong_args` without any embedding computation
  2. A span whose flattened argument values are semantically mismatched with the prompt is flagged using hybrid (50/50 cosine + BOW) scoring; a span with empty or all-numeric flattened values is not sent to the embedding path
  3. `low_confidence: True` is absent from all `wrong_args` flag details
  4. Running `calibrate.py --flag-type wrong_tool_args` in isolation completes and reports P/R metrics without crashing
  5. Running `calibrate.py` with a binary flag type (e.g., `tool_use_violation`) skips the numeric sweep and reports correctly
**Plans**: 5 plans

Plans:
- [x] 07-01-PLAN.md — Calibration infrastructure: BINARY_FLAG_TYPES set + --flag-type arg for calibrate.py (CAL-01, CAL-02)
- [x] 07-02-PLAN.md — Hybrid scoring utility: bow_score + hybrid_score in base.py (HYBRID-01)
- [x] 07-03-PLAN.md — wrong_args rewrite: error-priority path + flattened-values hybrid scoring, remove low_confidence (ARGS-01 to ARGS-05)
- [x] 07-04-PLAN.md — Schema file v0: draft detection_patterns.yml; user reviews and approves (NOTOOL-04/06 prep)
- [x] 07-05-PLAN.md — Calibration run: wrong_tool_args calibration — threshold=0.30, P=0.40, R=0.90; ARGS-06 satisfied

### Phase 8: wrong_tool Rewrite
**Goal**: `_check_wrong_tool` flags spans where the model called a tool that is not the best match for the prompt, using single-threshold logic on top1 tool score; also flags immediately when a tool was called but no tools were available
**Depends on**: Phase 7
**Requirements**: WTOOL-01, WTOOL-02, WTOOL-03, WTOOL-04, WTOOL-05, WTOOL-06
**Success Criteria** (what must be TRUE):
  1. A span where top1_score >= `wrong_tool_called` and the top-ranked tool differs from the called tool is flagged; a span where top1_score < `wrong_tool_called` (no tool was appropriate) is also flagged; reported score is top1_score
  2. A span where a tool is called but `available_tools` is None or empty is immediately flagged (no threshold check needed)
  3. The threshold key `wrong_tool_called` appears in `calibrated_thresholds.json` after calibration
  4. Running `calibrate.py --flag-type wrong_tool` completes; calibration maximizes recall (minimize false negatives) while keeping precision as high as possible; both P and R are reported
  5. A span previously suppressed by the inverted AND gate (high top-score span with a wrong tool) is now correctly flagged
**Plans**: 3 plans

Plans:
- [ ] 08-01-PLAN.md — wrong_tool rewrite: three-branch logic, threshold key rename across 5 files, 4 new unit tests (WTOOL-01, WTOOL-02, WTOOL-03, WTOOL-04, WTOOL-05)
- [ ] 08-02-PLAN.md — Algorithm review: user inspects implementation and approves before calibration runs (WTOOL-01, WTOOL-02, WTOOL-03, WTOOL-04)
- [ ] 08-03-PLAN.md — Calibration run: fixture augmentation + wrong_tool calibration passes P/R benchmark (WTOOL-06)

### Phase 9: no_tool + tool_use_violation Split
**Goal**: The single `_check_no_tool` method is split into two independently-calibrated methods — one for capability gaps (tool needed, none called) using available_tools similarity, and one for explicit prohibition violations using keyword regex; both pass P/R benchmarks
**Depends on**: Phase 8
**Requirements**: NOTOOL-01, NOTOOL-02, NOTOOL-03, NOTOOL-04, NOTOOL-05, NOTOOL-06, NOTOOL-07, NOTOOL-08
**Success Criteria** (what must be TRUE):
  1. A span where the prompt semantically overlaps with at least one available tool (max hybrid score > threshold) and no tool was called is flagged as `no_tool`; a span with no available_tools is not flagged
  2. A span where the prompt contains a prohibition phrase ("do not use tools") and a tool was called is flagged as `tool_use_violation`; a span where no tool was called is not flagged by `_check_tool_use_violation`
  3. The detection patterns file (YAML or JSON) exists on disk, is reviewed and approved by user before implementation, and the check reads patterns from it at init without code changes needed to add a new pattern
  4. Running `calibrate.py --flag-type no_tool` and `calibrate.py --flag-type tool_use_violation` each complete; `tool_use_violation` uses proximity-based scoring through the P/R sweep (not excluded as binary)
  5. Both `no_tool` and `tool_use_violation` achieve >= 80% precision on their respective labelled sets
**Plans**: TBD

Plans:
- [ ] 09-01: Schema file final approval — user reviews and approves patterns file before implementation begins (NOTOOL-04, NOTOOL-06)
- [ ] 09-02: no_tool rewrite — max hybrid similarity against available_tools (NOTOOL-01, NOTOOL-02)
- [ ] 09-03: tool_use_violation extraction — new method with windowed proximity detection (NOTOOL-03, NOTOOL-05), calibrate.py proximity scoring (NOTOOL-07)
- [ ] 09-04: Calibration run — no_tool and tool_use_violation calibration both pass P/R benchmark (NOTOOL-08)

### Phase 10: excessive_tool Rewrite
**Goal**: `_check_excessive_tool` identifies spans where the prompt did not require any tool call, using a necessity delta signal that measures how much more the prompt resembles "answer directly" than "use a tool"; the method calibrates cleanly and does not double-fire with wrong_tool
**Depends on**: Phase 9
**Requirements**: EXTOOL-01, EXTOOL-02, EXTOOL-03, EXTOOL-04
**Success Criteria** (what must be TRUE):
  1. A span whose prompt is clearly answerable without external tools (necessity_delta < threshold) is flagged as `excessive_tool`; a span where wrong_tool already fired on the same span is not flagged by `_check_excessive_tool`
  2. When tool_output is available, `prompt_vs_tool_output_overlap` is logged as a secondary metric in the flag detail but does not control whether the flag fires
  3. The threshold direction is documented in code: negative necessity_delta values trigger the flag (inverted convention vs other thresholds)
  4. Running `calibrate.py --flag-type excessive_tool` completes and the resulting `excessive_tool_delta` threshold achieves >= 80% precision on labelled spans
**Plans**: TBD

Plans:
- [ ] 10-01: excessive_tool rewrite — necessity delta signal (EXTOOL-01), secondary overlap signal (EXTOOL-02), threshold direction documentation (EXTOOL-03)
- [ ] 10-02: Schema file final review — post-implementation pass over all patterns; user approves final state
- [ ] 10-03: Calibration run — excessive_tool calibration passes P/R benchmark; full suite run across all v1.1 methods (EXTOOL-04)

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
| 8. wrong_tool Rewrite | 1/3 | In Progress|  | - |
| 9. no_tool + tool_use_violation Split | v1.1 | 0/4 | Not started | - |
| 10. excessive_tool Rewrite | v1.1 | 0/3 | Not started | - |
