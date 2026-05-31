---
phase: 30-diagnosticer-prompt
plan: 01
subsystem: api
tags: [pathlib, format_map, template, diagnosticer, context_assembly, python]

# Dependency graph
requires:
  - phase: 29-license-assets-cleanup
    provides: SPDX headers on all Python source files; prompt.md correctly gets NO header
provides:
  - "prompt.md template file co-located with context_assembly.py, read at import time"
  - "_PROMPT_TEMPLATE module-level constant in context_assembly.py"
  - "_format_context rewritten to use format_map instead of f-string"
  - "test_context_assembly.py with 5 tests covering substitution, flags, FileNotFoundError"
affects: [30-02-plan, diagnosticer-service, prompt-content-authorship]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Import-time file read: Path(__file__).parent / 'filename' read once at module level into a constant"
    - "Template substitution via str.format_map with named {placeholder} keys"
    - "FileNotFoundError at import = fail-fast sentinel for missing co-located assets"

key-files:
  created:
    - xeter/services/diagnosticer/prompt.md
    - xeter/tests/diagnosticer/test_context_assembly.py
  modified:
    - xeter/services/diagnosticer/context_assembly.py

key-decisions:
  - "prompt.md has no SPDX header — it is a template file sent to the LLM, not source code; a header would appear as visible text in the prompt"
  - "format_map used for substitution (not sentinel str.replace) — prompt prose contains no literal curly braces, so no escaping needed"
  - "Import-time read (module level) not per-request read — static asset, read once per process lifetime"
  - "FileNotFoundError at import is the correct fail-fast behavior: service refuses to start rather than running with a missing prompt"
  - "test_missing_prompt_file_raises uses unittest.mock.patch on pathlib.Path.read_text + importlib.reload to simulate missing file without deleting the real prompt.md"

patterns-established:
  - "Pattern: Co-located template files read via Path(__file__).parent at module level"
  - "Pattern: format_map dict keys mirror span.get() field names for clear correspondence"

requirements-completed: [DIAG-01]

# Metrics
duration: 57min
completed: 2026-05-30
---

# Phase 30 Plan 01: Diagnosticer Prompt Summary

**Inline f-string prompt extracted from _format_context into prompt.md, read at import via Path(__file__).parent, substituted via format_map — 5 tests pass, endpoint regression green**

## Performance

- **Duration:** ~57 min
- **Started:** 2026-05-30T22:58:00Z
- **Completed:** 2026-05-30T21:54:53Z
- **Tasks:** 2
- **Files modified:** 3 (1 created: prompt.md, 1 modified: context_assembly.py, 1 created: test_context_assembly.py)

## Accomplishments
- Extracted the inline f-string prompt from `_format_context()` into `xeter/services/diagnosticer/prompt.md` with nine `{variable}` placeholders for span fields plus `{prompt_text}`, `{response_text}`, `{flags_section}`
- Added `_PROMPT_TEMPLATE: str` module-level constant (import-time read via `Path(__file__).parent`) and rewrote `_format_context` body to use `_PROMPT_TEMPLATE.format_map(...)` — no f-string prompt literal remains, signature unchanged
- Created `test_context_assembly.py` with 5 tests: substitution, flag rendering, payload interpolation, import-time template presence, FileNotFoundError on missing file — all passing; existing 7 endpoint tests remain green

## Task Commits

Each task was committed atomically:

1. **Task 1: Create prompt.md template + wire import-time read and format_map** - `3eb0e04` (feat)
2. **Task 2: Add test_context_assembly.py** - `cd16a50` (test)

**Plan metadata:** `[pending final docs commit]` (docs: complete plan)

## Files Created/Modified
- `xeter/services/diagnosticer/prompt.md` - Prompt template with `{variable}` placeholders; no SPDX header (template file, not source code)
- `xeter/services/diagnosticer/context_assembly.py` - Added `from pathlib import Path`, `_PROMPT_TEMPLATE` constant, rewrote `_format_context` body to use `format_map`
- `xeter/tests/diagnosticer/test_context_assembly.py` - 5-test suite covering substitution, flag rendering, payload interpolation, template presence, FileNotFoundError

## Decisions Made
- `prompt.md` has no SPDX header — it is a template sent verbatim to the LLM; a header would appear as visible text in the prompt (per Pitfall 3 from research)
- `str.format_map()` chosen over sentinel replacement — the prompt prose contains no literal curly braces, so no escaping is needed; `format_map` is idiomatic
- Import-time read (module-level) not per-request read — Python import system caches modules; one read per process lifetime
- `test_missing_prompt_file_raises` uses `unittest.mock.patch` on `pathlib.Path.read_text` + `importlib.reload` — does NOT rename or delete the real `prompt.md` on disk

## Deviations from Plan

None - plan executed exactly as written.

Note: The worktree branch predated the commits that added `context_assembly.py`, `providers/`, and `tests/diagnosticer/` to the repo. A fast-forward `git merge main` was required at execution start to bring the worktree branch up to the current HEAD before any task work began. This is a git worktree setup detail, not a plan deviation.

## Issues Encountered
- Worktree branch was behind main by ~30 commits (predating `context_assembly.py`). Resolved with `git merge main --no-edit` (fast-forward, no conflicts).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DIAG-01 satisfied: prompt extracted to file, read at import, span data substituted from template
- Plan 02 can now rewrite `prompt.md` content with system message, CoT scaffold, verdict decision criteria, and severity calibration guidance — the substitution mechanism is in place

---
*Phase: 30-diagnosticer-prompt*
*Completed: 2026-05-30*
