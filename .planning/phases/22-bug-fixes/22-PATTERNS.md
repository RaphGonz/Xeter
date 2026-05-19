# Phase 22: Bug Fixes - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 4 (3 modified, 1 new)
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `xeter/services/worker/main.py` | utility (module-level helper extraction) | event-driven | `xeter/services/worker/main.py` — `process_span()` (lines 78–116) | exact |
| `xeter/services/worker/score_writer.py` | service | CRUD | `xeter/services/worker/flag_writer.py` (lines 51–108) | exact |
| `xeter/tests/worker/test_flush_stale_traces.py` | test | event-driven | `xeter/tests/worker/test_worker_loop.py` | exact |
| DB migration (new file) | migration | CRUD | `xeter/migrations/versions/005_trace_flags_schema.py` | exact |

---

## Pattern Assignments

### `xeter/services/worker/main.py` — extract `_flush_stale_traces()`

**Analog:** `process_span()` in the same file (lines 78–116) for the module-level function shape; the inline flush block (lines 166–187) for the logic body.

**Module-level function pattern** (lines 78–99):
```python
def process_span(span_id: str, analyzers: list) -> SpanData:
    """Fetch a span and dispatch it to all registered analyzers.

    Designed to accept an ``analyzers`` parameter (not a global) so integration
    tests can inject mock analyzers without monkeypatching module globals.
    ...
    """
```

Key attributes to copy:
- Module-level placement (not nested inside `main()`)
- Docstring explaining purpose and args
- Parameters passed in — no implicit globals used inside the function body
- `-> None` return type for the new helper (it mutates dicts in place)

**Inline flush block to extract** (lines 166–187 — becomes the body of `_flush_stale_traces()`):
```python
now = time.monotonic()
ready_trace_ids = [
    tid for tid, last in trace_last_seen.items()
    if now - last >= WORKER_TRACE_FLUSH_TIMEOUT_S
]
for tid in ready_trace_ids:
    spans_for_trace = trace_buffer[tid]
    tenant_id_for_trace = spans_for_trace[0].tenant_id
    try:
        trace_flags = trace_analyzer.analyze(spans_for_trace)
        if trace_flags:
            write_flags(None, tenant_id_for_trace, tid, trace_flags)
        logger.info(
            "worker: flushed trace trace_id=%s spans=%d flags=%d",
            tid, len(spans_for_trace), len(trace_flags),
        )
    except Exception as exc:
        logger.error("worker: failed to flush trace trace_id=%s: %s", tid, exc)
    finally:
        trace_buffer.pop(tid, None)
        trace_last_seen.pop(tid, None)
```

**D-05/INFRA-02 addition** — after `trace_analyzer.analyze()`, add `flush_scores()` call and `write_scores(None, ...)` call inside the `try` block, modelled exactly on `process_span()` lines 107–111:
```python
# Existing pattern (process_span, lines 107–111):
scores = analyzer.flush_scores()
all_scores.extend(scores)
write_scores(span_id, span.tenant_id, all_scores)

# New pattern inside _flush_stale_traces() try block:
trace_flags = trace_analyzer.analyze(spans_for_trace)
trace_scores = trace_analyzer.flush_scores()
write_scores(None, tenant_id_for_trace, trace_scores)
if trace_flags:
    write_flags(None, tenant_id_for_trace, tid, trace_flags)
```

**Call-site pattern** — call `_flush_stale_traces()` from both branches:
```python
# Branch 1: BRPOP timeout (currently has `continue`, replace with):
if result is None:
    _flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)
    continue

# Branch 2: after successful span processing (replaces inline block at lines 166–187):
_flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)
```

---

### `xeter/services/worker/score_writer.py` — type update `span_id: Optional[str]`

**Analog:** `flag_writer.py` `write_flags()` signature (lines 51–56) — already uses `span_id: str | None` and maps `None` to SQL NULL via psycopg2.

**Existing flag_writer pattern** (lines 51–56):
```python
def write_flags(
    span_id: str | None,
    tenant_id: str,
    trace_id: str,
    flags: list[Flag],
) -> None:
```

**Existing flag_writer None-handling docstring** (lines 63–66):
```python
        span_id: The span that triggered the flags, or None for trace-level
                 flags produced by TraceAnalyzer (which analyze a full trace,
                 not a single span). psycopg2 maps None to SQL NULL automatically.
```

