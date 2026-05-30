---
phase: 29-license-assets-cleanup
reviewed: 2026-05-30T00:00:00Z
depth: quick
files_reviewed: 87
files_reviewed_list:
  - LICENSE
  - sdk/xeter_sdk/__init__.py
  - sdk/xeter_sdk/decorator.py
  - xeter/migrations/env.py
  - xeter/migrations/versions/001_initial.py
  - xeter/migrations/versions/002_span_scores.py
  - xeter/migrations/versions/003_diagnoses.py
  - xeter/migrations/versions/004_db_foundation.py
  - xeter/migrations/versions/005_trace_flags_schema.py
  - xeter/migrations/versions/006_span_scores_nullable_span_id.py
  - xeter/scripts/add_fixture_spans.py
  - xeter/scripts/build_social_centroid.py
  - xeter/scripts/calibrate.py
  - xeter/scripts/delete_tenant.py
  - xeter/scripts/generate_labelled_fixture.py
  - xeter/scripts/load_test.py
  - xeter/scripts/preflight_diagnoses_audit.py
  - xeter/scripts/reset.py
  - xeter/scripts/seed.py
  - xeter/scripts/seed_spans.py
  - xeter/scripts/validate.py
  - xeter/services/analyser/auth.py
  - xeter/services/analyser/batch.py
  - xeter/services/analyser/ingest.py
  - xeter/services/analyser/main.py
  - xeter/services/analyser/queue.py
  - xeter/services/analyser/s3.py
  - xeter/services/analyser/schemas.py
  - xeter/services/diagnosticer/context_assembly.py
  - xeter/services/diagnosticer/main.py
  - xeter/services/diagnosticer/providers/__init__.py
  - xeter/services/diagnosticer/providers/anthropic.py
  - xeter/services/diagnosticer/providers/base.py
  - xeter/services/diagnosticer/providers/ollama.py
  - xeter/services/diagnosticer/providers/openai.py
  - xeter/services/presenter/deps.py
  - xeter/services/presenter/diagnosis_service.py
  - xeter/services/presenter/main.py
  - xeter/services/presenter/routers/auth.py
  - xeter/services/presenter/routers/diagnose.py
  - xeter/services/presenter/routers/spans.py
  - xeter/services/presenter/routers/traces.py
  - xeter/services/worker/base.py
  - xeter/services/worker/flag_writer.py
  - xeter/services/worker/main.py
  - xeter/services/worker/output_schema_analyzer.py
  - xeter/services/worker/score_writer.py
  - xeter/services/worker/semantic_span_analyzer.py
  - xeter/services/worker/span_fetcher.py
  - xeter/services/worker/tool_call_analyzer.py
  - xeter/services/worker/tool_call_registry.py
  - xeter/services/worker/trace_analyzer.py
  - xeter/shared/dal/api_keys.py
  - xeter/shared/dal/base.py
  - xeter/shared/dal/diagnoses.py
  - xeter/shared/dal/tenants.py
  - xeter/shared/dal/users.py
  - xeter/shared/db/clickhouse.py
  - xeter/shared/db/postgres.py
  - xeter/shared/db/redis.py
  - xeter/shared/db/session.py
  - xeter/shared/models.py
  - xeter/tests/analyser/test_ingest.py
  - xeter/tests/conftest.py
  - xeter/tests/dal/test_registration.py
  - xeter/tests/dal/test_tenant_guard.py
  - xeter/tests/diagnosticer/test_diagnose_endpoint.py
  - xeter/tests/presenter/test_auth_login.py
  - xeter/tests/presenter/test_diagnose.py
  - xeter/tests/presenter/test_s3_key_assertion.py
  - xeter/tests/presenter/test_span_detail.py
  - xeter/tests/presenter/test_spans_list.py
  - xeter/tests/presenter/test_spans_list_filters.py
  - xeter/tests/presenter/test_traces.py
  - xeter/tests/sdk/test_decorator.py
  - xeter/tests/test_calibrate_routing.py
  - xeter/tests/test_expected_output_schema_ingest.py
  - xeter/tests/test_secrets.py
  - xeter/tests/test_semantic_span_analyzer.py
  - xeter/tests/test_span_data_fields.py
  - xeter/tests/test_trace_analyzer.py
  - xeter/tests/validation/conftest.py
  - xeter/tests/validation/test_isolation.py
  - xeter/tests/worker/test_flush_stale_traces.py
  - xeter/tests/worker/test_output_schema_analyzer.py
  - xeter/tests/worker/test_score_writer.py
  - xeter/tests/worker/test_tool_call_analyzer.py
  - xeter/tests/worker/test_trace_analyzer.py
  - xeter/tests/worker/test_trace_analyzer_phase26.py
  - xeter/tests/worker/test_trace_buffer.py
  - xeter/tests/worker/test_worker_loop.py
findings:
  critical: 1
  warning: 2
  info: 0
  total: 3
