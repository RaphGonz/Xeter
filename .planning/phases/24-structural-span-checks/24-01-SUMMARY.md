---
phase: 24-structural-span-checks
plan: "01"
subsystem: worker/testing
tags: [tdd, testing, output-schema, span-analyzer, red-phase]
dependency_graph:
  requires: []
  provides:
    - test scaffold defining OutputSchemaAnalyzer behavioral contract
  affects:
    - xeter/tests/worker/test_output_schema_analyzer.py
tech_stack:
  added: []
  patterns:
    - TDD RED phase test scaffold mirroring test_tool_call_analyzer.py structure
    - make_span / make_mock_embedder / make_analyzer helper pattern
    - flush_scores() log_score invariant verification
key_files:
  created:
    - xeter/tests/worker/test_output_schema_analyzer.py
  modified: []
decisions:
  - D-01 scope enforced: only sub-case A (response not JSON) tested; no sub-case B tests
  - D-04 invariant: log_score verified for both fire and clean paths, and early-exit guard produces empty flush_scores
  - D-06 constructor: test_constructor_accepts_embedder_and_thresholds verifies signature without calling embed()
  - Pitfall 2: co-fire test (test_schema_02_and_schema_04_co_fire_independently) ensures independent firing
  - Pitfall 3: test_schema_03_does_not_fire_on_malformed_but_closed_json enforces end-char heuristic
  - Pitfall 4: test_schema_03_fires_on_anthropic_stop_reason_max_tokens covers Anthropic path
metrics:
  duration: "8 minutes"
  completed: "2026-05-21"
  tasks_completed: 3
  files_changed: 1
---

# Phase 24 Plan 01: OutputSchemaAnalyzer RED Phase Test Scaffold Summary

## One-liner

31-test RED phase scaffold covering OutputSchemaAnalyzer's 5 deterministic checks (SCHEMA-01 through CTX-01) with log_score invariant and early-exit guard verification.

## What Was Built

Created `xeter/tests/worker/test_output_schema_analyzer.py` — the TDD RED phase test file for `OutputSchemaAnalyzer`. The file defines the complete behavioral contract for all 5 Phase 24 checks. All 31 tests fail only on `ModuleNotFoundError` for the missing `output_schema_analyzer` module, which plan 24-02 will implement.

### Test Coverage

| Check | Tests | Key scenarios |
|-------|-------|---------------|
| Contract | 3 | name property, analyze() return type, D-06 constructor signature |
| SCHEMA-01 | 5 | fire+no-fire+schema-None+response-None+log_score clean |
| SCHEMA-02 | 4 | required_fields fire+no-fire+None guard+malformed schema |
| SCHEMA-04 | 4 | type_coercion (string+integer)+no-fire+co-fire with SCHEMA-02 |
| CTX-01 | 5 | over+under threshold+None guard+log_score (clean+fired) |
| SCHEMA-03 | 7 | OpenAI length+Anthropic max_tokens+unclosed (response+tool_args)+Pitfall3+stop+malformed raw |
| log_score | 3 | all 4 binary metrics clean+fired 1.0+early-exit empty flush |
| **Total** | **31** | |

### Structural Notes

- File: 511 lines, well over the 200-line minimum
- Import pattern: `from xeter.services.worker.output_schema_analyzer import OutputSchemaAnalyzer` (the RED point)
- Helpers at module scope: `make_mock_embedder()`, `make_span(**kwargs)`, `make_analyzer(thresholds=None)`
- `DEFAULT_THRESHOLDS = {"context_overflow": 8000}` at module scope (D-03 default)
- No numpy vectors, no embedding calls — pure structural/deterministic test logic
- Zero references to sub-case B, CTX-03, prompt_injection

## Commits

| Hash | Message |
|------|---------|
| 68da3cf | test(24-01): add RED phase test scaffold for OutputSchemaAnalyzer |

## Deviations from Plan

None — plan executed exactly as written. All 3 tasks (scaffold+SCHEMA-01+contract, SCHEMA-02+SCHEMA-04+CTX-01, SCHEMA-03+log_score) were implemented in a single Write operation covering the complete 31-test file. This is equivalent to the sequential append approach described in the plan — the final file content is identical.

## Known Stubs

None. This plan creates only a test file; no implementation stubs exist.

## Threat Flags

None. This plan creates only a test file; no new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- `xeter/tests/worker/test_output_schema_analyzer.py` exists: FOUND
- Commit 68da3cf exists: FOUND
- 31 test functions present: VERIFIED (`grep -c "^def test_"` = 31)
- File parses (`ast.parse`): VERIFIED (exit 0)
- Fails only on ModuleNotFoundError for OutputSchemaAnalyzer: VERIFIED
- Zero sub-case B / CTX-03 / prompt_injection references: VERIFIED
