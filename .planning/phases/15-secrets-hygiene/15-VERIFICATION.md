---
phase: 15-secrets-hygiene
verified: 2026-04-29T14:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 15: Secrets Hygiene Verification Report

**Phase Goal:** Secrets cannot be accidentally committed, the deployment stack uses safe defaults, and Redis is authenticated
**Verified:** 2026-04-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `git add .env` is blocked — .env excluded after .gitignore is in place | VERIFIED | `.gitignore` line 2 contains `.env`; `git check-ignore -v .env` returns `.gitignore:2:.env .env`; .env absent from `git status` output |
| 2 | Operator can run `bash generate-secrets.sh` and receive a valid .env with random secrets in one step | VERIFIED | `generate-secrets.sh` exists, is executable, guards against tracked .env via `git ls-files`, generates all shared passwords before heredoc, writes .env with all required vars |
| 3 | `.env.example` documents every required var with `CHANGE_ME_BEFORE_DEPLOY` for secrets | VERIFIED | 13 `CHANGE_ME_BEFORE_DEPLOY` occurrences confirmed; non-secret defaults (hosts, ports, bucket names) retain real values |
| 4 | Redis requires password authentication — `--requirepass ${REDIS_PASSWORD}` in command | VERIFIED | `docker-compose.yml` line 43: `command: redis-server --requirepass ${REDIS_PASSWORD}` |
| 5 | Redis healthcheck authenticates with `-a ${REDIS_PASSWORD}` | VERIFIED | `docker-compose.yml` line 47: `test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]` |
| 6 | MinIO xeter-payloads bucket is asserted private on every startup via `mc anonymous set none` | VERIFIED | `docker-compose.yml` line 82: `&& mc anonymous set none local/xeter-payloads` in minio-init command |
| 7 | All hardcoded `xeter_dev_password` literals removed from docker-compose.yml (no `:- ` fallbacks on secrets) | VERIFIED | `grep -c "xeter_dev_password" deploy/docker-compose.yml` returns 0; no `SECRET_KEY:-` fallback present |
| 8 | `minio-init` mc alias command references `${MINIO_ROOT_PASSWORD}` not a hardcoded literal | VERIFIED | `docker-compose.yml` line 80: `mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}` |
| 9 | `documentation/deployment-guide.md` documents `mc anonymous set none`, deprecated `mc policy set` note, and `aws s3api put-public-access-block` | VERIFIED | All three present; `put-public-access-block` on line 28, deprecated note on line 20, `mc anonymous set none` on line 16 |
| 10 | `passlib[bcrypt]` does not appear in `pyproject.toml` or any Python import | VERIFIED | `grep "passlib" xeter/pyproject.toml` returns empty; `python -c "import passlib"` raises `ModuleNotFoundError` |
| 11 | CI fails if bcrypt cost factor drops below 12 — test asserts `$2b$12$` hash prefix | VERIFIED | `xeter/tests/test_secrets.py` `test_bcrypt_cost_factor_minimum()` asserts `prefix == "$2b$12$"` against default `gensalt()` call |
| 12 | `test_auth_login.py` uses `rounds=4` session-scoped fixture instead of module-level `gensalt()` | VERIFIED | Session-scoped `password_hash_fixture` with `rounds=4` on lines 34-39; no module-level `PASSWORD_HASH = bcrypt.hashpw(...)` present; `_make_user()` accepts hash as parameter |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.gitignore` | Root-level secret file exclusions | VERIFIED | Exists at repo root; contains `.env`, `.env.local`, `.env.*.local`, Python artefacts, test/coverage dirs, editor files |
| `generate-secrets.sh` | One-command .env generator using `openssl rand` | VERIFIED | Executable; `set -euo pipefail`; git-tracked guard; all shared passwords generated into shell vars before heredoc; `openssl rand -hex 32` used for PG_PASS, REDIS_PASS, MINIO_PASS, CH_PASS, SECRET_KEY |
| `.env.example` | Documented env var template with `CHANGE_ME_BEFORE_DEPLOY` | VERIFIED | 13 `CHANGE_ME_BEFORE_DEPLOY` entries; all 22 vars documented; non-secret defaults intact |
| `deploy/docker-compose.yml` | Hardened with env var substitution and Redis `--requirepass` | VERIFIED | All secrets use `${VAR}` with no `:-` fallback; Redis command, healthcheck, and all REDIS_URLs updated |
| `deploy/docker-compose.yml` | MinIO bucket privacy assertion in minio-init | VERIFIED | `mc anonymous set none local/xeter-payloads` in minio-init command chain |
| `documentation/deployment-guide.md` | Operator reference for bucket privacy enforcement | VERIFIED | Contains `mc anonymous set none`, deprecated `mc policy set` note, and full `aws s3api put-public-access-block` command with all four block flags |
| `xeter/pyproject.toml` | Clean dependency list without passlib, with direct `bcrypt>=4.0` | VERIFIED | `passlib` absent; `"bcrypt>=4.0"` on line 19 |
| `xeter/tests/test_secrets.py` | bcrypt cost factor CI enforcement test | VERIFIED | `test_bcrypt_cost_factor_minimum()` present; asserts `$2b$12$` prefix against default `bcrypt.gensalt()` |
| `xeter/tests/presenter/test_auth_login.py` | Updated auth test with `rounds=4` session-scoped fixture | VERIFIED | `@pytest.fixture(scope="session")` `password_hash_fixture` with `rounds=4`; `_make_user(password_hash: str)`; all 3 test functions accept fixture; no module-level hash |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `.gitignore` | `.env` | `git check-ignore` | WIRED | `git check-ignore -v .env` returns `.gitignore:2:.env .env`; `.env` absent from `git status` |
| `generate-secrets.sh` | `.env` | heredoc with pre-generated vars | WIRED | `PG_PASS`, `REDIS_PASS`, `MINIO_PASS`, `CH_PASS`, `SECRET_KEY` generated as shell vars; heredoc references them — `DATABASE_URL` and `POSTGRES_URL` both use `${PG_PASS}` |
| `docker-compose.yml redis.command` | `redis-server --requirepass ${REDIS_PASSWORD}` | Docker Compose command override | WIRED | Line 43 confirmed |
| `docker-compose.yml redis.healthcheck` | `redis-cli -a ${REDIS_PASSWORD} ping` | healthcheck test array | WIRED | Line 47 confirmed |
| `docker-compose.yml minio-init.command` | `mc anonymous set none local/xeter-payloads` | shell -c chain | WIRED | Line 82 confirmed |
| `docker-compose.yml` all app services | `REDIS_URL: "redis://:${REDIS_PASSWORD}@redis:6379"` | environment block | WIRED | Lines 108, 139, 180 — analyser, presenter, worker all updated; diagnosticer has no Redis dependency (no `REDIS_URL` entry, intentional) |
| `documentation/deployment-guide.md` | `aws s3api put-public-access-block` | cloud deployment section | WIRED | Line 28 confirmed with all four `BlockPublic*=true` flags |
| `xeter/tests/test_secrets.py` | `bcrypt.gensalt()` default rounds assertion | `$2b$12$` prefix check | WIRED | `test_bcrypt_cost_factor_minimum()` calls `bcrypt.gensalt()` without args and asserts prefix equals `"$2b$12$"` |
| `xeter/tests/presenter/test_auth_login.py` | `bcrypt.gensalt(rounds=4)` | session-scoped fixture | WIRED | `password_hash_fixture` uses `rounds=4`; all three test functions accept it as parameter; `_make_user()` receives hash as argument |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| OPS-01 | 15-01, 15-02 | Developer cannot accidentally commit secrets — root .gitignore excludes .env; docker-compose uses env var refs | SATISFIED | `.gitignore` blocks `.env`; `docker-compose.yml` has zero hardcoded secrets, all `${VAR}` references |
| OPS-02 | 15-01 | Operator can generate a valid random .env in one command via `generate-secrets.sh` | SATISFIED | `generate-secrets.sh` executable; `openssl rand` for all shared secrets; prints operator reminder for API keys |
| OPS-03 | 15-02 | xeter-payloads MinIO bucket asserted private on every startup; deployment guide documents `mc anonymous set none` and S3 IAM | SATISFIED | `mc anonymous set none` in minio-init command; `documentation/deployment-guide.md` contains both local mc and AWS S3 instructions; `mc policy set` deprecated note present |
| OPS-04 | 15-03 | CI fails if bcrypt cost factor drops below 12; test fixtures use `rounds=4` with session scope | SATISFIED | `test_bcrypt_cost_factor_minimum` asserts `$2b$12$` prefix; `test_auth_login.py` uses session-scoped `rounds=4` fixture |
| OPS-05 | 15-02 | Redis requires password authentication — `REDIS_PASSWORD` env var with no `:-` fallback; Redis started with `--requirepass` | SATISFIED | `command: redis-server --requirepass ${REDIS_PASSWORD}` (no fallback); `REDIS_PASSWORD: ${REDIS_PASSWORD}` in environment; healthcheck passes `-a ${REDIS_PASSWORD}` |
| DB-04 | 15-03 | Project has no dead `passlib[bcrypt]` dependency — removed from pyproject.toml | SATISFIED | `grep "passlib" xeter/pyproject.toml` returns empty; `python -c "import passlib"` raises `ModuleNotFoundError`; `bcrypt>=4.0` added as direct dep |

All 6 requirements satisfied. No orphaned requirements found.

---

### Anti-Patterns Found

None. Scanned `.gitignore`, `generate-secrets.sh`, `.env.example`, `deploy/docker-compose.yml`, `xeter/tests/test_secrets.py`, and `xeter/tests/presenter/test_auth_login.py` — no TODO, FIXME, placeholder, empty handler, or stub patterns detected.

---

### Human Verification Required

#### 1. Redis authentication enforcement at runtime

**Test:** Start the Docker stack with a valid `.env`, then run `docker exec -it <redis-container> redis-cli ping` (without `-a` flag).
**Expected:** Returns `NOAUTH Authentication required` — confirming unauthenticated access is rejected.
**Why human:** Cannot spin up Docker stack in this environment to verify runtime enforcement; static analysis confirms `--requirepass` is in the command, but runtime behaviour requires a live container.

#### 2. MinIO bucket privacy enforcement at runtime

**Test:** Start the Docker stack, wait for minio-init to complete, then attempt an anonymous HTTP GET to `http://localhost:9100/xeter-payloads/` (no auth header).
**Expected:** Returns `403 Access Denied` or similar — confirming the bucket is not publicly accessible.
**Why human:** `mc anonymous set none` command is verified in compose file, but runtime enforcement requires a live MinIO instance.

#### 3. `generate-secrets.sh` password consistency check

**Test:** Run `bash generate-secrets.sh`, then run `grep "DATABASE_URL\|POSTGRES_URL\|POSTGRES_PASSWORD" .env` and confirm all three contain the same hex value.
**Expected:** All three share an identical password string (shared `PG_PASS` variable).
**Why human:** The script writes to `.env` at runtime; static analysis confirms `${PG_PASS}` is used for all three, but runtime output should be spot-checked once.

---

### Gaps Summary

No gaps. All 12 observable truths are verified, all 9 artifacts pass all three levels (exists, substantive, wired), all 9 key links are confirmed, and all 6 requirements (OPS-01 through OPS-05, DB-04) are satisfied with concrete file evidence.

Three human verification items are flagged for runtime spot-checks, but these do not block the goal — the static implementation is complete and correct.

---

_Verified: 2026-04-29_
_Verifier: Claude (gsd-verifier)_
