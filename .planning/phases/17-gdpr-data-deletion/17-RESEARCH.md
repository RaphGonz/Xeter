# Phase 17: GDPR Data Deletion - Research

**Researched:** 2026-04-30
**Domain:** Multi-store tenant data deletion (ClickHouse, PostgreSQL, S3/MinIO, Redis)
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GDPR-01 | Operator can delete all data for a given tenant in one command — `delete_tenant.py --tenant-id <id>` shows a dry-run summary of affected rows and S3 objects by default; `--confirm` flag required to execute; deletion covers ClickHouse spans, all PostgreSQL tables, all S3 objects under `{tenant_id}/` prefix, and a documented Redis key flush procedure; script is idempotent | All four data stores fully mapped; S3 key prefix structure confirmed; existing script patterns (preflight_diagnoses_audit.py, reset.py) provide direct implementation templates |
</phase_requirements>

---

## Summary

Phase 17 implements a single-tenant deletion script (`delete_tenant.py`) covering all four data stores: ClickHouse (MergeTree `ALTER TABLE ... DELETE`), PostgreSQL (seven tables in dependency order), S3/MinIO (prefix-based recursive delete), and Redis (documented manual procedure). The project already has the necessary libraries, connection patterns, and env var conventions — no new dependencies are required.

The script follows the exact operator-script pattern established by `xeter/scripts/preflight_diagnoses_audit.py` and `xeter/scripts/reset.py`: a standalone Python script under `xeter/scripts/`, reading env vars, using psycopg2 (sync) for PostgreSQL, `clickhouse_connect` for ClickHouse, and `boto3` (sync) for S3. The dry-run / `--confirm` two-phase pattern matches GDPR-01 exactly and is a well-established operator safety pattern in this codebase.

**Critical finding:** The GDPR-01 requirement text mentions `diagnoses` but the schema has two tenant-scoped tables — `diagnostics` (Phase 1 legacy placeholder, `__tablename__ = "diagnostics"`) and `diagnoses` (Phase 11 Diagnosticer, `__tablename__ = "diagnoses"`). Both carry `tenant_id` and must be deleted. The planner should include both.

**S3 key structure confirmed:** Keys are `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`. The prefix `{tenant_id}/` cleanly covers all months and all spans for a tenant. Boto3's `list_objects_v2` + `delete_objects` (batch up to 1000) is the correct pattern; the requirement says `aws s3 rm --recursive` which is equivalent but requires the AWS CLI — using boto3 directly keeps the script self-contained.

**Primary recommendation:** One plan, one file: `xeter/scripts/delete_tenant.py`. Three sections: dry-run counts, confirmation gate (`--confirm`), deletion in safe dependency order. Script uses the same env vars already present in docker-compose.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2-binary | >=2.9.0 | Sync PostgreSQL connection for DELETE statements | Already in pyproject.toml; all operator scripts use this (flag_writer.py, score_writer.py, preflight_diagnoses_audit.py) |
| clickhouse-connect | 0.15.0 | ClickHouse HTTP client for ALTER TABLE ... DELETE | Already in pyproject.toml; get_clickhouse_client() already in shared/db/clickhouse.py |
| boto3 | >=1.35.0 | Sync S3 list + delete operations | Already in pyproject.toml; aioboto3 used in services but boto3 (sync) is correct for a CLI script |
| python-dotenv | latest | Load .env in dev context | Already in pyproject.toml; used in reset.py |
| argparse | stdlib | CLI argument parsing (--tenant-id, --confirm) | No new dependency needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| redis (sync) | >=5.0 | Optional: count items in analysis_queue for dry-run | Redis key flush is documented procedure, not scripted — but queue length can be shown in dry-run |
| uuid | stdlib | Validate --tenant-id is a valid UUID before touching DBs | Prevents typos from causing silent no-ops |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| boto3 (sync) | aioboto3 | aioboto3 is async — requires asyncio.run() wrapper; boto3 is simpler for a CLI script |
| Raw psycopg2 DELETE | SQLAlchemy async | SQLAlchemy adds RLS complexity (SET LOCAL required per transaction); psycopg2 is simpler and matches existing scripts |
| `aws s3 rm --recursive` | boto3 list+delete | CLI depends on AWS CLI being installed; boto3 is self-contained and handles pagination cleanly |

