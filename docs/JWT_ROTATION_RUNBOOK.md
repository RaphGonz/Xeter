# JWT_SECRET Rotation Runbook

**Audience:** Operators with production access.
**Applies to:** Xeter v1.3+ (Phase 16 auth hardening).
**Last updated:** 2026-04-30

---

## Overview

`SECRET_KEY` is a required environment variable loaded via `os.environ["SECRET_KEY"]` in both the Presenter and Diagnosticer services. There is **no fallback** — if the variable is unset, both services raise `KeyError` at startup and refuse to start.

`SECRET_KEY` is used to sign and verify **HS256 JWTs**:

- **Access tokens** — expire after **30 minutes** (`TOKEN_EXPIRE_MINUTES = 30` in `deps.py`)
- **Refresh tokens** — expire after **30 days** (`REFRESH_TOKEN_EXPIRE_DAYS = 30` in `deps.py`)

The signing secret is identical for both token types at v1.3. There is no DB revocation store; revocation is deferred to a future phase (AUTH-F01).

---

## When to Rotate

- Suspected or confirmed `SECRET_KEY` compromise
- Routine rotation policy (e.g., quarterly)
- A team member with production access offboards
- A `.env` file was accidentally committed or transmitted insecurely

---

## Option A: Simple Rotation with 30-Minute Re-Login Gap (Recommended)

This is the recommended approach for v1.3. It is operationally simple — no temporary code changes required. Users experience a 30-minute re-login gap for active access tokens (and up to 30 days for refresh tokens).

### Steps

1. **Generate a new key:**
   ```bash
   openssl rand -hex 32
   ```
   Copy the output — this is your new `SECRET_KEY` value.

2. **Update your secret store:**
   Replace `SECRET_KEY=<old-value>` with `SECRET_KEY=<new-value>` in your `.env` file or secret manager (AWS Secrets Manager, Vault, etc.).

3. **Restart Diagnosticer first:**
   ```bash
   docker compose restart diagnosticer
   ```
   Diagnosticer does not issue tokens — it only verifies them. Restarting it first avoids a window where Presenter issues new tokens that Diagnosticer still rejects.

4. **Restart Presenter:**
   ```bash
   docker compose restart presenter
   ```
   Once Presenter restarts, all newly issued tokens are signed with the new key.

### What Happens to Existing Tokens

- All tokens signed with the old key are **immediately invalid** after restart.
- Users will receive a `401 Unauthorized` on their next authenticated request.
- The 401 interceptor in the frontend calls `POST /api/auth/refresh`, which calls `POST /auth/refresh` on Presenter.
- Because the refresh token is also signed with the old key, the refresh call will fail too.
- **Users must log in again manually.** There is no silent re-authentication path during rotation.

### Re-Login Gap Duration

| Token Type | Gap Duration |
|------------|-------------|
| Access token | Up to **30 minutes** (tokens already expire in 30 min) |
| Refresh token | Up to **30 days** (long-absent users with valid refresh cookies) |

This gap is the correct tradeoff for operational simplicity. Accept it — the security benefit (compromised key is immediately invalid) outweighs the UX cost.

---

## Option B: Dual-Secret Window (Zero Forced Re-Authentication)

Use this option **only** if zero forced re-authentication is a hard requirement. It requires a temporary code change and redeploy.

### Background: Why python-jose Requires a Workaround

`python-jose`'s `jwt.decode(token, secret, algorithms=[...])` accepts a **single secret string** for HS256. Unlike RS256 (where a JWKS endpoint can carry multiple public keys), there is no built-in multi-secret mode for HS256. A manual try/except decode loop is required.

### Steps

1. **Generate a new key:**
   ```bash
   openssl rand -hex 32
   ```

