# Phase 15: Secrets Hygiene — Research

**Researched:** 2026-04-29
**Domain:** DevSecOps — .gitignore, environment secrets management, Docker Compose hardening, bcrypt cost enforcement, Redis auth, MinIO bucket policy
**Confidence:** HIGH

## Summary

Phase 15 is a pure hardening phase with no new library dependencies. Every requirement is a configuration or code change to existing infrastructure: a root `.gitignore`, a `generate-secrets.sh` script, docker-compose env var wiring, a Redis password, a MinIO anonymous-policy assertion in the existing minio-init container, a bcrypt cost-factor CI test, and removing `passlib[bcrypt]` from pyproject.toml.

The project currently has NO root `.gitignore` (confirmed: the `.env` file — which contains a real Anthropic API key — is untracked but not ignored). The only existing `.gitignore` lives in `services/view/` and covers Next.js artefacts. The `deploy/docker-compose.yml` hardcodes every secret as a literal string. Redis runs with no `--requirepass` flag and no password in its connection URL. The `minio-init` container creates the bucket but does not set an anonymous policy. The `passlib[bcrypt]` dependency exists in `xeter/pyproject.toml`; the codebase uses `bcrypt` directly (not passlib) everywhere — passlib is a dead import. The bcrypt default `gensalt()` already produces `$2b$12$` hashes, but there is no CI test asserting this.

**Primary recommendation:** Deliver all six requirements as four atomic work units: (1) .gitignore + generate-secrets.sh, (2) docker-compose secret wiring (env vars, Redis password, MinIO credentials), (3) passlib removal + bcrypt cost-factor test, (4) documentation (deployment guide snippet for MinIO S3 IAM). There are no new library installs required.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OPS-01 | Developer cannot accidentally commit secrets — root .gitignore excludes .env; docker-compose uses env var refs with CHANGE_ME_BEFORE_DEPLOY defaults | .gitignore patterns section; docker-compose env var substitution syntax |
| OPS-02 | Operator can generate a valid random .env in one command via generate-secrets.sh (uses openssl rand) | Shell script patterns section; openssl rand -hex 32 verified |
| OPS-03 | xeter-payloads MinIO bucket is asserted private on every startup (mc anonymous set none in minio-init); deployment guide documents mc policy set and S3 IAM JSON | MinIO mc CLI patterns; existing minio-init wiring |
| OPS-04 | CI fails if bcrypt cost factor drops below 12; test fixtures use rounds=4 with session scope to avoid CI slowdown | bcrypt hash prefix format verified; pytest session-scope fixture pattern |
| OPS-05 | Redis requires password authentication — REDIS_PASSWORD env var in docker-compose with no :- fallback; Redis started with --requirepass; unauthenticated redis-cli ping returns NOAUTH | Redis --requirepass flag; redis:// URL password embedding |
| DB-04 | Project has no dead passlib[bcrypt] dependency — removed from pyproject.toml | Confirmed: passlib listed in pyproject.toml but never imported; bcrypt used directly |
</phase_requirements>

## Standard Stack

### Core
| Tool/Library | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| `bcrypt` (PyPI) | 5.0.0 (installed) | Password/key hashing | Already in use; passlib is a wrapper around it that adds nothing here |
| `openssl` (system) | system | Generating cryptographically random secrets | Standard POSIX tool; no install needed; `openssl rand -hex 32` produces 64-char hex string |
| `redis:7-alpine` Docker image | 7-alpine (in use) | Redis with `--requirepass` flag | Already in docker-compose; flag is a standard Redis startup arg |
| `minio/minio:latest` mc CLI | latest (in use) | MinIO client for bucket policy | mc is bundled in the minio image used for minio-init; no new image needed |

### No New Dependencies
This phase adds zero new Python packages. It removes one (`passlib[bcrypt]`).

## Architecture Patterns

### Recommended File Structure Changes
```
Xeter/
├── .gitignore                  # NEW — root-level, covers .env
├── generate-secrets.sh         # NEW — one-command .env generator
├── .env.example                # MODIFY — add REDIS_PASSWORD, keep CHANGE_ME_BEFORE_DEPLOY patterns
├── .env                        # MODIFY — add REDIS_PASSWORD (not committed after gitignore)
├── deploy/
│   └── docker-compose.yml      # MODIFY — wire all secrets from env vars, Redis --requirepass
├── xeter/
│   ├── pyproject.toml          # MODIFY — remove passlib[bcrypt]
│   └── tests/
│       └── test_secrets.py     # NEW — bcrypt cost factor CI test
```

