# Phase 28: Precision Improvements - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix algorithm precision for 14 flag types identified during the Phase 27 calibration run. All fixes are internal to existing `_check_*()` methods — no new analyzers, no new flag types, no architectural changes. After fixes, all 14 types are re-calibrated and the full-suite mean precision target (≥ 95%) becomes achievable for Phase 27 plan 27-03.

</domain>

<decisions>
## Implementation Decisions

### Scope Constraint
- **D-01:** No architectural changes. Fixes stay inside existing `_check_*()` methods in `xeter/services/worker/trace_analyzer.py`, `xeter/services/worker/tool_call_analyzer.py`, and `xeter/services/worker/semantic_span_analyzer.py`.
- **D-02:** No new dependencies. Use libraries already in the environment (rapidfuzz, spaCy, sklearn/cosine, tiktoken).
- **D-03:** No new flag types. The 14 types being fixed already exist; the goal is precision, not new detection.

### Tier 1 — Broken (P=0, needs root cause debug)
- **D-04:** `tool_not_available` produces P=0. Root cause unknown — investigate `_check_tool_not_available()` in `tool_call_analyzer.py`. May be a scoring bug, a fixture mismatch, or a logic error.

### Tier 2 — Scale Mismatch (math bug)
- **D-05:** `stale_context` and `step_repetition` both use `fuzz.ratio()` which returns 0–100, but the hill-climb threshold is on the 0.0–0.95 scale. The comparison `score >= threshold` is always True since any fuzz score >> 0.95. Fix: normalize by dividing fuzz output by 100 before storing/comparing, so scores are on the same 0.0–1.0 scale as all other metrics.
- **D-06:** `termination_loop` grid sweep over n=[2,3,4,5] shows no influence of n on precision (P=0.208 at n=5). Fix: investigate the consecutive-repeat counting logic in `_check_termination_loop()` — the n gate may not be enforced correctly (e.g., counting total calls instead of consecutive).

### Tier 3 — Algorithm Too Broad (fires on almost everything)
- **D-07:** `missing_details` P=0.012 — fires on nearly every span. The NLP check for entity coverage in the response is too permissive. Needs tighter conditions: require a minimum number of entities in the prompt before flagging, or raise the coverage-deficit threshold.
- **D-08:** `no_verification` P=0.025 — keyword-absence check fires on ~97.5% of all spans. Needs stronger preconditions: only flag traces where a verification-like tool call was expected (e.g., trace contains a write/mutate tool call, so verification was warranted).

### Tier 4 — Precision Too Low (FP-heavy)
- **D-09:** `context_propagation_failure` P=0.25 — cosine similarity drops too often on clean spans. Tighten by requiring the similarity drop to be sustained across multiple span hops, not just a single span pair.
- **D-10:** `wrong_agent_handoff` P=0.3 — graph membership check too broad. Review the routing graph logic: should only fire when the handoff edge does NOT exist in the configured graph, but may be firing when graph is sparse/empty.
- **D-11:** `wrong_tool_choice` P=0.3, R=0.818 — was higher before the fixture was extended. FP rate increased with more clean spans. Tighten the tool-coherence scoring to require a larger gap between the chosen tool's score and the best alternative.
- **D-12:** `history_loss` P=0.4 — cosine centroid divergence too easily triggered on clean spans. Add a minimum span count gate (e.g., require ≥ 3 prior spans before flagging) and/or raise the divergence threshold.
- **D-13:** `information_withholding` P=0.444 — NE recall ratio too easily triggered. Tighten: only flag when the ratio drop is significant (e.g., > 50% entities withheld) AND the prior span had a non-trivial NE count.
- **D-14:** `wrong_tool_args` P=0.455 (was 0.882 before fixture extension) — more clean spans exposed FPs. Investigate which clean-span types the checker misfires on; likely needs a tighter argument-mismatch signal.
- **D-15:** `response_anomaly` P=0.458 (was 0.818) — same regression pattern as wrong_tool_args. Tighten the anomaly scoring to reduce false positives on normal spans.
- **D-16:** `conversation_reset` P=0.6 — best of the bad lot. Cosine centroid drop check; may benefit from requiring the drop to occur after a minimum trace length and to be more abrupt (larger delta in a single step).

### Calibration After Fixes
- **D-17:** After all algorithm fixes, re-run `python -m xeter.scripts.calibrate --flag-type <type>` for each fixed type and verify: precision improved, recall ≥ 0.10 (recall floor not violated), no RECALL FLOOR ERROR.
- **D-18:** Final full-suite run (`python -m xeter.scripts.calibrate`) after all 14 types are fixed to confirm mean precision ≥ 95%. This is the prerequisite for Phase 27 plan 27-03.

