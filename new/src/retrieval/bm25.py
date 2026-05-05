"""Okapi BM25 lexical retrieval with optional quantum-token boost."""
from __future__ import annotations

import math
from collections import Counter

from ..utils import Q_TOKENS, tokenize
from .chunkers import CodeChunk


class MiniBM25:
    """Minimal Okapi BM25 implementation (no external deps)."""

    def __init__(self, docs: list[list[str]]) -> None:
        self.docs = docs
        self.N = len(docs)
        self.lens = [len(d) for d in docs]
        self.avg = sum(self.lens) / max(1, self.N)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        self.df = dict(df)

    def idf(self, t: str) -> float:
        df = self.df.get(t, 0)
        return 0.0 if df == 0 else math.log(1 + (self.N - df + 0.5) / (df + 0.5))

    def score(self, q: list[str], doc: list[str], dl: int, k1: float = 1.5, b: float = 0.75) -> float:
        f = Counter(doc)
        s = 0.0
        for t in q:
            if t not in self.df:
                continue
            tf = f.get(t, 0)
            if tf == 0:
                continue
            denom = tf + k1 * (1 - b + b * dl / max(1, self.avg))
            s += self.idf(t) * (tf * (k1 + 1)) / denom
        return s


def quantum_boost_map(alpha: float = 1.8) -> dict[str, float]:
    return {t.lower(): alpha for t in Q_TOKENS}


class HybridIndex:
    """BM25 index over code chunks, with an optional per-token additive boost."""

    def __init__(self, boost_map: dict[str, float] | None = None,
                 include_paths: bool = False) -> None:
        self.boost_map = {k.lower(): float(v) for k, v in (boost_map or {}).items()}
        self.include_paths = include_paths
        self.records: list[dict] = []
        self.docs: list[list[str]] = []
        self.bm25: MiniBM25 | None = None

    def build(self, chunks: list[CodeChunk]) -> None:
        self.records = []
        self.docs = []
        for c in chunks:
            header = f"{c.symbol} {c.kind} "
            if self.include_paths:
                header += c.file_path + " "
            toks = tokenize(header + "\n" + c.text)
            boost_sum = sum(self.boost_map.get(t, 0.0) for t in toks)
            self.records.append({"chunk": c, "tokens": toks, "boost_sum": float(boost_sum)})
            self.docs.append(toks)
        self.bm25 = MiniBM25(self.docs)

    def search(self, query: str, topk: int = 10) -> list[dict]:
        if self.bm25 is None:
            return []
        q = tokenize(query)
        scored: list[tuple[float, int]] = []
        for i, rec in enumerate(self.records):
            s = self.bm25.score(q, rec["tokens"], len(rec["tokens"]))
            s += 0.02 * rec.get("boost_sum", 0.0)
            scored.append((s, i))
        scored.sort(reverse=True)
        out = []
        for s, i in scored[:topk]:
            c: CodeChunk = self.records[i]["chunk"]
            out.append({
                "score": float(s), "re_score": 0.0,
                "file": c.file_path, "symbol": c.symbol, "kind": c.kind,
                "start": int(c.start_line), "end": int(c.end_line),
                "preview": "\n".join(c.text.splitlines()[:120]),
                "repo_key": c.repo_key,
            })
        return out
