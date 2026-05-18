# Pitfalls Research

**Domain:** Adding 18 new analyser checks (B1-B4, C3-C4, D1-D3, D5, E3, F1-F2, F4-F5, G1-G2, H2) to an existing AI observability worker.
**Researched:** 2026-05-18
**Confidence:** HIGH — based on direct codebase inspection of worker/main.py, base.py, tool_call_analyzer.py, trace_analyzer.py, flag_writer.py, score_writer.py, span_fetcher.py, and calibrate.py.

---

## Critical Pitfalls

### Pitfall 1: Sparse Fixture Problem — New Checks Cannot Be Calibrated With the Existing Fixture

**What goes wrong:**
`calibrate.py` loads `fixtures/labelled_spans.jsonl` and hill-climbs against `ToolCallAnalyzer` (line 144 of calibrate.py: the harness instantiates only `ToolCallAnalyzer`). The existing fixture labels use `anomaly_type` matching the seven A-category flag types. Every new v1.5 check (output_schema_violation, step_repetition, context_propagation_failure, etc.) has zero labelled examples in that fixture. Hill-climbing on zero positives produces P=0/0 (the division guard returns 0.0) and the hill-climb converges immediately with `best_threshold = HILL_CLIMB_START = 0.10` — a threshold so low it fires on nearly any span. The summary prints "WARN" but still writes the bad threshold to `calibrated_thresholds.json` and patches `docker-compose.yml`. The check is deployed and flags everything.

**Why it happens:**
The calibration harness is tightly coupled to `ToolCallAnalyzer`. Even if new fixture entries are added with the correct `anomaly_type`, the harness never dispatches to `OutputSchemaAnalyzer` or `TraceAnalyzer`. The harness loop on line 444 iterates `active_flag_types` (a string list) and calls `ToolCallAnalyzer(embedder, thresholds).analyze()` — new analyzer classes are invisible to it.

**How to avoid:**
- Build fixtures before implementing checks. Minimum viable: 15 positive + 15 negative labelled examples per check. For trace-level checks (C3, C4, D1, D2, F1-F5, G1-G2), the fixture format must be a list of SpanData per trace, not a single span row.
- Extend `calibrate.py` with an `--analyzer` flag that instantiates the correct class, or create a separate `calibrate_v15.py`. Do not modify the working v1.4 harness mid-milestone — it covers 112+ passing tests.
- Register every new threshold key in `THRESHOLDS` in `main.py` (and `DEFAULT_THRESHOLDS` in `calibrate.py`) in the same PR that introduces the check method. A missing key raises `KeyError` at runtime, not at import time.

**Warning signs:**
- Hill-climb completes in 1 step with precision=0.0 for any new flag type.
- `calibrate.py` prints "WARN (<80% precision)" for every new check.
- New `self._thresholds["some_key"]` reference added but the key is absent from `THRESHOLDS` in `main.py`.

**Phase to address:**
The fixture-definition phase preceding each check group. Threshold registration must ship in the same PR as the check method — not as a follow-up.

---

### Pitfall 2: Trace Flush Does Not Fire During Idle — Buffer Grows Unbounded

**What goes wrong:**
The flush check in `main.py` lives inside the `for attempt in range(3)` success branch (lines 168-188 of main.py). It fires only when a new span is successfully processed. BRPOP with `timeout=2` returns `None` on the quiet path, hits `continue`, and skips the buffer check entirely. If a developer sends one trace and then stops sending spans, the trace buffer entry sits in memory indefinitely. No trace-level flags are ever written for that trace, no matter how long the worker runs. The 30-second timeout is a "time since last span" measurement, not a wall-clock ticker.

**Why it happens:**
The flush check was correctly placed to avoid a second sleep loop. The architectural consequence — that the buffer is only inspected on new span arrival — is easy to miss. The bug is invisible in integration tests that always follow a trace with more traffic, and invisible in unit tests that call `trace_analyzer.analyze()` directly.

