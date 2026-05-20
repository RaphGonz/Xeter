---
phase: 23-infrastructure
plan: "02"
subsystem: infra
tags: [clickhouse, pydantic, fastapi, sdk, schema-validation]

# Dependency graph
requires:
  - phase: 23-01
    provides: SpanData.expected_output_schema and parent_span_id fields on SpanData model
provides:
  - expected_output_schema field wired end-to-end: SpanPayload -> SPAN_COLUMNS -> ingest row -> ClickHouse DDL -> idempotent ALTER -> SDK trace() kwarg
affects:
  - 24-schema-validation
  - any phase reading expected_output_schema from ClickHouse spans table

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-write DDL pattern: CREATE TABLE IF NOT EXISTS for fresh deployments + idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS for live deployments (D-04)"
    - "Decorator-level schema kwarg: dict serialized to JSON string by SDK before dispatch (D-02)"

key-files:
  created:
    - xeter/tests/test_expected_output_schema_ingest.py
  modified:
    - xeter/services/analyser/schemas.py
    - xeter/services/analyser/batch.py
    - xeter/services/analyser/ingest.py
    - xeter/shared/db/clickhouse.py
    - xeter/services/analyser/main.py
    - sdk/xeter_sdk/decorator.py

key-decisions:
  - "D-04 dual-write: DDL column added for fresh deployments; idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS for live deployments"
  - "D-02 decorator-level kwarg: expected_output_schema is a dict at the call site, serialized to JSON string by SDK _dispatch() before transmission"
  - "SPAN_COLUMNS index 9 reserved for expected_output_schema (after tool_arguments at index 8, before tool_output at index 10)"

patterns-established:
  - "Idempotent alter function pattern: alter_spans_add_* called in lifespan immediately after create_spans_table — safe on every restart"
  - "TDD gate: RED commit (test) before GREEN commit (feat) enforces test-first discipline for pipeline wiring"

requirements-completed:
  - INFRA-05

# Metrics
duration: 13min
completed: 2026-05-20
---

# Phase 23 Plan 02: expected_output_schema ingest pipeline Summary

**expected_output_schema field wired from SpanPayload through SPAN_COLUMNS, ingest row, ClickHouse DDL, idempotent ALTER at startup, and SDK trace() decorator kwarg**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-20T19:37:35Z
- **Completed:** 2026-05-20T19:50:52Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- SpanPayload.expected_output_schema: Optional[str] = None field added; SPAN_COLUMNS now has 18 items with expected_output_schema at index 9; ingest row matches with assert guard enforced at runtime
- SPANS_TABLE_DDL updated with expected_output_schema Nullable(String); alter_spans_add_expected_output_schema() added with IF NOT EXISTS guard; analyser lifespan calls it immediately after create_spans_table
- SDK trace() decorator now accepts expected_output_schema: dict | None = None; _dispatch() serializes it to JSON string and includes it in the span dict sent to the analyser

## Task Commits

Each task was committed atomically:

1. **RED gate: failing tests** - `b880f4b` (test)
2. **Task 1: SpanPayload, SPAN_COLUMNS, ingest row** - `f1feda1` (feat)
3. **Task 2: DDL column + alter function + analyser startup** - `0d5d60e` (feat)
4. **Task 3: SDK trace() decorator** - `ffd20f8` (feat)

_Note: Task 1 used TDD — RED commit before GREEN commit._

## Files Created/Modified
- `xeter/tests/test_expected_output_schema_ingest.py` - 5 tests verifying SpanPayload field, SPAN_COLUMNS length/index, and ingest row sync
- `xeter/services/analyser/schemas.py` - Added expected_output_schema: Optional[str] = None to SpanPayload
- `xeter/services/analyser/batch.py` - Inserted "expected_output_schema" at SPAN_COLUMNS index 9 (18 items total)
- `xeter/services/analyser/ingest.py` - Added span.expected_output_schema to row list at position 9; updated comment block
- `xeter/shared/db/clickhouse.py` - Added expected_output_schema Nullable(String) to DDL; added alter_spans_add_expected_output_schema()
- `xeter/services/analyser/main.py` - Imported and called alter_spans_add_expected_output_schema after create_spans_table
- `sdk/xeter_sdk/decorator.py` - Added expected_output_schema: dict | None = None kwarg; serialization to JSON string in _dispatch(); key in span dict

## Decisions Made
- D-04 dual-write DDL pattern: both CREATE TABLE and ALTER TABLE guard cover fresh and live deployments respectively
- D-02 decorator kwarg: dict at decoration time, JSON string in transit (matches SpanPayload Optional[str] field)
- Column position 9 after tool_arguments maintains logical grouping of tool-related metadata

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing tool_output in test row construction**
- **Found during:** Task 1 (GREEN phase verification)
- **Issue:** The initial test file built a 17-item row (tool_output omitted between expected_output_schema and prompt_ref), causing a length mismatch assertion
- **Fix:** Added span.tool_output at index 10 in the test row construction to match SPAN_COLUMNS exactly
- **Files modified:** xeter/tests/test_expected_output_schema_ingest.py
- **Verification:** All 5 tests pass after fix
- **Committed in:** f1feda1 (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test row construction)
**Impact on plan:** Bug was in the test helper, not in production code. No scope creep. SPAN_COLUMNS, SpanPayload, and ingest.py all stayed in sync correctly.

## TDD Gate Compliance

- RED commit: `b880f4b` — `test(23-02): add failing tests for expected_output_schema ingest wiring` (5 tests, all failing)
- GREEN commit: `f1feda1` — `feat(23-02): add expected_output_schema to SpanPayload SPAN_COLUMNS and ingest row` (5 tests, all passing)
- REFACTOR: not needed

Both gates satisfied.

## Issues Encountered
None beyond the test row construction bug documented above.

## Known Stubs
None — all fields wired to real data sources.

## Threat Surface Scan
No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond those covered in the plan's threat model. T-23-02-01 (row drift) is enforced by the existing assert len(row) == len(SPAN_COLUMNS) guard. T-23-02-02 (startup DoS) is accepted via IF NOT EXISTS. T-23-02-03 (injection) is accepted — stored as Nullable(String), not evaluated.

## Next Phase Readiness
- expected_output_schema is now in ClickHouse spans table (DDL + live ALTER)
- Phase 24 schema-validation checks can query expected_output_schema directly from the spans table
- SDK consumers can pass expected_output_schema={"type": "object"} to @xeter.trace() now

---
*Phase: 23-infrastructure*
*Completed: 2026-05-20*
