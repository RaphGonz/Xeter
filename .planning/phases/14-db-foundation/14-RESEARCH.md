# Phase 14: DB Foundation - Research

**Researched:** 2026-04-28
**Domain:** PostgreSQL RLS enforcement, Alembic CHECK constraint migrations, S3 tenant-scoped key isolation
**Confidence:** HIGH

## Summary

Phase 14 tightens database and S3 security across four dimensions: (1) adding RLS + FORCE ROW LEVEL SECURITY to `span_scores`, (2) retroactively forcing RLS on all six RLS-enabled tables so the table owner role cannot bypass policies, (3) adding CHECK constraints on `diagnoses.verdict` and `diagnoses.severity` via the NOT VALID + VALIDATE CONSTRAINT two-step to avoid ACCESS EXCLUSIVE locks, and (4) asserting tenant ownership before the Presenter returns S3 payload content.

A critical pre-existing conflict must be resolved before any constraint work: the Diagnosticer providers (`base.py`, `anthropic.py`, `openai.py`, `ollama.py`) currently define `verdict` as `Literal["model","architecture","prompt","undetermined"]` and `severity` as `Literal["low","medium","high","critical"]`. DB-03 requires the DB constraint to accept `('model','architecture','prompt','unknown')` for verdict (not `undetermined`) and `('low','medium','high')` for severity (not `critical`). The providers must be updated first so no new rows will violate the new constraints. Existing `diagnoses` rows must be audited with a pre-flight query before `VALIDATE CONSTRAINT` runs.

The S3 key format currently in use is `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json` (with a month segment). Requirement S3-01 specifies `{tenant_id}/{span_id}/...` without a month component. The planner must decide: either (a) accept the month-segment key format as the "prefix" (the key still starts with `{tenant_id}/`) and add only the assertion guard in Presenter, or (b) treat this as an explicit format migration. Given that S3-01's success criteria says "all S3 payload keys for _new_ spans use `{tenant_id}/{span_id}/...` prefix" and "Presenter S3 fetch asserts the key belongs to the requesting tenant", the guard approach (check `key.startswith(f"{tenant_id}/")`) will work regardless of whether the month segment is present, since the key always starts with the tenant UUID.

**Primary recommendation:** Execute changes in strict order — (1) update provider Literals to remove `undetermined`/`critical`, (2) run pre-flight audit query against existing diagnoses, (3) apply migration 004 (span_scores RLS + FORCE RLS on all tables + NOT VALID constraints), (4) run VALIDATE CONSTRAINT, (5) add Presenter key-prefix guard + integration test.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DB-01 | span_scores has tenant_isolation RLS policy; score_writer.py uses SET LOCAL in explicit transaction | Existing flag_writer.py pattern is the exact model; span_scores migration 002 deliberately omitted RLS; migration 004 adds it |
| DB-02 | FORCE ROW LEVEL SECURITY applied to all six RLS tables so table owner cannot bypass | PostgreSQL ALTER TABLE ... FORCE ROW LEVEL SECURITY verified; relforcerowsecurity in pg_class confirmed; superusers/BYPASSRLS still bypass even with FORCE |
| DB-03 | CHECK constraints on diagnoses.verdict and diagnoses.severity using NOT VALID + VALIDATE two-step | ALTER TABLE ADD CONSTRAINT ... NOT VALID uses SHARE UPDATE EXCLUSIVE (not ACCESS EXCLUSIVE); VALIDATE CONSTRAINT confirmed; provider Literal mismatch documented |
| S3-01 | S3 key prefix includes tenant_id; Presenter asserts key starts with requesting tenant's ID; cross-tenant 403 test | Current key format `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json` satisfies prefix check since it starts with tenant_id; Presenter `_fetch_s3_payload` has no current assertion; add startswith guard + 403 integration test |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| alembic | 1.18.4 (already installed) | Migration file for migration 004 | Already in pyproject.toml; all prior migrations use it |
| psycopg2-binary | >=2.9.0 (already installed) | score_writer.py SET LOCAL transaction | flag_writer.py uses identical pattern; already installed |
| sqlalchemy | 2.0.48 (already installed) | ORM session / op.execute for raw SQL | All existing migrations use op.execute for RLS DDL |
| pytest | installed | Unit + integration tests | Already configured via pyproject.toml asyncio_mode=auto |
| httpx | installed | Integration test HTTP calls | Already used in validation/conftest.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncpg | 0.31.0 (already installed) | Async PostgreSQL connection (Presenter/Diagnosticer) | Only for async paths; score_writer uses psycopg2 sync |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| NOT VALID + VALIDATE two-step | Direct ADD CONSTRAINT (VALID) | Direct requires ACCESS EXCLUSIVE + full table scan; rejected because of existing data risk and lock duration |
| CHECK constraint (string enum) | PostgreSQL ENUM type | ENUMs require ALTER TYPE + downtime to add values; string CHECK is zero-schema-change extensible |