**How to avoid:**
Move the `ready_trace_ids` block so it also runs on the `result is None` branch (the BRPOP timeout path). When BRPOP returns None, check `trace_last_seen` for any trace that has exceeded the timeout and flush it. This is a one-line structural change to the main loop.

**Warning signs:**
- Integration test sends exactly N spans for a trace, waits 35 seconds with `WORKER_TRACE_FLUSH_TIMEOUT_S=5`, and sees zero trace-level flags.
- `trace_buffer` grows over a long run and its length never decreases.
- No trace-level flags appear in the flags table despite spans being processed.

**Phase to address:**
The phase that implements the first trace-level check. If trace flags never fire in tests, this is the cause. Add a `test_trace_flush_on_idle` integration test that explicitly verifies the BRPOP-timeout path.

---

### Pitfall 3: Trace-Level Scores Silently Not Persisted — Calibration Dataset Is Empty for All C/D/F/G Checks

**What goes wrong:**
`process_span()` calls `analyzer.analyze(span)` then `analyzer.flush_scores()` and passes scores to `write_scores(span_id, tenant_id, scores)`. In the trace flush loop (main.py lines 175-188), `trace_analyzer.analyze(spans_for_trace)` is called and flags are written, but `trace_analyzer.flush_scores()` is never called — and even if it were, `write_scores` takes `span_id: str` with no None handling. The `span_scores` table may also have `span_id NOT NULL`. The result: every `log_score()` call inside trace-level check methods accumulates in `self._scores` indefinitely (buffer leak) and no trace scores ever reach the database. The calibration dataset for all C/D/F/G checks is permanently empty.

**Why it happens:**
`write_scores` was written for span-level use exclusively. The v1.4 scaffold wired only `write_flags` for the trace path. No one noticed because `TraceAnalyzer.analyze()` returned `[]` and `log_score()` was never called.

**How to avoid:**
- Inspect the `span_scores` schema for `span_id NOT NULL` before the first trace check lands. If NOT NULL, add a migration to make it nullable, or add a `trace_id` column and create a `write_trace_scores(trace_id, tenant_id, scores)` function.
- In the flush loop, after `trace_analyzer.analyze()`, call `trace_analyzer.flush_scores()` and write the results. Do this in the same PR as the first trace-level check.
- Add a buffer-leak test: call `trace_analyzer.analyze(spans)` twice without flushing and assert that `len(trace_analyzer._scores)` grows — confirming the leak is present before the fix, then confirm the flush zeroes it.

**Warning signs:**
- `span_scores` shows zero rows with `analyzer_name = 'trace_analyzer'` after multiple trace flushes.
- `trace_analyzer._scores` grows without bound over multiple analyze() calls (no flush in the loop).
- Calibration data for C/D/F/G checks is empty even after full processing runs.

**Phase to address:**
The phase implementing the first trace-level check. Score persistence must be in the same PR as the check — not deferred to a "calibration cleanup" phase.

---

### Pitfall 4: Second Span-Level Analyzer Doubles Embedder Round-Trips Per Span

**What goes wrong:**
`process_span()` iterates `for analyzer in analyzers` and dispatches each independently. If `OutputSchemaAnalyzer` (B1-B4) and `ContentAnalyzer` (D3/D5/E3/H2) are both appended to `ANALYZERS`, and both embed `span.prompt`, each makes a separate `POST /encode` to the embedder service. With the synchronous `EmbedderClient`, this is two blocking HTTP round-trips per span for identical input. The per-tool embedding cache in `ToolCallAnalyzer` is instance-scoped and invisible to other analyzers. At dev volume, this is imperceptible. As span volume grows, each additional span analyzer multiplies embedder load linearly.

**Why it happens:**
`BaseAnalyzer.embed()` has no cross-analyzer caching. The design is correct for single-analyzer use. Multi-analyzer extension was not anticipated when the cache was designed.

