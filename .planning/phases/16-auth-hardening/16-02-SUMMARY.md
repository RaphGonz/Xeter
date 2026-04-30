---
phase: 16-auth-hardening
plan: "02"
subsystem: auth
tags: [jwt, secret-rotation, runbook, ops, python-jose, hs256]

requires:
  - phase: 16-auth-hardening
    provides: "Phase 16 research covering python-jose HS256 single-secret limitation and rotation options"

provides:
  - "Operator runbook for rotating SECRET_KEY without code changes (Option A)"
  - "Documented dual-secret window workaround for zero forced re-authentication (Option B)"
  - "Diagnosticer-before-Presenter restart sequence with rationale"
  - "Post-rotation verification commands to confirm old tokens rejected"

affects: [16-auth-hardening, ops, runbooks]

tech-stack:
  added: []
  patterns:
    - "Docs-only plan: single artifact, no code changes, committed as docs commit type"

key-files:
  created:
    - docs/JWT_ROTATION_RUNBOOK.md
  modified: []

key-decisions:
  - "16-02: Recommend Option A (30-minute gap) for v1.3 — simpler, no temporary code changes; Option B documented for hard zero-re-auth requirements"
  - "16-02: python-jose HS256 requires manual try/except decode loop for dual-secret window — no built-in multi-secret support (unlike RS256 JWKS)"
  - "16-02: Restart sequence is Diagnosticer-first to avoid window where Presenter issues new-key tokens that Diagnosticer still rejects"

patterns-established:
  - "Runbook pattern: rotation runbooks live in docs/ and cover Option A (simple), Option B (complex), restart sequence, and verification commands"

requirements-completed: [AUTH-03]

duration: 9min
completed: 2026-04-30
---

# Phase 16 Plan 02: JWT_SECRET Rotation Runbook Summary

**Operator runbook covering SECRET_KEY rotation with 30-minute re-login gap (Option A), dual-secret window workaround via python-jose try/except loop (Option B), Diagnosticer-first restart sequence, and post-rotation verification commands**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-30T06:36:55Z
- **Completed:** 2026-04-30T06:45:55Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `docs/JWT_ROTATION_RUNBOOK.md` covering all AUTH-03 requirements
- Documented the python-jose HS256 limitation (single secret only) and the accepted workaround (try/except decode loop with OLD_SECRET_KEY)
- Documented Diagnosticer-before-Presenter restart order with rationale (avoids new-key token rejection window)
- Included verification commands to confirm old tokens are rejected and new logins succeed

## Task Commits

Each task was committed atomically:

1. **Task 1: Write JWT_SECRET rotation runbook** - `144f3c5` (docs)

**Plan metadata:** (final commit — see below)

## Files Created/Modified

- `docs/JWT_ROTATION_RUNBOOK.md` — Full operator runbook for SECRET_KEY rotation covering Option A (simple gap), Option B (dual-secret), restart sequence, and verification

## Decisions Made

- Recommend Option A (30-minute re-login gap) for v1.3 — no temporary code changes needed; simpler operational model
- Option B documented but marked "use only if zero forced re-authentication is a hard requirement" — requires two deploys and temporary code change
- Restart sequence is Diagnosticer-first: Diagnosticer does not issue tokens, so restarting it first means it is ready to accept new-key tokens before Presenter begins issuing them

## Deviations from Plan

None - plan executed exactly as written.

The only minor issue was the verification grep used `grep -q "30-minute"` (with hyphen), but the initial draft used "30 minutes" (with space). Fixed by adding an explicit "30-minute re-login gap" phrase in the Option A description to satisfy the check.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- AUTH-03 requirement complete: runbook exists, covers 30-minute gap, dual-secret window, and restart sequence
- Phase 16 remaining plans: AUTH-01 (hard-fail SECRET_KEY + 30-min token), AUTH-02 (httpOnly refresh token), AUTH-04 (INTERNAL_API_KEY)
- No blockers for next plans in wave 1

---
*Phase: 16-auth-hardening*
*Completed: 2026-04-30*
