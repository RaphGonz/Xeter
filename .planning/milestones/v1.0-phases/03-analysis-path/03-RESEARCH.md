# Phase 3: Analysis Path - Research

**Researched:** 2026-03-28
**Domain:** Embedding-based anomaly detection worker — sentence-transformers, Redis BLPOP, PostgreSQL score storage
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Extensibility pattern:** `BaseAnalyzer` is the template — `embed()`, `compare()`, `log_score()` helpers; subclasses override `analyze(span) → list[Flag]`. ANALYZERS list in `worker/main.py` is the registry.
- **ToolCallAnalyzer structure:** One class, multiple private methods: `_check_wrong_tool()`, `_check_no_tool()`, `_check_excessive_tool()`, `_check_parsing_error()`, `_check_wrong_args()` — all called from `analyze()`.
- **Embedding provider:** sentence-transformers, local, model `all-MiniLM-L6-v2` (384-dim, ~80MB). Loaded once at worker startup and kept in memory.
- **Base class API:** `embed(text)` and `compare(a, b)` exposed to subclasses as helpers.
- **Tool embedding cache:** In-memory dict keyed by content hash of `available_tools` JSON to avoid re-embedding identical tool lists across spans.
- **Score storage:** `span_scores` table in PostgreSQL — `(span_id, analyzer_name, metric_name, score)`, one row per metric, every span (flagged or not).
- **Flags table:** Existing PostgreSQL `flags` table from Phase 1 — `flag_type` is VARCHAR.
- **Worker architecture:** Separate Docker service, BLPOP loop from Redis, log-and-skip on failure.

### Claude's Discretion

- Exact Flag dataclass/namedtuple structure returned by `analyze()`
- BLPOP timeout value
- Exact column names and indexes on `span_scores` table
- How worker startup/shutdown is handled (signal handling, graceful drain)

### Deferred Ideas (OUT OF SCOPE)

- OutputAnalyzer (B1–B4) — future phase
- ReasoningAnalyzer (C1–C5) — future phase
- ContextAnalyzer (D1–D5), InstructionAnalyzer (E1–E3), MultiAgentAnalyzer (F1–F6), VerificationAnalyzer (G1–G3), OutputContentAnalyzer (H1–H3) — future phases
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FLAG-01 | Analyzer registry pattern — analyzers register independently, pipeline dispatches to all | ANALYZERS list + BaseAnalyzer pattern; simple list dispatch in worker main loop |
| FLAG-02 | Each analyzer defines its own flag types, scoring logic, and thresholds via common interface | BaseAnalyzer ABC with `analyze(span) → list[Flag]` + configurable threshold dict |
| FLAG-03 | `flag_type` field in PostgreSQL is an open string (not enum) | Already enforced in 001_initial.py migration — VARCHAR, confirmed |
| FLAG-04 | Vector similarity between prompt and tool_name to detect wrong tool usage | sentence-transformers `embed()` + `compare()` pattern |
| FLAG-05 | Vector similarity between prompt and tool_description to detect semantic mismatch | Same `embed()` + `compare()` — additional metric in `_check_wrong_tool()` |
| FLAG-06 | Vector similarity between prompt and response to detect response anomalies | Same pattern — included in `_check_wrong_tool()` scoring |
| FLAG-07 | Embedding of model_name + prompt to detect parsing error patterns | Concatenate model_name + prompt string before embed; `_check_parsing_error()` |
| FLAG-08 | Classifies anomalies into: wrong_tool, wrong_tool_args, no_tool, excessive_tool, parsing_error | Five private `_check_*` methods, each returns `list[Flag]` |
| FLAG-09 | Similarity thresholds configurable per analyzer, not hardcoded | Config dict passed to analyzer constructor; read from env or config file |
| FLAG-10 | All similarity scores logged for every span (flagged or not) | `self.log_score()` called inside every `_check_*` method before threshold test |
| FLAG-11 | Embed prompt against each tool in `available_tools` (from S3); flag `wrong_tool` if called tool not top-ranked | S3 fetch pattern exists in s3.py; embed all tools, rank by cosine, compare called tool |
| FLAG-12 | Embed prompt against `tool_arguments` values; flag `wrong_tool_args` if inconsistent (low-confidence) | `_check_wrong_args()` — embed prompt vs argument values; low-confidence flag in detail |
| STOR-03 | Flags stored as append-only rows in PostgreSQL with span_id, flag_type, score, detail | `flags` table exists from Phase 1; new Alembic migration for `span_scores` table |
</phase_requirements>