2. **Add `OLD_SECRET_KEY` support to `deps.py` (temporary code change):**

   In `xeter/services/presenter/deps.py`, add the following fallback decode logic to `verify_session_token`:

   ```python
   import os
   from jose import JWTError, jwt

   SECRET_KEY = os.environ["SECRET_KEY"]           # new key
   OLD_SECRET_KEY = os.environ.get("OLD_SECRET_KEY")  # old key — optional, temporary

   def verify_session_token(token: str) -> str:
       try:
           payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
       except JWTError:
           if OLD_SECRET_KEY:
               payload = jwt.decode(token, OLD_SECRET_KEY, algorithms=[ALGORITHM])
           else:
               raise
       tenant_id: str | None = payload.get("sub")
       if not tenant_id:
           raise _SESSION_UNAUTHORIZED
       return tenant_id
   ```

3. **Deploy this code change** with both env vars set:
   ```
   SECRET_KEY=<new-value>
   OLD_SECRET_KEY=<old-value>
   ```

4. **Restart services** (same order as Option A — Diagnosticer first, then Presenter).
   Apply the same fallback decode change to Diagnosticer's `verify_session_token` if it also decodes tokens directly.

5. **Wait for old tokens to expire:**
   - **30 minutes** — all old access tokens have expired naturally.
   - **30 days** — all old refresh tokens have expired (or force re-login for remaining users).

6. **Remove the temporary code and old env var:**
   - Remove `OLD_SECRET_KEY` env var from `.env` / secret manager.
   - Remove the fallback decode block from `deps.py`.
   - Redeploy.

### Recommendation

Use Option A for v1.3. Option B adds temporary code complexity and requires two deploys. Reserve Option B for when zero forced re-authentication is a hard contractual or SLA requirement.

---

## Service Restart Sequence

**Always restart in this order:**

1. **Diagnosticer** (does not issue tokens — safe to restart first)
2. **Presenter** (issues tokens — once restarted, all new tokens use the new key)

### Why This Order Matters

If Presenter restarts first, it immediately begins issuing tokens signed with the new key. Diagnosticer — still running with the old key — will reject those new tokens for the brief window before it restarts. By restarting Diagnosticer first, Diagnosticer is ready to accept new-key tokens before Presenter starts issuing them.

---

## Verification

After completing the rotation, verify the new key is active:

```bash
# Confirm services started without KeyError
docker compose logs presenter | grep -E "started|KeyError"
docker compose logs diagnosticer | grep -E "started|KeyError"
```

A healthy start shows no `KeyError`. A misconfigured start shows:
```
KeyError: 'SECRET_KEY'
```
which means the env var was not set correctly before restart.

### Verify Old Tokens Are Rejected (Option A)

Obtain a token **before** rotation, then verify it is rejected **after** restart:

```bash
# Step 1: Before rotation — get a token and store it
OLD_TOKEN=$(curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' | jq -r .session_token)

echo "OLD_TOKEN=$OLD_TOKEN"

# Step 2: After rotation — this request must return 401
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/spans \
  -H "Authorization: Bearer $OLD_TOKEN"
# Expected: 401
```

### Verify New Login Works

```bash
# After rotation — new login must succeed
curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}' | jq .session_token
# Expected: a non-null JWT string
```

---

## Related Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SECRET_KEY` | Yes — no fallback | none | Raises `KeyError` at startup if unset. Generate with `openssl rand -hex 32`. Loaded at module level in `deps.py` via `os.environ["SECRET_KEY"]`. |
| `OLD_SECRET_KEY` | No — Option B only | none | Loaded via `os.environ.get("OLD_SECRET_KEY")`. Temporary — remove after rotation window. |
| `TOKEN_EXPIRE_MINUTES` | n/a | 30 | Hardcoded in `deps.py`. Not a runtime env var. Changing it requires a code change and redeploy. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | n/a | 30 | Hardcoded in `deps.py`. Not a runtime env var. |

---

## Related Source Files

| File | Relevance |
|------|-----------|
| `xeter/services/presenter/deps.py` | Loads `SECRET_KEY` via `os.environ["SECRET_KEY"]`; defines `TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `create_session_token`, `verify_session_token` |
| `xeter/services/diagnosticer/main.py` | Loads `SECRET_KEY` via `os.environ["SECRET_KEY"]`; uses it to verify session tokens on authenticated endpoints |
| `docs/JWT_ROTATION_RUNBOOK.md` | This file |
