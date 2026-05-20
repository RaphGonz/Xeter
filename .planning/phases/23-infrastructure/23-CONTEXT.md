# Phase 23: Infrastructure - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 23 delivers the infrastructure that every v1.5 check depends on. Phases 24–27 focus exclusively on new detection checks — no pipeline wiring, no calibration refactors, no SDK changes.

Four deliverables:
1. **Dependencies** — `jsonschema`, `tiktoken`, `rapidfuzz` added to worker environment
2. **calibrate.py multi-analyzer routing** — static registry routes `--flag-type` to the correct analyzer class; recall floor enforced in hill-climb
3. **`SpanData.expected_output_schema`** — full pipeline: SDK decorator param → Analyser ingest → ClickHouse column → `span_fetcher` → `SpanData`
4. **`SpanData.parent_span_id`** — `SpanData` dataclass field + `span_fetcher` update (ClickHouse already has this column)

</domain>

<decisions>
## Implementation Decisions

### expected_output_schema Pipeline
- **D-01:** Full pipeline in Phase 23. SDK decorator gets the param, Analyser ingest stores it, ClickHouse column added, span_fetcher fetches it, SpanData carries it. Phases 24+ touch none of this — they only write check logic.
- **D-02:** Decorator-level kwarg on `@xeter.trace()`. Same pattern as `tool_name`, `parent_span_id`. Usage: `@xeter.trace(..., expected_output_schema={"type": "object", "required": ["city"]})`. Sent in span dict, serialized to JSON string by SDK.
- **D-03:** Stored as `Nullable(String)` inline in ClickHouse — same pattern as `tool_arguments`. No S3 ref needed (small JSON schema, not a large payload).
- **D-04:** ClickHouse column added two ways: (a) update `SPANS_TABLE_DDL` in `clickhouse.py` for fresh deployments, (b) add idempotent `ALTER TABLE spans ADD COLUMN IF NOT EXISTS expected_output_schema Nullable(String)` call to the analyser startup lifespan sequence, immediately after `create_spans_table(client)`. No-op if column already exists.

### calibrate.py Multi-Analyzer Routing
- **D-05:** Static registry dict `FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type]` in `calibrate.py`. Same structural pattern as `FLAG_TYPE_ALIAS: dict[str, str]` already in the file.
- **D-06:** All existing flag types (`tool_not_available`, `wrong_tool_choice`, `unnecessary_tool_call`, `wrong_tool_args`, `no_tool`, `parsing_error`, `response_anomaly`) explicitly map to `ToolCallAnalyzer`. Zero behavior change for existing calibration runs.
- **D-07:** `evaluate_flag_type()` replaces the single hardcoded `ToolCallAnalyzer(embedder, thresholds)` line with a registry lookup: `analyzer_cls = FLAG_TYPE_TO_ANALYZER_CLASS[flag_type]; analyzer = analyzer_cls(embedder, thresholds)`.
- **D-08:** Recall floor enforcement (INFRA-03, from STATE.md): hill-climb rejects degenerate P=1.0, R=0.0 convergence. Any result where R < 0.10 causes `sys.exit(1)` with an explicit recall-floor error message. Checked after each hill-climb run before accepting the result.

### Dependencies
- **D-09:** `jsonschema`, `tiktoken`, `rapidfuzz` added to both `xeter/pyproject.toml` (under `dependencies`) and `services/worker/Dockerfile` (pip install line). Exact same dual-location pattern as `spacy`.