status: issues_found
---

# Phase 29: Code Review Report

**Reviewed:** 2026-05-30T00:00:00Z
**Depth:** quick
**Files Reviewed:** 87
**Status:** issues_found

## Summary

Phase 29 inserted SPDX license headers (`# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0`) into every Python source file and created the `LICENSE` file combining GPL-3.0 and the Commons Clause condition.

**Header insertion: clean across all 87 files.** Every non-shebang file has the SPDX identifier on line 1. Both shebang files (`delete_tenant.py`, `preflight_diagnoses_audit.py`) correctly preserve `#!/usr/bin/env python3` on line 1 with the SPDX comment on line 2. No existing module-level code was displaced, duplicated, or corrupted.

**LICENSE file content: structurally correct** — the full GPL-3.0 body is present and terminated with "END OF TERMS AND CONDITIONS", the Commons Clause v1.0 block follows on lines 3–13, and all three required fields are populated correctly (`Software: Xeter`, `License: GNU General Public License v3.0`, `Licensor: RaphGonz`).

Three defects were found that are unrelated to the header insertion but were exposed by reading every file at full depth as required by the review scope.

## Critical Issues

### CR-01: KeyError crash at CLI startup in load_test.py — `e2e_latency` key never written to results dict

**File:** `xeter/scripts/load_test.py:513`
**Issue:** The `__main__` block accesses `results["e2e_latency"]["e2e_assert_passed"]` on line 513, but `_main_async()` returns a dict with only two top-level keys: `"load"` and `"clickhouse_parts"`. The E2E latency probe (`_probe_e2e_latency`) is defined in the file but is never called from `_main_async()` — the call was removed or never wired up. Executing `python xeter/scripts/load_test.py` with any arguments will therefore raise `KeyError: 'e2e_latency'` immediately after the load test completes, preventing the exit-code check from running and producing a confusing crash instead of a FAIL/PASS result.

**Fix:** Either wire the probe into `_main_async()` (call `_probe_e2e_latency` on one of the registered tenant API keys and include the result in the returned dict) or, if the probe is intentionally disabled for this release, remove the dead reference in the exit check:
```python
# Option A — remove the dead key reference while keeping the two live checks:
all_passed = (
    results["clickhouse_parts"]["passed"]
    and results["load"]["p95_ms"] < 200
)

# Option B — wire the probe back in (return dict must include "e2e_latency"):
e2e_result = _probe_e2e_latency(api_keys[0])
return {
    "load": load_result,
    "clickhouse_parts": parts_result,
    "e2e_latency": e2e_result,
}
```

## Warnings

### WR-01: LICENSE line 1 — entire GPL-3.0 body collapsed onto a single line

**File:** `LICENSE:1`
**Issue:** The complete GPL-3.0 text (header, preamble, all 17 sections, and the "How to Apply" appendix) is stored as a single long line with all internal newlines stripped. Lines 2–13 (blank line + Commons Clause block) are formatted normally. The legal text is substantively complete and legally operative, but the single-line formatting breaks every standard tool that inspects license files: `cat`, `head`, `grep`, diff viewers, GitHub's license detection heuristic, and REUSE/SPDX compliance scanners all expect line-separated text. GitHub in particular will fail to auto-detect the license and will show "No license file" in the repository UI.

**Fix:** Replace line 1 with the canonical GPL-3.0 text formatted with standard line breaks (available at https://www.gnu.org/licenses/gpl-3.0.txt). The Commons Clause block on lines 3–13 is already correctly formatted and must be preserved unchanged after the GPL-3.0 body.

### WR-02: `xeter/scripts/delete_tenant.py` — table name interpolated via f-string in `_count_postgres` (noqa suppression masks the issue)

**File:** `xeter/scripts/delete_tenant.py:101`
**Issue:** The count query uses an f-string to interpolate the table name directly into the SQL:
```python
cur.execute(
    f"SELECT COUNT(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608
    (tenant_id,),
)
```
The table names come from the module-level `_PG_DELETE_TABLES` list (a hardcoded constant), so in the current code there is no injection vector from external input. The `# noqa: S608` suppression is therefore functionally correct. However, the same pattern is repeated in `_delete_postgres()` at line 204 with the same suppression. The risk is that a future developer adds an external-input path to `_PG_DELETE_TABLES` (e.g., a `--table` CLI flag) without noticing the f-string, at which point both functions become SQL-injectable with no warning. Using `psycopg2.sql.Identifier` from the `psycopg2.extras` module would make the parameterization explicit and immune to future mutation.

**Fix:**
```python
from psycopg2 import sql

cur.execute(
    sql.SQL("SELECT COUNT(*) FROM {} WHERE tenant_id = %s").format(
        sql.Identifier(table)
    ),
    (tenant_id,),
)
```
Apply the same change to the DELETE statement in `_delete_postgres()`.

---

_Reviewed: 2026-05-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