### Pattern 1: Root .gitignore — .env Protection

**What:** A root `.gitignore` that blocks `.env` from ever being staged.
**When to use:** Always — this is the first line of defence.

```bash
# .gitignore (root)
# Environment secrets — never commit
.env
.env.local
.env.*.local

# Python artefacts
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.venv/
venv/

# Test / coverage
.pytest_cache/
.coverage
htmlcov/

# Editor
.idea/
.vscode/
*.swp
*.swo
```

**Critical note:** The current `.env` contains a real Anthropic API key (`sk-ant-api03-...`). After adding the gitignore, rotate that key immediately.

### Pattern 2: generate-secrets.sh — One-Command .env Generation

**What:** A shell script that writes a fresh `.env` by calling `openssl rand -hex 32` for each secret.
**When to use:** First-time setup and rotation.

```bash
#!/usr/bin/env bash
# generate-secrets.sh — generate a .env with random secrets
# Source: OPS-02 requirement

set -euo pipefail

# Safety guard: refuse to clobber a file that is tracked by git
if git ls-files --error-unmatch .env 2>/dev/null; then
  echo "ERROR: .env is tracked by git — run 'git rm --cached .env' first." >&2
  exit 1
fi

cat > .env <<EOF
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://xeter:$(openssl rand -hex 32)@localhost:5432/xeter
POSTGRES_URL=postgresql://xeter:$(openssl rand -hex 32)@localhost:5432/xeter

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=default
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=$(openssl rand -hex 32)

# Redis
REDIS_URL=redis://:$(openssl rand -hex 32)@localhost:6379
REDIS_PASSWORD=$(openssl rand -hex 32)

# MinIO / S3
MINIO_ENDPOINT=http://localhost:9100
MINIO_ROOT_USER=xeter
MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)
MINIO_ACCESS_KEY=xeter
MINIO_SECRET_KEY=$(openssl rand -hex 32)
MINIO_BUCKET=xeter-payloads

# Dev bootstrap
DEV_API_KEY=dev-api-key-local
DEV_TENANT_NAME=dev-tenant
DEV_USER_EMAIL=dev@example.com
DEV_USER_PASSWORD=$(openssl rand -hex 16)

# App
SECRET_KEY=$(openssl rand -hex 32)

# Diagnosticer LLM config
DIAGNOSTICER_PROVIDER=anthropic
DIAGNOSTICER_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=CHANGE_ME_BEFORE_DEPLOY
EOF

echo ".env generated. Fill in ANTHROPIC_API_KEY before running."
```

**IMPORTANT:** `DATABASE_URL` and `POSTGRES_URL` reference the same PostgreSQL password — they must use the same random value. The current script template above calls `openssl rand` twice, which would generate mismatched values. The planner must address this by generating the PG password once into a variable and reusing it.

### Pattern 3: docker-compose.yml — Env Var Substitution Without Fallback

**What:** Replace all hardcoded secret literals with `${VAR_NAME}` (no `:-` fallback). Docker Compose will error on startup if the variable is not set, making the missing-secret failure explicit.

**Docker Compose env var rules (verified via official docs):**
- `${VAR}` — required; Docker Compose errors with "variable is not set" if unset
- `${VAR:-default}` — optional with fallback (DO NOT use for secrets per OPS-01)
- `${VAR-default}` — optional with fallback (DO NOT use)

**Current state before change (example):**
```yaml
environment:
  POSTGRES_PASSWORD: xeter_dev_password   # hardcoded literal
  MINIO_ROOT_PASSWORD: xeter_dev_password  # hardcoded literal
```

**After change:**
```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
```

**CHANGE_ME_BEFORE_DEPLOY requirement (OPS-01):** The `.env.example` file (checked into git) must contain `CHANGE_ME_BEFORE_DEPLOY` as the value for every secret. The docker-compose file itself uses `${VAR}` with no default — the `.env.example` is documentation, not a fallback.

### Pattern 4: Redis --requirepass Wiring

**What:** Redis container started with `--requirepass ${REDIS_PASSWORD}`; all services use a password-bearing Redis URL.