**How to avoid:**
Before appending a second class to `ANALYZERS`, add a span-level embedding cache at the `process_span()` level: a `dict[str, np.ndarray]` keyed by `hashlib.sha256(text.encode()).hexdigest()`. Pass the cache to each analyzer, or wrap `EmbedderClient` with a cache layer. Alternatively, compute shared embeddings (prompt, response) once before the loop and inject them into `SpanData` as optional pre-computed fields.
The minimum viable mitigation for v1.5: document this as TECH-01 and accept the duplicate calls at dev scale, but add the cache before any production load test.

**Warning signs:**
- Embedder service logs show two `POST /encode` calls with identical `texts` payloads within milliseconds of each other.
- Worker per-span processing time increases by ~50ms per additional span analyzer.
- `EmbedderClient.encode()` is called with the same text string multiple times in a single span's analysis.

**Phase to address:**
The phase that appends the second span-level analyzer to `ANALYZERS`. Add the cross-analyzer cache in the same PR, not as a follow-up.

---

### Pitfall 5: F1/F2/F4/F5 Heuristic Brittleness — Proxy Signals Without a Documented False-Positive Mode Are Just Wrong Flags

**What goes wrong:**
F1 (wrong agent handoff), F2 (information withholding), F4 (conversation reset), and F5 (fail to ask for clarification) have no ground truth in OTel spans. No standard span attribute declares `handoff_target`, `required_fields_passed`, or `conversation_reset`. Every implementation must use a proxy signal: e.g., F1 approximated by comparing `agent_name` transitions across spans, F4 approximated by detecting a span response with no reference to prior tool outputs. These proxies have structural false-positive modes that are independent of threshold calibration — they fire on correct agent behaviour that coincidentally matches the heuristic pattern.

**Why it happens:**
The IBM/Berkeley taxonomy defines failures at the semantic level (what the agent *should* have done). OTel spans record what the agent *did*. The gap between intent and action cannot be closed by heuristics alone without richer instrumentation.

**How to avoid:**
- Define a precision floor for each F-check before writing a single line of implementation. If F1 cannot reach 65% precision on a hand-curated fixture without a `handoff_target` span attribute, defer F1 until the SDK emits that attribute.
- Write the proxy signal and its known false-positive mode in the check method's docstring before any code. This forces the false-positive decision to be made at spec time, not discovered in the dashboard.
- Assign all F-checks to `BINARY_FLAG_TYPES` in `calibrate.py` (no threshold sweep, single evaluation pass) so they cannot be over-fitted to a threshold that masks poor signal quality.
- Add a `confidence: "low"` field to the `Flag.detail` dict for F-checks so the dashboard can visually distinguish them from high-confidence A/B flags.

**Warning signs:**
- F-check precision on a hand-crafted fixture is below 0.60.
- The same trace triggers F1 and F4 simultaneously (heuristic overlap rather than distinct signal).
- The check fires on single-agent traces with no handoff spans.
- A check method docstring has no paragraph describing the proxy signal and its false-positive mode.

**Phase to address:**
The phase defining F-check specifications. Each spec must include proxy signal, false-positive mode, and precision floor as go/no-go criteria before any implementation code is written.

---

### Pitfall 6: G1/G2 Fires on Every Non-Verification Agent — Structural False Positives at the Trace Level

**What goes wrong:**
G1 (no verification) and G2 (incomplete verification) are trace-level: "did the agent include any self-check or cross-check step?" Most agent traces — data retrieval, action execution, single-step tasks — legitimately have no verification step because the task does not require one. With no span attribute declaring `task_requires_verification`, G1 flags every single-step trace, every simple fetch trace, every trace where verification was correctly absent. At realistic agent traffic, G1 fires on the majority of traces with a precision near zero.

