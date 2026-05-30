---
phase: 30-diagnosticer-prompt
plan: 02
subsystem: api
tags: [diagnosticer, prompt-engineering, llm, python, pytest]

# Dependency graph
requires:
  - phase: 30-01
    provides: prompt.md template file extracted from context_assembly.py with format_map substitution wired
provides:
  - Rewritten prompt.md with system message (root-cause framing), four-verdict decision criteria (model/architecture/prompt/unknown), severity calibration (high/medium/low), and CoT reasoning scaffold
  - Four DIAG-02 content-presence tests asserting each required section renders in _format_context output
affects:
  - 31-readme-overhaul (may reference prompt.md structure)
  - future diagnosticer tuning phases

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Content-presence test pattern: call _format_context with a stub span, assert durable substrings case-insensitively"
    - "Prose-over-JSON-examples pattern: avoid literal braces in format_map templates by writing instructional prose instead"

key-files:
  created: []
  modified:
    - xeter/services/diagnosticer/prompt.md
    - xeter/tests/diagnosticer/test_context_assembly.py

key-decisions:
  - "Verdict decision criteria expanded from one-line _DIAGNOSIS_TOOL descriptions into multi-sentence distinguishing-signal paragraphs within the user message"
  - "CoT scaffold placed after the data sections (Span Information, Prompt Text, Response Text, Anomaly Flags) so the model reads evidence before seeing reasoning instructions"
  - "No literal braces used in rewritten prompt prose, avoiding format_map escaping complexity"

patterns-established:
  - "DIAG-02 pattern: system message as literal text at top of user message (no provider-level system param)"
  - "Content-presence tests use .lower() and substring checks, not full-prose equality, for durability"

requirements-completed: [DIAG-02]

# Metrics
duration: 37min
completed: 2026-05-31
---

# Phase 30 Plan 02: Diagnosticer Prompt Summary

**Rewritten prompt.md with structured system message, four-verdict decision criteria, severity calibration (high/medium/low), and chain-of-thought reasoning scaffold — DIAG-02 satisfied, 9 tests passing**

## Performance

- **Duration:** 37 min
- **Started:** 2026-05-30T22:20:00Z
- **Completed:** 2026-05-31T22:57:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Replaced the minimal one-line role framing with a structured system message that names root-cause analysis as the sole task and references the `record_diagnosis` tool call
- Added four-verdict decision criteria section with distinguishing signals per verdict (model / architecture / prompt / unknown), referencing concrete flag types from the analyser
- Added severity calibration guidance (high / medium / low) with task-impact definitions
- Added Reasoning Steps chain-of-thought scaffold instructing per-flag analysis before verdict
- Appended four DIAG-02 content-presence tests to `test_context_assembly.py` locking in all required sections
- All 16 diagnosticer tests pass (7 endpoint + 9 context assembly)

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite prompt.md content** - `2511d83` (feat)
2. **Task 2: Add four DIAG-02 content-presence tests** - `8897276` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `xeter/services/diagnosticer/prompt.md` - Rewritten: system message + four-verdict criteria + severity calibration + CoT scaffold (54 lines added, 3 removed)
- `xeter/tests/diagnosticer/test_context_assembly.py` - Four content-presence tests appended in `TestPromptContent` class (66 lines added)

## Decisions Made

- Verdict decision criteria expanded from one-line `_DIAGNOSIS_TOOL` descriptions to multi-sentence paragraphs with distinguishing signals and concrete flag type examples — gives the LLM actionable discrimination rather than terse labels
- CoT scaffold placed after the data sections so the model reads all evidence (span, flags) before the reasoning instructions; reduces the risk of the model deciding before reviewing the data
- No literal braces added to prompt prose, avoiding `format_map` escaping entirely — simpler to maintain

## Deviations from Plan

None — plan executed exactly as written.

**Note:** One pre-existing failing test (`tests/test_semantic_span_analyzer.py::test_missing_details_logs_score_before_threshold_check`) was observed during full-suite run but confirmed pre-existing before any changes in this plan. It is out of scope per deviation Rule boundary (pre-existing, unrelated file). Logged to deferred-items.

## Issues Encountered

None beyond the pre-existing test noted above.

## User Setup Required

None — no external service configuration required. Content and test changes only.

## Next Phase Readiness

- DIAG-02 complete; prompt.md is the active diagnosticer template used by all three providers (Anthropic / OpenAI / Ollama)
- Phase 30 complete (both DIAG-01 and DIAG-02 satisfied)
- Ready for Phase 31 (README overhaul) which may reference the prompt.md structure

## Self-Check

### Files exist:
- [x] xeter/services/diagnosticer/prompt.md — FOUND (modified)
- [x] xeter/tests/diagnosticer/test_context_assembly.py — FOUND (modified)

### Commits exist:
- [x] 2511d83 — feat(30-02): rewrite prompt.md
- [x] 8897276 — test(30-02): add four DIAG-02 content-presence tests

## Self-Check: PASSED

---
*Phase: 30-diagnosticer-prompt*
*Completed: 2026-05-31*