**Installation:**
No new packages needed. All dependencies are already in `xeter/pyproject.toml`.

---

## Architecture Patterns

### Recommended Project Structure
```
xeter/scripts/
├── delete_tenant.py      # NEW — the GDPR Art. 17 deletion script
├── preflight_diagnoses_audit.py  # Reference pattern for operator scripts
├── reset.py              # Reference pattern for multi-store operations
└── ...existing scripts...

docs/
└── GDPR_DELETION_RUNBOOK.md   # NEW — deployment guide section (matches JWT_ROTATION_RUNBOOK.md style)
```

### Pattern 1: Dry-Run + Confirm Gate
**What:** Script counts affected rows/objects in all stores and prints summary. Exits without changes unless `--confirm` is passed.
**When to use:** All destructive operator scripts — mandatory per GDPR-01.
**Example:**
```python
# Source: xeter/scripts/preflight_diagnoses_audit.py (existing pattern)
import argparse, sys

def main() -> None:
    parser = argparse.ArgumentParser(description="Delete all data for a tenant (GDPR Art. 17)")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID to delete")
    parser.add_argument("--confirm", action="store_true", help="Execute deletion (default: dry-run only)")
    args = parser.parse_args()

    # Validate UUID before any DB touch
    try:
        tenant_uuid = str(uuid.UUID(args.tenant_id))
    except ValueError:
        print(f"ERROR: '{args.tenant_id}' is not a valid UUID.")
        sys.exit(1)

    counts = _count_all(tenant_uuid)
    _print_dry_run_summary(counts)

    if not args.confirm:
        print("\nDRY-RUN: No data deleted. Pass --confirm to execute.")
        sys.exit(0)

    _delete_all(tenant_uuid)
    print("\nDELETION COMPLETE.")
```

### Pattern 2: PostgreSQL Deletion — Dependency Order (CRITICAL)
**What:** Foreign key constraints require deleting child rows before parent rows. The `tenants` row must be deleted LAST.
**When to use:** Any multi-table PostgreSQL deletion.

**Correct deletion order (child before parent):**
```
1. span_scores      — references no FK to tenants directly, but tenant-scoped
2. diagnostics      — legacy placeholder, no FK, tenant-scoped
3. diagnoses        — no FK to tenants directly, tenant-scoped
4. flags            — no FK to tenants directly, tenant-scoped
5. api_keys         — FK to tenants.tenant_id
6. users            — FK to tenants.tenant_id
7. tenants          — parent row, deleted LAST
```

**Example:**
```python
# Source: inspection of xeter/migrations/versions/001_initial.py
import psycopg2

_PG_DELETE_TABLES = [
    "span_scores",   # no FK to tenants; safe first
    "diagnostics",   # no FK to tenants; legacy placeholder
    "diagnoses",     # no FK to tenants
    "flags",         # no FK to tenants
    "api_keys",      # FK: api_keys.tenant_id -> tenants.tenant_id
    "users",         # FK: users.tenant_id -> tenants.tenant_id
    "tenants",       # parent — LAST
]

def _delete_postgres(conn, tenant_id: str) -> None:
    with conn.cursor() as cur:
        for table in _PG_DELETE_TABLES:
            cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
    conn.commit()
```

Note: The script connects with the existing DATABASE_URL which uses the BYPASSRLS role. No SET LOCAL is needed for deletion (BYPASSRLS bypasses the RLS filter). Avoid string-interpolating tenant_id into SQL — always use parameterised queries.

### Pattern 3: ClickHouse Deletion — ALTER TABLE ... DELETE (Lightweight Delete)
**What:** ClickHouse MergeTree does not support standard SQL DELETE. The correct mutation syntax is `ALTER TABLE spans DELETE WHERE tenant_id = :id`.
**When to use:** All ClickHouse row deletions on MergeTree tables.

```python
# Source: clickhouse-connect docs + GDPR-01 requirement spec
from xeter.shared.db.clickhouse import get_clickhouse_client

def _delete_clickhouse(tenant_id: str) -> None:
    client = get_clickhouse_client()
    # ALTER TABLE ... DELETE is an async mutation in ClickHouse
    # clickhouse-connect .command() sends it and returns when accepted (not when complete)
    client.command(
        "ALTER TABLE spans DELETE WHERE tenant_id = %(tenant_id)s",
        parameters={"tenant_id": tenant_id},
    )
```

