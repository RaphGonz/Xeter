---
phase: 31-readme-overhaul
reviewed: 2026-05-31T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - deploy/docker-compose.yml
  - README.md
findings:
  critical: 3
  warning: 5
  info: 2
  total: 10
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-05-31
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Two files reviewed: `deploy/docker-compose.yml` (the canonical runtime configuration) and `README.md` (the developer-facing documentation). The README is the primary deliverable of this phase, but it makes specific factual claims about default threshold values that are directly contradicted by the docker-compose file that ships alongside it. This is the dominant defect category: a developer reading the README and then tuning calibration against those documented defaults will be working from wrong baselines. Three of the mismatches are large enough to meaningfully alter detection behavior. In addition, docker-compose has a structural gap where application services can start before the MinIO bucket is provisioned, and the `minio-init` container is missing its `restart: "no"` guard. The README also references an env var (`WORKER_TRACE_FLUSH_TIMEOUT_S`) that has no corresponding entry in docker-compose, leaving it undiscoverable via the documented workflow.

---

## Critical Issues

### CR-01: README threshold table disagrees with docker-compose on 9 of 14 tunable flags

**File:** `README.md:128-149` (table), cross-referenced `deploy/docker-compose.yml:209-222`

**Issue:** The Detection Checks table documents "Default threshold" values that are the authoritative reference a user will consult before running calibration (per the Calibration section: "Reset tunable thresholds to defaults"). Every value in the table that differs from docker-compose becomes a misleading baseline. The mismatches, comparing `README claimed → docker-compose actual`:

| Flag | README | docker-compose | Delta |
|------|--------|----------------|-------|
| `unnecessary_tool_call` | 0.15 | 0.25 | +0.10 |
| `wrong_tool_args` | 0.4 | 0.2 | -0.20 |
| `no_tool` | 0.6 | 0.25 | -0.35 |
| `response_anomaly` | 0.4 | 0.1 | -0.30 |
| `missing_details` | 0.6 | 0.65 | +0.05 |
| `stale_context` | **85.0** | **0.75** | scale mismatch |
| `context_propagation_failure` | 0.5 | 0.35 | -0.15 |
| `history_loss` | 0.4 | 0.95 | +0.55 |
| `information_withholding` | 0.5 | 0.95 | +0.45 |
| `conversation_reset` | 0.25 | 0.3 | +0.05 |
| `incomplete_verification` | 0.7 | 0.95 | +0.25 |

The `stale_context` row is particularly dangerous: README shows 85.0 (percentage scale, consistent with `step_repetition`) while docker-compose sets 0.75 (decimal fraction). These are not the same unit. If the worker reads the env var as a decimal fraction, the README is misleading the user by 2 orders of magnitude about the threshold scale.

**Fix:** Reconcile the table with the actual docker-compose values. The table's "Default threshold" column must reflect what is actually set in `deploy/docker-compose.yml`, since that is what ships. Update every mismatched row. For `stale_context`, first determine which scale the worker code uses (checking `WORKER_THRESHOLD_STALE_CONTEXT` consumption in `xeter/services/worker/`) and ensure both files use the same unit, then update the table.

---

### CR-02: Application services start before MinIO bucket is provisioned

**File:** `deploy/docker-compose.yml:109-119` (analyser), `131-152` (presenter), `186-198` (worker), `224-241` (diagnosticer)

**Issue:** All four application services declare `minio: condition: service_healthy` as their MinIO dependency, but `minio` healthy means only the MinIO server process is running — the `minio-init` container creates the `xeter-payloads` bucket and sets the policy. None of the application services declare a dependency on `minio-init`. On a clean first boot the race is:

1. `minio` becomes healthy
2. All four application services start concurrently with `minio-init`
3. Any service that writes to `xeter-payloads` before `minio-init` completes gets a `NoSuchBucket` error

In practice the analyser writes span payloads to S3 on first ingest. If a span arrives before `minio-init` finishes, the write fails. This is a data-loss risk on the initial `--build` boot.

**Fix:** Add `minio-init: condition: service_completed_successfully` to the `depends_on` block of `analyser`, `worker`, `presenter`, and `diagnosticer`, mirroring the same pattern already used for `db-init`.

```yaml
# Example — apply the same block to analyser, presenter, worker, diagnosticer
depends_on:
  minio:
    condition: service_healthy
  minio-init:
    condition: service_completed_successfully   # <-- add this
  db-init:
    condition: service_completed_successfully
```

---

### CR-03: `minio-init` injects env vars into a shell command string — command injection if credentials contain special characters

**File:** `deploy/docker-compose.yml:79-82`

**Issue:** The `minio-init` command is constructed as a YAML block scalar passed to `/bin/sh -c`. The `${MINIO_ROOT_USER}` and `${MINIO_ROOT_PASSWORD}` values are interpolated by Docker Compose into the command string before the shell sees it:

```yaml
command: >-
  -c "mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
   && mc mb local/xeter-payloads --ignore-existing
   && mc anonymous set none local/xeter-payloads"
```

If `MINIO_ROOT_PASSWORD` contains a double-quote, space, `&&`, or shell metacharacter, the shell will interpret it as a command separator or argument boundary, producing either a broken command or arbitrary command execution. A password such as `pass"&&touch /pwned` would escape the quoted string. While this is a local-dev compose file, the pattern is still a security defect and a reliability hazard even with legitimate complex passwords.

**Fix:** Pass the credentials via the environment (they are already set in `environment:`) and reference them inside the shell string using single-quoted env var expansions, or use the `mc` flag form that accepts environment variables directly:

```yaml
entrypoint: /bin/sh
command: >-
  -c "mc alias set local http://minio:9000 \"$$MINIO_ROOT_USER\" \"$$MINIO_ROOT_PASSWORD\"
   && mc mb local/xeter-payloads --ignore-existing
   && mc anonymous set none local/xeter-payloads"
```

Note: in Docker Compose, `$$VAR` is a literal `$VAR` in the container (prevents Compose interpolation; shell then expands it at runtime). This avoids embedding the secret value into the command string at compose-interpolation time.

---

## Warnings

### WR-01: `WORKER_TRACE_FLUSH_TIMEOUT_S` documented in README but absent from docker-compose

**File:** `README.md:200-207` cross-referenced `deploy/docker-compose.yml:182-222`

**Issue:** The Performance section tells users:

> Set under the `worker` service in `deploy/docker-compose.yml`.

But `WORKER_TRACE_FLUSH_TIMEOUT_S` does not appear anywhere in the `worker` service environment block. A user following the documented tuning instructions will add the env var and get results, but there is no discoverable starting point — the var is invisible in the canonical config file. Worse, the README implies the var is already present with a commented default (it is not).

**Fix:** Add `WORKER_TRACE_FLUSH_TIMEOUT_S: "30"` to the `worker` service environment block in `deploy/docker-compose.yml` so the default is visible and the README's instruction is accurate.

---

### WR-02: `minio-init` missing `restart: "no"` — may restart on failure and re-run `mc mb`

**File:** `deploy/docker-compose.yml:70-82`

**Issue:** `db-init` explicitly sets `restart: "no"` (line 96) to ensure it runs exactly once. `minio-init` has no `restart:` directive. The Docker Compose v2 default restart policy for services run via `docker compose up` is `no`, but this is an implicit assumption. If the compose project is later orchestrated with a non-default restart policy (e.g., `--restart always` or a production override), `minio-init` will restart on failure and re-execute `mc mb`, which is idempotent due to `--ignore-existing`, but the missing symmetry with `db-init` is a consistency hazard.

**Fix:** Add `restart: "no"` to `minio-init` for symmetry with `db-init` and to make the intent explicit.

---

### WR-03: Redis healthcheck embeds password via Compose interpolation into CLI argument

**File:** `deploy/docker-compose.yml:47`

**Issue:**

```yaml
test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
```

Docker Compose resolves `${REDIS_PASSWORD}` at parse time and bakes the plaintext password into the healthcheck command array. This means the plaintext password appears in `docker inspect` output and in compose-generated process listings. The `redis-cli` manual recommends using `REDISCLI_AUTH` env var or piping through stdin to avoid password exposure in process arguments.

**Fix:** Use the environment variable approach:

```yaml
healthcheck:
  test: ["CMD-SHELL", "REDISCLI_AUTH=$$REDIS_PASSWORD redis-cli ping"]
  interval: 10s
  timeout: 5s
  retries: 5
```

---

### WR-04: `OLLAMA_BASE_URL` documented in README Pluggable LLM section but not in docker-compose `diagnosticer` env block

**File:** `README.md:191` cross-referenced `deploy/docker-compose.yml:243-255`

**Issue:** The Pluggable LLM table in the README lists `OLLAMA_BASE_URL` as a required env var when using the Ollama provider. The `diagnosticer` service environment block in docker-compose does not include `OLLAMA_BASE_URL` at all — not even as a commented-out example. A user switching to Ollama must know to add this var manually; there is no discoverable template in the compose file to guide them.

**Fix:** Add a commented-out `OLLAMA_BASE_URL` entry to the `diagnosticer` service environment block:

```yaml
# OLLAMA_BASE_URL: http://host.docker.internal:11434  # Uncomment when DIAGNOSTICER_PROVIDER=ollama
```

---

### WR-05: README Quick Start references `<repo-url>` placeholder — not substituted

**File:** `README.md:24`

**Issue:**

```bash
git clone <repo-url> && cd Xeter
```

`<repo-url>` is a literal placeholder that was never replaced with the actual repository URL. A user copying this command will get a git clone error. This is a documentation correctness failure in the primary onboarding path.

**Fix:** Replace `<repo-url>` with the actual repository URL, or use a GitHub badge/link so it stays current.

---

## Info

### IN-01: `S3_ACCESS_KEY: xeter` hardcoded across four services — should reference `${MINIO_ROOT_USER}`

**File:** `deploy/docker-compose.yml:127, 161, 206, 247`

**Issue:** `S3_ACCESS_KEY` is hardcoded as the literal string `xeter` in all four application service environment blocks. `MINIO_ROOT_USER` in `.env.example` is also `xeter`, so this works by coincidence, but the values are not linked. If an operator changes `MINIO_ROOT_USER` in `.env`, `S3_ACCESS_KEY` in all four services would need to be updated manually and would silently break S3 writes if missed.

**Fix:** Use `${MINIO_ROOT_USER}` (or `${MINIO_ACCESS_KEY}` as defined in `.env.example`) instead of the hardcoded string `xeter`:

```yaml
S3_ACCESS_KEY: ${MINIO_ROOT_USER}
```

---

### IN-02: README Detection Checks table `context_overflow` assigned to `OutputSchemaAnalyzer` — likely wrong analyzer class

**File:** `README.md:137`

**Issue:** The table assigns `context_overflow` to `OutputSchemaAnalyzer`. Context overflow is an input token count check, not an output schema validation concern. This is almost certainly a mis-classification in the table (it belongs under a context/input analyzer). While it may be an implementation artifact, it misleads users about where to look for configuration.

**Fix:** Verify the actual analyzer class in `xeter/services/worker/` that handles `context_overflow` and update the table to reflect the correct class name.

---

_Reviewed: 2026-05-31_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