**No new installations needed.** All dependencies already present.

## Architecture Patterns

### Recommended Project Structure
```
xeter/
├── migrations/versions/
│   └── 004_db_foundation.py        # new migration (span_scores RLS + FORCE RLS + NOT VALID constraints)
├── services/
│   ├── worker/
│   │   └── score_writer.py         # add SET LOCAL inside explicit transaction (copy flag_writer pattern)
│   ├── diagnosticer/
│   │   └── providers/
│   │       ├── base.py             # update DiagnosisResult Literals: remove undetermined/critical
│   │       ├── anthropic.py        # update _DIAGNOSIS_TOOL enum to remove undetermined/critical
│   │       ├── openai.py           # update _OPENAI_TOOL enum to remove undetermined/critical
│   │       └── ollama.py           # update _DiagnosisOutput Literals to remove undetermined/critical
│   └── presenter/
│       └── routers/
│           └── spans.py            # add tenant-prefix assertion in _fetch_s3_payload
└── tests/
    ├── worker/
    │   └── test_score_writer.py    # new: test SET LOCAL in transaction (unit, mock psycopg2)
    ├── validation/
    │   └── test_rls_span_scores.py # new: integration test for span_scores RLS silent-empty
    └── validation/
        └── test_s3_isolation.py    # new: cross-tenant S3 fetch returns 403
```

### Pattern 1: span_scores RLS via flag_writer.py pattern (DB-01)

**What:** Add tenant_isolation RLS policy to span_scores; update score_writer.py to use SET LOCAL inside an explicit transaction with autocommit=False.

**When to use:** Any table that stores tenant-scoped rows where the worker connects.

**Template (score_writer.py after change):**
```python
# Source: flag_writer.py (already in codebase) — exact same pattern
conn = psycopg2.connect(_get_dsn())
conn.autocommit = False
try:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.current_tenant_id = %s", (str(tenant_id),))
        cur.executemany(_INSERT_SQL, rows)
    conn.commit()
except Exception as exc:
    conn.rollback()
    logger.error("score_writer: failed ...", len(scores), span_id, exc)
    raise
finally:
    conn.close()
```

**Migration fragment for span_scores RLS:**
```python
# Source: PostgreSQL official docs + existing migration 001/003 pattern
op.execute("ALTER TABLE span_scores ENABLE ROW LEVEL SECURITY;")
op.execute("""
    CREATE POLICY tenant_isolation ON span_scores
        USING (tenant_id::text = current_setting('app.current_tenant_id', true));
""")
```

### Pattern 2: FORCE ROW LEVEL SECURITY retroactively (DB-02)

**What:** Force RLS on all tables that already have ENABLE ROW LEVEL SECURITY, so the table owner role cannot issue queries that bypass the tenant_isolation policy. Verified via pg_class.relforcerowsecurity.

**Key fact (HIGH confidence, PostgreSQL official docs):**
- `FORCE ROW LEVEL SECURITY` applies to table owners only
- Superusers and roles with `BYPASSRLS` attribute still bypass, even with FORCE enabled
- The migration role (DATABASE_URL) likely has BYPASSRLS, so it is unaffected

**Migration SQL:**
```python
# Source: https://www.postgresql.org/docs/current/sql-altertable.html
for table in ("tenants", "users", "api_keys", "flags", "diagnostics", "diagnoses"):
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
# span_scores gets FORCE in the same migration after ENABLE RLS is added
op.execute("ALTER TABLE span_scores FORCE ROW LEVEL SECURITY;")
```