### parent_span_id
- **D-10:** ClickHouse column already exists. Analyser already stores it (`SPAN_COLUMNS` + `ingest.py` row). SDK already sends it (`SpanPayload`). Phase 23 scope is limited to: add `parent_span_id: Optional[str]` to `SpanData` dataclass + update `_FETCH_COLUMNS`, `_FETCH_QUERY`, and `SpanData(...)` constructor in `span_fetcher.py`. No ingest or SDK changes needed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core files to modify
- `xeter/services/worker/base.py` — `SpanData` dataclass; add `expected_output_schema: Optional[str]` and `parent_span_id: Optional[str]` fields
- `xeter/services/worker/span_fetcher.py` — `_FETCH_COLUMNS`, `_FETCH_QUERY`, and `SpanData(...)` constructor call; add both new fields
- `xeter/shared/db/clickhouse.py` — `SPANS_TABLE_DDL` (add `expected_output_schema Nullable(String)` column); add `alter_spans_add_expected_output_schema(client)` idempotent function
- `xeter/services/analyser/schemas.py` — `SpanPayload`; add `expected_output_schema: Optional[str] = None`
- `xeter/services/analyser/batch.py` — `SPAN_COLUMNS` list; insert `expected_output_schema` at the correct position (matches DDL column order)
- `xeter/services/analyser/ingest.py` — row construction list; add `span.expected_output_schema` at the matching position; guard `assert len(row) == len(SPAN_COLUMNS)` will catch drift
- `sdk/xeter_sdk/decorator.py` — `trace()` function signature; add `expected_output_schema: dict | None = None` kwarg; serialize to JSON string in `_dispatch()`; include in span dict
- `xeter/scripts/calibrate.py` — add `FLAG_TYPE_TO_ANALYZER_CLASS` registry; update `evaluate_flag_type()` to use it; add recall floor check after `hill_climb()` returns
- `xeter/pyproject.toml` — add `jsonschema`, `tiktoken`, `rapidfuzz` to `dependencies`
- `services/worker/Dockerfile` — add `jsonschema tiktoken rapidfuzz` to `pip install` line

### Key constraints (do not break)
- `xeter/services/analyser/ingest.py` line 131: `assert len(row) == len(SPAN_COLUMNS)` — the `SPAN_COLUMNS` list, the row construction, and the DDL column list must all stay in sync
- `calibrate.py` `FLAG_TYPES` and `BINARY_FLAG_TYPES` — existing entries must still route to `ToolCallAnalyzer` with no behavior change
- `SpanData` is a `@dataclass` — new fields must be `Optional` with `= None` default to not break existing construction sites (`build_span_data()` in `calibrate.py`, tests)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Patterns
- `FLAG_TYPE_ALIAS: dict[str, str]` in `calibrate.py` (line 58) — structural template for the new `FLAG_TYPE_TO_ANALYZER_CLASS: dict[str, type]`
- `parent_span_id: Optional[str] = None` in `SpanPayload` (schemas.py line 30) — exact pattern to follow for `expected_output_schema` in `SpanPayload`
- `tool_arguments: Optional[str]` in both `SpanData` and `SpanPayload` — inline JSON string pattern; `expected_output_schema` uses the same storage approach
- Analyser startup lifespan pattern: `create_spans_table(client)` is called at startup; `alter_spans_add_expected_output_schema(client)` slots in immediately after

### Integration Points
- `_FETCH_COLUMNS` (list) and `_FETCH_QUERY` (raw SQL string) in `span_fetcher.py` must be updated together — they define the same column set in two different representations
- `SPAN_COLUMNS` in `batch.py` and the row list in `ingest.py` must stay in sync — the `assert` guard enforces this at runtime but both must be updated in the same commit
- `build_span_data()` in `calibrate.py` constructs `SpanData` from fixture rows — must add `expected_output_schema=row.get("expected_output_schema")` and `parent_span_id=row.get("parent_span_id")` to avoid missing-arg errors after the dataclass is updated

### Current State of TraceAnalyzer
- `TraceAnalyzer` in `trace_analyzer.py` is a stub — `analyze()` returns `[]`. Phase 23 does NOT add trace-level checks or calibration routing for trace-level flag types. Trace calibration is Phase 27 scope.

</code_context>

<specifics>
## Specific Ideas

- User confirmed: `expected_output_schema` is decorator-level (not call-time). The schema describes what that decorated function's tool output should always look like — it does not vary per invocation.
- Recall floor: "a R < 0.10 result causes the run to fail with an explicit recall-floor error" (from STATE.md). Emit a clear human-readable message before `sys.exit(1)` so it's obvious in CI output.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 23-infrastructure*
*Context gathered: 2026-05-20*