---

## Summary

Phase 3 builds the Embedding Worker: a standalone Python process that reads span IDs from Redis via a synchronous BLPOP loop, fetches the span from ClickHouse, retrieves large payloads from S3 (specifically `available_tools`), computes cosine similarities using a locally loaded sentence-transformers model, writes scores to PostgreSQL for every span, and writes flag rows only for spans that breach thresholds.

The worker is synchronous (not asyncio-based). sentence-transformers and ClickHouse's synchronous `clickhouse-connect` client work naturally in a blocking loop. The PostgreSQL writes use `psycopg2` directly (or SQLAlchemy sync engine) to avoid running an event loop inside a synchronous worker — the existing `asyncpg`-based `get_async_engine()` is for async services only. A key architectural decision from CONTEXT.md is that BLPOP uses a short timeout (e.g., 2 seconds) so the running flag can be checked between polls, enabling clean SIGTERM handling.

The two new PostgreSQL objects this phase creates are: (1) a new Alembic migration adding the `span_scores` table, and (2) direct INSERTs into the existing `flags` table. The `span_scores` table is not RLS-protected (worker writes bypass RLS; the table is internal, not tenant-queryable in Phase 3) — this is a discretionary call that avoids complexity. All similarity thresholds are read from environment variables or a config dict at startup, never hardcoded.

**Primary recommendation:** Build a synchronous worker service under `services/worker/` with its own Dockerfile, entry point, and `xeter/services/worker/` module package. Sentence-transformers is loaded in `worker/main.py` startup, passed into each analyzer constructor. The BLPOP loop with a 2-second timeout and a `running` flag set by a SIGTERM handler is the correct graceful-shutdown pattern.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sentence-transformers | 5.3.0 (latest as of 2026-03-28) | Local embedding model, cosine similarity | Locked by user decision; all-MiniLM-L6-v2 is the de facto lightweight embedding model |
| redis (sync client) | already in pyproject.toml | Synchronous BLPOP loop | Worker is synchronous; `redis.asyncio` is for async services — use `redis.Redis` not `redis.asyncio.Redis` |
| psycopg2-binary | 2.9.x | Synchronous PostgreSQL writes from worker | asyncpg requires an event loop; worker is synchronous; psycopg2 is the standard sync driver |
| clickhouse-connect | 0.15.0 (already in pyproject.toml) | Read span rows from ClickHouse | Already used in analyser — reuse same client factory |
| aioboto3 / boto3 | boto3 for sync use | Fetch `available_tools` JSON from S3 | Existing aioboto3 session in analyser is async; worker should use `boto3` (sync) for simplicity |
| SQLAlchemy (sync) | 2.0.48 (already in pyproject.toml) | Optional ORM layer for span_scores insert | Can use raw psycopg2 or SQLAlchemy Core with sync engine |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| torch | >=1.11.0 (sentence-transformers dep) | tensor operations underlying ST | Installed automatically as sentence-transformers dependency |
| transformers | >=4.34.0 (sentence-transformers dep) | Model loading | Installed automatically |
| numpy | (sentence-transformers dep) | Embedding arrays | Used for cosine similarity when not using model.similarity() |
| hashlib | stdlib | Content hash for tool embedding cache | `hashlib.sha256(json.encode()).hexdigest()` as dict key |
| signal | stdlib | SIGTERM handler for graceful shutdown | Set `running = False` on SIGTERM, BLPOP timeout allows loop to exit |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sentence-transformers (local) | OpenAI embeddings API | Network call, API key, cost, offline risk — user locked local |
| psycopg2 (sync writes) | asyncio + asyncpg in an event loop | asyncio event loop inside a sync worker is over-engineered; psycopg2 is simpler |
| boto3 (sync S3 fetch) | aioboto3 (async) | Worker is sync; using aioboto3 requires asyncio.run() per call — boto3 is cleaner |
| BLPOP with timeout | asyncio BRPOP | Worker is intentionally synchronous; no async needed for this loop |

