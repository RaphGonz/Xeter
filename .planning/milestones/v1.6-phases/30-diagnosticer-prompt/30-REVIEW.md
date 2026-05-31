---
phase: 30-diagnosticer-prompt
reviewed: 2026-05-31T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - xeter/services/diagnosticer/context_assembly.py
  - xeter/services/diagnosticer/prompt.md
  - xeter/tests/diagnosticer/test_context_assembly.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 30: Code Review Report

**Reviewed:** 2026-05-31T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed three files implementing the Diagnosticer context-assembly path: the assembler module (`context_assembly.py`), the LLM prompt template (`prompt.md`), and the unit-test suite (`test_context_assembly.py`).

The prompt template itself is clear, well-structured, and free of injection risk. The test suite covers the core formatter thoroughly. Two critical issues exist in `context_assembly.py`: silent S3 credential failures that will silently degrade LLM input in production, and a broad bare `except Exception` swallowing errors (including `asyncio.CancelledError` in Python < 3.8, and masking all non-timeout errors). Three warnings relate to a double-UUID conversion bug, missing error handling after the `asyncio.gather` in `assemble_context`, and an `aioboto3.Session` being constructed per-call. Two info items round out the report.

---

## Critical Issues

### CR-01: S3 credentials silently pass `None` — unauthenticated requests in production

**File:** `xeter/services/diagnosticer/context_assembly.py:84-85`

**Issue:** `os.environ.get("S3_ACCESS_KEY")` and `os.environ.get("S3_SECRET_KEY")` return `None` when the environment variables are absent. `aioboto3.Session(aws_access_key_id=None, aws_secret_access_key=None)` falls back to boto3 credential chain resolution — if no IAM role or credentials file is present (the typical state in Docker without explicit env vars) boto3 will try anonymous access and then fail. The failure is caught by the bare `except Exception` on line 96 and replaced with `"[S3 fetch error]"`, so the LLM silently receives placeholder text instead of real prompt/response payloads. This corrupts every diagnosis produced in an environment where the env vars are missing — without any log message, metric, or error. The comments on lines 84-85 acknowledge the risk but do not fix it.

**Fix:**
```python
# Fail fast at call time rather than silently degrading.
access_key = os.environ["S3_ACCESS_KEY"]   # raises KeyError if not set
secret_key = os.environ["S3_SECRET_KEY"]   # raises KeyError if not set

s3_session = aioboto3.Session(
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
)
```

If silent degradation is an intentional design choice (e.g. anonymous-access MinIO in dev), the fallback must at minimum log a warning so operators can detect the issue:
```python
import logging
_log = logging.getLogger(__name__)

access_key = os.environ.get("S3_ACCESS_KEY")
if access_key is None:
    _log.warning("S3_ACCESS_KEY not set; S3 fetches will use anonymous credentials")
```

---

### CR-02: Bare `except Exception` silently swallows all S3 errors — no observability

**File:** `xeter/services/diagnosticer/context_assembly.py:96-97`

**Issue:** The inner `_fetch` closure catches every exception — including `botocore.exceptions.NoCredentialsError`, `botocore.exceptions.ClientError` (e.g. 403 Forbidden, 404 Not Found), JSON decode errors, and any other unexpected error — and returns the opaque string `"[S3 fetch error]"`. There is no logging, no re-raise, and no distinction between transient errors (network timeout), auth failures (wrong credentials), and data errors (malformed JSON). The LLM receives `"[S3 fetch error]"` in the payload fields and produces a diagnosis on incomplete data. The caller has no way to distinguish a successful empty payload from a silent fetch failure.

In Python 3.8+, `asyncio.CancelledError` inherits from `BaseException` not `Exception`, so it is not swallowed here — but `asyncio.TimeoutError` (before 3.11) inherits from `concurrent.futures.TimeoutError` which inherits from `Exception`, meaning the inner `except Exception` can absorb the timeout before `wait_for` sees it if the timeout races with internal boto3 machinery.

**Fix:**
```python
import logging
_log = logging.getLogger(__name__)

async def _fetch(key: str | None) -> str:
    if not key:
        return "[not available]"
    try:
        async with s3_session.client("s3", endpoint_url=endpoint_url) as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            body = await resp["Body"].read()
            data = json.loads(body)
            return data.get("value", "[empty payload]")
    except json.JSONDecodeError as exc:
        _log.error("S3 payload for key %r is not valid JSON: %s", key, exc)
        return "[S3 fetch error: invalid JSON]"
    except Exception as exc:
        _log.error("S3 fetch failed for key %r: %s", key, exc)
        return "[S3 fetch error]"
```

---

## Warnings

### WR-01: Double UUID conversion is redundant and fragile

**File:** `xeter/services/diagnosticer/context_assembly.py:122-125`

**Issue:** `_fetch_flags` receives `tenant_id: str` and immediately calls `_uuid.UUID(str(tenant_id))` on line 125 for the `Flag.tenant_id` WHERE predicate. Two problems:

1. `tenant_id` is already typed as `str`, so `str(tenant_id)` is a no-op. The `uuid.UUID()` conversion exists to match the `UUID(as_uuid=True)` column type, but SQLAlchemy with asyncpg handles both `str` and `uuid.UUID` transparently for `UUID(as_uuid=True)` columns — no manual conversion is needed.

