---
phase: 15-secrets-hygiene
plan: "01"
subsystem: infra
tags: [secrets, gitignore, openssl, bash, env]

# Dependency graph
requires:
  - phase: 14-db-foundation
    provides: completed DB foundation before secrets hardening
provides:
  - Root .gitignore blocking .env, .env.local, Python artefacts, and editor files
  - generate-secrets.sh — one-command .env generator with cryptographically random secrets
  - .env.example with CHANGE_ME_BEFORE_DEPLOY for all 13 secret fields

affects:
  - 15-02
  - 16-score-pipeline
  - onboarding

# Tech tracking
tech-stack:
  added: [openssl rand -hex 32 for secret generation]
  patterns:
    - "Pre-generate shared passwords into shell vars before heredoc to avoid multiple openssl calls producing different values"
    - "CHANGE_ME_BEFORE_DEPLOY placeholder convention for all secret fields in .env.example"

key-files:
  created:
    - .gitignore
    - generate-secrets.sh
  modified:
    - .env.example

key-decisions:
  - "Shared passwords (PG_PASS, REDIS_PASS, MINIO_PASS, CH_PASS) generated once into shell variables before heredoc — prevents DATABASE_URL and POSTGRES_URL from receiving different passwords"
  - "DEV_USER_PASSWORD uses inline openssl rand inside heredoc (single-use var, safe — only appears once)"
  - "ANTHROPIC_API_KEY and OPENAI_API_KEY intentionally left as CHANGE_ME_BEFORE_DEPLOY in generate-secrets.sh — require manual operator input"
  - "services/view/.gitignore preserved unchanged — root .gitignore is additive"

patterns-established:
  - "Shell heredoc secret generation: generate all shared values into vars first, then write with cat > .env <<EOF"
  - "git ls-files guard in secret scripts prevents accidental overwrite of a tracked .env"

requirements-completed: [OPS-01, OPS-02]

# Metrics
duration: 13min
completed: 2026-04-29
---

# Phase 15 Plan 01: Secrets Hygiene Summary

**Root .gitignore, one-command generate-secrets.sh with shared-password reuse pattern, and .env.example with 13 CHANGE_ME_BEFORE_DEPLOY placeholders closing the open secret-commit vector**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-29T13:11:29Z
- **Completed:** 2026-04-29T13:24:29Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Root .gitignore created — `git check-ignore -v .env` confirms `.env` is permanently excluded from staging
- generate-secrets.sh generates all service passwords with `openssl rand -hex 32`; shared passwords assigned to shell variables before the heredoc so DATABASE_URL and POSTGRES_URL always carry identical PG_PASS
- .env.example rewritten with 13 CHANGE_ME_BEFORE_DEPLOY entries covering PostgreSQL, ClickHouse, Redis, MinIO/S3, dev bootstrap, SECRET_KEY, and both LLM API keys

## Task Commits

Each task was committed atomically:

1. **Task 1: Create root .gitignore blocking .env and Python artefacts** - `b5cd575` (chore)
2. **Task 2: Create generate-secrets.sh with correct password reuse pattern** - `9f4d2dc` (chore)
3. **Task 3: Update .env.example with CHANGE_ME_BEFORE_DEPLOY and all required vars** - `0b5fb4e` (chore)

**Plan metadata:** (docs commit — created after self-check)

## Files Created/Modified
- `.gitignore` — Root-level exclusions: .env variants, Python artefacts, test/coverage dirs, editor files
- `generate-secrets.sh` — Executable bash script; generates .env with openssl rand; guards against git-tracked .env; prints operator reminder for API keys
- `.env.example` — Complete var documentation with CHANGE_ME_BEFORE_DEPLOY for all 13 secret fields; non-secret defaults intact (hosts, ports, bucket names, user names)

## Decisions Made
- Shared passwords generated once into shell vars before heredoc — prevents DATABASE_URL and POSTGRES_URL password mismatch that would cause DB connection failures
- DEV_USER_PASSWORD uses inline `openssl rand -hex 16` inside heredoc (single-use var, only appears once, safe)
- ANTHROPIC_API_KEY and OPENAI_API_KEY left as CHANGE_ME_BEFORE_DEPLOY in generated .env — require manual input by operator
- services/view/.gitignore untouched — root .gitignore is additive

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

After running `bash generate-secrets.sh`, operators must manually set:
- `ANTHROPIC_API_KEY` — obtain from https://console.anthropic.com
- `OPENAI_API_KEY` — obtain from https://platform.openai.com

## Next Phase Readiness
- .env vector is closed — git add .env fails silently, new operators have single-command .env setup
- Ready for Phase 15 remaining plans (docker-compose hardening, Alembic env hardening, etc.)
- Existing .env on disk is not git-tracked; no existing secrets were committed

---
*Phase: 15-secrets-hygiene*
*Completed: 2026-04-29*