**Installation (additions to `xeter/pyproject.toml`):**
```bash
# Add to pyproject.toml dependencies:
sentence-transformers>=5.0.0
psycopg2-binary>=2.9.0
boto3>=1.35.0
```

---

## Architecture Patterns

### Recommended Project Structure

```
services/worker/
├── Dockerfile               # Python 3.12-slim, installs xeter + sentence-transformers
├── __init__.py
└── main.py                  # Entry point: load model, start BLPOP loop

xeter/services/worker/
├── __init__.py
├── main.py                  # BLPOP loop, ANALYZERS registry, span fetch, dispatch
├── base.py                  # BaseAnalyzer ABC: embed(), compare(), log_score(), analyze()
├── tool_call_analyzer.py    # ToolCallAnalyzer: _check_wrong_tool(), etc.
├── span_fetcher.py          # Fetch span row from ClickHouse + available_tools from S3
├── score_writer.py          # INSERT into span_scores table (psycopg2 / SQLAlchemy sync)
└── flag_writer.py           # INSERT into flags table (psycopg2 / SQLAlchemy sync)

xeter/tests/worker/
├── __init__.py
├── test_base_analyzer.py    # Unit tests for BaseAnalyzer helpers
├── test_tool_call_analyzer.py  # Unit tests for each _check_* method
└── test_worker_loop.py      # Integration test: mock Redis + span → flag in PostgreSQL

xeter/migrations/versions/
└── 002_span_scores.py       # Alembic migration: CREATE TABLE span_scores
```

### Pattern 1: BaseAnalyzer ABC

**What:** Abstract base class providing `embed()`, `compare()`, `log_score()` helpers. Subclasses must implement `analyze(span) -> list[Flag]`.
**When to use:** Every analyzer — ToolCallAnalyzer and all future analyzers.

```python
# Source: project design (CONTEXT.md) — no external library required
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import numpy as np

@dataclass
class Flag:
    flag_type: str          # "wrong_tool", "no_tool", etc.
    score: float            # Similarity score that triggered the flag
    detail: dict[str, Any]  # Structured detail for dashboard

@dataclass
class SpanData:
    span_id: str
    tenant_id: str
    trace_id: str
    tool_name: str | None
    tool_description: str | None
    tool_arguments: str | None
    tool_output: str | None
    prompt: str | None       # fetched from S3
    response: str | None     # fetched from S3
    available_tools: list[dict] | None  # fetched from S3, parsed JSON

class BaseAnalyzer(ABC):
    def __init__(self, model, thresholds: dict[str, float]):
        self._model = model
        self._thresholds = thresholds
        self._scores: list[tuple[str, str, float]] = []  # (analyzer_name, metric_name, score)

    def embed(self, text: str) -> np.ndarray:
        return self._model.encode(text)

    def compare(self, a: np.ndarray, b: np.ndarray) -> float:
        # Returns scalar cosine similarity in [-1, 1]
        similarity = self._model.similarity(a.reshape(1, -1), b.reshape(1, -1))
        return float(similarity[0][0])

    def log_score(self, metric_name: str, score: float) -> None:
        self._scores.append((self.name, metric_name, score))

    def flush_scores(self) -> list[tuple[str, str, float]]:
        scores = list(self._scores)
        self._scores.clear()
        return scores

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def analyze(self, span: SpanData) -> list[Flag]: ...
```

### Pattern 2: BLPOP Worker Loop with Graceful Shutdown

**What:** Synchronous Redis BLPOP loop with a `running` flag set by SIGTERM/SIGINT handler. BLPOP timeout (2 seconds) ensures the loop checks the flag between polls.
**When to use:** The only worker loop — `xeter/services/worker/main.py`.