**ClickHouse mutation caveat (HIGH confidence):** `ALTER TABLE ... DELETE` in ClickHouse is an *asynchronous mutation* — the command returns immediately but the actual deletion happens in the background. For an operator script, this is acceptable. The dry-run can count rows with `SELECT count() FROM spans WHERE tenant_id = :id` before deletion.

### Pattern 4: S3 Deletion — Paginated Batch Delete
**What:** boto3 `list_objects_v2` with prefix, then `delete_objects` in batches of up to 1000.
**When to use:** Deleting all S3 objects under a tenant prefix.

```python
# Source: boto3 docs (standard paginated delete pattern)
import boto3, os

def _count_s3_objects(s3, bucket: str, prefix: str) -> int:
    count = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        count += len(page.get("Contents", []))
    return count

def _delete_s3_objects(s3, bucket: str, prefix: str) -> int:
    deleted = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        keys = [{"Key": obj["Key"]} for obj in objects]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        deleted += len(keys)
    return deleted

def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )
```

**S3 prefix:** `{tenant_id}/` — confirmed from `xeter/services/analyser/s3.py` line 94: `prefix = f"{tenant_id}/{month}/{span_id}"`. The tenant UUID is always the first path segment.

### Pattern 5: Redis — Documented Manual Flush
**What:** Redis holds a single global queue key `analysis_queue` (LPUSH/BRPOP list). There are no per-tenant Redis keys in v1.3. The flush is documented, not scripted, because flushing the global queue would affect other tenants.
**When to use:** When GDPR Art. 17 right-to-erasure request is received.

The documented Redis procedure is:
```bash
# 1. Find span_ids for the tenant (get from ClickHouse dry-run output)
# 2. If the queue is processing, stop the Worker briefly
# 3. Inspect queue: redis-cli -a $REDIS_PASSWORD LRANGE analysis_queue 0 -1
# 4. Remove matching span_ids: redis-cli -a $REDIS_PASSWORD LREM analysis_queue 0 <span_id>
# 5. Restart Worker
#
# NOTE: In practice, analysis_queue is a short-lived transit queue.
# Spans are processed within seconds of ingestion. GDPR deletion is typically
# invoked after the tenant is inactive, making this queue empty.
```

The script should print this procedure text as part of the dry-run output rather than attempting automated Redis manipulation (which could corrupt the global queue for other tenants).

### Anti-Patterns to Avoid
- **Deleting tenants row before child rows:** FK violation — `api_keys` and `users` reference `tenants.tenant_id`. Delete tenants LAST.
- **String-interpolating tenant_id into SQL:** SQL injection risk. Always use parameterised queries (`%s` for psycopg2, `%(key)s` for clickhouse-connect).
- **Omitting `diagnostics` table:** The GDPR-01 requirement text says `diagnoses` but the schema has both `diagnostics` (legacy) and `diagnoses` (v1.2). Both have `tenant_id` and must be deleted.
- **Assuming ClickHouse DELETE is synchronous:** `ALTER TABLE ... DELETE` is a background mutation — the script should note this in output. Do not assume the count drops to zero immediately after running.
- **Not validating tenant_id as UUID before queries:** A typo in the UUID will silently match zero rows (no error). Validate with `uuid.UUID()` before any DB call.
- **Using `FLUSHDB` for Redis:** Would delete all tenants' queued spans, not just the target tenant's.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| S3 object listing with pagination | Manual page-tracking loop | `s3.get_paginator("list_objects_v2")` | Handles the 1000-object page boundary automatically |
| S3 batch deletion | One delete per object | `delete_objects` with batch of up to 1000 keys | boto3 API limit; batch is far faster |
| Database connection from env | Custom DSN parser | `_get_dsn()` helper from flag_writer.py / preflight_diagnoses_audit.py | Already tested in this codebase; handles asyncpg scheme stripping |
| ClickHouse client | Direct HTTP calls | `get_clickhouse_client()` from `xeter.shared.db.clickhouse` | Already wired to CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD env vars |
| Argument parsing | Manual sys.argv parsing | `argparse` stdlib | Gives `--help` for free, validates required args |
| UUID validation | Regex | `uuid.UUID(args.tenant_id)` — raises ValueError on bad input | Standard library, handles all UUID formats |