**Verification query (SUCCESS CRITERION 2):**
```sql
SELECT relname, relforcerowsecurity
FROM pg_class
WHERE relname IN ('spans','flags','span_scores','diagnoses','tenants','api_keys');
-- All rows must have relforcerowsecurity = true
```

Note: `spans` is a ClickHouse table — not in PostgreSQL. The six tables to check are: `tenants`, `users`, `api_keys`, `flags`, `diagnostics`, `diagnoses`, `span_scores`. The success criterion lists `spans` but that may refer to the ClickHouse table which has no PostgreSQL RLS. Planner must confirm which six PostgreSQL tables are intended (likely: `tenants`, `users`, `api_keys`, `flags`, `diagnostics`, `diagnoses` — all five from 001 + `diagnoses` from 003; `span_scores` is the seventh being added in 004).

### Pattern 3: CHECK constraints via NOT VALID + VALIDATE two-step (DB-03)

**What:** Add CHECK constraints to diagnoses.verdict and diagnoses.severity as NOT VALID (no ACCESS EXCLUSIVE, no table scan), then after pre-flight audit run VALIDATE CONSTRAINT.

**Why NOT VALID:** VALIDATE CONSTRAINT acquires only SHARE UPDATE EXCLUSIVE lock (allows concurrent reads/writes). Regular ADD CONSTRAINT acquires ACCESS EXCLUSIVE (blocks all concurrent operations). For any table with existing rows, NOT VALID is the safe approach.

**Critical pre-flight audit (run BEFORE migration 004):**
```sql
-- Run manually or as part of Wave 0 task BEFORE applying migration 004
SELECT COUNT(*) FROM diagnoses
WHERE verdict NOT IN ('model', 'architecture', 'prompt', 'unknown')
   OR severity NOT IN ('low', 'medium', 'high');
-- Must return 0 before VALIDATE CONSTRAINT will succeed
```

**Provider change required FIRST (before any DB writes):**

Current `DiagnosisResult` in `base.py`:
```python
verdict: Literal["model", "architecture", "prompt", "undetermined"]
severity: Literal["low", "medium", "high", "critical"]
```

Required (DB-03):
```python
verdict: Literal["model", "architecture", "prompt", "unknown"]
severity: Literal["low", "medium", "high"]
```

All three provider tool definitions (`anthropic.py`, `openai.py`, `ollama.py`) also enumerate `"undetermined"` and `"critical"` — these must be updated to match.

**Migration fragment:**
```python
# Source: https://www.postgresql.org/docs/current/sql-altertable.html
# Step 1: Add constraint as NOT VALID (no scan, SHARE UPDATE EXCLUSIVE lock only)
op.execute("""
    ALTER TABLE diagnoses
        ADD CONSTRAINT diagnoses_verdict_check
        CHECK (verdict IN ('model', 'architecture', 'prompt', 'unknown'))
        NOT VALID;
""")
op.execute("""
    ALTER TABLE diagnoses
        ADD CONSTRAINT diagnoses_severity_check
        CHECK (severity IN ('low', 'medium', 'high'))
        NOT VALID;
""")
# Step 2: VALIDATE (SHARE UPDATE EXCLUSIVE — non-blocking for concurrent DML)
# ONLY run after pre-flight confirms zero violations
op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_verdict_check;")
op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_severity_check;")
```

**Idempotency note:** Wrap constraint creation with IF NOT EXISTS equivalent. Alembic does not natively support idempotent ADD CONSTRAINT, so use `op.execute` with DO $$ blocks or accept that second run errors on "constraint already exists" — handle by checking `pg_constraint` first or catching the error in downgrade.

### Pattern 4: Presenter S3 key tenant-prefix assertion (S3-01)

**What:** Before returning S3 payload content, assert the fetched key begins with the requesting tenant's UUID. Return 403 if the key is for a different tenant.

**Current state:** `_fetch_s3_payload` in `spans.py` has no tenant check — it accepts any key and fetches it.

**Current key format:** `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`
The key always starts with `{tenant_id}/`, so a `key.startswith(f"{tenant_id}/")` check is sufficient regardless of the month segment.

