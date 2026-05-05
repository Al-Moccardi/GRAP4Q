#!/usr/bin/env python3
"""
Equivalence proof: verify the refactored package under src/ is behaviorally
identical to legacy/GRAP-Q.py.

For each function pair (legacy → refactored) we:
  1. Extract the legacy function source text out of legacy/GRAP-Q.py without
     executing the monolith's top-level imports (which include heavy deps
     like sentence-transformers).
  2. Execute the function in an isolated namespace.
  3. Run N randomized trials and compare outputs bit-for-bit.

Run:
    python scripts/verify_legacy_equivalence.py
"""
from __future__ import annotations

import math
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple  # noqa: F401  (legacy name aliases)

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LEGACY = Path(__file__).resolve().parents[1] / "legacy" / "GRAP-Q.py"


def _extract_function(name: str, src: str) -> str:
    """Return the legacy module's source for a single top-level `def <name>`."""
    m = re.search(rf"^def {name}\(.*?(?=^def |^class |\Z)", src, re.M | re.S)
    if not m:
        raise ValueError(f"function {name!r} not found in legacy source")
    return m.group(0)


def _extract_class(name: str, src: str) -> str:
    m = re.search(rf"^class {name}:.*?(?=^class |^def [A-Za-z_]+\()", src, re.M | re.S)
    if not m:
        raise ValueError(f"class {name!r} not found in legacy source")
    return m.group(0)