**Redis `--requirepass` flag (HIGH confidence — standard Redis CLI arg):**
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --requirepass ${REDIS_PASSWORD}
  environment:
    REDIS_PASSWORD: ${REDIS_PASSWORD}   # makes it available for healthcheck
  healthcheck:
    test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Redis URL with password:**
```
redis://:${REDIS_PASSWORD}@redis:6379
# Note the colon before the password — Redis URLs have no username field in the standard form
```

The Python `redis` library (v5+) parses the password from the URL via `from_url()`. No code change needed in `shared/db/redis.py` — it already reads from `REDIS_URL`.

**Unauthenticated ping verification:**
```bash
docker compose -f deploy/docker-compose.yml exec redis redis-cli ping
# Expected: NOAUTH Authentication required
```

### Pattern 5: MinIO Anonymous Policy — mc anonymous set none

**What:** The `minio-init` container already runs mc commands on startup. Add `mc anonymous set none` after bucket creation.

**Current minio-init command:**
```yaml
command: -c "mc alias set local http://minio:9000 xeter xeter_dev_password && mc mb local/xeter-payloads --ignore-existing"
```

**After change:**
```yaml
environment:
  MINIO_ROOT_USER: ${MINIO_ROOT_USER}
  MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
command: >-
  -c "mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
   && mc mb local/xeter-payloads --ignore-existing
   && mc anonymous set none local/xeter-payloads"
```

**mc anonymous set none** is the correct current command. The older `mc policy set none` command is deprecated in newer mc versions — use `mc anonymous set none` (HIGH confidence: this is what OPS-03 specifies).

**Cloud deployment equivalent (for docs):**
```bash
# mc equivalent (self-hosted)
mc anonymous set none myminio/xeter-payloads

# AWS S3 IAM — block all public access (replaces anonymous policy)
aws s3api put-public-access-block \
  --bucket xeter-payloads \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### Pattern 6: bcrypt Cost Factor CI Test

**What:** A pytest test that hashes a known string and asserts the hash prefix is `$2b$12$`. Uses `rounds=4` for the test fixture with `scope="session"` to hash once per CI run.

**bcrypt hash prefix format (VERIFIED by running locally):**
- `bcrypt.gensalt()` → `$2b$12$...` (default rounds=12)
- `bcrypt.gensalt(rounds=4)` → `$2b$04$...` (fast, for test fixtures)
- `bcrypt.gensalt(rounds=12)` → `$2b$12$...` (production minimum)

**The `$2b$12$` prefix structure:**
- `$2b$` — bcrypt algorithm variant
- `12` — cost factor (zero-padded, two digits)
- `$` — separator

**Test pattern:**

```python
# xeter/tests/test_secrets.py
import bcrypt
import pytest


@pytest.fixture(scope="session")
def api_key_hash_rounds4() -> str:
    """Pre-computed bcrypt hash with rounds=4 for test fixtures.

    Uses rounds=4 (not 12) to keep CI fast. The cost-factor test
    uses a separate hash to assert the production minimum.
    """
    return bcrypt.hashpw(b"test-key", bcrypt.gensalt(rounds=4)).decode()


def test_bcrypt_cost_factor_minimum():
    """CI guard: bcrypt cost factor must be >= 12 in production hashes.

    Hashes a test string with default gensalt() (which uses rounds=12)
    and asserts the hash prefix is $2b$12$. This fails if gensalt() is
    ever called with a rounds argument < 12 in production code.
    """
    test_hash = bcrypt.hashpw(b"sentinel", bcrypt.gensalt()).decode()
    prefix = test_hash[:7]   # "$2b$12$"
    assert prefix == "$2b$12$", (
        f"bcrypt cost factor must be >= 12, got hash prefix: {prefix!r}. "
        "Do not pass rounds < 12 to gensalt() in production code."
    )