```python
# Source: Redis BLPOP docs + Python signal stdlib
import signal
import redis

QUEUE_KEY = "analysis_queue"
BLPOP_TIMEOUT = 2  # seconds — allows SIGTERM response within 2s

running = True

def _handle_signal(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

while running:
    result = r.blpop(QUEUE_KEY, timeout=BLPOP_TIMEOUT)
    if result is None:
        continue  # timeout expired, check running flag
    _, span_id = result  # result is (key_name, value)
    try:
        process_span(span_id)
    except Exception as exc:
        logger.error("worker: failed to process span %s: %s", span_id, exc)
        # log-and-skip: continue loop, no retry, no dead-letter queue

logger.info("worker: shutdown complete")
```

### Pattern 3: Tool Embedding Cache by Content Hash

**What:** In-memory dict mapping `sha256(available_tools_json)` → `list[np.ndarray]`. Avoids re-embedding identical tool lists across spans.
**When to use:** Inside `ToolCallAnalyzer` — populated lazily on first encounter of each unique tool list.

```python
# Source: project design (CONTEXT.md)
import hashlib
import json

class ToolCallAnalyzer(BaseAnalyzer):
    def __init__(self, model, thresholds):
        super().__init__(model, thresholds)
        self._tool_embed_cache: dict[str, list[np.ndarray]] = {}

    def _get_tool_embeddings(self, available_tools: list[dict]) -> list[np.ndarray]:
        tools_json = json.dumps(available_tools, sort_keys=True)
        cache_key = hashlib.sha256(tools_json.encode()).hexdigest()
        if cache_key not in self._tool_embed_cache:
            self._tool_embed_cache[cache_key] = [
                self.embed(f"{t.get('name', '')} {t.get('description', '')}")
                for t in available_tools
            ]
        return self._tool_embed_cache[cache_key]
```

### Pattern 4: ANALYZERS Registry Dispatch

**What:** A flat list in `worker/main.py`. The loop iterates over all analyzers, collects flags and scores, then writes to PostgreSQL.
**When to use:** Only registry location — never modify analyzers to know about other analyzers.

```python
# Source: project design (CONTEXT.md)
ANALYZERS = [ToolCallAnalyzer(model, config["thresholds"]["tool_call"])]

def process_span(span_id: str) -> None:
    span = fetch_span(span_id)            # ClickHouse + S3
    all_flags = []
    all_scores = []
    for analyzer in ANALYZERS:
        flags = analyzer.analyze(span)
        scores = analyzer.flush_scores()
        all_flags.extend(flags)
        all_scores.extend(scores)
    write_scores(span_id, span.tenant_id, all_scores)
    if all_flags:
        write_flags(span_id, span.tenant_id, span.trace_id, all_flags)
```

### Pattern 5: span_scores Table Schema

**What:** New PostgreSQL table for calibration data. One row per metric per span.
**When to use:** `score_writer.py` INSERTs here for every processed span regardless of flag outcome.

```sql
-- Source: CONTEXT.md decision + project conventions
CREATE TABLE span_scores (
    score_id      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    span_id       TEXT NOT NULL,
    tenant_id     UUID NOT NULL,
    analyzer_name TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    score         FLOAT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ix_span_scores_span ON span_scores (span_id);
CREATE INDEX ix_span_scores_tenant ON span_scores (tenant_id, analyzer_name);
```

Note: No RLS on `span_scores` in Phase 3 — the worker writes as a privileged internal service using `DATABASE_URL` (superuser/BYPASSRLS). The Phase 4 read path will add RLS or filtering when exposing scores to the dashboard.

### Anti-Patterns to Avoid

- **Async event loop inside the worker:** Do not use `asyncio.run()` to call `asyncpg` or `aioboto3` from within the BLPOP loop. Use `psycopg2` (sync) and `boto3` (sync). Running `asyncio.run()` inside a tight loop is wasteful and error-prone.
- **Hardcoded thresholds:** Never put a numeric threshold literal in `_check_*` methods. All thresholds are read from `self._thresholds[metric_name]` at call time.
- **Embedding at query time (not cache-hit):** If the tool list is identical across many spans, re-embedding is wasted CPU. Always hit the cache first.
- **Raising inside the BLPOP loop:** An unhandled exception in `process_span()` must be caught and logged; the loop must continue. The user decision is explicit: log-and-skip, no retry.
- **Using redis.asyncio.Redis in the worker:** The worker uses `redis.Redis` (sync), not `redis.asyncio.Redis`. The analyser uses the async client; the worker must not.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity | Custom numpy dot-product formula | `model.similarity(a, b)` or `util.cos_sim(a, b)` from sentence-transformers | Handles normalization, dtype, shape edge cases; model.similarity is the documented API |
| Sentence encoding | Custom tokenization loop | `model.encode(text)` | Handles batching, padding, truncation, device placement |
| Model download/cache | Manual HTTP download | sentence-transformers auto-caches to `~/.cache/torch/` on first load | Built-in caching; model loads from cache on subsequent starts |
| PostgreSQL upsert | Custom "check then insert" | `INSERT ... ON CONFLICT DO NOTHING` via SQLAlchemy `on_conflict_do_nothing()` | Atomic; avoids race conditions |
| Content hashing | Manual string comparison of tool lists | `hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()` | Deterministic, collision-resistant, fast |