**Updated `_fetch_s3_payload`:**
```python
async def _fetch_s3_payload(
    s3_client,
    bucket: str,
    key: str | None,
    tenant_id: str,   # NEW parameter
) -> str | None:
    if not key:
        return None
    # Tenant ownership assertion (S3-01)
    if not key.startswith(f"{tenant_id}/"):
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "S3 key does not belong to requesting tenant"},
        )
    response = await s3_client.get_object(Bucket=bucket, Key=key)
    body = await response["Body"].read()
    data = json.loads(body)
    return data.get("value")
```

**Note:** The caller `_fetch_all_s3_payloads` and `get_span_detail` must pass `tenant_id` through. The ClickHouse query already filters `WHERE tenant_id = %(tenant_id)s AND span_id = %(span_id)s`, so a cross-tenant key appearing in `prompt_ref` would only happen if ClickHouse data is corrupted. The assertion is defence-in-depth.

### Pattern 5: RLS silent-empty detection integration test (DB-01 Success Criterion 7)

**What:** Connect to PostgreSQL WITHOUT calling `set_config` / `SET LOCAL`, verify that `SELECT COUNT(*) FROM span_scores` returns 0 even when rows exist. This proves RLS filters silently rather than errors.

**Key behaviors confirmed (MEDIUM confidence, multiple web sources):**
- RLS `USING` clause that evaluates to FALSE returns zero rows (no error)
- `current_setting('app.current_tenant_id', true)` returns NULL when variable is unset (second arg `true` = no-error-on-missing)
- `tenant_id::text = NULL` evaluates to NULL (not TRUE), so ALL rows are filtered out

**Test pattern (integration, requires VALIDATION_STACK=1):**
```python
import psycopg2

def test_rls_span_scores_silent_empty_without_set_config():
    """Connecting without SET LOCAL must see zero span_scores rows."""
    # Connect as a non-BYPASSRLS role (NOT the migration superuser DATABASE_URL)
    conn = psycopg2.connect(os.environ["DATABASE_URL_RLS_ROLE"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM span_scores")
        count = cur.fetchone()[0]
    conn.close()
    assert count == 0, f"RLS not enforced: got {count} rows without SET LOCAL"
```

**Important:** This test requires a second DATABASE_URL pointing to a non-BYPASSRLS role. Alternatively, the test can connect as the same migration user but verify via `pg_class.relrowsecurity` and `pg_class.relforcerowsecurity` that the constraint is in place, then trust the policy logic.

### Anti-Patterns to Avoid

- **Running VALIDATE CONSTRAINT before pre-flight audit:** If existing diagnoses rows have `verdict='undetermined'` or `severity='critical'`, VALIDATE will fail with a constraint violation error. Run the audit SELECT first.
- **Using the BYPASSRLS migration role to test RLS:** The BYPASSRLS role bypasses all RLS policies; testing with it gives false confidence. Use a separate non-BYPASSRLS connection for the silent-empty test.
- **Assuming FORCE ROW LEVEL SECURITY blocks BYPASSRLS roles:** It does NOT. FORCE only affects table owners. Superusers and BYPASSRLS roles always bypass regardless.
- **Changing S3 key format for historical keys:** The month-segment format is already in use for existing spans. Only new spans need the new prefix. The `startswith(f"{tenant_id}/")` check works for both formats since `{tenant_id}/{YYYY-MM}/...` still starts with `{tenant_id}/`.
- **Updating providers without also updating the DB constraint:** The provider Literals and the DB CHECK must be consistent. Provider says `unknown`, DB constraint says `('model','architecture','prompt','unknown')` — these must match exactly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Idempotent migration | Custom try/except SQL wrapper | `op.execute("ALTER TABLE ... ADD CONSTRAINT ... NOT VALID")` inside `upgrade()` — use `op.get_bind().dialect.name` checks or wrap in DO $$ EXCEPTION | Alembic tracks applied revisions; migration only runs once in normal usage. The idempotency requirement is for "fresh + second run" — second run = same alembic_version row, so upgrade() is not called twice. |
| Tenant prefix validation | Regex or UUID parsing | Simple `key.startswith(f"{tenant_id}/")` string check | The key format is controlled by this codebase; prefix check is sufficient and fast |
| New ENUM type for verdict/severity | PostgreSQL ENUM | String CHECK constraint | ENUMs require ALTER TYPE to add values; CHECK on VARCHAR is zero-downtime extensible |