**Why it happens:**
Verification absence is only a failure when verification was *expected*. The check cannot distinguish "correctly skipped" from "incorrectly omitted" without declarative intent metadata in the trace.

**How to avoid:**
Gate G1 and G2 on structural prerequisites:
- Minimum span count threshold: the trace must contain at least N spans with tool use (N >= 3 is a reasonable proxy for "substantial work that might warrant a check"). Exclude all single-span traces unconditionally.
- Prefer an opt-in span attribute: `xeter.verification_expected: true`. Without that attribute on at least one span, skip G1/G2 entirely. This shifts the signal burden to the instrumentation layer but eliminates structural false positives.
- If opt-in is not viable for v1.5, tag G1/G2 flags with `confidence: "low"` in `Flag.detail` so the dashboard can filter them separately.

**Warning signs:**
- G1 fires on every trace with a single tool-call span.
- G1 precision on a manually curated fixture is below 0.50 even with selected positive examples.
- The flag appears on traces where the task is clearly a single-step lookup (no multi-step reasoning expected).

**Phase to address:**
The phase implementing G1/G2. The multi-span prerequisite gate must be in the spec before implementation — adding it as a post-hoc patch after dashboard noise appears means deleting and rewriting the check.

---

### Pitfall 7: Hill-Climb Degenerate Solution — P=1.0, R=0.0 Reported as "OK"

**What goes wrong:**
The hill-climb algorithm (`calibrate.py` lines 247-278) raises the threshold until precision drops. For a check with few positive examples in the fixture (say, 5 positives out of 100 spans), the hill-climb converges to a high threshold that classifies everything as negative: P=1.0 (no false positives — nothing predicted), R=0.0 (no true positives detected). The script reports "OK" because `P >= 0.80` is satisfied. The deployed check then flags nothing. No operator notice. Calibration "succeeded."

**Why it happens:**
The stopping condition is "precision stopped improving." With a low-prevalence check and a high threshold, precision trivially reaches 1.0. There is no recall floor in the current algorithm.

**How to avoid:**
Add `RECALL_FLOOR = 0.40` to `calibrate.py`. In `hill_climb()`, update `best_threshold` only when both `precision >= precision_floor` AND `recall >= RECALL_FLOOR`. If no threshold satisfies both, report the threshold with the best F1 score and print a warning. This prevents the degenerate all-negative solution from being silently accepted. Additionally, print the R value alongside the "OK" status in the calibration summary so a P=1.0, R=0.0 result is visually obvious.

**Warning signs:**
- Calibration reports P=1.0, R=0.0 for a new check type and marks it "OK."
- The check produces zero flags on the full production fixture.
- Hill-climb converges in 2 steps (threshold 0.10 already achieves P=1.0 trivially).
- `calibrate.py` prints `steps=2` for a new check type.

**Phase to address:**
The calibration infrastructure phase for v1.5. The recall floor must be added to `calibrate.py` before any v1.5 calibration runs, not discovered after seeing a deployed check that never fires.

---

### Pitfall 8: TraceAnalyzer Registered in ANALYZERS — Dispatched With Single SpanData Instead of List

**What goes wrong:**
`main.py` `ANALYZERS` list currently contains only `BaseSpanAnalyzer` instances. `process_span()` calls `analyzer.analyze(span)` for each — passing a single `SpanData`. `TraceAnalyzer(BaseTraceAnalyzer)` defines `analyze(self, spans: list[SpanData]) -> list[Flag]`. If `TraceAnalyzer` is accidentally appended to `ANALYZERS` instead of kept as the separate `trace_analyzer` instance, it receives a single `SpanData` where it expects a list. The first check method that calls `spans[0].span_id` works fine (a SpanData is subscriptable as `span[0]` returns a character). It will either return wrong results silently or raise a `TypeError` mid-analysis, which the log-and-skip handler catches and swallows.

