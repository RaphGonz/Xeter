---
phase: 31-readme-overhaul
fixed_at: 2026-05-31T00:00:00Z
review_path: .planning/phases/31-readme-overhaul/31-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 7
skipped: 1
status: partial
---

# Phase 31: Code Review Fix Report

**Fixed at:** 2026-05-31
**Source review:** .planning/phases/31-readme-overhaul/31-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (CR-01, CR-02, CR-03, WR-01, WR-02, WR-03, WR-04, WR-05)
- Fixed: 7 (CR-02, CR-03, WR-01, WR-02, WR-03, WR-04 applied; CR-01 confirmed false positive)
- Skipped: 1 (WR-05 — already fixed in prior commit per fix_instructions)

## Fixed Issues

### CR-01: README threshold table disagrees with calibrate.py

**Files modified:** none (false positive — no change needed)
**Commit:** (no commit — false positive, table already correct)
**Applied fix:** Verified `DEFAULT_THRESHOLDS` in `xeter/scripts/calibrate.py` against every row
in the README Detection Checks table. All 11 tunable threshold values in the README exactly match
`DEFAULT_THRESHOLDS`:
- `unnecessary_tool_call`: 0.15 = calibrate.py 0.15
- `wrong_tool_args`: 0.4 = calibrate.py 0.4
- `no_tool`: 0.6 = calibrate.py 0.6
- `response_anomaly`: 0.4 = calibrate.py 0.4
- `missing_details`: 0.6 = calibrate.py 0.6
- `stale_context`: 85.0 = calibrate.py 85.0
- `context_propagation_failure`: 0.5 = calibrate.py 0.5
- `history_loss`: 0.4 = calibrate.py 0.4
- `information_withholding`: 0.5 = calibrate.py 0.5
- `conversation_reset`: 0.25 = calibrate.py 0.25
- `incomplete_verification`: 0.7 = calibrate.py 0.7

The reviewer compared README to docker-compose values (post-calibration tuned values), but the
fix instructions specify the README must reflect `DEFAULT_THRESHOLDS` (calibration baselines) — which
it already does correctly. The CR-01 finding is a false positive. No table edits required.

---

### CR-02: Application services start before MinIO bucket is provisioned

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Added `minio-init: condition: service_completed_successfully` to the `depends_on`
block of all four application services: analyser, presenter, worker, and diagnosticer. This ensures
the `xeter-payloads` bucket is fully provisioned before any service that writes to S3 starts up,
eliminating the `NoSuchBucket` race on first boot.

---

### CR-03: minio-init command injection via Compose interpolation

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Changed `${MINIO_ROOT_USER}` and `${MINIO_ROOT_PASSWORD}` to
`\"$$MINIO_ROOT_USER\"` and `\"$$MINIO_ROOT_PASSWORD\"` in the minio-init command string.
The `$$VAR` syntax prevents Docker Compose from interpolating the credentials at parse time;
the shell expands them at container runtime. The surrounding escaped double-quotes ensure values
with internal spaces are treated as single arguments to `mc alias set`.

---

### WR-01: WORKER_TRACE_FLUSH_TIMEOUT_S absent from docker-compose worker env block

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Added `WORKER_TRACE_FLUSH_TIMEOUT_S: "30"` to the worker service environment
block, placed before the `WORKER_THRESHOLD_*` vars. This makes the var discoverable in the
canonical config file, matching the README Performance section's instructions.

---

### WR-02: minio-init missing restart: "no"

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Added `restart: "no"` to the minio-init service definition, placed before the
`command:` key. This mirrors the pattern already used by `db-init` and makes the one-shot intent
explicit regardless of any project-level restart policy override.

---

### WR-03: Redis healthcheck exposes password via process arguments

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Replaced `["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]` with
`["CMD-SHELL", "REDISCLI_AUTH=$$REDIS_PASSWORD redis-cli ping"]`. The `$$REDIS_PASSWORD` syntax
prevents Compose from baking the plaintext password into the healthcheck spec; the shell sets
`REDISCLI_AUTH` at runtime, which redis-cli reads instead of a `-a` argument. This eliminates
the password from `docker inspect` output and process listings.

---

### WR-04: OLLAMA_BASE_URL not present in diagnosticer env block

**Files modified:** `deploy/docker-compose.yml`
**Commit:** b3732f0
**Applied fix:** Added commented-out entry
`# OLLAMA_BASE_URL: http://host.docker.internal:11434  # Uncomment when DIAGNOSTICER_PROVIDER=ollama`
at the end of the diagnosticer service environment block. Users switching to Ollama now have a
discoverable template with the correct `host.docker.internal` address for Docker-on-macOS/Windows.

---

## Skipped Issues

### WR-05: README Quick Start references placeholder repo URL

**File:** `README.md:24`
**Reason:** Already fixed in a prior commit per fix_instructions — `<repo-url>` was replaced with
the actual GitHub URL `https://github.com/RaphGonz/Xeter.git` before this fix run.
**Original issue:** `git clone <repo-url> && cd Xeter` contained a literal placeholder that would
cause `git clone` to fail for any user copying the command.

---

_Fixed: 2026-05-31_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
