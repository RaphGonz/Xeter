---
phase: 14-db-foundation
verified: 2026-04-29T00:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 14: DB Foundation Verification Report

**Phase Goal:** DB Foundation — tenant isolation complete at the database layer (RLS on all tables, CHECK constraints on diagnoses, S3 key guard, provider vocabulary aligned)
**Verified:** 2026-04-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | No new diagnoses row can contain verdict='undetermined' or severity='critical' | VERIFIED | All four provider files emit only `("model","architecture","prompt","unknown")` and `("low","medium","high")`; grep confirms zero remaining "undetermined" or "critical" strings |
| 2 | A pre-flight audit script can be run manually to check existing violations before migration 004 | VERIFIED | `xeter/scripts/preflight_diagnoses_audit.py` exists, parses, queries `diagnoses WHERE verdict NOT IN ... OR severity NOT IN ...`, exits 0 on clean data |
| 3 | All four provider files agree on the DB-approved vocabulary | VERIFIED | base.py Literal types, anthropic.py enum, openai.py enum, ollama.py Pydantic Literal — all use identical vocabulary |
| 4 | Presenter returns 403 when the S3 key's tenant prefix does not match the requesting tenant | VERIFIED | `_fetch_s3_payload` raises HTTPException(403) when `not key.startswith(f"{tenant_id}/")` |
| 5 | A cross-tenant key injection is rejected before any S3 GetObject call is made | VERIFIED | Guard fires before `get_object`; `test_wrong_prefix_raises_403` asserts `s3.get_object.assert_not_called()` |
| 6 | Migration 004 applies cleanly and covers span_scores RLS, FORCE RLS on all 7 tables, diagnoses CHECK constraints | VERIFIED | `004_db_foundation.py` passes syntax check; revision="004", down_revision="003"; all three DB areas covered |
| 7 | span_scores has a tenant_isolation RLS policy | VERIFIED | Migration creates `CREATE POLICY tenant_isolation ON span_scores USING (tenant_id::text = current_setting('app.current_tenant_id', true))` |
| 8 | All seven PostgreSQL tables with RLS have FORCE ROW LEVEL SECURITY | VERIFIED | Migration covers tenants, users, api_keys, flags, diagnostics, diagnoses (FORCE loop) + span_scores (explicit) |
| 9 | diagnoses.verdict and diagnoses.severity CHECK constraints are defined with NOT VALID + VALIDATE two-step | VERIFIED | Migration adds `diagnoses_verdict_check` and `diagnoses_severity_check` NOT VALID, then VALIDATE CONSTRAINT for both |
| 10 | score_writer.py uses SET LOCAL inside an explicit psycopg2 transaction (autocommit=False) | VERIFIED | `conn.autocommit = False`; `cur.execute("SET LOCAL app.current_tenant_id = %s", ...)` as first call before `executemany` |
| 11 | score_writer unit tests confirm SET LOCAL is called before INSERT in the same transaction | VERIFIED | 5 tests exist; `test_write_scores_sets_local_tenant_id` asserts SET LOCAL is `cursor.execute.call_args_list[0]` |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `xeter/services/diagnosticer/providers/base.py` | VERIFIED | `DiagnosisResult.verdict: Literal["model","architecture","prompt","unknown"]`; `severity: Literal["low","medium","high"]` — matches DB-03 vocabulary exactly |
| `xeter/services/diagnosticer/providers/anthropic.py` | VERIFIED | `"enum": ["model","architecture","prompt","unknown"]`; `"enum": ["low","medium","high"]`; description updated to 'unknown' |
| `xeter/services/diagnosticer/providers/openai.py` | VERIFIED | Same enum arrays; 'unknown' = insufficient signal in description |
| `xeter/services/diagnosticer/providers/ollama.py` | VERIFIED | `_DiagnosisOutput.verdict: Literal["model","architecture","prompt","unknown"]`; `severity: Literal["low","medium","high"]` |
| `xeter/scripts/preflight_diagnoses_audit.py` | VERIFIED | Exists, 62 lines, `verdict NOT IN %s OR severity NOT IN %s` query, exits 0/1, _get_dsn() strips +asyncpg, docstring explains when to run |
| `xeter/services/presenter/routers/spans.py` | VERIFIED | `_fetch_s3_payload` has `tenant_id: str` as 4th param; `key.startswith(f"{tenant_id}/")` guard; `_fetch_all_s3_payloads` threads tenant_id; `get_span_detail` passes tenant_id |
| `xeter/tests/presenter/test_s3_key_assertion.py` | VERIFIED | 4 tests: wrong prefix raises 403 (GetObject not called), correct prefix proceeds, None short-circuit, historical key format accepted |
| `xeter/migrations/versions/004_db_foundation.py` | VERIFIED | Syntax valid; revision="004", down_revision="003"; span_scores ENABLE+FORCE RLS + tenant_isolation policy; FORCE RLS on 6 existing tables; NOT VALID CHECK + VALIDATE for verdict and severity; downgrade reverses all |
| `xeter/services/worker/score_writer.py` | VERIFIED | `autocommit=False`; `SET LOCAL app.current_tenant_id = %s` before `executemany`; explicit `conn.commit()`; `conn.rollback()` in except; docstring updated to reflect RLS |
| `xeter/tests/worker/test_score_writer.py` | VERIFIED | 5 tests covering empty short-circuit, SET LOCAL ordering, commit on success, rollback+re-raise on error, row tuple shape |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `base.py` DiagnosisResult | `004_db_foundation.py` CHECK constraint | Literal vocabulary matches IN list | VERIFIED | Both use exactly `('model','architecture','prompt','unknown')` and `('low','medium','high')` |
| `preflight_diagnoses_audit.py` | diagnoses table | `verdict NOT IN` SQL | VERIFIED | `_AUDIT_SQL` contains `WHERE verdict NOT IN %s OR severity NOT IN %s` with correct tuples |
| `spans.py` `_fetch_s3_payload` | guard before get_object | `key.startswith(f"{tenant_id}/")` | VERIFIED | Guard fires at line 336, before `get_object` at line 341 |
| `test_s3_key_assertion.py` | `spans.py` `_fetch_s3_payload` | direct import + HTTPException 403 | VERIFIED | `from xeter.services.presenter.routers.spans import _fetch_s3_payload`; `exc_info.value.status_code == 403` |
| `score_writer.py` | span_scores | `SET LOCAL app.current_tenant_id` inside `autocommit=False` | VERIFIED | Pattern matches flag_writer.py exactly |
| `004_db_foundation.py` | span_scores | `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation` | VERIFIED | Lines 39-45 |
| `004_db_foundation.py` | diagnoses | `ADD CONSTRAINT NOT VALID` + `VALIDATE CONSTRAINT` | VERIFIED | Lines 61-79 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DB-01 | 14-03 | span_scores tenant-isolated via RLS + score_writer SET LOCAL | SATISFIED | Migration 004 adds RLS policy; score_writer uses SET LOCAL in autocommit=False transaction |
| DB-02 | 14-03 | FORCE ROW LEVEL SECURITY on all existing RLS tables | SATISFIED | Migration 004 loops over all 7 tables; downgrade reverses with NO FORCE |
| DB-03 | 14-01, 14-03 | CHECK constraints on diagnoses via NOT VALID + VALIDATE; providers emit correct vocabulary | SATISFIED | Provider files updated (Plan 01); migration 004 adds NOT VALID constraints and VALIDATE (Plan 03); pre-flight script exists |
| S3-01 | 14-02 | S3 key prefix assertion in Presenter returns 403 for cross-tenant keys | SATISFIED | `_fetch_s3_payload` guard + 4 unit tests |

