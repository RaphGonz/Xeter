---
phase: 18-cleanup-baseanalyzer-refactor
plan: "02"
subsystem: worker
tags: [python, abc, inheritance, analyzer, hierarchy]

# Dependency graph
requires:
  - phase: 18-cleanup-baseanalyzer-refactor
    provides: "Phase 18-01 cleanup — dead code removed, worker base ready for hierarchy split"
provides:
  - "3-class analyzer hierarchy: BaseAnalyzer (generic root), BaseSpanAnalyzer, BaseTraceAnalyzer"
  - "ToolCallAnalyzer now inherits BaseSpanAnalyzer (satisfies span-level contract)"
  - "BaseTraceAnalyzer stub ready for Phase 19 TraceAnalyzer scaffold"
affects: [19-trace-analyzer-scaffold, phase-21]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3-class ABC hierarchy: generic root → domain-specific abstract subclasses"
    - "analyze() contract lives on the subclass, not on BaseAnalyzer root"

key-files:
  created: []
  modified:
    - xeter/services/worker/base.py
    - xeter/services/worker/tool_call_analyzer.py

key-decisions:
  - "BaseAnalyzer root retains embed/compare/log_score/flush_scores/name but no analyze() — allows span-level and trace-level subclasses to define independent signatures"
  - "BaseTraceAnalyzer added as stub only — no concrete subclass until Phase 19"

patterns-established:
  - "Span-level analyzers: subclass BaseSpanAnalyzer, implement analyze(span: SpanData) -> list[Flag]"
  - "Trace-level analyzers: subclass BaseTraceAnalyzer, implement analyze(spans: list[SpanData]) -> list[Flag]"

requirements-completed: [TANA-01]

# Metrics
duration: 12min
completed: 2026-05-14
---

# Phase 18 Plan 02: BaseAnalyzer Refactor Summary

**3-class analyzer hierarchy established in base.py: BaseAnalyzer (generic root) splits into BaseSpanAnalyzer and BaseTraceAnalyzer; ToolCallAnalyzer re-parented to BaseSpanAnalyzer**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-14T00:00:00Z
- **Completed:** 2026-05-14T00:12:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Split monolithic `BaseAnalyzer(ABC)` into three classes: generic root + two domain-specific abstract subclasses
- `BaseAnalyzer` retains all shared helpers (embed, compare, log_score, flush_scores, name) with no analyze() abstract method
- `BaseSpanAnalyzer(BaseAnalyzer)` defines `analyze(span: SpanData) -> list[Flag]` — contract for all span-level analyzers
- `BaseTraceAnalyzer(BaseAnalyzer)` defines `analyze(spans: list[SpanData]) -> list[Flag]` — contract for Phase 19 TraceAnalyzer
- `ToolCallAnalyzer` re-parented from `BaseAnalyzer` to `BaseSpanAnalyzer` with zero behavior change
- All 35 non-spaCy worker tests pass unchanged (13 pre-existing spaCy env failures are environment-only, not regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Introduce 3-class hierarchy in base.py** - `1fc2723` (refactor)
2. **Task 2: Update ToolCallAnalyzer to inherit BaseSpanAnalyzer** - `e1c9be2` (refactor)

**Plan metadata:** _(final docs commit — see below)_

## Files Created/Modified

- `xeter/services/worker/base.py` — Split BaseAnalyzer into 3 classes; updated module docstring; added BaseSpanAnalyzer and BaseTraceAnalyzer
- `xeter/services/worker/tool_call_analyzer.py` — Import updated to BaseSpanAnalyzer; class definition updated to inherit BaseSpanAnalyzer

## Decisions Made

- `BaseAnalyzer` root keeps the `name` abstract property (all concrete analyzers must still provide a name, regardless of whether they are span- or trace-level)
- `BaseTraceAnalyzer` added as an abstract stub only — Phase 19 will provide the concrete `TraceAnalyzer` implementation
- No changes to worker/main.py needed — `analyzers: list` annotation is duck-typed so ToolCallAnalyzer continues to satisfy the contract

## Deviations from Plan

None — plan executed exactly as written.

Pre-existing spaCy environment failures (13 tests in test_tool_call_analyzer.py) are unchanged before and after the refactor; these are environment-only failures due to spaCy not being installed in the Python 3.14 test environment, not caused by any change in this plan.

## Issues Encountered

None — refactor was straightforward. Git stash was used mid-execution to confirm pre-existing test failure baseline, then stash-popped to restore changes.

## Next Phase Readiness

- Phase 19 (TraceAnalyzer scaffold) can import `BaseTraceAnalyzer` from `xeter.services.worker.base` directly
- Hierarchy assertions confirmed: `issubclass(BaseSpanAnalyzer, BaseAnalyzer)`, `issubclass(BaseTraceAnalyzer, BaseAnalyzer)`, `issubclass(ToolCallAnalyzer, BaseSpanAnalyzer)` all pass
- `BaseAnalyzer.__abstractmethods__` does not include `analyze` — root is not abstract on analyze

---
*Phase: 18-cleanup-baseanalyzer-refactor*
*Completed: 2026-05-14*
