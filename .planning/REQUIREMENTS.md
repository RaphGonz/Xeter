# Requirements: Xeter v1.1 Analyser Accuracy

**Defined:** 2026-04-06
**Core Value:** When a tool call fails, tell the developer whether it was the model, the architecture, or the prompt — and why.

## v1.1 Requirements

Redesign the four conceptually-wrong heuristic check methods in `ToolCallAnalyzer`. Each method is independently run on the same span — no cross-method logic or double-flagging guards. Each phase ends with a per-method calibration run that must pass P/R benchmarks before the next phase begins.

Untouched: `_check_parsing_error`, `_check_response_anomaly`.

### Cross-cutting

- [x] **HYBRID-01**: Shared hybrid scoring utility — 50/50 blend of cosine similarity (embedding) and bag-of-words score (token overlap / BM25) used by all similarity-based checks

### wrong_args Rewrite

- [ ] **ARGS-01**: Detects bad arguments via tool_output error pattern matching (regex, no embedding, fires first)
- [ ] **ARGS-02**: Detects semantic mismatch by embedding flattened argument *values* (not raw JSON string)
- [ ] **ARGS-03**: Uses hybrid scoring (50/50 embed + BOW) for the semantic path
- [ ] **ARGS-04**: Skips semantic check when flattened values are empty or all-numeric
- [ ] **ARGS-05**: `low_confidence: True` removed from flag detail
- [ ] **ARGS-06**: Per-method calibration run passes P/R benchmark before next phase

### wrong_tool Rewrite

- [ ] **WTOOL-01**: Two-gate logic: floor gate (ranking is trustworthy) + gap gate (top_tool − called_tool margin)
- [ ] **WTOOL-02**: Reported score is the gap, not top_score
- [ ] **WTOOL-03**: Skips check when available_tools is None or empty
- [ ] **WTOOL-04**: Uses hybrid scoring (50/50) for prompt vs tool similarity comparisons
- [ ] **WTOOL-05**: Three threshold keys: `wrong_tool_gap`, `wrong_tool_rank_floor`, `wrong_tool_called`
- [ ] **WTOOL-06**: Per-method calibration run passes P/R benchmark before next phase

### no_tool + tool_use_violation Split

- [ ] **NOTOOL-01**: `_check_no_tool` uses max hybrid similarity (prompt vs each available_tool name+description), flags if max > threshold and no tool was called
- [ ] **NOTOOL-02**: `_check_no_tool` skips when available_tools is None or empty
- [ ] **NOTOOL-03**: `_check_tool_use_violation` uses windowed proximity detection — finds tool-triggering terms in prompt, checks if a negation motif appears within 1–4 words before it; score based on proximity distance (1 word away = highest confidence)
- [ ] **NOTOOL-04**: Detection patterns (negation motifs + tool-triggering terms) stored in an external schema file (YAML/JSON), editable without code rebuild
- [ ] **NOTOOL-05**: `_check_tool_use_violation` fires only when `span.tool_name` is not None (a tool was actually called)
- [ ] **NOTOOL-06**: Schema file reviewed and approved by user before implementation begins
- [ ] **NOTOOL-07**: `calibrate.py` handles `tool_use_violation` scoring (proximity-based, not binary — stays in P/R sweep)
- [ ] **NOTOOL-08**: Per-method calibration run passes P/R benchmark before next phase

### excessive_tool Rewrite

- [ ] **EXTOOL-01**: Necessity delta signal — hybrid similarity (prompt vs "use a tool" reference) minus hybrid similarity (prompt vs "answer directly" reference); flags when delta is negative
- [ ] **EXTOOL-02**: `prompt_vs_tool_output_overlap` logged as secondary signal (calibration data only, not flagged in v1.1)
- [ ] **EXTOOL-03**: Threshold direction documented: necessity_delta flags on negative values (inverted vs other thresholds)
- [ ] **EXTOOL-04**: Per-method calibration run passes P/R benchmark before next phase

### Calibration Infrastructure

- [ ] **CAL-01**: `calibrate.py` supports `"binary": true` per flag type to exclude from numeric P/R sweep
- [ ] **CAL-02**: `calibrate.py` supports per-method mode — calibrate a single flag_type in isolation

## Future Requirements

### Diagnosticer

- LLM-powered root cause analysis (reads full trace + flags, returns model/architecture/prompt diagnosis)
- Trace-level aggregation for excessive tool use patterns (cross-span signal, belongs in Diagnosticer not Analyzer)

### Other

- TypeScript SDK
- Cloud deployment (SaaS hosting)
- SSE push events for real-time flag updates
- Trace tree visualization
- Alerting on flag thresholds

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cross-span aggregation in Analyzer | Trace-level analysis is the Diagnosticer's job |
| Double-flagging guards between methods | Methods are independent; a span can legitimately trigger multiple flags |
| LLM-as-a-judge for wrong_args | Most accurate approach but belongs in Diagnosticer, not heuristic worker |
| Changing embedding model | all-MiniLM-L6-v2 stays; hybrid signal improves it sufficiently |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HYBRID-01 | Phase 7 | Complete |
| ARGS-01 | Phase 7 | Pending |
| ARGS-02 | Phase 7 | Pending |
| ARGS-03 | Phase 7 | Pending |
| ARGS-04 | Phase 7 | Pending |
| ARGS-05 | Phase 7 | Pending |
| ARGS-06 | Phase 7 | Pending |
| WTOOL-01 | Phase 8 | Pending |
| WTOOL-02 | Phase 8 | Pending |
| WTOOL-03 | Phase 8 | Pending |
| WTOOL-04 | Phase 8 | Pending |
| WTOOL-05 | Phase 8 | Pending |
| WTOOL-06 | Phase 8 | Pending |
| NOTOOL-01 | Phase 9 | Pending |
| NOTOOL-02 | Phase 9 | Pending |
| NOTOOL-03 | Phase 9 | Pending |
| NOTOOL-04 | Phase 9 | Pending |
| NOTOOL-05 | Phase 9 | Pending |
| NOTOOL-06 | Phase 9 | Pending |
| NOTOOL-07 | Phase 9 | Pending |
| NOTOOL-08 | Phase 9 | Pending |
| EXTOOL-01 | Phase 10 | Pending |
| EXTOOL-02 | Phase 10 | Pending |
| EXTOOL-03 | Phase 10 | Pending |
| EXTOOL-04 | Phase 10 | Pending |
| CAL-01 | Phase 7 | Pending |
| CAL-02 | Phase 7 | Pending |

**Coverage:**
- v1.1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-06*
*Last updated: 2026-04-06 after initial definition*