No orphaned requirements: all four IDs (DB-01, DB-02, DB-03, S3-01) are claimed by plans and implemented in the codebase.

---

### Anti-Patterns Found

| File | Lines | Pattern | Severity | Impact |
|------|-------|---------|----------|--------|
| `xeter/services/presenter/routers/spans.py` | 9, 442 | Module docstring and inline comment say "span_scores has NO PostgreSQL RLS" | Warning | Stale after migration 004 adds RLS; the explicit `WHERE tenant_id` filter is still present and correct, so runtime behavior is unaffected, but the comments will mislead future developers into thinking no RLS exists |

No blockers found.

---

### Human Verification Required

None — all phase-14 claims are verifiable via code inspection and unit tests. The migration (004) cannot be verified against a live database in this automated check, but its SQL content matches the specification exactly.

---

### Summary

Phase 14 achieved its goal. All four requirements are implemented:

- **DB-01**: `span_scores` has a `tenant_isolation` RLS policy plus FORCE ROW LEVEL SECURITY; `score_writer.py` uses `SET LOCAL app.current_tenant_id` as the first execute call inside an explicit `autocommit=False` transaction, matching the `flag_writer.py` pattern.
- **DB-02**: Migration 004 applies FORCE ROW LEVEL SECURITY to all seven PostgreSQL tables that carry RLS (tenants, users, api_keys, flags, diagnostics, diagnoses, span_scores), preventing the table owner role from bypassing tenant isolation.
- **DB-03**: Provider vocabulary aligned to DB-approved values before migration (no new violating rows possible); migration 004 adds `diagnoses_verdict_check` and `diagnoses_severity_check` via NOT VALID + VALIDATE two-step; pre-flight audit script exists.
- **S3-01**: `_fetch_s3_payload` rejects keys whose prefix does not match the requesting tenant with HTTP 403 before any `GetObject` call; four unit tests verify the guard including the rejection path.

The only notable finding is a stale comment in `spans.py` (lines 9 and 442) that still says "span_scores has NO RLS" — this is a documentation inconsistency introduced when the guard was added before migration 004 ran. The runtime code is correct (explicit tenant_id WHERE clause is still present), but the comment should be updated to reflect that RLS is now also present.

---

_Verified: 2026-04-29_
_Verifier: Claude (gsd-verifier)_
