---
phase: 23-infrastructure
plan: 01
subsystem: infra
tags: [jsonschema, tiktoken, rapidfuzz, spacy, clickhouse, spandata, dataclass, python]

# Dependency graph
requires:
  - phase: 22-bug-fixes
    provides: stable worker pipeline and scoring infrastructure
provides:
  - jsonschema==4.26.0, tiktoken==0.13.0, rapidfuzz==3.14.5 in worker environment
  - SpanData.expected_output_schema Optional[str] field (15 total fields)
  - SpanData.parent_span_id Optional[str] field
  - span_fetcher._FETCH_COLUMNS and _FETCH_QUERY updated with both new columns
  - fetch_span() SpanData constructor passes expected_output_schema and parent_span_id
  - build_span_data() in calibrate.py passes both new fields from row dict
affects:
  - 23-infrastructure (plans 02-03 — multi-analyzer routing and ClickHouse DDL depend on SpanData shape)
  - 24-structural-checks (expected_output_schema used in schema validation checks)
  - 25-semantic-checks (rapidfuzz, tiktoken used in semantic distance checks)
  - 26-response-anomaly (jsonschema used for output structure checks)
  - 27-trace-checks (parent_span_id used for trace-level relationship checks)

# Tech tracking
tech-stack:
  added:
    - jsonschema==4.26.0
    - tiktoken==0.13.0
    - rapidfuzz==3.14.5
  patterns:
    - Dual-location dependency declaration (pyproject.toml + Dockerfile pip install line)
    - Optional[str] with None default for new SpanData fields (same as tool_arguments pattern)
    - TDD: failing tests committed before implementation (RED → GREEN sequence)

key-files:
  created:
    - xeter/tests/test_span_data_fields.py
  modified:
    - xeter/pyproject.toml
    - services/worker/Dockerfile
    - xeter/services/worker/base.py
    - xeter/services/worker/span_fetcher.py
    - xeter/scripts/calibrate.py

key-decisions:
  - "D-09: jsonschema/tiktoken/rapidfuzz pinned to exact versions in both pyproject.toml and Dockerfile — same dual-location pattern as spacy"
  - "D-03: expected_output_schema stored as Optional[str] inline — same pattern as tool_arguments (no S3 ref needed for small JSON schemas)"
  - "D-10: parent_span_id scope limited to SpanData + span_fetcher — ClickHouse column already exists, no ingest or SDK changes needed"

patterns-established:
  - "New SpanData fields with defaults: always Optional[str] = None, appended after existing fields to avoid breaking existing construction sites"
  - "span_fetcher consistency: _FETCH_COLUMNS list, _FETCH_QUERY SQL string, and SpanData constructor call must all be updated together"
  - "calibrate.py build_span_data(): use row.get() for all SpanData fields so empty fixture rows never raise KeyError"

requirements-completed:
  - INFRA-04
  - INFRA-05
  - INFRA-06

# Metrics
duration: 14min
completed: 2026-05-20
---

# Phase 23 Plan 01: Infrastructure Foundation Summary

**Three v1.5 dependencies (jsonschema, tiktoken, rapidfuzz) added to worker env; SpanData extended with expected_output_schema and parent_span_id fields wired through span_fetcher and calibrate.py; 8 tests pass**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-20T19:11:42Z
- **Completed:** 2026-05-20T19:25:21Z
- **Tasks:** 2 (Task 1 auto, Task 2 TDD)
- **Files modified:** 5 (+ 1 created)

## Accomplishments
- Added jsonschema==4.26.0, tiktoken==0.13.0, rapidfuzz==3.14.5 to both xeter/pyproject.toml and services/worker/Dockerfile pip install line
- Extended SpanData dataclass to 15 total fields by appending expected_output_schema: Optional[str] = None and parent_span_id: Optional[str] = None after available_tools
- Updated span_fetcher._FETCH_COLUMNS (now 15 items), _FETCH_QUERY SELECT clause, and fetch_span() SpanData constructor to carry both new columns from ClickHouse
- Updated calibrate.py build_span_data() to pass expected_output_schema=row.get() and parent_span_id=row.get() so fixture rows without these keys work without KeyError
- 8 tests pass covering all behavior cases specified in the plan

## Task Commits

Each task was committed atomically:

1. **Task 1: Add jsonschema, tiktoken, rapidfuzz to pyproject and Dockerfile** - `5aa877e` (feat)
2. **Task 2 RED: Failing tests for expected_output_schema and parent_span_id** - `ac31784` (test)
3. **Task 2 GREEN: Extend SpanData + span_fetcher + calibrate** - `bad7275` (feat)

_Note: TDD task has two commits (test RED → feat GREEN)_

## Files Created/Modified
- `xeter/pyproject.toml` - Added jsonschema==4.26.0, tiktoken==0.13.0, rapidfuzz==3.14.5 to [project].dependencies
- `services/worker/Dockerfile` - Extended pip install line with jsonschema tiktoken rapidfuzz
- `xeter/services/worker/base.py` - Added expected_output_schema and parent_span_id fields to SpanData dataclass (now 15 fields)
- `xeter/services/worker/span_fetcher.py` - Added both columns to _FETCH_COLUMNS (15 items), _FETCH_QUERY, and fetch_span() SpanData constructor
- `xeter/scripts/calibrate.py` - Added expected_output_schema= and parent_span_id= kwargs to build_span_data() SpanData call
- `xeter/tests/test_span_data_fields.py` - 8 tests covering SpanData defaults, field carrying, build_span_data pass-through, and _FETCH_COLUMNS content

## Decisions Made
- Used exact pinned versions (D-09) matching the plan specification
- Optional[str] with None default matches the existing tool_arguments pattern (D-03)
- parent_span_id scope limited to SpanData + span_fetcher (D-10) — ClickHouse already has the column

## Deviations from Plan

None - plan executed exactly as written.

Note: The plan specified 6 tests; the implementation has 8 tests because tests 1 (SpanData defaults) and 6 (_FETCH_COLUMNS) were each split into two single-assertion tests (one per field). This improves failure isolation with no behavior difference.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all fields are wired end-to-end through SpanData, span_fetcher, and calibrate.py.

## Threat Flags
No new network endpoints, auth paths, or trust boundaries introduced. The three PyPI packages are pinned to exact versions (T-23-01 mitigated by version pinning). expected_output_schema originates from SDK-controlled ingest path (T-23-02 accepted per plan threat model).

## Self-Check

**Files exist:**
- xeter/pyproject.toml: FOUND
- services/worker/Dockerfile: FOUND
- xeter/services/worker/base.py: FOUND
- xeter/services/worker/span_fetcher.py: FOUND
- xeter/scripts/calibrate.py: FOUND
- xeter/tests/test_span_data_fields.py: FOUND

**Commits exist:**
- 5aa877e: FOUND
- ac31784: FOUND
- bad7275: FOUND

**Test run:** 8 passed, 0 failed

## Self-Check: PASSED

## Next Phase Readiness
- Phase 23 Plan 02 (calibrate.py multi-analyzer routing) can proceed — SpanData shape is now stable
- Phase 23 Plan 03 (ClickHouse DDL for expected_output_schema) can proceed — SpanData field name is confirmed
- Phases 24-27 (v1.5 checks) have their dependency prerequisites in place (jsonschema, tiktoken, rapidfuzz in env; SpanData fields defined)

---
*Phase: 23-infrastructure*
*Completed: 2026-05-20*