**Key insight:** sentence-transformers handles all the ML complexity. The worker's job is orchestration (fetch → embed → compare → threshold → write), not ML engineering.

---

## Common Pitfalls

### Pitfall 1: Model Loading Time at First Request

**What goes wrong:** sentence-transformers downloads the ~80MB all-MiniLM-L6-v2 model on first use if not cached. In Docker, the cache directory is inside the container and lost on rebuild.
**Why it happens:** Default model cache is `~/.cache/huggingface/` inside the container filesystem.
**How to avoid:** Pre-download the model in the Dockerfile with `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` — this bakes the model into the image layer, avoiding runtime download.
**Warning signs:** Worker takes 30-60 seconds to process first span; CI test failures due to network access.

### Pitfall 2: BLPOP With No Timeout Cannot Be Interrupted

**What goes wrong:** `r.blpop(key, timeout=0)` blocks indefinitely. Docker `stop` sends SIGTERM, waits 10 seconds (default), then sends SIGKILL. If BLPOP is blocking, the signal handler cannot run until BLPOP returns.
**Why it happens:** Python signal handlers only execute between bytecodes — a blocking C-extension call (socket recv) does not yield.
**How to avoid:** Use `timeout=2` in BLPOP. The loop wakes every 2 seconds at worst to check the `running` flag. On SIGTERM, the worker finishes the current span and exits within ~2 seconds.
**Warning signs:** `docker stop` takes the full 10-second timeout before the container exits.

### Pitfall 3: Worker Service Cannot Find xeter Package

**What goes wrong:** `xeter/services/worker/` imports `from xeter.shared.db.postgres import ...` but the worker Dockerfile does not install the `xeter` package.
**Why it happens:** The analyser Dockerfile is similarly minimal — it installs only fastapi and uvicorn. The worker Dockerfile must `pip install -e .` or `COPY xeter/ xeter/` and set `PYTHONPATH`.
**How to avoid:** Worker Dockerfile must `COPY xeter/ xeter/` and `RUN pip install -e xeter/` (or use the monorepo install). Pattern matches Phase 2 Dockerfile approach.
**Warning signs:** `ModuleNotFoundError: No module named 'xeter'` on worker startup.

### Pitfall 4: RLS Blocks Worker PostgreSQL Writes

**What goes wrong:** Worker tries to INSERT into `span_scores` or `flags` but gets blocked by RLS because `app.current_tenant_id` is not set.
**Why it happens:** RLS is enabled on `flags`. Worker does not go through the DAL's `tenant_session()` pattern.
**How to avoid:** Two options — (1) use a DATABASE_URL that connects as the BYPASSRLS role (same role as migrations), or (2) call `SET LOCAL app.current_tenant_id = <tenant_id>` before each INSERT in the worker. Option (1) is simpler for a privileged internal service. `span_scores` has no RLS so it is fine. For `flags`, use the `tenant_session()` helper or connect as BYPASSRLS.
**Warning signs:** `ERROR: new row violates row-level security policy for table "flags"`.

### Pitfall 5: available_tools JSON Shape Assumptions