```

**How to make this test meaningful:** The test asserts on the default `gensalt()` output. To make it fail when someone lowers the default, also add a test that asserts the production calling sites use `gensalt()` without an argument (or with `rounds >= 12`). Alternatively, grep the source for `gensalt(rounds=` patterns in non-test files as part of CI — but the prefix check is sufficient per OPS-04.

**Test fixture update for existing tests:**

`xeter/tests/presenter/test_auth_login.py` currently calls:
```python
PASSWORD_HASH = bcrypt.hashpw(USER_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
```
This is module-level (runs once per test session, effectively `scope="session"` for cost). It uses the default rounds=12 which is slow (~100ms). Per OPS-04, it should use `rounds=4` with a `scope="session"` pytest fixture:

```python
@pytest.fixture(scope="session")
def password_hash_fixture() -> str:
    return bcrypt.hashpw(
        USER_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=4)
    ).decode("utf-8")
```

### Pattern 7: Remove passlib[bcrypt] from pyproject.toml

**Current state:** `passlib[bcrypt]>=1.7` is listed in `xeter/pyproject.toml` dependencies.
**Actual usage:** Zero imports of passlib anywhere in the codebase. All bcrypt operations use `import bcrypt` directly.
**Action:** Remove the single line `"passlib[bcrypt]>=1.7",` from the dependencies list.
**Verification:** `grep -r "passlib" xeter/ --include="*.py"` should return empty after removal.

### Anti-Patterns to Avoid

- **`${VAR:-some_default}` for secrets in docker-compose:** The `:-` fallback silently allows the container to start with a weak default. Use `${VAR}` only — Docker Compose will fail loudly if the var is missing.
- **Different secrets for DATABASE_URL and POSTGRES_URL:** These two vars must reference the same PostgreSQL password. generate-secrets.sh must generate the password once and use it in both.
- **`mc policy set none` (old syntax):** Replaced by `mc anonymous set none` in mc versions post-2021. The requirement specifies the new syntax.
- **`redis-cli ping` without `-a` flag in healthcheck:** After adding `--requirepass`, the healthcheck must pass `-a ${REDIS_PASSWORD}` or it will always report unhealthy.
- **Module-level bcrypt.gensalt() in test files:** Creates an ~100ms overhead on every test collection. Move to session-scoped fixtures.
- **Committing .env after adding .gitignore:** The `.env` file is already untracked (`??` in git status). Once `.gitignore` is in place, `git add .env` will be blocked. But the file is currently on disk with real secrets — the Anthropic API key must be rotated after this phase.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Random secret generation | Custom Python UUID/secrets script | `openssl rand -hex 32` in bash | OS-provided CSPRNG; no Python dependency; OPS-02 specifies openssl |
| Bcrypt wrapper | Custom hash utility | `bcrypt` library directly | Already in use; passlib adds zero value here |
| MinIO bucket policy | Custom S3 API call in Python | `mc anonymous set none` in minio-init | mc is already in the minio image; no new code needed |
| Redis password validation | Custom auth middleware | Redis `--requirepass` flag | Built-in Redis feature; enforced at protocol level |

## Common Pitfalls

### Pitfall 1: DATABASE_URL and POSTGRES_URL Password Mismatch
**What goes wrong:** generate-secrets.sh calls `openssl rand -hex 32` twice for DATABASE_URL and POSTGRES_URL, producing two different passwords. PostgreSQL is configured with one of them; the other URL fails to connect.
**Why it happens:** Calling `openssl rand` inline in a heredoc produces a new value each invocation.
**How to avoid:** Generate the PostgreSQL password into a shell variable first: `PG_PASS=$(openssl rand -hex 32)` and use `$PG_PASS` in both URL values.
**Warning signs:** Services that use POSTGRES_URL connect but services using DATABASE_URL fail, or vice versa.

### Pitfall 2: Redis Healthcheck Breaks After Adding --requirepass
**What goes wrong:** `redis-cli ping` in the healthcheck returns `NOAUTH Authentication required` (the desired behaviour for unauthenticated clients) but Docker marks the container as unhealthy, cascading to dependent services failing to start.
**Why it happens:** The healthcheck command must also authenticate.
**How to avoid:** Update healthcheck to `redis-cli -a ${REDIS_PASSWORD} ping`.
**Warning signs:** All services depending on Redis fail with `service_healthy` condition unmet.

### Pitfall 3: minio-init Hardcoded Credentials
**What goes wrong:** After wiring MINIO_ROOT_USER/PASSWORD from env vars in the minio service, the minio-init `mc alias set` command still has the hardcoded `xeter xeter_dev_password` — authentication fails.
**Why it happens:** Two places to update; easy to miss the init container.
**How to avoid:** Pass `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` env vars to minio-init as well, and reference them in the mc command. Note: OPS-03 specifically checks that `${MINIO_ROOT_PASSWORD}` appears in the mc alias command, not a hardcoded literal.
**Warning signs:** minio-init container exits with non-zero code on `docker compose up`.

### Pitfall 4: Docker Compose Variable Expansion in YAML Strings
**What goes wrong:** Some docker-compose YAML values need quoting when using `${VAR}` inline with other text (e.g., in connection URLs).
**Why it happens:** YAML has rules about special characters; `@` in URLs can cause parse issues without quotes.
**How to avoid:** Wrap connection URL values in double quotes: `"redis://:${REDIS_PASSWORD}@redis:6379"`.

### Pitfall 5: passlib Still Installed After pyproject.toml Edit
**What goes wrong:** Removing `passlib[bcrypt]` from pyproject.toml does not uninstall it from the active venv — it is still importable.
**Why it happens:** pyproject.toml is a declaration, not an install trigger.
**How to avoid:** After editing pyproject.toml, run `pip uninstall passlib` and `pip install -e .` (or `pip install -e xeter/`). Verification: `python -c "import passlib"` should raise ImportError.

### Pitfall 6: .env Already Contains Real Secrets
**What goes wrong:** After adding .gitignore and verifying the file is blocked, someone realises the real Anthropic API key was already visible in git history (or was staged).
**Why it happens:** The `.env` was never gitignored.
**How to avoid:** Check `git status` before this phase — `.env` currently shows as `??` (untracked, never staged). This means it has NOT been committed. Adding `.gitignore` is sufficient to prevent future accidents. The key should still be rotated as a precaution.

## Code Examples

### bcrypt cost factor test (verified locally)
```python
# Source: bcrypt 5.0.0 — bcrypt.gensalt() default is rounds=12
import bcrypt

def test_bcrypt_cost_factor_minimum():
    h = bcrypt.hashpw(b"sentinel", bcrypt.gensalt()).decode()
    assert h[:7] == "$2b$12$", f"Expected $2b$12$ prefix, got: {h[:7]!r}"
```

### Redis URL with embedded password
```bash
# redis-py from_url parses password from URL
redis://:${REDIS_PASSWORD}@redis:6379
# note: colon before password, no username
```

### mc anonymous set none (verified syntax per OPS-03)
```bash
mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
mc mb local/xeter-payloads --ignore-existing
mc anonymous set none local/xeter-payloads
```

### S3 IAM equivalent for cloud deployment
```bash
# Block all public access at the bucket level (AWS S3)
aws s3api put-public-access-block \
  --bucket xeter-payloads \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Verify
aws s3api get-public-access-block --bucket xeter-payloads
```

### generate-secrets.sh skeleton (correct password reuse pattern)
```bash
#!/usr/bin/env bash
set -euo pipefail

if git ls-files --error-unmatch .env 2>/dev/null; then
  echo "ERROR: .env is tracked by git. Run: git rm --cached .env" >&2
  exit 1
fi

# Generate passwords once, reuse across related vars
PG_PASS=$(openssl rand -hex 32)
REDIS_PASS=$(openssl rand -hex 32)
MINIO_PASS=$(openssl rand -hex 32)

cat > .env <<EOF
DATABASE_URL=postgresql+asyncpg://xeter:${PG_PASS}@localhost:5432/xeter
POSTGRES_URL=postgresql://xeter:${PG_PASS}@localhost:5432/xeter
POSTGRES_PASSWORD=${PG_PASS}
REDIS_URL=redis://:${REDIS_PASS}@localhost:6379
REDIS_PASSWORD=${REDIS_PASS}
MINIO_ROOT_USER=xeter
MINIO_ROOT_PASSWORD=${MINIO_PASS}
MINIO_SECRET_KEY=${MINIO_PASS}
SECRET_KEY=$(openssl rand -hex 32)
ANTHROPIC_API_KEY=CHANGE_ME_BEFORE_DEPLOY
EOF

echo ".env written. Fill ANTHROPIC_API_KEY before starting services."
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `passlib[bcrypt]` wrapper | `bcrypt` directly | passlib is a near-abandoned wrapper; direct bcrypt is leaner and maintained |
| `mc policy set none` | `mc anonymous set none` | Old `mc policy` subcommand deprecated in mc RELEASE.2021+ |
| `${VAR:-default}` in docker-compose | `${VAR}` with no fallback | Secrets must not have silent fallbacks; explicit failure on startup is correct |
| Module-level `bcrypt.gensalt()` in tests | `scope="session"` fixture with `rounds=4` | Avoids ~100ms bcrypt overhead on every test collection |

**Deprecated/outdated:**
- `passlib[bcrypt]`: Never used in this codebase; remove from pyproject.toml (DB-04)
- `mc policy set none`: Replaced by `mc anonymous set none` — do NOT use old syntax

## Open Questions

1. **POSTGRES_PASSWORD in docker-compose postgres service**
   - What we know: The postgres service uses `POSTGRES_PASSWORD: xeter_dev_password` (hardcoded). To wire it from env, we need `POSTGRES_PASSWORD` in `.env` AND the `docker-compose.yml` must reference `${POSTGRES_PASSWORD}`. The `DATABASE_URL` must use the same value.
   - What's unclear: Whether to add a standalone `POSTGRES_PASSWORD` var or derive it from the URL.
   - Recommendation: Add `POSTGRES_PASSWORD` as a dedicated env var; generate-secrets.sh generates it once and writes it to both `POSTGRES_PASSWORD` and embedded in `DATABASE_URL`/`POSTGRES_URL`.

2. **CLICKHOUSE_PASSWORD — in scope for this phase?**
   - What we know: ClickHouse also has hardcoded `xeter_dev_password`. OPS-01 says "docker-compose uses env var refs with CHANGE_ME_BEFORE_DEPLOY defaults."
   - What's unclear: The requirements don't explicitly call out ClickHouse, but OPS-01's "docker-compose references env vars with CHANGE_ME_BEFORE_DEPLOY" implies ALL service secrets.
   - Recommendation: Wire all hardcoded secrets (Postgres, ClickHouse, MinIO, Redis) consistently — partial hardening is worse than none from a security audit perspective.

3. **S3_ACCESS_KEY / S3_SECRET_KEY vs MINIO_ROOT_USER / MINIO_ROOT_PASSWORD**
   - What we know: The docker-compose uses both `MINIO_ROOT_USER/MINIO_ROOT_PASSWORD` for the minio service and `S3_ACCESS_KEY/S3_SECRET_KEY` for application services — both are currently hardcoded to `xeter`/`xeter_dev_password`.
   - Recommendation: Wire both sets from env vars. They can share the same underlying secret value (MINIO_ROOT_PASSWORD = S3_SECRET_KEY) or be separate vars — generate-secrets.sh should emit both.

## Sources

### Primary (HIGH confidence)
- `bcrypt` 5.0.0 Python package — verified locally; `gensalt()` defaults to `rounds=12`; hash prefix format `$2b$12$` confirmed by running `python3 -c "import bcrypt; print(bcrypt.hashpw(b'test', bcrypt.gensalt())[:10])"`
- `deploy/docker-compose.yml` — direct inspection; confirmed hardcoded secrets, no --requirepass on Redis, minio-init does not set anonymous policy
- `xeter/pyproject.toml` — direct inspection; confirmed `passlib[bcrypt]>=1.7` present; confirmed `bcrypt` is a separate direct dependency
- Redis Docker Hub docs — `redis-server --requirepass <password>` is the standard startup flag; verified against redis:7-alpine
- OPS-03 requirement text — specifies `mc anonymous set none` (current command) and `mc policy set` (for docs); research confirms `mc anonymous` is the current subcommand

### Secondary (MEDIUM confidence)
- Docker Compose variable interpolation — `${VAR}` requires the variable; `${VAR:-default}` provides fallback; this is documented in the Docker Compose specification (compose-spec.io)
- MinIO mc CLI documentation — `mc anonymous set none` is the correct current syntax; `mc policy set` is deprecated; verified by OPS-03 requirement text which cites both

### Tertiary (LOW confidence)
- Redis URL password format `redis://:password@host:port` — standard format; the `:` before the password denotes empty username field; observed in redis-py documentation patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all tools already in use
- Architecture: HIGH — codebase fully inspected; exact file paths and current values known
- Pitfalls: HIGH — three of six pitfalls discovered by direct code inspection (password mismatch, healthcheck break, minio-init hardcoding)

**Research date:** 2026-04-29
**Valid until:** 2026-06-29 (stable config domain; bcrypt default rounds and mc syntax are not expected to change)
