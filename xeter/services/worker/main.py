"""Embedding Worker core module.

BRPOP loop that consumes span_ids from the Redis ``analysis_queue``, fetches
each span from ClickHouse + S3, dispatches it to every registered analyzer in
ANALYZERS, writes similarity scores to PostgreSQL for every span (calibration
dataset), and writes flags to PostgreSQL only for spans where at least one
analyzer returned a Flag.

Extensibility: to add a new analyzer, import it and append it to the ANALYZERS
list built inside ``main()`` — nothing else changes. The ``process_span()``
function iterates over whatever list it receives, so the registry is open for
extension at zero modification cost.

Environment variables:
  REDIS_URL                         — Redis connection URL (required)
  DATABASE_URL                      — PostgreSQL DSN (required by writers)
  CLICKHOUSE_HOST                   — ClickHouse host (default: "clickhouse")
  S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET
                                    — MinIO/S3 credentials (required by fetcher)
  WORKER_THRESHOLD_WRONG_TOOL_CALLED — cosine threshold, default 0.5
  WORKER_THRESHOLD_WRONG_TOOL_ARGS  — grounding threshold, default 0.4
  WORKER_THRESHOLD_NO_TOOL          — cosine threshold, default 0.6
  WORKER_THRESHOLD_EXCESSIVE_TOOL   — cosine threshold, default 0.3
  WORKER_THRESHOLD_PARSING_ERROR    — cosine threshold, default 0.5
  WORKER_THRESHOLD_RESPONSE_ANOMALY — cosine threshold, default 0.4
  WORKER_TRACE_FLUSH_TIMEOUT_S      — seconds of inactivity before a trace is
                                      flushed to TraceAnalyzer (default: 30).
                                      Tune based on expected inter-span latency.
"""

from __future__ import annotations

import logging
import os
import signal
import time

import redis

from xeter.services.worker.base import EmbedderClient, SpanData
from xeter.services.worker.flag_writer import write_flags
from xeter.services.worker.score_writer import write_scores
from xeter.services.worker.span_fetcher import fetch_span
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer
from xeter.services.worker.trace_analyzer import TraceAnalyzer

logger = logging.getLogger(__name__)

QUEUE_KEY = "analysis_queue"
BRPOP_TIMEOUT = 2  # seconds — allows SIGTERM response within ~2 s

THRESHOLDS: dict[str, float] = {
    "tool_coherence_threshold": float(os.environ.get("WORKER_THRESHOLD_TOOL_COHERENCE", "0.15")),  # [safe-default] calibration value; tune via calibration scripts
    "unnecessary_tool_call": float(os.environ.get("WORKER_THRESHOLD_UNNECESSARY_TOOL_CALL", "0.15")),  # [safe-default] calibration value; tune via calibration scripts
    "wrong_tool_args": float(os.environ.get("WORKER_THRESHOLD_WRONG_TOOL_ARGS", "0.4")),  # [safe-default] calibration value; tune via calibration scripts
    "no_tool": float(os.environ.get("WORKER_THRESHOLD_NO_TOOL", "0.6")),  # [safe-default] calibration value; tune via calibration scripts
    "response_anomaly": float(os.environ.get("WORKER_THRESHOLD_RESPONSE_ANOMALY", "0.4")),  # [safe-default] calibration value; tune via calibration scripts
}

WORKER_TRACE_FLUSH_TIMEOUT_S: float = float(
    os.environ.get("WORKER_TRACE_FLUSH_TIMEOUT_S", "30")  # [safe-default] 30s window; tune for your trace latency
)

# ---- signal handling --------------------------------------------------------

running = True  # module-level flag; mutated by _handle_signal


def _handle_signal(signum, frame) -> None:  # noqa: ANN001
    """Set running=False so the BRPOP loop exits cleanly on SIGTERM/SIGINT."""
    global running
    running = False


# ---- span dispatch ----------------------------------------------------------