**What goes wrong:** `available_tools` is stored in S3 as `{"value": <original_string>}` (per s3.py pattern). The value itself is a JSON string that must be parsed again to get `list[dict]`.
**Why it happens:** The S3 upload pattern wraps the value: `json.dumps({"value": field_value})`. The worker must unwrap: `json.loads(s3_body)["value"]` then `json.loads(available_tools_string)`.
**How to avoid:** In `span_fetcher.py`, double-decode: first parse the S3 JSON wrapper, then parse the inner available_tools string. Assert the result is a list before embedding.
**Warning signs:** `TypeError: string indices must be integers` when iterating tools; `AttributeError: 'str' object has no attribute 'get'`.

### Pitfall 6: Numpy Array Shape Mismatch in compare()

**What goes wrong:** `model.similarity(a, b)` expects 2D arrays `[n, d]`. A single-sentence encode returns shape `(d,)` — calling similarity on two 1D arrays may raise a shape error.
**Why it happens:** `model.encode("text")` returns shape `(384,)`. `model.similarity` expects `(1, 384)`.
**How to avoid:** In `BaseAnalyzer.compare()`, always reshape: `a.reshape(1, -1)` and `b.reshape(1, -1)`. Return `float(similarity[0][0])`.
**Warning signs:** `ValueError: Expected 2D array, got 1D array`.

---

## Code Examples

Verified patterns from official sources:

### Loading model once at startup

```python
# Source: https://sbert.net/docs/quickstart.html
from sentence_transformers import SentenceTransformer

# Load once — subsequent uses hit the in-process cache
model = SentenceTransformer("all-MiniLM-L6-v2")
```

### Encoding text and computing cosine similarity

```python
# Source: https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html
import numpy as np

embedding_a = model.encode("send email to Alice")          # shape (384,)
embedding_b = model.encode("email_sender tool")            # shape (384,)

# Reshape for similarity() API
similarity = model.similarity(
    embedding_a.reshape(1, -1),
    embedding_b.reshape(1, -1)
)
score = float(similarity[0][0])  # scalar in [-1, 1]
```

### BLPOP synchronous call pattern

```python
# Source: https://redis.io/docs/latest/commands/blpop/
# redis-py: result is (key_bytes, value_bytes) or None on timeout
result = r.blpop("analysis_queue", timeout=2)
if result is not None:
    _, span_id = result  # decode_responses=True gives strings
```

### Alembic migration for span_scores

```python
# Source: project conventions (001_initial.py pattern)
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

def upgrade() -> None:
    op.create_table(
        "span_scores",
        sa.Column("score_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analyzer_name", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("score_id"),
    )
    op.create_index("ix_span_scores_span", "span_scores", ["span_id"])
    op.create_index("ix_span_scores_tenant", "span_scores", ["tenant_id", "analyzer_name"])
```

### Fetching available_tools from S3 (double-decode pattern)