### Claude's Discretion
- Order of fixes within the phase (suggest: Tier 1 first, then Tier 2, then Tier 3, then Tier 4).
- Whether to fix each type in its own plan or batch related types together.
- Exact threshold values — the calibration run determines these, not the plan.
- Test strategy for verifying precision improvements (calibration run is the acceptance test).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Analyzer implementations (files to fix)
- `xeter/services/worker/trace_analyzer.py` — TraceAnalyzer: contains `_check_*()` for stale_context, step_repetition, termination_loop, context_propagation_failure, history_loss, information_withholding, conversation_reset, wrong_agent_handoff, no_verification, incomplete_verification, clarification_skipped
- `xeter/services/worker/tool_call_analyzer.py` — ToolCallAnalyzer: contains `_check_*()` for tool_not_available, wrong_tool_choice, wrong_tool_args, unnecessary_tool_call, no_tool, response_anomaly
- `xeter/services/worker/semantic_span_analyzer.py` — SemanticSpanAnalyzer: contains `_check_missing_details()`

### Calibration infrastructure
- `xeter/scripts/calibrate.py` — hill-climb calibration harness; `hill_climb()`, `evaluate_flag_type()`, `BINARY_FLAG_TYPES`, `DEFAULT_THRESHOLDS`, `FLAG_TYPE_TO_ANALYZER_CLASS`
- `fixtures/labelled_spans.jsonl` — 738-row calibration fixture (anomaly_type names now correct after Phase 27 fixture fix)
- `fixtures/calibrated_thresholds.json` — current calibrated thresholds; updated after each per-type fix

### Phase history
- `.planning/phases/27-calibration-pass/27-02-SUMMARY.md` — Phase 27 calibration results and known issues (scale mismatch for stale_context/step_repetition, fuzz.ratio 0–100 issue)
- `.planning/STATE.md` — current milestone state

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hill_climb()` in `calibrate.py` — re-run per type after each fix to verify precision improved
- `evaluate_flag_type()` in `calibrate.py` — single-threshold P/R evaluation; use `--eval-only` for binary types
- `fuzz.ratio()` (rapidfuzz) — currently misused at 0–100 scale in stale_context and step_repetition; must normalize to 0–1

### Established Patterns
- All `_check_*()` methods return `list[Flag]`; scores are logged via `log_score()` before the flag/clean decision
- Binary types (BINARY_FLAG_TYPES) produce only 0.0/1.0 scores — no threshold tuning needed
- Threshold-tunable types read their threshold from `self._thresholds[flag_type]` at evaluation time
- `low_confidence: true` is set in flag detail for best-effort checks (wrong_agent_handoff, conversation_reset, clarification_skipped)

### Integration Points
- `calibrate.py` re-runs must be done after each fix to confirm improvement and update `calibrated_thresholds.json`
- `xeter/tests/test_calibrate_routing.py` (28 tests) must stay green throughout — routing tests do not test precision but ensure the check infrastructure is wired correctly

</code_context>

<specifics>
## Specific Ideas

- The fuzz.ratio scale bug (D-05) is the highest-confidence fix: dividing by 100 is a one-liner and should immediately resolve the "threshold has no effect" symptom for stale_context and step_repetition.
- For wrong_tool_choice regression (D-11): the fixture now has 11 correct wrong_tool_choice entries + 10 unnecessary_tool_call entries (fixed in Phase 27 fixture patch). The larger clean pool (539 rows vs ~20 before) exposes FPs that were hidden before. The signal itself may be fine; the threshold just needs recalibration with the full fixture.
- tool_not_available (D-04) had P=0 with the embedder running — this suggests the analyzer method may be broken (not just a fixture issue), since the fixture does have tool_not_available entries.

</specifics>

<deferred>
## Deferred Ideas

- Adding new fixture rows for types with only 8–10 flagged examples (if precision target still not met after algorithm fixes) — belongs in a follow-up calibration phase if needed.
- Fixture quality improvements (more diverse clean spans, adversarial examples) — post-Phase-28.
- Plan 27-03 (full-suite calibration run + docker-compose WORKER_THRESHOLD_* patch) — blocked on this phase; runs after Phase 28 is complete.

</deferred>

---

*Phase: 28-precision-improvements*
*Context gathered: 2026-05-28*