**Why it happens:**
Both `ToolCallAnalyzer` and `TraceAnalyzer` subclass `BaseAnalyzer`. They look structurally similar at the registration site. The type signatures differ (`SpanData` vs `list[SpanData]`) but Python does not enforce this at construction time.

**How to avoid:**
- Keep `trace_analyzer` as a named variable separate from the `ANALYZERS` list, as it is today.
- Add a type assertion comment at the ANALYZERS definition: `# NOTE: BaseSpanAnalyzer instances only. TraceAnalyzer is dispatched separately below.`
- Add a runtime assertion in the main function: `assert all(isinstance(a, BaseSpanAnalyzer) for a in analyzers)` before the BRPOP loop begins.

**Warning signs:**
- `TraceAnalyzer` appears in the `analyzers` parameter passed to `process_span()`.
- `process_span()` raises `TypeError` on trace-related spans after new analyzers are added.
- Logs show "worker: failed to process span" immediately after a new analyzer is registered.

**Phase to address:**
The phase adding the second span-level analyzer. The type assertion guard should be added then, before the ANALYZERS list grows.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `calibrate.py` as-is by adding new entries to `FLAG_TYPES` | No new harness code | Harness instantiates only `ToolCallAnalyzer`, so new analyzer check methods never run during calibration. Calibration scores are artifacts. | Never for v1.5. Create a separate calibration entry point or refactor to accept an analyzer class. |
| Hard-code proxy signal for F1/F2/F4/F5 without specifying false-positive modes | Faster implementation | False positive modes discovered in production dashboards; no documented baseline to measure regression. | Only if each check has a documented precision floor and false-positive mode in its docstring before merging. |
| Add all 18 checks as inline code in `TraceAnalyzer.analyze()` | Simpler file structure | Single method becomes a 400-line god function. Cannot calibrate checks independently. Tests require mocking the entire method. | Never. Each check must be a private method (`_check_c3`, `_check_c4`, etc.) mirroring ToolCallAnalyzer. |
| Skip `log_score()` calls for non-threshold heuristic checks | Less boilerplate | Calibration dataset is permanently incomplete. Cannot retrospectively analyse why a check fires. | Never. Even binary/heuristic checks should log a meaningful score (repetition_count, overlap_ratio) via `log_score()`. |
| Deploy new checks with `threshold=0.0` (always fire) until calibrated | Immediate dashboard visibility | Every trace gets flagged. Dashboard becomes noise. Customers stop trusting the product. | Never. Deploy with `threshold=1.1` (never fires) and lower only after calibration. |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `ANALYZERS` list in `main.py` | Append `TraceAnalyzer` to `ANALYZERS` alongside span-level analyzers | Only `BaseSpanAnalyzer` instances belong in `ANALYZERS`. `TraceAnalyzer` is a separate `trace_analyzer` instance dispatched in the flush loop. Mixing them calls `TraceAnalyzer.analyze(span)` with a single SpanData instead of `list[SpanData]`. |
| `THRESHOLDS` dict in `main.py` | Read `self._thresholds["new_key"]` from a check method before registering the key | All threshold keys must exist in `THRESHOLDS` in `main.py` before the worker starts. A missing key raises `KeyError` mid-analysis, silently dropping the entire span result via the log-and-skip handler. |
| `flush_scores()` in the trace flush loop | Never call `trace_analyzer.flush_scores()` after `trace_analyzer.analyze()` | `BaseAnalyzer._scores` accumulates across calls. Without a flush, the buffer grows unbounded across all trace flushes, and scores from trace N contaminate trace N+1. |
| `write_flags` with `span_id=None` for trace flags | Assume `span_id=None` works everywhere because migration 005 made `flags.span_id` nullable | `flag_writer.py` correctly handles `None` (psycopg2 maps None to SQL NULL). But `score_writer.py` takes `span_id: str` with no None path. The writers behave differently. Verify schema nullable before calling write_scores with None. |
| Score writing for trace-level checks | Call `write_scores(span_id=None, ...)` assuming `span_scores.span_id` is nullable | Inspect the migration for `span_scores.span_id` nullability before writing. If NOT NULL, add a migration to make it nullable or create a `trace_scores` table. |
| `calibrate.py` `FLAG_TYPES` list + new checks | Add new flag type string to `FLAG_TYPES` and assume calibration covers it | The harness dispatches to `ToolCallAnalyzer` only. Adding a string to `FLAG_TYPES` without also extending the harness to instantiate the correct analyzer class produces calibration data against the wrong analyzer. |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| 10 trace-level checks each embedding all spans | Worker flush time spikes from ~50ms to >5s per trace with 20+ spans | Pre-compute embeddings for each span's prompt+response once at flush time; pass pre-computed vectors to each check method as arguments | At ~10 spans per trace, 2 embeddings each, 10 checks each re-embedding independently: 200 embedder HTTP calls per flush. Noticeable at dev scale; catastrophic at production scale. |
| `trace_buffer` holds full S3 payloads in memory | Worker OOM on long-running traces with large prompt/response fields | SpanData.prompt and SpanData.response are full strings fetched from S3. For traces with 50+ spans and multi-KB prompts, the buffer holds MBs. Consider buffering only the fields trace checks actually need (span_id, agent_name, tool_name, tool_output). | At >50 spans per trace with >10KB prompts: potential OOM. Not a v1.5 concern at dev scale, but a v2.0 production risk to document now. |
| spaCy `_get_spacy()` reimplemented in TraceAnalyzer | First trace flush blocks ~2s while a second spaCy model instance loads | Import `_get_spacy` from `tool_call_analyzer.py` rather than reimplementing it. The global `_NLP` singleton is already loaded by ToolCallAnalyzer before any trace flush occurs. | Only on first flush after worker restart. Not sustained, but breaks flush latency SLA on the first trace. |
| One psycopg2 connection per flag in the flush loop | Connection pool exhaustion on traces producing many flags | `write_flags` opens and closes one connection per call. The flush loop calls it once per trace (all flags in one call). This is already correct. Do not break it into per-flag calls. | At >20 per-flag calls: connection pool exhaustion. Current pattern is safe — do not change it. |

