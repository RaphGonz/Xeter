# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Build the social-prompt centroid vector for unnecessary_tool_call detection.

Reads fixtures/social_prompts.txt (one prompt per line, # comments ignored),
embeds each prompt via the embedder microservice, and saves the mean vector to
fixtures/social_centroid.npy.

The saved array is loaded at import time by tool_call_analyzer._SOCIAL_CENTROID.

Usage (requires live embedder at http://localhost:8002):
    python xeter/scripts/build_social_centroid.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PROMPTS_PATH = _PROJECT_ROOT / "fixtures" / "social_prompts.txt"
CENTROID_PATH = _PROJECT_ROOT / "fixtures" / "social_centroid.npy"
EMBEDDER_URL = "http://localhost:8002"


def load_prompts() -> list[str]:
    lines = PROMPTS_PATH.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def main() -> None:
    from xeter.services.worker.base import EmbedderClient

    prompts = load_prompts()
    if not prompts:
        print(f"No prompts found in {PROMPTS_PATH}. Add prompts and re-run.")
        sys.exit(1)

    print(f"Embedding {len(prompts)} prompts via {EMBEDDER_URL} ...")
    embedder = EmbedderClient(base_url=EMBEDDER_URL)
    vectors = np.stack([embedder.encode(p) for p in prompts])  # (N, D)

    centroid = vectors.mean(axis=0)  # (D,)
    np.save(CENTROID_PATH, centroid)
    print(f"Centroid saved to {CENTROID_PATH}  shape={centroid.shape}")


if __name__ == "__main__":
    main()
