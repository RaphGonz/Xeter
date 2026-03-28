"""
ClickHouse batch flusher for the Analyser service.

Provides:
  - SPAN_COLUMNS: ordered list of ClickHouse span table column names
  - SpanBatcher: asyncio.Queue-based batcher with size-or-time flush trigger
  - get_clickhouse_client: factory function reading config from environment

The batcher buffers span rows in an in-memory asyncio.Queue. A background
asyncio task flushes the buffer to ClickHouse when either:
  - XETER_BATCH_SIZE rows are buffered (default: 100), OR
  - XETER_FLUSH_INTERVAL seconds have elapsed (default: 5.0 seconds)

whichever comes first (Pattern 3 from 02-RESEARCH.md).

Spans lost in an in-flight batch on crash are acceptable — observability data
is not transactional. The batcher logs errors but does not re-raise on flush
failure.

Environment variables:
  XETER_BATCH_SIZE      — flush batch size (default: 100)
  XETER_FLUSH_INTERVAL  — flush interval in seconds (default: 5.0)
  CLICKHOUSE_HOST       — ClickHouse host (default: "clickhouse")
  CLICKHOUSE_PORT       — ClickHouse HTTP port (default: 8123)
  CLICKHOUSE_DATABASE   — ClickHouse database (default: "xeter")
"""

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

# ClickHouse column names in insertion order.
# Must match the spans table DDL ORDER BY (tenant_id, trace_id, time_begin).
# Set once — changing this breaks existing ClickHouse rows.
SPAN_COLUMNS = [
    "span_id",
    "trace_id",
    "parent_span_id",
    "tenant_id",
    "agent_name",
    "agent_model",
    "tool_name",
    "tool_description",
    "tool_arguments",
    "tool_output",
    "prompt_ref",
    "response_ref",
    "raw_response_ref",
    "available_tools_ref",
    "time_begin",
    "time_end",
    "schema_version",
]


class SpanBatcher:
    """Buffers span rows and flushes to ClickHouse in batches.

    Flush is triggered by size (XETER_BATCH_SIZE) or time
    (XETER_FLUSH_INTERVAL), whichever comes first.

    Usage::

        batcher = SpanBatcher(get_clickhouse_client())
        await batcher.start()            # starts background flush task
        await batcher.add(row)           # row: list of values in SPAN_COLUMNS order
        await batcher.stop()             # cancels task, final flush on shutdown
    """

    def __init__(self, ch_client) -> None:
        """Initialise the batcher.

        Args:
            ch_client: A clickhouse_connect client instance (sync).
                       insert() is called via asyncio.to_thread.
        """
        self._ch = ch_client
        self._queue: asyncio.Queue = asyncio.Queue()
        self._batch_size = int(os.environ.get("XETER_BATCH_SIZE", "100"))
        self._flush_interval = float(os.environ.get("XETER_FLUSH_INTERVAL", "5"))
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background flush task.

        Must be called once during application startup (e.g. in FastAPI lifespan).
        """
        self._task = asyncio.create_task(self._flush_loop())
        logger.info(
            "batcher: started (batch_size=%d, flush_interval=%.1fs)",
            self._batch_size,
            self._flush_interval,
        )

    async def stop(self) -> None:
        """Stop the background flush task and flush remaining rows.

        Cancels the flush loop, waits for it to finish, then drains any
        remaining rows in the queue and writes them to ClickHouse.
        Must be called during application shutdown.
        """
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await self._flush_all()
        logger.info("batcher: stopped")

    async def add(self, row: list) -> None:
        """Accept a span row into the batch queue.

        Non-blocking — the queue is unbounded. Returns immediately.

        Args:
            row: List of field values in SPAN_COLUMNS order.
        """
        await self._queue.put(row)

    async def _flush_loop(self) -> None:
        """Background task: drain queue with size-or-time flush trigger.

        Implements Pattern 3 from 02-RESEARCH.md exactly:
          - Wait up to `_flush_interval` seconds for the next row.
          - If a row arrives, append to buffer.
            - If buffer reaches `_batch_size`, flush immediately and reset.
          - If timeout elapses with rows in buffer, flush and reset.
          - Runs forever until cancelled by stop().
        """
        buffer: list = []
        deadline = time.monotonic() + self._flush_interval
        while True:
            timeout = max(0, deadline - time.monotonic())
            try:
                row = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                buffer.append(row)
                if len(buffer) >= self._batch_size:
                    await self._flush(buffer)
                    buffer = []
                    deadline = time.monotonic() + self._flush_interval
            except asyncio.TimeoutError:
                if buffer:
                    await self._flush(buffer)
                    buffer = []
                deadline = time.monotonic() + self._flush_interval

    async def _flush(self, rows: list) -> None:
        """Write a batch of rows to ClickHouse.

        Calls clickhouse_connect's sync insert() via asyncio.to_thread to avoid
        blocking the event loop. Logs errors but does not re-raise — observability
        data loss on crash is acceptable.

        Args:
            rows: List of row lists, each in SPAN_COLUMNS order.
        """
        try:
            await asyncio.to_thread(
                self._ch.insert,
                "spans",
                rows,
                column_names=SPAN_COLUMNS,
            )
            logger.debug("batcher: flushed %d rows to ClickHouse", len(rows))
        except Exception as exc:
            logger.error("batcher: flush failed (%d rows dropped): %s", len(rows), exc)

    async def _flush_all(self) -> None:
        """Drain the queue synchronously and flush any remaining rows.

        Called during shutdown after the flush loop is cancelled.
        Uses get_nowait() to avoid blocking — only processes rows already
        in the queue at the time of shutdown.
        """
        rows = []
        while not self._queue.empty():
            rows.append(self._queue.get_nowait())
        if rows:
            await self._flush(rows)
            logger.info("batcher: flushed %d remaining rows on shutdown", len(rows))


def get_clickhouse_client():
    """Create a ClickHouse client from environment variables.

    Uses clickhouse_connect.get_client() (sync). The returned client
    is used by SpanBatcher via asyncio.to_thread.

    Environment variables:
      CLICKHOUSE_HOST     — default "clickhouse"
      CLICKHOUSE_PORT     — default 8123
      CLICKHOUSE_DATABASE — default "xeter"

    Returns:
        A clickhouse_connect.driver.client.Client instance.
    """
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        database=os.environ.get("CLICKHOUSE_DATABASE", "xeter"),
    )
