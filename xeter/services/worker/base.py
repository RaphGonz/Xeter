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

Embedding calls are delegated to the embedder microservice over HTTP.
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


class EmbedderClient:
    """HTTP client for the embedder microservice."""

    def __init__(self, base_url: str) -> None:
        import httpx
        self._client = httpx.Client(base_url=base_url, timeout=30.0)

    def encode(self, text: str) -> np.ndarray:
        """Encode a single text to a 384-dim vector."""
        resp = self._client.post("/encode", json={"texts": [text]})
        resp.raise_for_status()
        return np.array(resp.json()["embeddings"][0])

    def encode_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Encode multiple texts in a single request."""
        resp = self._client.post("/encode", json={"texts": texts})
        resp.raise_for_status()
        return [np.array(v) for v in resp.json()["embeddings"]]

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        resp = self._client.post("/similarity", json={
            "a": a.flatten().tolist(),
            "b": b.flatten().tolist(),
        })
        resp.raise_for_status()
        return resp.json()["score"]


class BaseAnalyzer(ABC):
    def __init__(self, embedder: EmbedderClient, thresholds: dict[str, float]) -> None:
        self._embedder = embedder
        self._thresholds = thresholds
        self._scores: list[tuple[str, str, float]] = []  # (analyzer_name, metric_name, score)

    def embed(self, text: str) -> np.ndarray:
        """Encode text to a 384-dim embedding vector. Returns shape (384,)."""
        return self._embedder.encode(text)

    def compare(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two embedding vectors. Returns scalar in [-1, 1].

        Computed locally via numpy — no network call needed.
        """
        a_flat = a.flatten()
        b_flat = b.flatten()
        dot = np.dot(a_flat, b_flat)
        norm = np.linalg.norm(a_flat) * np.linalg.norm(b_flat)
        if norm == 0:
            return 0.0
        return float(dot / norm)

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


# ---------------------------------------------------------------------------
# Hybrid scoring utility (HYBRID-01)
# Used by all similarity-based check methods in ToolCallAnalyzer.
# ---------------------------------------------------------------------------

def bow_score(text_a: str, text_b: str) -> float:
    """Jaccard token overlap between two strings. Returns value in [0, 1].

    Tokenizes by lowercased whitespace split. Returns 0.0 if either
    string is empty after splitting (avoids division by zero).

    Used as the BOW component of hybrid_score().
    """
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def hybrid_score(cosine: float, bow: float, weight: float = 0.5) -> float:
    """50/50 blend of cosine similarity and bag-of-words score.

    Returns weight * cosine + (1 - weight) * bow.
    Default weight=0.5 gives equal contribution (HYBRID-01 specification).

    Args:
        cosine: Cosine similarity from BaseAnalyzer.compare(), in [-1, 1].
        bow:    BOW score from bow_score(), in [0, 1].
        weight: Cosine weight. Default 0.5 (50/50 blend).
    """
    return weight * cosine + (1.0 - weight) * bow