```python
# Source: inferred from s3.py upload pattern — {"value": <original_string>}
import boto3, json

s3 = boto3.client("s3", endpoint_url=..., ...)
obj = s3.get_object(Bucket="xeter-payloads", Key=available_tools_ref)
wrapper = json.loads(obj["Body"].read())        # {"value": "[{...}]"}
tools_string = wrapper["value"]                 # original JSON string
available_tools = json.loads(tools_string) if tools_string else []
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `util.cos_sim()` (from sentence_transformers) | `model.similarity()` method | sentence-transformers v3.x | Cleaner API; model.similarity is now the documented primary method |
| Manual SIGTERM loop checking | signal handler + `running` flag + BLPOP timeout | Established pattern | Standard; no library needed |
| Redis BRPOP (right pop) | BLPOP is fine — queue uses LPUSH + BRPOP or LPUSH + BLPOP | Both work | queue.py uses LPUSH; worker uses BLPOP (left pop) — note: the existing queue.py docstring says "BRPOP" but the code uses LPUSH and the worker should use BRPOP for FIFO. See Open Questions. |

**Deprecated/outdated:**
- `asyncio.get_event_loop()`: replaced by `asyncio.run()` — but worker is synchronous so neither is needed.
- `passlib.CryptContext`: not relevant here, but noted from Phase 1 that bcrypt is used directly.

---

## Open Questions

1. **BLPOP vs BRPOP — queue directionality**
   - What we know: `queue.py` uses `LPUSH` (push to left/head). The docstring says "BRPOP (right-pop) gives FIFO order." BLPOP pops from the left (head); BRPOP pops from the right (tail).
   - What's unclear: The worker should use BRPOP (not BLPOP) to get FIFO order per the queue.py docstring. The CONTEXT.md says "BLPOP loop" which technically pops from the left — same end as LPUSH, giving LIFO, not FIFO.
   - Recommendation: Use BRPOP in the worker to match the queue.py intention. Ordering matters minimally for anomaly detection (all spans will be processed), but FIFO is more debuggable. The planner should confirm: `r.brpop(QUEUE_KEY, timeout=2)`.

2. **span_scores RLS policy**
   - What we know: `flags` table has RLS. `span_scores` is new — user deferred RLS decision to Claude's Discretion.
   - What's unclear: Should `span_scores` have RLS? Phase 4 will query it per tenant.
   - Recommendation: Add RLS to `span_scores` in the migration (consistent with all other tables). The worker connects as BYPASSRLS via DATABASE_URL — same approach as migrations. This avoids a Phase 4 migration to add RLS retroactively.

3. **Threshold initial value**
   - What we know: No published benchmarks for agent tool-call cosine similarity exist (per STATE.md concern).
   - What's unclear: What numeric value should the default threshold be?
   - Recommendation: Default `0.5` for wrong_tool (conservative), `0.4` for wrong_tool_args (low-confidence per FLAG-12). Document these as hypothesis values requiring Phase 6 calibration. Read from `WORKER_THRESHOLD_WRONG_TOOL` and `WORKER_THRESHOLD_WRONG_ARGS` env vars.

4. **Worker Docker service naming**
   - What we know: docker-compose.yml has `analyser` and `presenter` services. No `worker` service exists yet.
   - What's unclear: Should the worker service be named `worker` or `embedding-worker`?
   - Recommendation: `worker` — short, unambiguous, consistent with `ANALYZERS` naming in code.

5. **ClickHouse span read for worker**
   - What we know: Worker needs to fetch a span row from ClickHouse by `span_id`. The existing `get_clickhouse_client()` is synchronous (clickhouse-connect is sync).
   - What's unclear: Is `span_id` indexed in ClickHouse? ClickHouse ORDER BY is `(tenant_id, trace_id, time_begin)` — `span_id` is not in the primary key.
   - Recommendation: Use `SELECT * FROM spans WHERE span_id = ?` with a full scan. This is acceptable for Phase 3 (low volume). Add a secondary index or use ClickHouse's lightweight index for `span_id` in Phase 6 if needed. Document this as a known performance limitation.

---

## Sources

### Primary (HIGH confidence)

- https://sbert.net/docs/quickstart.html — model loading and encode API verified
- https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html — model.similarity() API verified
- https://pypi.org/project/sentence-transformers/ — version 5.3.0 confirmed as of 2026-03-28
- https://redis.io/docs/latest/commands/blpop/ — BLPOP semantics, return value format, timeout behavior
- Project source files — queue.py, s3.py, ingest.py, shared/db/postgres.py, 001_initial.py, clickhouse.py all read directly

### Secondary (MEDIUM confidence)

- https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html — encode() returns numpy array, similarity() is 2D
- Python `signal` stdlib documentation — SIGTERM handler pattern with running flag
- SQLAlchemy PostgreSQL dialect docs — `on_conflict_do_nothing()` for span_scores idempotent insert

### Tertiary (LOW confidence)

- WebSearch: BLPOP graceful shutdown timeout=N pattern — multiple community sources agree on the timeout + running flag approach; confirmed against Redis official docs. Elevated to MEDIUM.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — sentence-transformers version verified via PyPI; Redis BLPOP verified via official Redis docs; existing project stack (psycopg2, clickhouse-connect) confirmed in source files
- Architecture: HIGH — patterns derived directly from CONTEXT.md locked decisions and existing codebase conventions
- Pitfalls: HIGH for model download, BLPOP timeout, RLS, S3 double-decode — all derived from existing code patterns. MEDIUM for numpy shape pitfall (training knowledge, consistent with official docs)

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (sentence-transformers moves fast but the 5.x API is stable; Redis BLPOP semantics are stable)
