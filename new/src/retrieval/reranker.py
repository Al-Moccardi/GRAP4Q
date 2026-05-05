"""Cross-encoder re-ranker wrapping sentence-transformers.

Loads lazily and degrades gracefully to a no-op if the model/library is absent.
"""
from __future__ import annotations

import numpy as np


class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self.enabled = False
        self.model = None
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            self.model = CrossEncoder(model_name)
            self.enabled = True
        except Exception as e:  # network-less / missing dep
            print(f"[WARN] CrossEncoder unavailable ({type(e).__name__}: {e}). "
                  f"Re-ranking will be skipped — all scores fall back to lexical.")

    def score_pairs(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        if not self.enabled or self.model is None:
            return np.zeros(len(pairs))
        return np.asarray(self.model.predict(pairs), dtype=float)


def apply_rerank(query: str, pool: list[dict], rr: CrossEncoderReranker | None) -> list[dict]:
    if rr is None or not rr.enabled:
        return pool
    pairs = [(query, h.get("preview", "")) for h in pool]
    scores = rr.score_pairs(pairs)
    for h, s in zip(pool, scores):
        h["re_score"] = float(s)
    return sorted(pool, key=lambda r: r.get("re_score", 0.0), reverse=True)
