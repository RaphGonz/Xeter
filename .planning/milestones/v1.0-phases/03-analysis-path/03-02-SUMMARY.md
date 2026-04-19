---
phase: 03-analysis-path
plan: "02"
subsystem: worker
tags: [embeddings, tdd, cosine-similarity, flags, calibration, sentence-transformers]

dependency_graph:
  requires:
    - phase: 03-01
      provides: BaseAnalyzer ABC, Flag and SpanData dataclasses, worker/__init__.py
  provides:
    - ToolCallAnalyzer concrete class (FLAG-04 through FLAG-12 detection)
    - 6 _check_* methods covering wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error, response_anomaly
    - Tool embedding cache (SHA-256-keyed in-memory dict)
    - 14 unit tests with mock model (no real weights needed)
  affects:
    - 03-03 and beyond (any code that instantiates or registers ToolCallAnalyzer)
    - Phase 4 read path (flags produced here appear in Diagnosticer output)

tech-stack:
  added: []
  patterns:
    - Mock-first TDD — MagicMock with side_effect controls similarity ranking without real model weights
    - Calibration-first — log_score() called BEFORE threshold comparison in every _check_* method
    - Cache-keyed by content hash — SHA-256 of sorted JSON prevents redundant tool embeds across spans
    - No numeric literals — self._thresholds[key] for every threshold comparison

key-files:
  created:
    - xeter/services/worker/tool_call_analyzer.py
    - xeter/tests/worker/__init__.py
    - xeter/tests/worker/test_tool_call_analyzer.py
  modified: []

key-decisions:
  - "test_wrong_tool_uses_available_tools_ranking side_effect list fixed inline — initial test had 3 encode side_effects but analyze() makes many more encode calls; simplified to use encode.return_value with similarity.side_effect providing enough values for all compare calls (Rule 1 auto-fix)"

patterns-established:
  - "Mock model pattern: MagicMock with encode.return_value (unit vector) and similarity.side_effect (per-call control) provides full test isolation without sentence-transformers load"
  - "Available tools ranking: iterate tool embeddings, compare each to prompt, sort descending, flag if called tool != top-ranked AND top_score < threshold"

requirements-completed:
  - FLAG-04
  - FLAG-05
  - FLAG-06
  - FLAG-07
  - FLAG-08
  - FLAG-09
  - FLAG-10
  - FLAG-11
  - FLAG-12

duration: 13min
completed: "2026-03-28"
---

# Phase 3 Plan 02: ToolCallAnalyzer Summary

**ToolCallAnalyzer with 6 _check_* methods detecting tool-call anomalies via cosine similarity — 14 tests pass, zero hardcoded thresholds, calibration-first score logging.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-28T21:31:34Z
- **Completed:** 2026-03-28T21:44:35Z
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 3

## Accomplishments

- `ToolCallAnalyzer(BaseAnalyzer)` with 6 check methods covering FLAGS 04-12: wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error, response_anomaly
- Tool embedding cache using SHA-256 content hash — `_get_tool_embeddings()` never re-embeds identical tool lists
- 14 unit tests using MagicMock — no real sentence-transformers weights, tests run in ~0.2s
- All similarity scores logged via `log_score()` before threshold comparison (calibration dataset pattern)

## Task Commits

Each task committed atomically:

1. **Task 1: RED — write failing tests for ToolCallAnalyzer** — `148af5a` (test)
2. **Task 2: GREEN — implement ToolCallAnalyzer to pass all tests** — `dc0babc` (feat)

**Plan metadata:** (docs commit below)

_TDD tasks: test commit (RED) followed by implementation commit (GREEN)_

## Files Created/Modified

- `xeter/services/worker/tool_call_analyzer.py` — ToolCallAnalyzer with 6 _check_* methods, tool embedding cache, no numeric threshold literals
- `xeter/tests/worker/__init__.py` — empty package marker
- `xeter/tests/worker/test_tool_call_analyzer.py` — 14 unit tests covering all 6 check methods, score logging, cache, and FLAG-06/11/12 contracts

## Decisions Made

- Test for FLAG-11 (available_tools ranking) uses `similarity.side_effect` with enough values to cover all compare calls across all 6 check methods — ordering matches implementation call sequence

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_wrong_tool_uses_available_tools_ranking side_effect exhaustion**
- **Found during:** Task 2 (GREEN — running tests against implementation)
- **Issue:** Test had `encode.side_effect = [3 values]` and `similarity.side_effect = [10 values]`, but `analyze()` calls all 6 check methods triggering many more encode/similarity calls than the test anticipated. `StopIteration` from exhausted side_effect list.
- **Fix:** Removed `encode.side_effect` (reverted to `encode.return_value` unit vector). Replaced `similarity.side_effect` with 8 precise values matching actual call order: 2 for tool ranking, 2 for name/desc, 1 for wrong_args, 1 for excessive_tool, 1 for parsing_error, 1 for response_anomaly. Used low scores (0.2/0.1) for ranking calls so wrong_tool flag fires; high scores (0.9) for non-relevant checks to suppress other flags.
- **Files modified:** `xeter/tests/worker/test_tool_call_analyzer.py`
- **Verification:** `14 passed` in 0.22s
- **Committed in:** `dc0babc` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test side_effect count)
**Impact on plan:** Necessary correctness fix; test contract unchanged, only the mock setup was adjusted.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- ToolCallAnalyzer is complete and ready to be registered in a worker main loop (Plan 03-03 or similar)
- All 6 flag types are detectable; threshold calibration deferred to Phase 6 (labelled dataset sourcing still unspecified)
- Cache is span-local (per-instance); a production worker will share one ToolCallAnalyzer instance across spans so the cache amortises tool embed cost naturally

---
*Phase: 03-analysis-path*
*Completed: 2026-03-28*