---

## Common Pitfalls

### Pitfall 1: Wrong PostgreSQL Deletion Order (FK Violation)
**What goes wrong:** Deleting `tenants` before `api_keys` or `users` raises `ForeignKeyViolation`.
**Why it happens:** `users.tenant_id` and `api_keys.tenant_id` are foreign keys referencing `tenants.tenant_id`.
**How to avoid:** Always delete in child-first order: `span_scores, diagnostics, diagnoses, flags, api_keys, users, tenants`.
**Warning signs:** `psycopg2.errors.ForeignKeyViolation` during development testing.

### Pitfall 2: Missing `diagnostics` Table (Legacy Placeholder)
**What goes wrong:** Deletion appears complete but `diagnostics` rows remain for the tenant (legacy Phase 1 placeholder table, `__tablename__ = "diagnostics"`).
**Why it happens:** GDPR-01 requirement only mentions `diagnoses` (the Phase 11 Diagnosticer table). The `diagnostics` table is the older placeholder. Both have `tenant_id`.
**How to avoid:** Explicitly include `diagnostics` in the deletion table list. Verify by checking `SELECT count(*) FROM diagnostics WHERE tenant_id = :id` returns 0 after deletion.
**Warning signs:** Incomplete GDPR erasure — rows remaining in a table the audit missed.

### Pitfall 3: ClickHouse Mutation Is Asynchronous
**What goes wrong:** Script reports "deletion complete" but `SELECT count()` still shows rows immediately after `ALTER TABLE spans DELETE`.
**Why it happens:** ClickHouse MergeTree mutations are applied in the background. `client.command()` returns when the mutation is *accepted*, not *applied*.
**How to avoid:** Add a note in script output: "ClickHouse deletion submitted as background mutation — rows may persist briefly. Run dry-run again after 30 seconds to verify." Do not spin-wait in the script.
**Warning signs:** Testing immediately after the script shows non-zero count. This is expected — wait a few seconds and recount.

### Pitfall 4: S3 Prefix Must Include Trailing Slash
**What goes wrong:** Prefix `{tenant_id}` without trailing `/` could match a tenant whose UUID is a prefix of another tenant's UUID (highly unlikely with UUIDs, but a correctness concern).
**Why it happens:** S3 prefix filtering is a string prefix match.
**How to avoid:** Always use `prefix = f"{tenant_id}/"` (with trailing slash). Confirmed: the actual key structure starts with `{tenant_id}/{YYYY-MM}/...` so the slash is always present.

### Pitfall 5: Idempotency — Second Run Must Not Error
**What goes wrong:** Script errors on second run because tenant row doesn't exist (DELETE on non-existent tenant raises no error in SQL, but script might error if it checks for tenant existence as a precondition).
**Why it happens:** If the script hard-errors when the tenant is not found (e.g., raises an exception after finding 0 rows), it is not idempotent.
**How to avoid:** Never treat "0 rows affected" as an error. DELETE WHERE is a no-op when no rows match — that is correct idempotent behavior. Only validate UUID format, not tenant existence.

### Pitfall 6: RLS Blocks COUNT on PostgreSQL in Dry-Run
**What goes wrong:** `SELECT count(*) FROM flags WHERE tenant_id = :id` returns 0 even when rows exist, because RLS is active and `app.current_tenant_id` is not set.
**Why it happens:** The deletion script connects with DATABASE_URL (BYPASSRLS role) — so RLS is bypassed automatically. But if someone tests with a non-BYPASSRLS role, counts will be wrong.
**How to avoid:** Document that the script must use the DATABASE_URL (BYPASSRLS role). The script does not need `SET LOCAL` for counting or deletion because BYPASSRLS bypasses the policy entirely.

---

## Code Examples

Verified patterns from existing codebase:

### PostgreSQL Connection (sync, matching existing scripts)
```python
# Source: xeter/scripts/preflight_diagnoses_audit.py
import os, psycopg2

def _get_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgres+asyncpg://", "postgresql://")
    )

conn = psycopg2.connect(_get_dsn())
conn.autocommit = True   # for counting; use False + explicit commit for deletes
```

### ClickHouse Count + Delete
```python
# Source: xeter/shared/db/clickhouse.py — get_clickhouse_client() factory
from xeter.shared.db.clickhouse import get_clickhouse_client

client = get_clickhouse_client()

# Count
result = client.query(
    "SELECT count() FROM spans WHERE tenant_id = %(tenant_id)s",
    parameters={"tenant_id": tenant_id},
)
ch_count = result.result_rows[0][0]

# Delete (async mutation — returns when accepted, not complete)
client.command(
    "ALTER TABLE spans DELETE WHERE tenant_id = %(tenant_id)s",
    parameters={"tenant_id": tenant_id},
)
```

### Dry-Run Summary Output Format (matching success criteria)
```
Dry-run summary for tenant: 550e8400-e29b-41d4-a716-446655440000

  ClickHouse spans:     1,243 rows
  PostgreSQL flags:       891 rows
  PostgreSQL span_scores: 4,972 rows
  PostgreSQL diagnostics:     0 rows
  PostgreSQL diagnoses:     412 rows
  PostgreSQL api_keys:        3 rows
  PostgreSQL users:           2 rows
  PostgreSQL tenants:         1 row
  S3 objects:             3,729 objects (prefix: 550e8400-e29b-41d4-a716-446655440000/)

  Redis (analysis_queue): ~0 items (transit queue — typically empty)
  Redis flush procedure: See GDPR deletion runbook.

DRY-RUN: No data deleted. Pass --confirm to execute.
```

### Full Script Invocations (matching GDPR-01 success criteria)
```bash
# Dry-run (safe, no changes):
python xeter/scripts/delete_tenant.py --tenant-id 550e8400-e29b-41d4-a716-446655440000

# Execute deletion:
python xeter/scripts/delete_tenant.py --tenant-id 550e8400-e29b-41d4-a716-446655440000 --confirm
```

---

## Data Store Inventory

Complete map of all stores and tenant-scoped data:

### ClickHouse
| Table | Deletion SQL | Notes |
|-------|-------------|-------|
| `spans` | `ALTER TABLE spans DELETE WHERE tenant_id = %(tenant_id)s` | Async mutation; confirm with subsequent count |

### PostgreSQL (deletion order — child before parent)
| Table | tenant_id column | FK? | Delete SQL |
|-------|-----------------|-----|-----------|
| `span_scores` | `tenant_id` (UUID) | No FK to tenants | `DELETE FROM span_scores WHERE tenant_id = %s` |
| `diagnostics` | `tenant_id` (UUID) | No FK | `DELETE FROM diagnostics WHERE tenant_id = %s` |
| `diagnoses` | `tenant_id` (UUID) | No FK | `DELETE FROM diagnoses WHERE tenant_id = %s` |
| `flags` | `tenant_id` (UUID) | No FK | `DELETE FROM flags WHERE tenant_id = %s` |
| `api_keys` | `tenant_id` (UUID) | FK -> tenants | `DELETE FROM api_keys WHERE tenant_id = %s` |
| `users` | `tenant_id` (UUID) | FK -> tenants | `DELETE FROM users WHERE tenant_id = %s` |
| `tenants` | `tenant_id` (PK) | N/A | `DELETE FROM tenants WHERE tenant_id = %s` |

### S3 / MinIO
| Key Pattern | Prefix for Deletion | Library |
|-------------|--------------------|----|
| `{tenant_id}/{YYYY-MM}/{span_id}/prompt.json` | `{tenant_id}/` | boto3 list_objects_v2 + delete_objects |
| `{tenant_id}/{YYYY-MM}/{span_id}/response.json` | `{tenant_id}/` | same |
| `{tenant_id}/{YYYY-MM}/{span_id}/raw_response.json` | `{tenant_id}/` | same |
| `{tenant_id}/{YYYY-MM}/{span_id}/available_tools.json` | `{tenant_id}/` | same |