**Key insight:** The NOT VALID / VALIDATE pattern is explicitly designed for this situation — add a constraint to a live table without an ACCESS EXCLUSIVE lock. Don't try to drop and recreate the table.

## Common Pitfalls

### Pitfall 1: undetermined vs unknown mismatch (DB-03)
**What goes wrong:** The existing providers emit `verdict="undetermined"`. DB-03 requires the DB constraint to accept `unknown` not `undetermined`. If you write the constraint first without changing providers, every new diagnosis write will fail with a constraint violation.
**Why it happens:** The requirements changed the allowed vocabulary between v1.2 (provider design) and v1.3 (DB hardening).
**How to avoid:** Update provider Literals FIRST (base.py, anthropic.py, openai.py, ollama.py), then run the pre-flight audit, then apply the constraint.
**Warning signs:** Any 500 from POST /diagnose after migration 004 is applied.

### Pitfall 2: Testing FORCE RLS with BYPASSRLS connection
**What goes wrong:** The test passes with BYPASSRLS role but the feature doesn't actually protect anything useful, giving false confidence.
**Why it happens:** FORCE ROW LEVEL SECURITY only applies to table owners (a specific PostgreSQL role), not BYPASSRLS roles.
**How to avoid:** Use `pg_class` catalog query to verify `relforcerowsecurity = true` on all six tables. This is the correct mechanical verification without needing a non-BYPASSRLS user.
**Warning signs:** `SELECT relforcerowsecurity FROM pg_class WHERE relname = 'span_scores'` returns `f`.

### Pitfall 3: silent-empty test using migration role
**What goes wrong:** Test connects as BYPASSRLS migration user, sees all rows, assumes RLS is working correctly (it's not — it's being bypassed).
**Why it happens:** The DATABASE_URL is typically a superuser or BYPASSRLS role to run migrations.
**How to avoid:** The silent-empty integration test (Success Criterion 7) should either (a) use a dedicated low-privilege test role, or (b) be implemented as a unit test that mocks psycopg2 and asserts SET LOCAL is called — verifying the behavior through the policy logic rather than a live connection.

### Pitfall 4: Alembic second-run idempotency
**What goes wrong:** Running `alembic upgrade head` twice errors on "policy already exists" or "constraint already exists".
**Why it happens:** Alembic tracks migrations via `alembic_version` table — once revision 004 is in that table, `upgrade()` will not run again on a second invocation. True idempotency issue only occurs on a fresh database.
**How to avoid:** Test with `alembic downgrade -1 && alembic upgrade head` cycle to verify the migration round-trips cleanly. The "second run" in success criterion 4 means running `alembic upgrade head` when already at head — that exits with no error naturally.

### Pitfall 5: S3 403 test tenant mismatch setup
**What goes wrong:** Integration test doesn't actually set up a cross-tenant scenario — it fetches the span as the owning tenant, not the cross-tenant user.
**Why it happens:** The ClickHouse `WHERE tenant_id = %(tenant_id)s` guard means a cross-tenant span fetch returns 404 before hitting S3. To test the S3 key assertion, you need a scenario where the S3 key itself has a different tenant prefix than the requesting tenant — which means either (a) injecting a malformed key directly, or (b) crafting a test that calls `_fetch_s3_payload` directly with a mismatched key.
**How to avoid:** Test `_fetch_s3_payload` as a unit test with a mismatched tenant prefix — don't rely on the full HTTP stack for this assertion.

## Code Examples

