"""TraceAnalyzer scaffold for the Embedding Worker.

Concrete implementation of BaseTraceAnalyzer. Phase 19 scaffold — analyze()
returns [] (no checks implemented yet). Actual trace-level checks land in v1.5.

Invoked by the worker after WORKER_TRACE_FLUSH_TIMEOUT_S elapses with no new
spans for a given trace_id.
"""

from __future__ import annotations

from xeter.services.worker.base import BaseTraceAnalyzer, EmbedderClient, Flag, SpanData


class TraceAnalyzer(BaseTraceAnalyzer):
    """Trace-level analyzer scaffold. Returns no flags until v1.5 checks are added."""

    def __init__(self, embedder: EmbedderClient, thresholds: dict[str, float]) -> None:
        super().__init__(embedder, thresholds)

    @property
    def name(self) -> str:
        return "trace_analyzer"

    def analyze(self, spans: list[SpanData]) -> list[Flag]:
        """Analyze all spans in a completed trace.

        Phase 19 scaffold: no checks implemented. Returns [] unconditionally.
        Future checks (v1.5 categories B/C/D/E/F/G/H) will be added here.

        Args:
            spans: All SpanData objects accumulated for this trace_id.

        Returns:
            Empty list — scaffold produces no flags.
        """
        return []