---

## "Looks Done But Isn't" Checklist

- [ ] **New threshold key registered:** Every `self._thresholds["new_key"]` reference has a corresponding entry in `THRESHOLDS` in `main.py` with an `os.environ.get()` override. Missing key = `KeyError` at runtime.
- [ ] **Fixture coverage before calibration:** `fixtures/labelled_spans.jsonl` (or the new trace fixture) has labelled examples for the new flag type before running `calibrate.py`. Hill-climb on zero positives writes a bad threshold to docker-compose.
- [ ] **Trace flush scores written:** After implementing a trace-level check, `trace_analyzer.flush_scores()` is called in the flush loop AND scores are persisted to a DB table that accepts `span_id = NULL` or uses `trace_id` as the key.
- [ ] **Flush fires on idle:** Integration test sends N spans then waits — flush fires on BRPOP timeout (not only on next-span arrival). Without the idle-path fix, this test will time out.
- [ ] **F-check false-positive mode documented:** Every F-category check has a docstring paragraph stating the proxy signal and its known false-positive mode. If this paragraph is absent, the check is not ready to merge.
- [ ] **G1/G2 prerequisite gate active:** Single-span trace produces zero G1/G2 flags. Verify with a test before merging.
- [ ] **TraceAnalyzer not in ANALYZERS:** `assert all(isinstance(a, BaseSpanAnalyzer) for a in analyzers)` passes at worker startup. If it fails, a TraceAnalyzer was accidentally registered.
- [ ] **Hill-climb recall floor:** Calibration results show recall > 0 for all threshold-based new checks. P=1.0, R=0.0 means the check never fires and calibration did not catch it.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Bad threshold deployed (check fires on everything) | LOW | Set `WORKER_THRESHOLD_<CHECK>=1.1` in docker-compose, restart worker. Existing false-positive flag rows must be manually deleted or marked invalid in the flags table. |
| Fixture-less calibration produced P=0.0 threshold | LOW | Revert threshold to `1.1` (never fires), build fixture with labelled examples, rerun `calibrate.py --flag-type <check>`. No code change needed. |
| Trace buffer never flushed (flush-on-idle not implemented) | LOW | One-line change to main.py: move ready_trace_ids block to also run on the `result is None` BRPOP path. Restart worker. Unflushed in-memory traces are lost on restart. |
| `span_scores` rejects None span_id from trace checks | MEDIUM | Add migration to make `span_scores.span_id` nullable, or create `trace_scores` table. Re-run affected traces (or accept historical gap in calibration data). |
| G1/G2 flooding dashboard with structural false positives | LOW | Add multi-span prerequisite gate (minimum N spans with tool use) as a guard in the check method. No migration required. Existing false-positive flags remain but new ones stop. |
| F-check precision below floor after calibration | MEDIUM | Demote the check to `confidence: "low"` in Flag.detail and add filtering to the dashboard. If precision is below 0.50, deactivate by setting threshold=1.1 until SDK emits the required metadata. |
| TraceAnalyzer accidentally added to ANALYZERS list | LOW | Remove from ANALYZERS list, confirm it is only referenced as the separate `trace_analyzer` variable in main(). Restart worker. No DB change required. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Sparse fixture / calibration harness not extended | Phase defining check specs (before any implementation) | Run `calibrate.py --flag-type <new_check>` before implementing; confirm "zero positives" error is raised explicitly rather than silently producing P=0 |
| Trace flush not firing on idle | Phase implementing first trace-level check (C3 or C4) | Integration test: send trace, wait 35s with no new spans, assert flags written without any follow-up span |
| Trace scores not persisted (buffer leak) | Phase implementing first trace-level check | Assert `len(trace_analyzer._scores) == 0` after flush; assert rows appear in span_scores with `analyzer_name='trace_analyzer'` |
| Second span analyzer doubles embedder calls | Phase appending second class to ANALYZERS | Embedder logs: no duplicate `POST /encode` with identical payloads within a single span's processing |
| F-check proxy signal undocumented | Phase defining F-check specifications | PR review gate: check method docstring must contain proxy signal and false-positive mode paragraph |
| G1/G2 fires on all single-step traces | Phase implementing G1/G2 | Test: single-tool-call trace produces zero G1/G2 flags |
| Hill-climb degenerate P=1.0 R=0.0 | Phase running first v1.5 calibration | Add recall floor assertion to calibrate.py before any new check calibration runs |
| TraceAnalyzer in ANALYZERS (wrong dispatch) | Phase adding any new analyzer | Runtime assertion at worker startup: `all(isinstance(a, BaseSpanAnalyzer) for a in analyzers)` |

---

## Sources

- Direct inspection: `xeter/services/worker/main.py`, `base.py`, `tool_call_analyzer.py`, `trace_analyzer.py`, `flag_writer.py`, `score_writer.py`, `span_fetcher.py`, `xeter/scripts/calibrate.py`
- Domain taxonomy: `documentation/silent_failures_ai_agents.md` (IBM arXiv 2511.04032, Berkeley MAST NeurIPS 2025, Microsoft AI Red Team Whitepaper 2025)
- Project history: `.planning/PROJECT.md` — Key Decisions log (v1.0-v1.4), established constraints (false positives erode trust, fixture-first calibration, three-branch wrong_tool logic)

---
*Pitfalls research for: Xeter v1.5 Silent Failure Detection — adding B1-B4, C3-C4, D1-D3, D5, E3, F1-F2, F4-F5, G1-G2, H2 analyser checks*
*Researched: 2026-05-18*