def process_span(span_id: str, analyzers: list) -> SpanData:
    """Fetch a span and dispatch it to all registered analyzers.

    Designed to accept an ``analyzers`` parameter (not a global) so integration
    tests can inject mock analyzers without monkeypatching module globals.

    All similarity scores are written for every span regardless of flag outcome —
    they form the calibration dataset used in Phase 6. Flag rows are written only
    when at least one Flag was returned.

    Args:
        span_id:   The span_id consumed from the Redis queue.
        analyzers: List of BaseAnalyzer instances to dispatch.

    Returns:
        The SpanData fetched for this span_id, for use by the trace buffer.

    Raises:
        ValueError: If the span does not exist in ClickHouse (fetch_span raises).
        Exception:  Any writer error is re-raised after logging; the caller
                    (BRPOP loop) handles log-and-skip at the span level.
    """
    span = fetch_span(span_id)

    all_flags: list = []
    all_scores: list = []

    for analyzer in analyzers:
        flags = analyzer.analyze(span)
        scores = analyzer.flush_scores()
        all_flags.extend(flags)
        all_scores.extend(scores)

    write_scores(span_id, span.tenant_id, all_scores)

    if all_flags:
        write_flags(span_id, span.tenant_id, span.trace_id, all_flags)

    return span


def _flush_stale_traces(
    trace_buffer: dict,
    trace_last_seen: dict,
    trace_analyzer,
) -> None:
    """Flush stale traces from the buffer to TraceAnalyzer.

    Args:
        trace_buffer:    dict mapping trace_id to list[SpanData] — the accumulated
                         spans for each in-flight trace.
        trace_last_seen: dict mapping trace_id to last-seen monotonic time — used
                         to determine whether the trace has exceeded the flush timeout.
        trace_analyzer:  TraceAnalyzer instance — receives the accumulated spans for
                         analysis once the trace is ready to flush.

    Returns:
        None.  Mutates both dicts in place (entries are removed after flush).
    """
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
            trace_scores = trace_analyzer.flush_scores()           # INFRA-02 fix
            write_scores(None, tenant_id_for_trace, trace_scores)  # INFRA-02 fix
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


# ---- entry point ------------------------------------------------------------


def main() -> None:
    """Worker main loop: load model, build analyzer registry, run BRPOP loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    embedder_url = os.environ.get("EMBEDDER_URL", "http://embedder:8002")  # [safe-default] docker-compose value
    logger.info("worker: connecting to embedder at %s", embedder_url)
    embedder = EmbedderClient(embedder_url)
    logger.info("worker: embedder client ready")

    analyzers = [ToolCallAnalyzer(embedder, THRESHOLDS)]

    trace_analyzer = TraceAnalyzer(embedder, THRESHOLDS)

    # Trace buffer: accumulate processed spans by trace_id for trace-level analysis.
    # trace_last_seen tracks time.monotonic() of the last span arrival per trace.
    trace_buffer: dict[str, list] = {}       # trace_id -> list[SpanData]
    trace_last_seen: dict[str, float] = {}   # trace_id -> last arrival time

    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("worker: starting BRPOP loop on queue=%s", QUEUE_KEY)

    while running:
        result = r.brpop(QUEUE_KEY, timeout=BRPOP_TIMEOUT)
        if result is None:
            _flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)
            continue
        _, span_id = result
        # Retry up to 3 times with backoff — the batcher may not have
        # flushed the span to ClickHouse yet when Redis delivers the id.
        for attempt in range(3):
            try:
                span = process_span(span_id, analyzers)
                logger.info("worker: processed span_id=%s", span_id)

                # Accumulate span in trace buffer
                trace_buffer.setdefault(span.trace_id, []).append(span)
                trace_last_seen[span.trace_id] = time.monotonic()

                _flush_stale_traces(trace_buffer, trace_last_seen, trace_analyzer)

                break
            except ValueError as exc:
                # "span not found" — likely batcher hasn't flushed yet
                if attempt < 2:
                    wait = (attempt + 1) * 5
                    logger.warning("worker: span %s not found (attempt %d/3), retrying in %ds", span_id, attempt + 1, wait)
                    time.sleep(wait)
                else:
                    logger.error("worker: failed to process span %s after 3 attempts: %s", span_id, exc)
            except Exception as exc:
                logger.error("worker: failed to process span %s: %s", span_id, exc)
                break

    logger.info("worker: shutdown complete")


if __name__ == "__main__":
    main()
