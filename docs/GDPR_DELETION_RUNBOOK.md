# GDPR Art. 17 Tenant Deletion Runbook

**Audience:** Operators with production access.
**Applies to:** Xeter v1.3+.
**Last updated:** 2026-04-30

---

## Overview

GDPR Article 17 ("Right to Erasure") requires that personal data be deleted upon a verified erasure request. `delete_tenant.py` is the single operator script that fulfills this obligation for Xeter.

The script covers all four data stores where tenant data resides:

| Store | What is deleted |
|-------|----------------|
| **ClickHouse** | All rows in the `spans` table for the tenant |
| **PostgreSQL** | Rows across 7 tables: `span_scores`, `diagnostics`, `diagnoses`, `flags`, `api_keys`, `users`, `tenants` |
| **S3** | All objects under the `{tenant_id}/` prefix |
| **Redis** | `analysis_queue` is a short-lived global transit queue — manual procedure documented below |

By default the script performs a **dry-run**: it counts affected data and prints a summary without deleting anything. Pass `--confirm` to execute the deletion.

---

## When to Use

- A GDPR right-to-erasure request has been verified and approved.
- A tenant account is being closed under a data deletion agreement.

---

## Prerequisites

The script must be run from the **repo root** (where `xeter/` is importable as a Python package):

```bash
cd /path/to/xeter-repo
```

The following environment variables must be set before running the script:

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | PostgreSQL connection URL. Accepted schemes: `postgresql+asyncpg://`, `postgres+asyncpg://`, or plain `postgresql://`. |
| `CLICKHOUSE_HOST` | Yes | ClickHouse server hostname. |
| `CLICKHOUSE_PASSWORD` | Yes | ClickHouse password. |
| `S3_ENDPOINT_URL` | Yes | S3-compatible endpoint URL (e.g., MinIO). |
| `S3_ACCESS_KEY` | Yes | S3 access key ID. |
| `S3_SECRET_KEY` | Yes | S3 secret access key. |
| `S3_BUCKET` | No | Bucket name. Defaults to `xeter-payloads` if unset. |
| `REDIS_URL` | Yes | Redis connection URL (e.g., `redis://:password@host:6379/0`). Used for queue-length display in dry-run only. Redis unavailability does not block the dry-run. |

If any required variable is unset, the script will raise a `KeyError` at the point where that variable is first accessed (after UUID validation). Ensure your environment is fully configured before running.

---

## Step-by-Step Procedure

### Step 1 — Dry-run: verify the correct tenant and review affected data

```bash
python xeter/scripts/delete_tenant.py --tenant-id <tenant-uuid>
```

The script validates the UUID, connects to all stores, and prints a summary like:

```
Connecting to data stores for tenant: 550e8400-e29b-41d4-a716-446655440000 ...

Dry-run summary for tenant: 550e8400-e29b-41d4-a716-446655440000

  ClickHouse spans:         12,481 rows
  PostgreSQL span_scores:      934 rows
  PostgreSQL diagnostics:      102 rows
  PostgreSQL diagnoses:        102 rows
  PostgreSQL flags:             47 rows
  PostgreSQL api_keys:           3 rows
  PostgreSQL users:              2 rows
  PostgreSQL tenants:            1 rows
  S3 objects:               12,481 objects  (prefix: 550e8400-e29b-41d4-a716-446655440000/)

  Redis (analysis_queue): ~0 items  (transit queue — typically empty after processing)
  Redis flush procedure:
    If tenant spans are still queued (rare):
    1. Stop the Worker service: docker compose stop worker
    2. Inspect queue: redis-cli -a $REDIS_PASSWORD LRANGE analysis_queue 0 -1
    3. Remove matching span_ids one by one: redis-cli -a $REDIS_PASSWORD LREM analysis_queue 0 <span_id>
    4. Restart Worker: docker compose start worker
    NOTE: The analysis_queue is a short-lived transit queue. Spans are processed within
    seconds of ingestion. GDPR deletion is typically invoked after the tenant is inactive,
    making this queue empty.

DRY-RUN: No data deleted. Pass --confirm to execute.
```

**Before continuing:** confirm the `tenant-uuid` in the output matches the erasure request. Once `--confirm` is passed, the deletion is immediate (PostgreSQL and S3) or submitted as a background mutation (ClickHouse).

---

### Step 2 — Execute deletion

```bash
python xeter/scripts/delete_tenant.py --tenant-id <tenant-uuid> --confirm
```

Expected output:

```
Connecting to data stores for tenant: 550e8400-e29b-41d4-a716-446655440000 ...

Dry-run summary for tenant: 550e8400-e29b-41d4-a716-446655440000

  ClickHouse spans:         12,481 rows
  ...
  DRY-RUN: No data deleted. Pass --confirm to execute.

Executing deletion for tenant: 550e8400-e29b-41d4-a716-446655440000 ...

  ClickHouse: mutation submitted (background — run dry-run again after 30s to verify count is 0)
  Deleted from PostgreSQL.span_scores: 934 rows
  Deleted from PostgreSQL.diagnostics: 102 rows
  Deleted from PostgreSQL.diagnoses: 102 rows
  Deleted from PostgreSQL.flags: 47 rows
  Deleted from PostgreSQL.api_keys: 3 rows
  Deleted from PostgreSQL.users: 2 rows
  Deleted from PostgreSQL.tenants: 1 rows
  Deleted from S3: 12,481 objects

DELETION COMPLETE. Tenant 550e8400-e29b-41d4-a716-446655440000 data removed from ClickHouse, PostgreSQL, and S3.
```

---

### Step 3 — Verify deletion (re-run dry-run)

Wait at least 30 seconds after Step 2, then re-run the dry-run to confirm all counts are zero:

```bash
python xeter/scripts/delete_tenant.py --tenant-id <tenant-uuid>
```

**Expected result:**
- All PostgreSQL counts: `0 rows`
- S3 objects: `0 objects`
- ClickHouse spans: `0 rows` — see ClickHouse async mutation note below. If the count is still non-zero immediately after deletion, wait 30 seconds and re-run.

---

## Redis Flush (If Needed)

The `analysis_queue` is a **global** FIFO transit queue shared by all tenants. Spans are pushed onto it at ingestion and consumed by the Worker service within seconds. Under normal conditions the queue is empty when GDPR deletion is invoked (tenants are inactive before an erasure request is fulfilled).

If the dry-run shows a non-zero queue length and you need to ensure the deleted tenant's spans are not processed after deletion:

1. **Stop the Worker service:**
   ```bash
   docker compose stop worker
   ```

2. **Inspect the queue** to identify which entries belong to the tenant:
   ```bash
   redis-cli -a $REDIS_PASSWORD LRANGE analysis_queue 0 -1
   ```
   Each entry is a `span_id`. Cross-reference with your records to identify which span IDs belong to the tenant being deleted.

3. **Remove matching entries one by one:**
   ```bash
   redis-cli -a $REDIS_PASSWORD LREM analysis_queue 0 <span_id>
   ```
   Repeat for each span ID that belongs to the tenant.

4. **Restart the Worker service:**
   ```bash
   docker compose start worker
   ```

**Important:** Do NOT use `FLUSHDB`. The `analysis_queue` is shared across all tenants — flushing it deletes queued spans for every tenant, not just the one being erased.

---

## Idempotency

Running the script twice on the same tenant is safe. `DELETE WHERE tenant_id = X` on a table that no longer contains rows for that tenant is a no-op — PostgreSQL returns `0 rows affected` and no error is raised. The script will print `0 rows` for each table on the second run and exit cleanly.

This means the deletion procedure can be re-run safely if interrupted or if verification requires a second pass.

---

## ClickHouse Async Mutation Note

The ClickHouse deletion uses `ALTER TABLE spans DELETE WHERE tenant_id = ...`, which is a **background mutation** in ClickHouse MergeTree. The command is accepted immediately and returns without waiting for the mutation to complete.

Practical implications:

- The script prints `mutation submitted` and moves on — this is correct behaviour.
- ClickHouse applies the mutation in the background across data parts. On a lightly loaded cluster this typically completes within seconds; on a heavily partitioned dataset it may take longer.
- **To verify completion:** re-run the dry-run after 30 seconds. The ClickHouse span count should be `0`. If not, wait and re-run again.
- To monitor active mutations directly:
  ```sql
  SELECT mutation_id, command, is_done, latest_failed_part
  FROM system.mutations
  WHERE table = 'spans'
  ORDER BY create_time DESC
  LIMIT 10;
  ```

---

## Related Source Files

| File | Relevance |
|------|-----------|
| `xeter/scripts/delete_tenant.py` | The GDPR deletion script — dry-run and `--confirm` deletion |
| `docs/JWT_ROTATION_RUNBOOK.md` | Style pattern for this runbook |
| `docs/GDPR_DELETION_RUNBOOK.md` | This file |