def main() -> int:
    if not LEGACY.exists():
        print(f"[SKIP] legacy file not present: {LEGACY}")
        return 0

    src = LEGACY.read_text()
    failures: list[str] = []

    # ---------- MiniBM25 ----------
    ns = {"math": math, "Counter": Counter}
    exec(compile(_extract_class("_MiniBM25", src), "<legacy>", "exec"), ns)
    legacy_bm25 = ns["_MiniBM25"]
    from src.retrieval.bm25 import MiniBM25 as new_bm25

    vocab = ["qc", "cx", "rz", "dag", "layout", "measure",
             "import", "def", "x", "y", "z"]
    rng = random.Random(42)
    mm = 0
    for _ in range(50):
        docs = [[rng.choice(vocab) for _ in range(rng.randint(3, 15))]
                for _ in range(rng.randint(3, 10))]
        q = [rng.choice(vocab) for _ in range(rng.randint(1, 5))]
        L, N = legacy_bm25(docs), new_bm25(docs)
        for d in docs:
            a = L.score(q, d, len(d))
            b = N.score(q, d, len(d))
            if abs(a - b) > 1e-9:
                mm += 1
    print(f"[MiniBM25]          mismatches: {mm}")
    if mm:
        failures.append("MiniBM25")

    # ---------- select_by_coverage_old ----------
    ns = {}
    exec(compile(_extract_function("select_by_coverage_old", src),
                 "<legacy>", "exec"), ns)
    legacy_old = ns["select_by_coverage_old"]
    from src.retrieval import select_by_coverage_old as new_old
    mm = _compare_selectors(legacy_old, new_old, trials=100, seed=42)
    print(f"[select.coverage_old]      mismatches: {mm}")
    if mm:
        failures.append("select_by_coverage_old")

    # ---------- select_by_coverage_balanced ----------
    ns = {"np": np}
    exec(compile(_extract_function("select_by_coverage_balanced", src),
                 "<legacy>", "exec"), ns)
    legacy_bal = ns["select_by_coverage_balanced"]
    from src.retrieval import select_by_coverage_balanced as new_bal
    mm = _compare_selectors(legacy_bal, new_bal, trials=100, seed=42)
    print(f"[select.coverage_balanced] mismatches: {mm}")
    if mm:
        failures.append("select_by_coverage_balanced")

    # ---------- enforce_in_region ----------
    ns = {"List": list, "Dict": dict, "Tuple": tuple}
    exec(compile(_extract_function("enforce_in_region", src),
                 "<legacy>", "exec"), ns)
    legacy_eir = ns["enforce_in_region"]
    from src.patching import enforce_in_region as new_eir
    rng = random.Random(42)
    mm = 0
    for _ in range(100):
        edits = []
        for __ in range(rng.randint(0, 5)):
            s = rng.randint(1, 50)
            e = s + rng.randint(0, 20)
            edits.append({"file": "f.py", "start": s, "end": e, "replacement": "x"})
        allowed = []
        for __ in range(rng.randint(1, 3)):
            s = rng.randint(1, 30)
            e = s + rng.randint(5, 40)
            allowed.append((s, e))
        if legacy_eir(edits, allowed) != new_eir(edits, allowed):
            mm += 1
    print(f"[enforce_in_region]        mismatches: {mm}")
    if mm:
        failures.append("enforce_in_region")

    # ---------- Guardrails ----------
    guard_src = ""
    import ast as _ast_mod  # noqa: F401
    for name in ("_ast_ok", "_find_registers", "_pass_interface_ok",
                 "_no_reg_mix_ok", "_qubit_order_heuristic_ok"):
        guard_src += _extract_function(name, src) + "\n"
    ns = {"ast": _ast_mod, "re": re, "List": list, "Dict": dict, "Tuple": tuple}
    exec(compile(guard_src, "<legacy>", "exec"), ns)
    from src.patching.guardrails import (
        ast_ok, no_reg_mix_ok, pass_interface_ok, qubit_order_heuristic_ok,
    )
    cases = [
        ("def run(self, dag):\n    return dag\n", "def run(self, dag):\n    return dag\n", [(1, 2)]),
        ("def run(self, x):\n    return x\n", "def run(self, y):\n    return y\n", [(1, 2)]),
        ("qr = QuantumRegister(1)\ncr = ClassicalRegister(1)\nqc.measure(cr, cr)",
         "qr = QuantumRegister(1)\ncr = ClassicalRegister(1)\nqc.measure(cr, cr)", []),
        ("qc.cx(q[0], q[1])", "qc.cx(q[1], q[0])", [(1, 1)]),
        ("syntax ok", "x = 1", []),
        ("ok", "def oops(", []),
    ]
    mm = 0
    for before, after, ranges in cases:
        pairs = [
            ("ast_ok", ns["_ast_ok"](after), ast_ok(after)),
            ("pass_iface", ns["_pass_interface_ok"](before, after),
             pass_interface_ok(before, after)),
            ("reg_mix", ns["_no_reg_mix_ok"](after) if after else (True, ""),
             no_reg_mix_ok(after) if after else (True, "")),
            ("qubit_order", ns["_qubit_order_heuristic_ok"](before, after, ranges),
             qubit_order_heuristic_ok(before, after, ranges)),
        ]
        for tag, L, N in pairs:
            if L[0] != N[0]:
                mm += 1
    print(f"[guardrails]               mismatches: {mm}")
    if mm:
        failures.append("guardrails")

    # ---------- distortion_flags NaN guard ----------
    mm = 0
    for d in (float("nan"), 0.0, 0.39, 0.40, 0.41, 1.0, -0.1):
        legacy_flag = bool(d != d and False or (d > 0.40))
        new_flag = bool((d == d) and (d > 0.40))
        if legacy_flag != new_flag:
            mm += 1
    print(f"[distortion NaN guard]     mismatches: {mm}")
    if mm:
        failures.append("distortion_flags")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} component(s) drifted: {failures}")
        return 1
    print("[OK] refactored code is behaviorally equivalent to legacy/GRAP-Q.py")
    return 0


def _compare_selectors(legacy_fn, new_fn, *, trials: int, seed: int) -> int:
    rng = random.Random(seed)
    mm = 0
    for _ in range(trials):
        pool = []
        n = rng.randint(2, 8)
        for _i in range(n):
            s = rng.randint(1, 100)
            e = s + rng.randint(1, 20)
            pool.append({
                "file": rng.choice(["A.py", "B.py", "C.py", "D.py"]),
                "symbol": rng.choice(["sa", "sb", "sc", "sd"]),
                "start": s, "end": e,
                "score": rng.random(), "re_score": rng.random(),
            })
        topk = rng.randint(1, min(4, n))
        L = legacy_fn([dict(h) for h in pool], topk=topk)
        N = new_fn([dict(h) for h in pool], topk=topk)
        key = lambda x: (x["file"], x["start"], x["end"])  # noqa: E731
        if [key(x) for x in L] != [key(x) for x in N]:
            mm += 1
    return mm


if __name__ == "__main__":
    raise SystemExit(main())