### Migration 004 complete structure
```python
# Source: PostgreSQL official docs + existing migrations 001/002/003 in codebase
revision: str = "004"
down_revision: str = "003"

def upgrade() -> None:
    # 1. span_scores RLS (DB-01)
    op.execute("ALTER TABLE span_scores ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation ON span_scores
            USING (tenant_id::text = current_setting('app.current_tenant_id', true));
    """)
    op.execute("ALTER TABLE span_scores FORCE ROW LEVEL SECURITY;")

    # 2. FORCE RLS on all existing RLS tables (DB-02)
    for table in ("tenants", "users", "api_keys", "flags", "diagnostics", "diagnoses"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    # 3. CHECK constraints NOT VALID (DB-03)
    op.execute("""
        ALTER TABLE diagnoses
            ADD CONSTRAINT diagnoses_verdict_check
            CHECK (verdict IN ('model', 'architecture', 'prompt', 'unknown'))
            NOT VALID;
    """)
    op.execute("""
        ALTER TABLE diagnoses
            ADD CONSTRAINT diagnoses_severity_check
            CHECK (severity IN ('low', 'medium', 'high'))
            NOT VALID;
    """)
    # 4. VALIDATE (requires zero pre-existing violations)
    op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_verdict_check;")
    op.execute("ALTER TABLE diagnoses VALIDATE CONSTRAINT diagnoses_severity_check;")

def downgrade() -> None:
    op.execute("DROP CONSTRAINT IF EXISTS diagnoses_severity_check ON diagnoses;")
    op.execute("DROP CONSTRAINT IF EXISTS diagnoses_verdict_check ON diagnoses;")
    for table in ("tenants", "users", "api_keys", "flags", "diagnostics", "diagnoses"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON span_scores;")
    op.execute("ALTER TABLE span_scores DISABLE ROW LEVEL SECURITY;")
```

### Pre-flight audit query (run before migration 004)
```sql
-- Source: success criterion 6
SELECT COUNT(*) FROM diagnoses
WHERE verdict NOT IN ('model', 'architecture', 'prompt', 'unknown')
   OR severity NOT IN ('low', 'medium', 'high');
-- Expected: 0
```

