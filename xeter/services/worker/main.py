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
  WORKER_THRESHOLD_WRONG_TOOL       — cosine threshold, default 0.5
  WORKER_THRESHOLD_WRONG_ARGS       — cosine threshold, default 0.4
  WORKER_THRESHOLD_NO_TOOL          — cosine threshold, default 0.6
  WORKER_THRESHOLD_EXCESSIVE_TOOL   — cosine threshold, default 0.3
  WORKER_THRESHOLD_PARSING_ERROR    — cosine threshold, default 0.5
  WORKER_THRESHOLD_RESPONSE_ANOMALY — cosine threshold, default 0.4
"""

from __future__ import annotations

import logging
import os
import signal
import time

import redis

from xeter.services.worker.base import EmbedderClient
from xeter.services.worker.flag_writer import write_flags
from xeter.services.worker.score_writer import write_scores
from xeter.services.worker.span_fetcher import fetch_span
from xeter.services.worker.tool_call_analyzer import ToolCallAnalyzer

logger = logging.getLogger(__name__)

QUEUE_KEY = "analysis_queue"
BRPOP_TIMEOUT = 2  # seconds — allows SIGTERM response within ~2 s

THRESHOLDS: dict[str, float] = {
    "wrong_tool": float(os.environ.get("WORKER_THRESHOLD_WRONG_TOOL", "0.5")),
    "wrong_tool_args": float(os.environ.get("WORKER_THRESHOLD_WRONG_ARGS", "0.4")),
    "no_tool": float(os.environ.get("WORKER_THRESHOLD_NO_TOOL", "0.6")),
    "excessive_tool": float(os.environ.get("WORKER_THRESHOLD_EXCESSIVE_TOOL", "0.3")),
    "parsing_error": float(os.environ.get("WORKER_THRESHOLD_PARSING_ERROR", "0.5")),
    "response_anomaly": float(os.environ.get("WORKER_THRESHOLD_RESPONSE_ANOMALY", "0.4")),
}

# ---- signal handling --------------------------------------------------------

running = True  # module-level flag; mutated by _handle_signal


def _handle_signal(signum, frame) -> None:  # noqa: ANN001
    """Set running=False so the BRPOP loop exits cleanly on SIGTERM/SIGINT."""
    global running
    running = False


# ---- span dispatch ----------------------------------------------------------


def process_span(span_id: str, analyzers: list) -> None:
    """Fetch a span and dispatch it to all registered analyzers.

    Designed to accept an ``analyzers`` parameter (not a global) so integration
    tests can inject mock analyzers without monkeypatching module globals.

    All similarity scores are written for every span regardless of flag outcome —
    they form the calibration dataset used in Phase 6. Flag rows are written only
    when at least one Flag was returned.

    Args:
        span_id:   The span_id consumed from the Redis queue.
        analyzers: List of BaseAnalyzer instances to dispatch.

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


# ---- entry point ------------------------------------------------------------


def main() -> None:
    """Worker main loop: load model, build analyzer registry, run BRPOP loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    embedder_url = os.environ.get("EMBEDDER_URL", "http://embedder:8002")
    logger.info("worker: connecting to embedder at %s", embedder_url)
    embedder = EmbedderClient(embedder_url)
    logger.info("worker: embedder client ready")

    analyzers = [ToolCallAnalyzer(embedder, THRESHOLDS)]

    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("worker: starting BRPOP loop on queue=%s", QUEUE_KEY)

    while running:
        result = r.brpop(QUEUE_KEY, timeout=BRPOP_TIMEOUT)
        if result is None:
            continue
        _, span_id = result
        # Retry up to 3 times with backoff — the batcher may not have
        # flushed the span to ClickHouse yet when Redis delivers the id.
        for attempt in range(3):
            try:
                process_span(span_id, analyzers)
                logger.info("worker: processed span_id=%s", span_id)
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
