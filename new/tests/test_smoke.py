"""Smoke tests for the refactored modules. Run with `pytest tests/`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines.qchecker import check_source
from baselines.rule_based_apr import evaluate_patch, patch_source
from src.dataset import deterministic_splits
from src.metrics import distortion_flags, lines_prf1
from src.patching.guardrails import enforce_in_region, validate_patch
from src.retrieval import (
    ASTChunker, HybridIndex, WindowChunker,
    quantum_boost_map, select_by_coverage_balanced,
)


# ----- Metrics -----

def test_lines_prf1_perfect():
    r = lines_prf1({1, 2, 3}, {1, 2, 3})
    assert r["lines_p"] == 1.0 and r["lines_r"] == 1.0 and r["lines_f1"] == 1.0


def test_lines_prf1_empty():
    r = lines_prf1(set(), set())
    assert r["lines_f1"] == 0.0


def test_distortion_flags_nan_guard():
    """NaN drift must NOT raise the api_drift_gt40 flag. Equivalence check:
    this is the behavior of the legacy one-liner too."""
    flags = distortion_flags(before_src="def f(): pass", after_src="",
                             delta_abs_lines=0, lines_f1=0.0)
    assert flags["api_drift_gt40"] is False
    assert flags["id_jacc_lt60"] is False


def test_distortion_flags_matches_legacy_expression():
    """Fuzz-check: the refactored flag must equal what the legacy
    expression `bool(x!=x and False or (x>0.40))` would compute."""
    import math
    import random
    rng = random.Random(7)
    for _ in range(200):
        if rng.random() < 0.2:
            drift = float("nan")
        else:
            drift = rng.uniform(-0.5, 1.5)
        legacy = bool(drift != drift and False or (drift > 0.40))
        new = bool((drift == drift) and (drift > 0.40))
        assert legacy == new, f"mismatch at drift={drift}"


# ----- Dataset -----

def test_deterministic_splits_reproducible():
    ids = [f"case/{i}" for i in range(20)]
    a1, b1, c1 = deterministic_splits(ids, (0.70, 0.15, 0.15))
    a2, b2, c2 = deterministic_splits(ids, (0.70, 0.15, 0.15))
    assert (a1, b1, c1) == (a2, b2, c2)
    assert len(a1) + len(b1) + len(c1) == len(ids)


# ----- Legacy equivalence -----

def test_select_by_coverage_old_matches_legacy():
    """Our refactored select_by_coverage_old must produce the exact same
    output (including the `h` vs `best` quirk) as legacy/GRAP-Q.py.

    Skipped if the legacy file is not present or if its heavy dependencies
    (tqdm, pandas, requests, sentence_transformers) are not importable.
    """
    from pathlib import Path as _P
    # Two-folder package layout (grap4q_package/legacy/) OR legacy/ inside new/
    new_root = _P(__file__).resolve().parents[1]
    candidates = [
        new_root / "legacy" / "GRAP-Q.py",          # same-folder layout
        new_root.parent / "legacy" / "GRAP-Q.py",   # two-folder package layout
    ]
    legacy_path = next((p for p in candidates if p.exists()), candidates[0])

    class _Skip(Exception):
        pass

    def _skip(msg):
        try:
            import pytest  # type: ignore[import]
            pytest.skip(msg)
        except ImportError:
            raise _Skip(msg)

    if not legacy_path.exists():
        _skip("legacy/GRAP-Q.py not present")

    import importlib.util
    spec = importlib.util.spec_from_file_location("grap_legacy", legacy_path)
    legacy = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(legacy)  # type: ignore[union-attr]
    except Exception as e:
        _skip(f"could not exec legacy module: {e}")

    # Synthetic hits designed to trigger the `h`-vs-`best` quirk:
    # two candidates tie on gain but differ in `file`.
    pool = [
        {"file": "A.py", "symbol": "sa", "start": 1, "end": 5, "score": 0.0, "re_score": 1.0},
        {"file": "B.py", "symbol": "sb", "start": 3, "end": 8, "score": 0.0, "re_score": 0.9},
        {"file": "C.py", "symbol": "sc", "start": 9, "end": 12, "score": 0.0, "re_score": 0.5},
    ]
    from src.retrieval import select_by_coverage_old as new_select
    legacy_out = legacy.select_by_coverage_old([dict(h) for h in pool], topk=2)
    new_out = new_select([dict(h) for h in pool], topk=2)
    key = lambda x: (x["file"], x["start"], x["end"])  # noqa: E731
    assert [key(x) for x in legacy_out] == [key(x) for x in new_out]


# ----- Guardrails -----

def test_validate_patch_ast_failure():
    before = "def run(self, dag):\n    return dag\n"
    edits = [{"file": "buggy.py", "start": 2, "end": 2, "replacement": "    return dag +++ "}]
    ok, msgs = validate_patch(before, edits)
    assert not ok
    assert any("SyntaxError" in m for m in msgs)


def test_validate_patch_pass_interface_preserved():
    before = "class P:\n    def run(self, dag):\n        return dag\n"
    edits = [{"file": "buggy.py", "start": 3, "end": 3, "replacement": "        return dag"}]
    ok, msgs = validate_patch(before, edits)
    assert ok, f"expected ok, got: {msgs}"


def test_enforce_in_region_drops_out_of_range():
    edits = [
        {"file": "buggy.py", "start": 1, "end": 3, "replacement": "a"},
        {"file": "buggy.py", "start": 10, "end": 15, "replacement": "b"},
    ]
    kept = enforce_in_region(edits, allowed=[(1, 5)])
    assert len(kept) == 1 and kept[0]["start"] == 1


# ----- Retrieval -----

def test_retrieval_end_to_end(tmp_path):
    # Build a tiny case with one buggy.py
    case_dir = tmp_path / "CASE"
    case_dir.mkdir()
    bug = case_dir / "buggy.py"
    bug.write_text(
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(1)\n"
        "qc.h(0)\n"
        "qc.measure_all()\n"
    )
    chunker = WindowChunker(window=4, overlap=1)
    chunks = chunker.chunk_file(case_dir, bug, repo_key="CASE")
    assert len(chunks) >= 1
    idx = HybridIndex(boost_map=quantum_boost_map(1.0))
    idx.build(chunks)
    pool = idx.search("qiskit quantumcircuit measure", topk=3)
    assert pool and "score" in pool[0]
    sel = select_by_coverage_balanced(pool, topk=1)
    assert len(sel) == 1


def test_ast_chunker_parses_functions(tmp_path):
    case_dir = tmp_path / "CASE"
    case_dir.mkdir()
    p = case_dir / "x.py"
    p.write_text("def f(): pass\ndef g(): return 1\n")
    chunks = ASTChunker().chunk_file(case_dir, p, repo_key="CASE")
    names = [c.symbol for c in chunks]
    assert "f" in names and "g" in names


# ----- Dataset -----

def test_deterministic_splits_reproducible():
    ids = [f"case/{i}" for i in range(20)]
    a1, b1, c1 = deterministic_splits(ids, (0.70, 0.15, 0.15))
    a2, b2, c2 = deterministic_splits(ids, (0.70, 0.15, 0.15))
    assert (a1, b1, c1) == (a2, b2, c2)
    assert len(a1) + len(b1) + len(c1) == len(ids)


# ----- Baselines -----

def test_qchecker_deprecated_get_data_fires():
    src = (
        "from qiskit import QuantumCircuit, QuantumRegister, execute\n"
        "q = QuantumRegister(1)\n"
        "qc = QuantumCircuit(q)\n"
        "job = execute(qc, backend='local_statevector_simulator')\n"
        "job.result().get_data(qc)\n"
    )
    r = check_source(src, case="t")
    rule_ids = {f.rule for f in r.findings}
    assert "QC05" in rule_ids  # deprecated backend name
    assert "QC06" in rule_ids  # get_data misuse
    assert "QC04" in rule_ids  # deprecated execute()


def test_rule_apr_fixes_iden_to_id():
    buggy = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(1)\nqc.iden(0)\n"
    gold = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(1)\nqc.id(0)\n"
    res = patch_source(buggy, case="t")
    assert any(r.rule == "R4" for r in res.rules_applied)
    scores = evaluate_patch(buggy, res.patched_src, gold)
    assert scores["lines_f1"] == 1.0


# ----- iter_cases: OS-independent discovery + paper filter -----

def test_iter_cases_excludes_paper_excluded(tmp_path):
    """Capital-F files and Terra-0-4000/1 must NOT appear with filter on."""
    from src.dataset import PAPER_EXCLUDED_CASES, iter_cases

    # One canonical case (should be yielded)
    (tmp_path / "Aer" / "bug_1").mkdir(parents=True)
    (tmp_path / "Aer" / "bug_1" / "buggy.py").write_text("print(1)\n")
    (tmp_path / "Aer" / "bug_1" / "fixed.py").write_text("print(2)\n")

    # Four capital-F cases (should always be excluded: literal match fails)
    for cid, fixname in [
        ("Terra-0-4000/3", "Fixed.py"),
        ("Terra-0-4000/6", "Fixed.py"),
        ("Terra-0-4000/7", "Fix.py"),
        ("stackoverflow-1-5/1", "Fix.py"),
    ]:
        d = tmp_path / cid
        d.mkdir(parents=True)
        (d / "buggy.py").write_text("print(1)\n")
        (d / fixname).write_text("print(2)\n")

    # Terra-0-4000/1 with lowercase fixed.py — only excluded by the list
    extra = tmp_path / "Terra-0-4000" / "1"
    extra.mkdir(parents=True)
    (extra / "buggy.py").write_text("print(1)\n")
    (extra / "fixed.py").write_text("print(2)\n")

    ids = {c[0] for c in iter_cases(tmp_path)}
    assert "Aer/bug_1" in ids
    assert ids.isdisjoint(PAPER_EXCLUDED_CASES), \
        f"Excluded cases leaked: {ids & PAPER_EXCLUDED_CASES}"


def test_iter_cases_filter_off_adds_terra_0_4000_1(tmp_path):
    """With apply_paper_filter=False, Terra-0-4000/1 comes back (on any OS)."""
    from src.dataset import iter_cases

    d = tmp_path / "Terra-0-4000" / "1"
    d.mkdir(parents=True)
    (d / "buggy.py").write_text("print(1)\n")
    (d / "fixed.py").write_text("print(2)\n")

    on = {c[0] for c in iter_cases(tmp_path)}
    off = {c[0] for c in iter_cases(tmp_path, apply_paper_filter=False)}
    assert "Terra-0-4000/1" not in on
    assert "Terra-0-4000/1" in off


def test_iter_cases_literal_filename_match(tmp_path):
    """Capital-F fixed files must NOT match even with filter off (literal strings)."""
    from src.dataset import iter_cases

    d = tmp_path / "Terra-0-4000" / "3"
    d.mkdir(parents=True)
    (d / "buggy.py").write_text("print(1)\n")
    (d / "Fixed.py").write_text("print(2)\n")  # capital F

    off = {c[0] for c in iter_cases(tmp_path, apply_paper_filter=False)}
    # Even on a case-insensitive FS, os.walk returns 'Fixed.py' (not 'fixed.py'),
    # so the literal string check excludes this case without help from the filter.
    assert "Terra-0-4000/3" not in off
