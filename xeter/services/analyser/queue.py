"""Redis queue operations for the Analyser.

Span IDs are pushed to the analysis queue after acceptance.
The Embedding Worker (Phase 3) consumes via BRPOP.

LPUSH + BRPOP gives FIFO order:
  - LPUSH adds to the left (head) of the list
  - BRPOP removes from the right (tail) — oldest item first

Error handling: enqueue failure is treated as a hard error (raise to caller).
A span that cannot be enqueued will not be analysed. Since there is no SDK
retry mechanism, the span is dropped. It is preferable to fail fast and return
5xx to the SDK (so the developer sees the error) than to silently accept a span
that will never be processed.
"""

import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ANALYSIS_QUEUE_KEY = "analysis_queue"


async def enqueue_span_id(redis: Redis, span_id: str) -> None:
    """Push span_id to the Redis analysis queue.

    Uses LPUSH — worker uses BRPOP (right-pop) for FIFO order.
    Called after span is accepted into the ClickHouse batch.

    Args:
        redis:   An open redis.asyncio.Redis client.
        span_id: The span UUID string to enqueue.

    Raises:
        redis.RedisError: If Redis is unreachable or the command fails.
        Caller should handle and return 5xx to SDK on enqueue failure.
    """
    await redis.lpush(ANALYSIS_QUEUE_KEY, span_id)
    logger.debug("enqueued span %s", span_id)