### Redis
| Key | Type | Content | Deletion Strategy |
|-----|------|---------|------------------|
| `analysis_queue` | List (LPUSH/BRPOP) | span_id strings (global, all tenants) | Documented manual procedure only — not scripted |

No per-tenant Redis keys exist in v1.3 (per-tenant queues are OPS-F02, deferred to v1.4).

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|-----------------|-------|
| ClickHouse `DELETE FROM` (standard SQL) | `ALTER TABLE ... DELETE WHERE` (mutation) | ClickHouse MergeTree has no standard SQL DELETE; mutations are the only mechanism |
| Direct S3 key enumeration | `list_objects_v2` paginator | Handles >1000 objects automatically via pagination |

---

## Open Questions

1. **Should `diagnostics` (legacy) be explicitly listed in GDPR-01 success criteria?**
   - What we know: The table exists, has tenant_id, and must be deleted for full erasure
   - What's unclear: The requirement text only mentions `diagnoses` — the planner should explicitly add `diagnostics` to the deletion list
   - Recommendation: Include `diagnostics` in the deletion, note the discrepancy in plan comments

2. **Should the script wait for ClickHouse mutation to complete?**
   - What we know: `ALTER TABLE ... DELETE` is asynchronous; `system.mutations` table can be polled
   - What's unclear: Whether a blocking wait is appropriate for an operator CLI
   - Recommendation: Do not block. Print a note: "ClickHouse mutation submitted — run dry-run again after 30s to verify count is 0." This keeps the script simple and avoids an arbitrary timeout.

3. **Runbook location — standalone docs/ file or deployment guide section?**
   - What we know: `docs/JWT_ROTATION_RUNBOOK.md` is a separate file; the success criteria says "documented in the deployment guide"
   - What's unclear: Whether there is an existing deployment guide file
   - Recommendation: Create `docs/GDPR_DELETION_RUNBOOK.md` mirroring the JWT runbook pattern. The deployment guide reference in success criteria can point to this file.

---

## Sources

### Primary (HIGH confidence)
- `xeter/scripts/preflight_diagnoses_audit.py` — operator script pattern (psycopg2 sync, env var loading, exit codes)
- `xeter/scripts/reset.py` — multi-store operator script pattern (postgres + clickhouse + seed)
- `xeter/shared/db/clickhouse.py` — ClickHouse client factory and `client.command()` / `client.query()` API
- `xeter/shared/db/postgres.py` — PostgreSQL async connection (reference; script uses sync psycopg2)
- `xeter/shared/db/redis.py` — Redis client; confirms `REDIS_URL` env var pattern
- `xeter/services/analyser/s3.py` — S3 key structure: `{tenant_id}/{YYYY-MM}/{span_id}/{field}.json`
- `xeter/services/analyser/queue.py` — Redis queue key: `analysis_queue` (global, not per-tenant)
- `xeter/shared/models.py` — All ORM models with `__tablename__` confirming both `diagnostics` and `diagnoses` exist
- `xeter/migrations/versions/001_initial.py` — FK structure: `users.tenant_id` and `api_keys.tenant_id` FK to `tenants`
- `deploy/docker-compose.yml` — All env var names: `DATABASE_URL`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `REDIS_URL`, `REDIS_PASSWORD`
- `xeter/services/worker/flag_writer.py` — `_get_dsn()` helper: asyncpg scheme stripping pattern

### Secondary (MEDIUM confidence)
- ClickHouse `ALTER TABLE ... DELETE` async mutation behavior — confirmed by clickhouse-connect docs and ClickHouse MergeTree documentation. Mutations are always background operations.
- boto3 `list_objects_v2` paginator + `delete_objects` batch pattern — standard AWS SDK pattern, well-documented.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml, all connection patterns verified in existing scripts
- Architecture: HIGH — deletion order derived from migration FK definitions; S3 prefix confirmed from source
- Pitfalls: HIGH — FK ordering and ClickHouse async mutation verified from schema/docs; `diagnostics` table gap is a direct schema inspection finding
- Redis: HIGH (documentation strategy) / MEDIUM (exact key content) — queue key name confirmed in source; no per-tenant keys confirmed

**Research date:** 2026-04-30
**Valid until:** 2026-05-30 (stable schema; boto3/psycopg2/clickhouse-connect APIs do not change at patch level)
