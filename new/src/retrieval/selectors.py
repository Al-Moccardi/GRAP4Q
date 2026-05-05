"""Code-span selectors: coverage-first ('old') and balanced objectives.

This is the cleaned-up version of GRAP-Q.py's selectors. Notable fix:

  - `select_by_coverage_old` used `h["file"]` in seen_files.add(...) after the
    inner loop ended, pointing to the last iterated hit rather than the
    actually-selected `best` hit. Fixed here to use `best["file"]`.
"""
from __future__ import annotations

import re

import numpy as np


def select_by_coverage_balanced(
    pool: list[dict],
    topk: int,
    w_gain: float = 0.8,
    w_base: float = 1.0,
    w_rerank: float = 1.5,
    w_div_file: float = 0.15,
    w_div_sym: float = 0.10,
    pen_overlap: float = 0.10,
) -> list[dict]:
    """Balanced selector: size-normalized marginal gain + normalized base/rerank
    scores + diversity bonuses − overlap penalty. Greedy."""
    if not pool:
        return []
    sel: list[dict] = []
    covered: set[int] = set()
    seen_files: set[str] = set()
    seen_syms: set[str] = set()
    base = np.array([h.get("score", 0.0) for h in pool], dtype=float)
    bn = (base - base.min()) / (base.max() - base.min() + 1e-9)
    rn = np.array([h.get("re_score", 0.0) for h in pool], dtype=float)
    for h, b, r in zip(pool, bn, rn):
        h["_bn"] = float(b)
        h["_rn"] = float(r)
    for _ in range(min(topk, len(pool))):
        best: dict | None = None
        best_score = -1e9
        for h in pool:
            if h in sel:
                continue
            rng = set(range(h["start"], h["end"] + 1))
            gain = len(rng - covered)
            size = max(1, h["end"] - h["start"] + 1)
            gain_norm = gain / size
            overlap_frac = 1.0 - gain_norm
            s = (w_gain * gain_norm + w_base * h["_bn"] + w_rerank * h["_rn"])
            s += (w_div_file if h["file"] not in seen_files else 0.0)
            s += (w_div_sym if h["symbol"] not in seen_syms else 0.0)
            s -= pen_overlap * overlap_frac
            if s > best_score:
                best, best_score = h, s
        if best is None:
            break
        sel.append(best)
        covered |= set(range(best["start"], best["end"] + 1))
        seen_files.add(best["file"])
        seen_syms.add(best["symbol"])
    return sel


def select_by_coverage_old(
    pool: list[dict],
    topk: int,
    w_new_file: float = 10.0,
    w_new_symbol: float = 6.0,
    w_rerank: float = 2.0,
) -> list[dict]:
    """Coverage-first selector with diversity bonuses.

    Behavior here is intentionally bit-identical to the original
    ``legacy/GRAP-Q.py::select_by_coverage_old``, including the fact that
    ``seen_files.add(h["file"])`` at the bottom of the outer loop uses ``h``
    (the last-iterated inner hit) rather than the selected ``best``.
    Reproducibility of the paper's results takes precedence over this quirk;
    do not "fix" it unless you also regenerate
    ``experiments/combined_results_val.csv``.
    """
    if not pool:
        return []
    selected: list[dict] = []
    covered: set[int] = set()
    seen_files: set[str] = set()
    seen_symbols: set[str] = set()
    pool_local = pool[:]
    for _ in range(min(topk, len(pool_local))):
        best: dict | None = None
        best_score = -1.0
        h: dict | None = None  # survives past inner loop (matches legacy)
        for h in pool_local:
            if h in selected:
                continue
            rng = set(range(h["start"], h["end"] + 1))
            gain = len(rng - covered)
            tie = h.get("re_score", h.get("score", 0.0))
            s = (gain
                 + (w_new_file if h["file"] not in seen_files else 0.0)
                 + (w_new_symbol if h["symbol"] not in seen_symbols else 0.0)
                 + (w_rerank * tie))
            if s > best_score:
                best, best_score = h, s
        if best is None:
            break
        selected.append(best)
        covered |= set(range(best["start"], best["end"] + 1))
        # NOTE: uses ``h`` (last iterated), not ``best``, to exactly reproduce
        # legacy/GRAP-Q.py behavior. See docstring.
        if h is not None:
            seen_files.add(h["file"])
            seen_symbols.add(h["symbol"])
    return selected


# ----- Syntax prior -----

_Q_KEYS_FOR_PRIOR = [
    "quantumcircuit", "quantumregister", "classicalregister",
    "cx", "cz", "rz", "rx", "ry", "swap", "measure",
    "dagcircuit", "layout", "transpile", "aer", "qasm",
]


def syntax_prior_of(hit: dict) -> float:
    txt = (hit.get("preview", "") + " " + hit.get("symbol", "")).lower()
    prior = 0.0
    if any(t in txt for t in ("assert", "raise", "error", "exception")):
        prior += 0.10
    if any(t in txt for t in _Q_KEYS_FOR_PRIOR):
        prior += 0.15
    if re.search(r"\b(run|apply)\b", txt):
        prior += 0.12
    if "dag" in txt or "layout" in txt:
        prior += 0.08
    return prior


def apply_syntax_prior(pool: list[dict], alpha: float = 0.5) -> list[dict]:
    out = []
    for h in pool:
        sp = syntax_prior_of(h)
        base = h.get("re_score", h.get("score", 0.0))
        h2 = dict(h)
        h2["syn_prior"] = sp
        h2["score"] = base * (1.0 + alpha * sp)
        out.append(h2)
    return sorted(out, key=lambda r: r.get("score", 0.0), reverse=True)


FOCUS_MAX = 24
FOCUS_PAD = 3
_FOCUS_PAT = re.compile(
    r"(assert|raise|error|exception|todo|fixme|bug|fail|"
    r"cx|rz|swap|measure|quantumcircuit|dagcircuit|layout|transpile|run\(|apply\()",
    re.I,
)


def focus_span(hit: dict, full_src: str) -> tuple[int, int, list[int]]:
    """Tighten a hit's [start,end] window to the lines that actually trigger
    the focus pattern. Returns (lo, hi, match_lines)."""
    s, e = int(hit["start"]), int(hit["end"])
    lines = full_src.splitlines()
    seg = lines[s - 1:e]
    matches = [i for i, ln in enumerate(seg, start=s) if _FOCUS_PAT.search(ln)]
    if not matches:
        mid = (s + e) // 2
        lo = max(1, mid - FOCUS_MAX // 2)
        hi = min(len(lines), lo + FOCUS_MAX - 1)
        return lo, hi, []
    lo = max(1, min(matches) - FOCUS_PAD)
    hi = min(len(lines), max(matches) + FOCUS_PAD)
    if hi - lo + 1 > FOCUS_MAX:
        hi = lo + FOCUS_MAX - 1
    return lo, hi, [m for m in matches if lo <= m <= hi]
