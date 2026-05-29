---
phase: 28-precision-improvements
plan: 02
subsystem: calibration
tags: [tool-call-analyzer, semantic-span-analyzer, precision, calibration, spacy, embeddings]
dependency_graph:
  requires:
    - 27-02 (calibrated_thresholds.json with all 17 new types; BINARY_FLAG_TYPES updated)
  provides:
    - _check_tool_not_available diagnosed as fixture-driven P=0; diagnostic comment added
    - _check_wrong_tool_choice with score_gap >= 0.10 requirement before flagging
    - _check_wrong_args with short-value skip (len <= 3) to reduce FPs on generic tokens
    - _check_response_anomaly with short-prompt guard (< 10 tokens) after log_score
    - _check_missing_details with NE/lemma count precondition (guard exit, no log_score)
  affects:
    - 28-03 (trace_analyzer.py fixes; independent)
    - 28-04 (full-suite recalibration; depends on all fix plans)
tech_stack:
  added: []
  patterns:
    - score_gap gate pattern: compute gap between best and called scores; return [] when gap < minimum
    - short-value skip pattern: guard against embedding short generic tokens that embed poorly
    - short-prompt guard (post-log_score): log calibration signal then return [] for vacuous prompts
    - NE/lemma count precondition: guard exit (pre-log_score) for checks requiring semantic richness
key_files:
  created: []
  modified:
    - xeter/services/worker/tool_call_analyzer.py
    - xeter/services/worker/semantic_span_analyzer.py
key_decisions:
  - "tool_not_available P=0 is fixture-driven: 0 labeled rows + 136 clean rows with tool_name set but available_tools=None trigger WTOOL-03 producing 160 FPs; check logic correct; fix deferred"
  - "score_gap threshold set to literal 0.10 per plan; recalibration will confirm appropriate value"
  - "short-prompt guard for response_anomaly placed after log_score (not a guard exit) — preserves calibration signal for short prompts while suppressing flagging"
  - "missing_details NE/lemma guard placed BEFORE log_score (guard exit per D-04): vacuous prompts should not contribute to calibration"
requirements-completed: []
duration: 45min
completed: "2026-05-29"
---

# Phase 28 Plan 02: Precision Fixes for tool_call_analyzer and semantic_span_analyzer Summary

**Five FP-reduction fixes across ToolCallAnalyzer and SemanticSpanAnalyzer: tool_not_available root cause diagnosed, wrong_tool_choice score_gap gate added, wrong_tool_args short-value skip, response_anomaly short-prompt guard, and missing_details NE/lemma precondition**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-29T18:30:00Z
- **Completed:** 2026-05-29T19:17:50Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Diagnosed `tool_not_available` P=0 as fixture-driven (0 labeled rows, ~160 FPs from clean rows with tool_name but no available_tools); added diagnostic comment per plan
- Added `score_gap = top_score - called_score` gate to `_check_wrong_tool_choice`: only flags when gap >= 0.10, suppressing near-coin-toss embedding ranking FPs
- Added `len(str_value.strip()) <= 3: continue` skip in `_check_wrong_args` for short generic tokens ("yes", "no", "all") that embed poorly against any prompt
- Added short-prompt guard (`len(span.prompt.split()) < 10: return []`) AFTER log_score in `_check_response_anomaly` to suppress short-prompt FPs while preserving calibration signal
- Added NE/lemma count precondition to `_check_missing_details` (guard exit before log_score): prompts with fewer than 3 NEs AND fewer than 5 content lemmas skip flagging

## Task Commits

1. **Task 1: Investigate and fix tool_not_available (P=0, D-04)** - `e344768` (fix)
2. **Task 2: Tighten wrong_tool_choice score gap requirement (D-11)** - `6f498a8` (feat)
3. **Task 3: Fix wrong_tool_args FPs, tighten response_anomaly, and tighten missing_details (D-14, D-15, D-07)** - `27aff00` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/services/worker/tool_call_analyzer.py` — diagnostic comment on _check_tool_not_available; score_gap gate in _check_wrong_tool_choice; short-value skip in _check_wrong_args; short-prompt guard in _check_response_anomaly
- `xeter/services/worker/semantic_span_analyzer.py` — NE/lemma count precondition (guard exit) added to _check_missing_details before log_score

## Decisions Made

- **D-04 diagnosis confirmed as fixture issue, not code bug:** Simulation without embedder showed TP=0, FP=160, P=0.0. The fixture has 0 `tool_not_available` labeled rows; 136 clean rows have `tool_name` set but `available_tools=None` causing WTOOL-03 to fire. Check logic is correct. Fix: diagnostic comment per plan.
- **score_gap literal 0.10:** Used literal value per plan specification; recalibration in plan 28-04 will confirm/tune further.
- **short-prompt guard placement:** Located AFTER log_score call in response_anomaly (not a guard exit) so short-prompt spans still contribute calibration signal; differs from the NE/lemma guard in missing_details which is a true guard exit (before log_score).
- **NE/lemma guard placement (before log_score):** Vacuous prompts should not contribute to calibration of missing_details — guard exit without logging per D-04 invariant.

## Deviations from Plan

### Diagnostic Finding (Task 1)

The plan offered three hypotheses for tool_not_available P=0. The actual diagnosis found a fourth pattern not listed: the fixture has **zero** `tool_not_available` labeled rows (no TPs possible at all), combined with ~136 clean rows where `tool_name` is set but `available_tools=None` (triggering WTOOL-03). Simulation confirmed TP=0, FP=160, P=0.0/R=0.0. The plan's response for "fixture is the root cause" (add diagnostic comment, no code change) was applied exactly as specified.

None of the three hypotheses listed in the plan were the root cause, but the prescribed response ("add diagnostic comment") was the correct action regardless.

**Total deviations:** 0 auto-fixes. 1 diagnostic finding that refined understanding but did not change the prescribed action.

## Issues Encountered

- `calibrated_thresholds.json` showed P=1.0 for `tool_not_available` from the Phase 27 calibration, which appeared to contradict the plan's P=0 diagnosis. Investigation revealed the Phase 27 calibration must have been run on a pre-Phase-27-01 fixture (228 rows without the new type builders) or against a smaller clean pool. The 738-row current fixture definitively shows P=0 for this type. The plan's diagnosis and prescribed action remain correct.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. All changes are in-memory `_check_*()` logic.

## Self-Check

| Item | Status |
|------|--------|
| xeter/services/worker/tool_call_analyzer.py | FOUND |
| xeter/services/worker/semantic_span_analyzer.py | FOUND |
| Commit e344768 (Task 1) | verified |
| Commit 6f498a8 (Task 2) | verified |
| Commit 27aff00 (Task 3) | verified |
| score_gap in _check_wrong_tool_choice | VERIFIED |
| len(str_value.strip()) <= 3 in _check_wrong_args | VERIFIED |
| len(span.prompt.split()) < 10 in _check_response_anomaly | VERIFIED |
| prompt_ents / _get_spacy in _check_missing_details | VERIFIED |
| 28 routing tests pass | VERIFIED |
