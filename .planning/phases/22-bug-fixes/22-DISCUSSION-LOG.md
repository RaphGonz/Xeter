# Phase 22: Bug Fixes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 22-Bug Fixes
**Areas discussed:** Flush check placement, Trace score write semantics, Test coverage strategy

---

## Flush Check Placement

### Q1 — Helper vs inline

| Option | Description | Selected |
|--------|-------------|----------|
| Extract helper (Recommended) | `_flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)` called from both branches. No duplication, directly unit-testable. | ✓ |
| Inline in result is None | Duplicate flush block in the timeout branch. Minimal diff but creates DRY violation. | |
| You decide | Claude picks approach. | |

**User's choice:** Extract helper

### Q2 — Helper parameters

| Option | Description | Selected |
|--------|-------------|----------|
| trace_buffer + trace_last_seen + trace_analyzer (Recommended) | Pure function, receives dicts + analyzer, mutates in place. Directly testable. | ✓ |
| No parameters — close over main() locals | Inner function. Harder to test in isolation. | |
| Add now as float too | Also pass current timestamp. Avoids patching time.monotonic but changes signature. | |

**User's choice:** trace_buffer + trace_last_seen + trace_analyzer

### Q3 — Module-level vs nested

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level (Recommended) | Importable in tests directly. Consistent with process_span(). | ✓ |
| Nested inside main() | Cleaner namespace but not directly importable. | |

**User's choice:** Module-level

---

## Trace Score Write Semantics

### Q1 — Always call vs guard

| Option | Description | Selected |
|--------|-------------|----------|
| Always call (Recommended) | Consistent with span behavior. score_writer.py already early-returns for empty list. | ✓ |
| Only when non-empty | Guard with `if trace_scores:`. Diverges from span convention. | |

**User's choice:** Always call write_scores

### Q2 — span_id value

| Option | Description | Selected |
|--------|-------------|----------|
| None (Recommended) | Consistent with write_flags(None, ...) for trace flags. | ✓ |
| First span_id of the trace | Misleading — trace scores are cross-span. | |
| You decide | Claude picks. | |

**User's choice:** None

### Q3 — Handle non-nullable span_id in schema

| Option | Description | Selected |
|--------|-------------|----------|
| Check schema + loosen type to Optional[str] (Recommended) | Grep span_scores migration, update write_scores signature. Add migration if NOT NULL exists. | ✓ |
| Use a sentinel string instead of None | Avoids schema changes but semantically wrong. | |
| You decide | Claude picks. | |

**User's choice:** Check schema + loosen type to Optional[str]

---

## Test Coverage Strategy

### Q1 — Test file location

| Option | Description | Selected |
|--------|-------------|----------|
| New test_flush_stale_traces.py (Recommended) | Dedicated file for the extracted helper. Clean separation. | ✓ |
| Add to test_trace_buffer.py | Keeps trace tests together but mixes inline-simulation with real helper calls. | |
| Add to test_worker_loop.py | Blurs scope of worker loop tests. | |

**User's choice:** New test_flush_stale_traces.py

### Q2 — Time control strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Patch time.monotonic (Recommended) | Standard mock.patch approach. No helper signature changes needed. | ✓ |
| Pass now as a parameter | More testable but changes helper signature from D-03. | |
| Set trace_last_seen far in the past | No patching but depends on real clock. | |

**User's choice:** Patch time.monotonic

### Q3 — Required test scenarios

| Option | Description | Selected |
|--------|-------------|----------|
| Idle flush fires on BRPOP timeout | Tests _flush_stale_traces() called from result=None path. | ✓ |
| Trace scores written via write_scores | Tests flush_scores() called and passed to write_scores(None, ...). | ✓ |
| Non-stale traces not flushed | Confirms timeout guard works correctly. | ✓ |
| flush handles trace_analyzer exception | Exception logged; trace still removed from buffer (no memory leak). | ✓ |

**User's choice:** All four scenarios

---

## Claude's Discretion

None — user made all decisions directly.

## Deferred Ideas

None — discussion stayed within phase scope.