**Score writer change** — update the signature and docstring only; psycopg2 already maps `None` → SQL NULL automatically, so the `rows` tuple construction at line 70 needs no change:
```python
# Current (line 46–50):
def write_scores(
    span_id: str,
    tenant_id: str,
    scores: list[tuple[str, str, float]],
) -> None:

# Updated:
def write_scores(
    span_id: str | None,
    tenant_id: str,
    scores: list[tuple[str, str, float]],
) -> None:
```

Also update the docstring `span_id:` line to match flag_writer wording — "The span being scored, or None for trace-level scores (psycopg2 maps None to SQL NULL automatically)."

The error-log line at line 87 references `span_id` — leave as-is; psycopg2 formats None as `None` in the log string which is acceptable.

---

### `xeter/tests/worker/test_flush_stale_traces.py` — NEW test file

**Analog:** `xeter/tests/worker/test_worker_loop.py` (entire file) — mock-all-IO pattern.

**Imports pattern** (test_worker_loop.py lines 1–17):
```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from xeter.services.worker.main import process_span
from xeter.services.worker.base import Flag, SpanData
```

New file imports — replace `process_span` with `_flush_stale_traces`:
```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from xeter.services.worker.main import _flush_stale_traces, WORKER_TRACE_FLUSH_TIMEOUT_S
from xeter.services.worker.base import Flag, SpanData
```

**make_test_span helper** — copy exactly from `test_trace_buffer.py` lines 26–48:
```python
def make_test_span(
    span_id: str = "test-span-1",
    trace_id: str = "trace-1",
    tenant_id: str = "tenant-uuid-1",
) -> SpanData:
    return SpanData(
        span_id=span_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        agent_name="agent",
        agent_model="gpt-4",
        tool_name="some_tool",
        tool_description="does something",
        tool_arguments='{"key": "value"}',
        tool_output="done",
        prompt="do the thing",
        response="I called some_tool",
        raw_response=None,
        available_tools=[{"name": "some_tool", "description": "does something"}],
    )
```

**mock_all_io pattern** — copy from test_worker_loop.py tests (lines 67–75). The three patches for every test:
```python
with (
    patch("xeter.services.worker.main.fetch_span", return_value=span),
    patch("xeter.services.worker.main.write_scores") as mock_write_scores,
    patch("xeter.services.worker.main.write_flags") as mock_write_flags,
):
```

For `_flush_stale_traces` tests, `fetch_span` is not called, so use only:
```python
with (
    patch("xeter.services.worker.main.write_scores") as mock_write_scores,
    patch("xeter.services.worker.main.write_flags") as mock_write_flags,
    patch("xeter.services.worker.main.time.monotonic", return_value=<far_future>),
):
```

**Time-patching pattern** — D-10 mandates `patch('xeter.services.worker.main.time.monotonic', return_value=<value>)`. The module imports `time` at line 36, so the patch target is the module-level `time` reference:
```python
with patch("xeter.services.worker.main.time.monotonic", return_value=9999.0):
    _flush_stale_traces(trace_buffer, trace_last_seen, mock_trace_analyzer)
```

**make_mock_analyzer helper** — copy from test_worker_loop.py lines 47–52, adapt for trace analyzer:
```python
def make_mock_trace_analyzer(flags=None, scores=None):
    analyzer = MagicMock()
    analyzer.analyze.return_value = flags if flags is not None else []
    analyzer.flush_scores.return_value = scores if scores is not None else []
    return analyzer
```

**D-11 test scenarios** — four tests structured after existing test pattern:

Test 1 (idle flush fires on timeout path):
```python
def test_idle_flush_fires_when_stale():
    span = make_test_span(trace_id="trace-A")
    trace_buffer = {"trace-A": [span]}
    trace_last_seen = {"trace-A": 0.0}  # far in the past
    mock_ta = make_mock_trace_analyzer(flags=[], scores=[])

    with (
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ta.analyze.assert_called_once_with([span])
    assert "trace-A" not in trace_buffer
    assert "trace-A" not in trace_last_seen
```

Test 2 (trace scores written via write_scores(None, ...)):
```python
def test_trace_scores_written_with_none_span_id():
    span = make_test_span(trace_id="trace-B")
    trace_buffer = {"trace-B": [span]}
    trace_last_seen = {"trace-B": 0.0}
    scores = [("trace_analyzer", "some_metric", 0.75)]
    mock_ta = make_mock_trace_analyzer(flags=[], scores=scores)

    with (
        patch("xeter.services.worker.main.write_scores") as mock_ws,
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ws.assert_called_once_with(None, span.tenant_id, scores)
```

