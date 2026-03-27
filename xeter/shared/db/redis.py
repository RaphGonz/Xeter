"""
Redis async client factory.

Phase 1 provides connection setup only. Actual queue operations
(batched ClickHouse writes, task queuing) are implemented in Phase 2.

Usage::

    from xeter.shared.db.redis import get_redis_client

    redis = await get_redis_client()
    await redis.ping()
    await redis.aclose()
"""

import os

import redis.asyncio as aioredis


def get_redis_client() -> aioredis.Redis:
    """Create a Redis async client from the REDIS_URL environment variable.

    Returns a redis.asyncio.Redis client. The connection is lazy — no network
    call is made until the first command is issued.

    Raises:
        KeyError: If REDIS_URL is not set in the environment.
    """
    redis_url = os.environ["REDIS_URL"]
    return aioredis.from_url(redis_url, decode_responses=True)
