"""Evaluation metrics: Lines-F1, API drift, identifier Jaccard, distortion flags."""
from __future__ import annotations

import ast
import difflib
from pathlib import Path

from .utils import safe_read, tokenize


def touched_lines(a: str, b: str) -> set[int]:
    al, bl = a.splitlines(), b.splitlines()
    sm = difflib.SequenceMatcher(None, al, bl, autojunk=False)
    t: set[int] = set()
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag in ("replace", "delete"):
            t.update(range(i1 + 1, i2 + 1))
    return t


def lines_prf1(gold_changed: set[int], pred_changed: set[int]) -> dict:
    inter = len(gold_changed & pred_changed)
    p = inter / max(1, len(pred_changed))
    r = inter / max(1, len(gold_changed))
    f1 = 0.0 if (p + r) == 0 else 2 * p * r / (p + r)
    return {"lines_p": p, "lines_r": r, "lines_f1": f1}


def evaluate_candidate(bug_path: Path, fix_path: Path, cand_path: Path | None) -> dict:
    a = safe_read(bug_path)
    b = safe_read(fix_path)
    c = safe_read(cand_path) if cand_path else ""
    gold = touched_lines(a, b)
    pred = touched_lines(a, c) if c else set()
    return lines_prf1(gold, pred)


def api_drift_score(before: str, after: str) -> float:
    def _names(s: str):
        try:
            t = ast.parse(s)
        except Exception:
            return set()
        out = set()
        for n in ast.walk(t):
            if isinstance(n, ast.FunctionDef):
                out.add(("fun", n.name, len(n.args.args)))
            elif isinstance(n, ast.ClassDef):
                out.add(("cls", n.name, 0))
        return out
    B, A = _names(before), _names(after)
    if not B and not A:
        return 0.0
    j = len(B & A) / max(1, len(B | A))
    return 1.0 - j


def identifier_jaccard(before: str, after: str) -> float:
    B, A = set(tokenize(before)), set(tokenize(after))
    if not (A or B):
        return 1.0
    return len(A & B) / max(1, len(A | B))


def distortion_flags(before_src: str, after_src: str, delta_abs_lines: int,
                     lines_f1: float) -> dict:
    """Structured safety flags.

    Equivalent to ``legacy/GRAP-Q.py::distortion_flags``. The original used
    an awkward expression, ``bool(drift!=drift and False or (drift>0.40))``,
    which is logically the same as ``drift > 0.40`` in Python (``x and False``
    is always falsy, and NaN comparisons with ``>`` return False). The
    rewrite below is cosmetic and produces identical boolean flags on all
    inputs — see ``tests/test_smoke.py::test_distortion_flags_nan_guard``.
    """
    try:
        ast.parse(after_src) if after_src else None
        ast_ok = bool(after_src)
    except SyntaxError:
        ast_ok = False
    drift = api_drift_score(before_src, after_src) if after_src else float("nan")
    jacc = identifier_jaccard(before_src, after_src) if after_src else float("nan")
    excessive_no_gain = (lines_f1 == 0.0) and (delta_abs_lines >= 5)
    # Cosmetic: explicit NaN check, logically identical to the legacy form.
    drift_gt40 = (drift == drift) and (drift > 0.40)
    jacc_lt60 = (jacc == jacc) and (jacc < 0.60)
    return {
        "ast_parse_fail": (not ast_ok),
        "api_drift_gt40": bool(drift_gt40),
        "id_jacc_lt60": bool(jacc_lt60),
        "excessive_no_gain": bool(excessive_no_gain),
        "drift": float(drift) if drift == drift else None,
        "id_jacc": float(jacc) if jacc == jacc else None,
        "delta_abs_lines": int(delta_abs_lines),
    }
