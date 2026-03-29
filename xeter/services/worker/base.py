"""Shared foundation for the Embedding Worker.

BaseAnalyzer ABC provides embed/compare/log_score helpers that all concrete
analyzers inherit. Subclasses override only:
  - name (property) — stable string identifier, used as analyzer_name in span_scores
  - analyze(span) -> list[Flag] — return zero or more Flag instances

To add a new analyzer: copy ToolCallAnalyzer, rename it, override analyze().
The ANALYZERS list in worker/main.py is the registry — add your class there.

Threshold values are injected at construction via the `thresholds` dict.
No numeric literal should appear in any check method — always read from
self._thresholds[key] so that calibration changes require zero code edits.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Flag:
    flag_type: str      # e.g. "wrong_tool", "no_tool", "excessive_tool", "parsing_error", "wrong_tool_args"
    score: float        # similarity score that triggered the flag
    detail: dict        # structured detail for dashboard display; always includes "metric" key


@dataclass
class SpanData:
    span_id: str
    tenant_id: str
    trace_id: str
    agent_name: str
    agent_model: str
    tool_name: Optional[str]
    tool_description: Optional[str]
    tool_arguments: Optional[str]       # raw JSON string, stored inline in ClickHouse
    tool_output: Optional[str]
    prompt: Optional[str]               # fetched from S3 via prompt_ref
    response: Optional[str]             # fetched from S3 via response_ref
    raw_response: Optional[str]         # fetched from S3 via raw_response_ref (full API JSON)
    available_tools: Optional[list[dict]]  # fetched from S3 via available_tools_ref, parsed JSON list


class BaseAnalyzer(ABC):
    def __init__(self, model, thresholds: dict[str, float]) -> None:
        self._model = model
        self._thresholds = thresholds
        self._scores: list[tuple[str, str, float]] = []  # (analyzer_name, metric_name, score)

    def embed(self, text: str) -> np.ndarray:
        """Encode text to a 384-dim embedding vector. Returns shape (384,)."""
        return self._model.encode(text)

    def compare(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two embedding vectors. Returns scalar in [-1, 1].

        Reshapes inputs to (1, d) to satisfy model.similarity() 2D requirement.
        """
        sim = self._model.similarity(a.reshape(1, -1), b.reshape(1, -1))
        return float(sim[0][0])

    def log_score(self, metric_name: str, score: float) -> None:
        """Record a similarity score for the current span. Called BEFORE threshold test.

        Scores are flushed after analyze() returns via flush_scores(). Every
        similarity computed must be logged regardless of whether it triggers a flag
        — these records form the calibration dataset used in Phase 6.
        """
        self._scores.append((self.name, metric_name, score))

    def flush_scores(self) -> list[tuple[str, str, float]]:
        """Return and clear all scores accumulated during analyze()."""
        scores = list(self._scores)
        self._scores.clear()
        return scores

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable analyzer name string used as analyzer_name in span_scores table."""
        ...

    @abstractmethod
    def analyze(self, span: SpanData) -> list[Flag]:
        """Analyze a span and return zero or more Flag instances.

        Must call log_score() for every similarity computed, regardless of flag
        outcome. This ensures the calibration dataset is complete.
        """
        ...