Test 3 (non-stale trace is NOT flushed):
```python
def test_non_stale_trace_not_flushed():
    span = make_test_span(trace_id="trace-C")
    trace_buffer = {"trace-C": [span]}
    trace_last_seen = {"trace-C": 9998.0}  # only 1s ago
    mock_ta = make_mock_trace_analyzer()

    with (
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)

    mock_ta.analyze.assert_not_called()
    assert "trace-C" in trace_buffer  # still in buffer
```

Test 4 (exception from analyze() → logged + buffer cleaned):
```python
def test_exception_in_analyze_logs_and_cleans_buffer():
    span = make_test_span(trace_id="trace-D")
    trace_buffer = {"trace-D": [span]}
    trace_last_seen = {"trace-D": 0.0}
    mock_ta = MagicMock()
    mock_ta.analyze.side_effect = RuntimeError("boom")

    with (
        patch("xeter.services.worker.main.write_scores"),
        patch("xeter.services.worker.main.write_flags"),
        patch("xeter.services.worker.main.time.monotonic", return_value=9999.0),
    ):
        _flush_stale_traces(trace_buffer, trace_last_seen, mock_ta)  # must not raise

    assert "trace-D" not in trace_buffer      # no memory leak
    assert "trace-D" not in trace_last_seen
```

---

### DB migration (new file `xeter/migrations/versions/006_span_scores_nullable_span_id.py`)

**Analog:** `xeter/migrations/versions/005_trace_flags_schema.py` — single-ALTER-COLUMN migration using `op.execute()` with raw SQL.

**Migration file structure** (005, lines 1–43):
```python
"""Flags table schema extension for trace-level flags.

Changes (Phase 19 v1.4 TraceAnalyzer Scaffold):
  TANA-04: span_id column made nullable — ...

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE flags ALTER COLUMN span_id DROP NOT NULL;")


def downgrade() -> None:
    op.execute("ALTER TABLE flags ALTER COLUMN span_id SET NOT NULL;")
```

**Schema fact confirmed:** `span_scores.span_id` is declared `nullable=False` in migration 002 (line 46: `sa.Column("span_id", sa.String(), nullable=False)`). A migration IS required.

**New migration template** — copy 005 structure exactly, update for span_scores:
```python
"""span_scores: make span_id nullable for trace-level scores.

Changes (Phase 22 v1.5 Bug Fixes):
  INFRA-02: span_id column made nullable — trace-level scores produced by
            TraceAnalyzer have no single span; span-level scores continue
            to populate span_id as before.

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE span_scores ALTER COLUMN span_id DROP NOT NULL;")


def downgrade() -> None:
    # WARNING: any trace-level score rows (span_id IS NULL) will block this.
    op.execute("ALTER TABLE span_scores ALTER COLUMN span_id SET NOT NULL;")
```

---

## Shared Patterns

### try/except/finally in flush loop
**Source:** `xeter/services/worker/main.py` lines 175–187
**Apply to:** `_flush_stale_traces()` body — the `finally` block is critical to prevent memory leak when `analyze()` raises.
```python
try:
    trace_flags = trace_analyzer.analyze(spans_for_trace)
    ...
except Exception as exc:
    logger.error("worker: failed to flush trace trace_id=%s: %s", tid, exc)
finally:
    trace_buffer.pop(tid, None)
    trace_last_seen.pop(tid, None)
```

### `flush_scores()` + `write_scores()` call pair
**Source:** `xeter/services/worker/main.py` lines 107–111 (`process_span`)
**Apply to:** `_flush_stale_traces()` try block — call `flush_scores()` immediately after `analyze()`, then pass result to `write_scores()`.
```python
scores = analyzer.flush_scores()
write_scores(span_id, span.tenant_id, scores)
```

### `span_id: str | None` accepting None for trace writes
**Source:** `xeter/services/worker/flag_writer.py` lines 51–56, 63–66
**Apply to:** `write_scores()` signature update — `str | None` union type; psycopg2 maps Python `None` to SQL NULL with no extra code.

### Mock-all-IO test structure
**Source:** `xeter/tests/worker/test_worker_loop.py` lines 60–75
**Apply to:** All four scenarios in `test_flush_stale_traces.py` — patch `write_scores`, `write_flags`, and `time.monotonic` at `xeter.services.worker.main.*`.

---

## No Analog Found

None — all four files have exact or role-match analogs in the codebase.

---

## Metadata

**Analog search scope:** `xeter/services/worker/`, `xeter/tests/worker/`, `xeter/migrations/versions/`
**Files scanned:** 7 source files + 5 migration files
**Pattern extraction date:** 2026-05-19