### pg_class verification query (DB-02)
```sql
-- Source: success criterion 2
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('tenants', 'users', 'api_keys', 'flags', 'diagnostics', 'diagnoses', 'span_scores');
-- All seven rows must have relrowsecurity = t AND relforcerowsecurity = t
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| span_scores no RLS (migration 002 comment: "Phase 4 will add per-tenant filtering") | span_scores + RLS tenant_isolation policy (Phase 14) | Phase 14 | score_writer.py must use SET LOCAL |
| table owner bypasses RLS silently | FORCE ROW LEVEL SECURITY on all tables | Phase 14 | table owner cannot accidentally bypass policies |
| diagnoses accepts any string in verdict/severity | CHECK constraint limits to approved values | Phase 14 | bad LLM outputs are rejected at DB layer |
| S3 keys fetched without tenant ownership check | Presenter asserts key starts with `{tenant_id}/` | Phase 14 | cross-tenant key injection blocked |

**Current provider vocabulary mismatch (must fix in Phase 14):**
- `base.py` DiagnosisResult: `verdict` includes `"undetermined"`, severity includes `"critical"` — BOTH must be removed
- DB constraint will accept: `verdict IN ('model','architecture','prompt','unknown')`, `severity IN ('low','medium','high')`

## Open Questions

1. **Which six tables does Success Criterion 2 refer to?**
   - What we know: The criterion says `('spans','flags','span_scores','diagnoses','tenants','api_keys')` — but `spans` is a ClickHouse table with no PostgreSQL presence.
   - What's unclear: Should `users` and `diagnostics` (the old Phase 1 table) also get FORCE RLS? They have ENABLE RLS from migration 001 but are not listed.
   - Recommendation: Apply FORCE RLS to ALL tables that have ENABLE RLS: `tenants`, `users`, `api_keys`, `flags`, `diagnostics`, `diagnoses`, `span_scores`. The success criterion likely meant the six *non-span-scores* tables (span_scores being newly added). Planner should verify with project owner.

2. **Does the pre-flight audit need to handle existing `undetermined`/`critical` rows?**
   - What we know: The STATE.md blocker says "existing v1.2 data may violate new constraints." The pre-flight query tells us the count.
   - What's unclear: If count > 0, does the plan include a data migration (UPDATE diagnoses SET verdict='unknown' WHERE verdict='undetermined')?
   - Recommendation: Plan should include a task to run the pre-flight query and, if violations exist, run a UPDATE migration step before VALIDATE CONSTRAINT.

3. **Silent-empty test role availability**
   - What we know: The integration test for Success Criterion 7 requires a non-BYPASSRLS role to connect and see zero rows.
   - What's unclear: Is a second DATABASE_URL (non-BYPASSRLS) available in the Docker stack, or should the test be a unit test?
   - Recommendation: Implement as a unit test that mocks psycopg2 and asserts `SET LOCAL` is called inside the transaction. Save the live integration test for a future phase if a non-BYPASSRLS role is created.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 0.24.0 |
| Config file | `xeter/pyproject.toml` — `[tool.pytest.ini_options]` asyncio_mode="auto", testpaths=["tests"] |
| Quick run command | `cd xeter && pytest tests/worker/test_score_writer.py tests/diagnosticer/ -x -q` |
| Full suite command | `cd xeter && pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | score_writer uses SET LOCAL in explicit transaction | unit | `cd xeter && pytest tests/worker/test_score_writer.py -x -q` | No — Wave 0 |
| DB-01 | tenant_isolation RLS policy on span_scores exists | manual SQL / integration | Run `\d+ span_scores` or pg_policies query | No — manual check |
| DB-02 | relforcerowsecurity = t for all seven tables | manual SQL | `SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN (...)` | No — manual check |
| DB-03 | INSERT with bad verdict/severity raises constraint | unit (mocked) or integration | `cd xeter && pytest tests/diagnosticer/test_diagnose_endpoint.py -x -q` | Partial (existing tests don't test constraint) |
| DB-03 | Provider emits only valid vocabulary | unit | `cd xeter && pytest tests/diagnosticer/ -x -q` | Partial |
| S3-01 | _fetch_s3_payload rejects mismatched tenant prefix | unit | `cd xeter && pytest tests/presenter/test_span_detail.py -x -q` | Partial (no S3 key assertion test yet) |
| S3-01 | Cross-tenant S3 fetch returns 403 | integration | `VALIDATION_STACK=1 pytest xeter/tests/validation/test_s3_isolation.py -v` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `cd xeter && pytest tests/worker/ tests/diagnosticer/ tests/presenter/ -x -q`
- **Per wave merge:** `cd xeter && pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `xeter/tests/worker/test_score_writer.py` — covers DB-01 (SET LOCAL inside explicit transaction)
- [ ] `xeter/tests/presenter/test_s3_key_assertion.py` — covers S3-01 (403 on mismatched prefix) — OR add to `test_span_detail.py`
- [ ] `xeter/tests/validation/test_s3_isolation.py` — integration test for S3-01 cross-tenant 403

## Sources

### Primary (HIGH confidence)
- PostgreSQL official docs (https://www.postgresql.org/docs/current/sql-altertable.html) — FORCE ROW LEVEL SECURITY, NOT VALID, VALIDATE CONSTRAINT syntax and locking behavior
- PostgreSQL official docs (https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — table owner bypass behavior, BYPASSRLS attribute behavior with FORCE RLS
- Existing codebase: `flag_writer.py` — definitive pattern for SET LOCAL in psycopg2 explicit transaction
- Existing codebase: `migrations/versions/001_initial.py`, `003_diagnoses.py` — established op.execute pattern for RLS DDL in Alembic

### Secondary (MEDIUM confidence)
- https://www.bytebase.com/blog/postgres-row-level-security-footguns/ — confirmed silent-empty behavior when `current_setting` returns NULL
- https://pgdash.io/blog/exploring-row-level-security-in-postgres.html — confirmed table owner bypass default + FORCE override

### Tertiary (LOW confidence)
- N/A — all critical claims verified with primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed; verified in pyproject.toml
- Architecture patterns (RLS, FORCE, NOT VALID): HIGH — verified against PostgreSQL official docs
- Provider vocabulary mismatch: HIGH — directly read from source code
- S3 key format: HIGH — directly read from s3.py source; prefix check logic is deterministic
- Silent-empty test role requirement: MEDIUM — behavior confirmed by docs/web sources; test role availability unknown

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 (PostgreSQL docs are stable; alembic 1.18.4 is current)
