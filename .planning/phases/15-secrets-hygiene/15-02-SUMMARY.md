---
phase: 15-secrets-hygiene
plan: "02"
subsystem: infra
tags: [docker-compose, redis, minio, secrets, env-vars, bucket-policy, aws-s3]

# Dependency graph
requires:
  - phase: 15-secrets-hygiene
    provides: "15-01 .env.example with all required env var names"
provides:
  - "Hardened docker-compose.yml with no hardcoded secrets (all env var references)"
  - "Redis --requirepass authentication with authenticated healthcheck"
  - "MinIO bucket privacy asserted via mc anonymous set none on every docker compose up"
  - "documentation/deployment-guide.md for operator reference on bucket privacy (local + cloud)"
affects: [16-auth-api, deployment, operations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "All secret values in docker-compose.yml use \${VAR} with no :- fallback — fail-loud at startup if unset"
    - "Redis password threaded through: service command, healthcheck, and all REDIS_URL values"
    - "mc anonymous set none runs in minio-init on every docker compose up (idempotent bucket privacy)"

key-files:
  created:
    - documentation/deployment-guide.md
  modified:
    - deploy/docker-compose.yml

key-decisions:
  - "No :- fallbacks for secrets — Docker Compose fails loudly at startup if a secret var is unset (intentional)"
  - "REDIS_URL format is redis://:PASSWORD@host:port (colon before password, no username field)"
  - "MINIO_ROOT_USER wired from env var for consistency even though it is not strictly secret"
  - "mc anonymous set none runs on every docker compose up via minio-init — idempotent, not just first-run"

patterns-established:
  - "Secret env vars in Compose: use \${VAR} with no fallback — breaks visibly at startup"
  - "Non-secret config vars (DIAGNOSTICER_PROVIDER, model, API keys) keep \${VAR:-default} form"

requirements-completed: [OPS-03, OPS-05]

# Metrics
duration: 6min
completed: 2026-04-29
---

# Phase 15 Plan 02: Secrets Hygiene — Docker Compose Hardening Summary

**Replaced all hardcoded `xeter_dev_password` literals with env var references, added Redis --requirepass auth with authenticated healthcheck, and asserted MinIO bucket privacy via `mc anonymous set none` on every stack startup**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-29T13:09:31Z
- **Completed:** 2026-04-29T13:15:36Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Zero hardcoded secrets remain in docker-compose.yml — all replaced with `${VAR}` references that fail loudly at startup if unset
- Redis now requires password auth: `--requirepass ${REDIS_PASSWORD}` in service command; healthcheck passes `-a ${REDIS_PASSWORD}`; all service REDIS_URLs include the password
- minio-init now asserts `mc anonymous set none local/xeter-payloads` after every bucket creation — closes OPS-03 runtime enforcement
- Created `documentation/deployment-guide.md` with mc anonymous set none, deprecated mc policy set note, and aws s3api put-public-access-block for cloud S3 — closes OPS-03 operator documentation clause

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace all hardcoded secrets with env var references in docker-compose.yml** - `b64d488` (feat)
2. **Task 2: Create deployment-guide.md documenting MinIO bucket privacy enforcement** - `8754bce` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `deploy/docker-compose.yml` - All hardcoded secrets replaced; Redis command/healthcheck/URLs updated; minio-init extended with mc anonymous set none
- `documentation/deployment-guide.md` - New operator reference: local mc commands, deprecated mc policy set note, AWS S3 put-public-access-block with all four block flags

## Decisions Made
- No `:-` fallbacks for secrets: Docker Compose fails loudly at startup if a secret variable is unset — this is intentional fail-fast behaviour
- REDIS_URL format `redis://:${REDIS_PASSWORD}@redis:6379` — colon before password, no username field (Redis AUTH protocol)
- `MINIO_ROOT_USER` wired from env var for consistency even though it is not a secret
- `mc anonymous set none` runs on every `docker compose up` via minio-init (idempotent) — not just first-run, so bucket privacy cannot be accidentally removed

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Operators must add the following new environment variables to their `.env` file (see `documentation/deployment-guide.md` and the `.env.example` from 15-01):

- `POSTGRES_PASSWORD`
- `CLICKHOUSE_PASSWORD`
- `REDIS_PASSWORD`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `MINIO_SECRET_KEY`
- `SECRET_KEY`

Without these, `docker compose up` will fail immediately with an unset variable error.

## Next Phase Readiness

- OPS-03 and OPS-05 closed — MinIO bucket privacy and Redis authentication hardened
- docker-compose.yml is now production-safe: no hardcoded credentials, fail-loud on missing secrets
- Phase 16 (auth API) can proceed with confidence that the infrastructure layer enforces proper authentication

---
*Phase: 15-secrets-hygiene*
*Completed: 2026-04-29*