2. More importantly, the `tenant_session` call on line 120 already uses `tenant_id` as a plain string for the RLS `SET LOCAL`. The WHERE clause then uses a re-parsed `uuid.UUID` object for the same value. If `tenant_id` is an invalid UUID string, `_uuid.UUID(str(tenant_id))` raises `ValueError` inside the async context manager, after the RLS variable has already been set, leading to a transaction rollback — but the caller in `assemble_context` (line 199) will see the ValueError propagate out of `asyncio.gather` with no context about which gather branch failed.

The redundancy also imports `uuid` inside the function body on every call (line 119), which is wasteful.

**Fix:**
```python
# Move import to module top-level
import uuid as _uuid

async def _fetch_flags(
    session: AsyncSession,
    span_id: str,
    tenant_id: str,
) -> list[Flag]:
    # Validate UUID once at the entry point, before entering any context manager
    tenant_uuid = _uuid.UUID(tenant_id)  # raises ValueError early if invalid
    async with tenant_session(session, tenant_id) as s:
        result = await s.execute(
            select(Flag).where(
                Flag.span_id == span_id,
                Flag.tenant_id == tenant_uuid,
            )
        )
        return list(result.scalars().all())
```

---

### WR-02: `asyncio.gather` in `assemble_context` does not handle partial failures

**File:** `xeter/services/diagnosticer/context_assembly.py:199-201`

**Issue:** `asyncio.gather(_fetch_flags(...), _fetch_s3_payloads(...))` uses the default `return_exceptions=False`. If `_fetch_flags` raises (e.g. the PostgreSQL session is unexpectedly closed, or a `ValueError` from the UUID conversion in WR-01), the gather cancels the in-flight S3 fetch coroutine and re-raises. However, `_fetch_s3_payloads` already handles its own errors internally, so cancellation of its awaitable may leave boto3 resources in an indeterminate state. More importantly, when `_fetch_flags` fails, the exception message gives no context about which branch failed — callers only see the raw SQLAlchemy or ValueError.

The docstring for `assemble_context` documents only `ValueError` (span not found), implying flag fetch errors are unexpected and unhandled.

**Fix:** Either document that all exceptions from the gather propagate to the caller and must be handled there, or use `return_exceptions=True` and inspect results:
```python
results = await asyncio.gather(
    _fetch_flags(session, span_id, tenant_id),
    _fetch_s3_payloads(span.get("prompt_ref"), span.get("response_ref")),
    return_exceptions=True,
)
flags_result, s3_result = results

if isinstance(flags_result, BaseException):
    _log.error("Flag fetch failed for span %r: %s", span_id, flags_result)
    flags_result = []  # or re-raise, depending on policy

if isinstance(s3_result, BaseException):
    # _fetch_s3_payloads should never raise, but guard anyway
    s3_result = ("[S3 fetch error]", "[S3 fetch error]")

flags = flags_result
prompt_text, response_text = s3_result
```

---

### WR-03: `aioboto3.Session` created on every call — resource and connection overhead

**File:** `xeter/services/diagnosticer/context_assembly.py:83-86`

**Issue:** A new `aioboto3.Session` is instantiated inside `_fetch_s3_payloads` on every invocation. `aioboto3.Session` is lightweight on its own, but each call to `s3_session.client(...)` inside `_fetch` also opens a new HTTP connection to MinIO/S3, bypassing connection pooling entirely. Under any meaningful load (e.g. multiple concurrent diagnoses), this creates a new connection per S3 fetch per call, without benefiting from keep-alive or connection reuse.

**Fix:** Hoist the session to module level or accept it as a dependency-injected argument so the HTTP connection pool is shared across calls:
```python
# Module-level — initialised lazily once
_s3_session: aioboto3.Session | None = None

def _get_s3_session() -> aioboto3.Session:
    global _s3_session
    if _s3_session is None:
        _s3_session = aioboto3.Session(
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        )
    return _s3_session
```

---

## Info

### IN-01: `uuid` import inside function body — should be at module level

**File:** `xeter/services/diagnosticer/context_assembly.py:119`

**Issue:** `import uuid as _uuid` appears inside `_fetch_flags`. Python caches module imports after the first load, so there is no correctness issue, but placing imports inside functions obscures the module's dependencies and deviates from PEP 8 convention (all imports at the top of the file).

**Fix:** Move `import uuid` to the top-level imports section alongside the other standard library imports.

---

### IN-02: Test `test_missing_prompt_file_raises` has a silent recovery that masks reload failures

**File:** `xeter/tests/diagnosticer/test_context_assembly.py:127-130`

**Issue:** After verifying the `FileNotFoundError` is raised on reload with the mock active, the test attempts to restore the module with a second `importlib.reload(context_assembly)` inside a bare `except Exception: pass` block. If the second reload fails for any reason (e.g. the working directory changed, or another test patched `Path.read_text` without cleanup), the module is left in a broken state and sibling tests will fail with confusing errors. The silent `except Exception: pass` means the restoration failure is invisible.

**Fix:** Remove the bare exception suppression. `importlib.reload` after the mock context exits should succeed normally; if it does not, that is a real test environment problem and should surface as a failure:
```python
def test_missing_prompt_file_raises(self):
    with unittest.mock.patch(
        "pathlib.Path.read_text",
        side_effect=FileNotFoundError("prompt.md not found"),
    ):
        with pytest.raises(FileNotFoundError):
            importlib.reload(context_assembly)
    # Restore — let failures surface naturally
    importlib.reload(context_assembly)
```

---

_Reviewed: 2026-05-31T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
