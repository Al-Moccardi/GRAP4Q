"""
Behavioral-equivalence tests between `legacy/GRAP-Q.py` and `new/src/`.

For every function that was moved from the monolith to the refactored
package, we assert that the two implementations return the *same* output on
the *same* input. Where legacy and new intentionally diverge (§3 of
REMAPPING.md), we assert the documented behavior of each separately.

Run:
    # From the new/ folder:
    python tests/test_equivalence_with_legacy.py

Dependencies: only numpy + stdlib. No Ollama, no network, no dataset.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Path plumbing: import the legacy monolith as a module, without polluting
# sys.path beyond this test.
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
NEW_ROOT = HERE.parent                     # .../new
PKG_ROOT = NEW_ROOT.parent                 # .../grap4q_package
LEGACY_PY = PKG_ROOT / "legacy" / "GRAP-Q.py"

if not LEGACY_PY.exists():
    raise SystemExit(
        f"[ERROR] Cannot find legacy source at {LEGACY_PY}. "
        "Run this test from within the grap4q_package directory tree."
    )


def _load_legacy_module():
    """Import legacy/GRAP-Q.py as a module named `legacy_grapq`."""
    spec = importlib.util.spec_from_file_location("legacy_grapq", str(LEGACY_PY))
    mod = importlib.util.module_from_spec(spec)
    # Some globals reference `ollama_chat` at import time, but nothing is
    # *executed* at import — only defs. We can import without Ollama.
    sys.modules["legacy_grapq"] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure the `new/` package is importable
sys.path.insert(0, str(NEW_ROOT))

legacy = _load_legacy_module()

# Imports from the refactored package
from src.utils import (  # noqa: E402
    changed_lines_in_A as new_changed_lines_in_A,
    safe_read as new_safe_read,
    tokenize as new_tokenize,
    top_tokens_query_from_text as new_top_tokens_query,
)
from src.metrics import (  # noqa: E402
    api_drift_score as new_api_drift,
    distortion_flags as new_distortion_flags,
    identifier_jaccard as new_identifier_jaccard,
    lines_prf1,
)
from src.dataset import deterministic_splits as new_deterministic_splits  # noqa: E402
from src.retrieval import (  # noqa: E402
    ASTChunker as NewASTChunker,
    HybridIndex as NewHybridIndex,
    apply_rerank as new_apply_rerank,
    focus_span as new_focus_span,
    quantum_boost_map as new_quantum_boost_map,
    select_by_coverage_balanced as new_select_balanced,
    syntax_prior_of as new_syntax_prior_of,
)
from src.patching import (  # noqa: E402
    enforce_in_region as new_enforce_in_region,
    ast_ok as new_ast_ok,
)


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    marker = "PASS" if cond else "FAIL"
    tail = f"  [{detail}]" if (detail and not cond) else ""
    print(f"  {marker}  {name}{tail}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SRC = """from qiskit import QuantumCircuit, QuantumRegister, execute
import random

q = QuantumRegister(2)
qc = QuantumCircuit(q)
qc.h(q[0])
qc.cx(q[0], q[1])
job = execute(qc, backend='local_statevector_simulator')
result = job.result()
data = result.get_data(qc)

def run(self, dag):
    return dag

class Foo:
    def __init__(self):
        self.x = 0
    def bar(self, n):
        return n * 2
"""

SAMPLE_FIX = SAMPLE_SRC.replace("local_statevector_simulator", "statevector_simulator") \
                       .replace("get_data(qc)", "get_statevector()")


# ---------------------------------------------------------------------------
# Group 1 — string/tokenization utilities (§ Text utilities in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_tokenize_identical():
    out_legacy = legacy.tokenize(SAMPLE_SRC)
    out_new = new_tokenize(SAMPLE_SRC)
    check("tokenize(): identical output", out_legacy == out_new,
          f"legacy={len(out_legacy)} tokens, new={len(out_new)}")


def test_top_tokens_query_identical():
    out_legacy = legacy.top_tokens_query_from_text(SAMPLE_SRC, k=6)
    out_new = new_top_tokens_query(SAMPLE_SRC, k=6)
    check("top_tokens_query_from_text(k=6): identical", out_legacy == out_new,
          f"legacy={out_legacy!r} new={out_new!r}")


def test_changed_lines_identical():
    out_legacy = legacy.changed_lines_in_A(SAMPLE_SRC, SAMPLE_FIX)
    out_new = new_changed_lines_in_A(SAMPLE_SRC, SAMPLE_FIX)
    check("changed_lines_in_A(): identical set",
          out_legacy == out_new,
          f"legacy={sorted(out_legacy)} new={sorted(out_new)}")


# ---------------------------------------------------------------------------
# Group 2 — metrics (§ Metrics in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_api_drift_identical():
    out_legacy = legacy.api_drift_score(SAMPLE_SRC, SAMPLE_FIX)
    out_new = new_api_drift(SAMPLE_SRC, SAMPLE_FIX)
    check("api_drift_score(): identical float",
          math.isclose(out_legacy, out_new, abs_tol=1e-12),
          f"legacy={out_legacy} new={out_new}")


def test_identifier_jaccard_identical():
    out_legacy = legacy.identifier_jaccard(SAMPLE_SRC, SAMPLE_FIX)
    out_new = new_identifier_jaccard(SAMPLE_SRC, SAMPLE_FIX)
    check("identifier_jaccard(): identical float",
          math.isclose(out_legacy, out_new, abs_tol=1e-12),
          f"legacy={out_legacy} new={out_new}")


def test_lines_prf1_matches_legacy_evaluate_candidate(tmp: Path):
    """evaluate_candidate in legacy is file-based; we feed it tmp files and
    compare its (p, r, f1) against the new string-based lines_prf1()."""
    bug_dir = tmp / "bug"; bug_dir.mkdir()
    fix_dir = tmp / "fix"; fix_dir.mkdir()
    cand_dir = tmp / "cand"; cand_dir.mkdir()
    (bug_dir / "buggy.py").write_text(SAMPLE_SRC, encoding="utf-8")
    (fix_dir / "buggy.py").write_text(SAMPLE_FIX, encoding="utf-8")
    (cand_dir / "buggy.py").write_text(SAMPLE_FIX, encoding="utf-8")  # perfect
    leg = legacy.evaluate_candidate(bug_dir, fix_dir, cand_dir)
    new = lines_prf1(new_changed_lines_in_A(SAMPLE_SRC, SAMPLE_FIX),
                     new_changed_lines_in_A(SAMPLE_SRC, SAMPLE_FIX))
    same = (math.isclose(leg["lines_p"], new["lines_p"], abs_tol=1e-12)
            and math.isclose(leg["lines_r"], new["lines_r"], abs_tol=1e-12)
            and math.isclose(leg["lines_f1"], new["lines_f1"], abs_tol=1e-12))
    check("evaluate_candidate <-> lines_prf1 (perfect patch): identical",
          same, f"legacy={leg} new={new}")


def test_distortion_flags_equivalent_per_remapping_3_2():
    """§3.2 of REMAPPING.md: on the same inputs, the legacy and new forms
    produce the *same* booleans, even though the legacy expression was written
    in a convoluted way."""
    # Case A: normal inputs
    for before, after in [
        (SAMPLE_SRC, SAMPLE_FIX),
        (SAMPLE_SRC, SAMPLE_SRC),
        ("def f(): pass\n", "def g(): pass\n"),
    ]:
        # Legacy needs bug_repo + cand_repo paths; we build tiny ones on the fly
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bug = td / "bug"; bug.mkdir()
            cand = td / "cand"; cand.mkdir()
            (bug / "buggy.py").write_text(before, encoding="utf-8")
            (cand / "buggy.py").write_text(after, encoding="utf-8")
            leg = legacy.distortion_flags(bug, [], cand, lines_f1=0.5)
            newf = new_distortion_flags(before, after, delta_abs_lines=0,
                                        lines_f1=0.5)
            same = (leg["api_drift_gt40"] == newf["api_drift_gt40"]
                    and leg["id_jacc_lt60"] == newf["id_jacc_lt60"]
                    and leg["excessive_no_gain"] == newf["excessive_no_gain"])
            check(f"distortion_flags({before[:15]!r}->{after[:15]!r}): equivalent flags",
                  same, f"legacy={leg} new={newf}")


# ---------------------------------------------------------------------------
# Group 3 — chunkers (§ Chunking in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_ast_chunker_identical(tmp: Path):
    case_dir = tmp / "CASE_ast"; case_dir.mkdir()
    p = case_dir / "x.py"
    p.write_text(SAMPLE_SRC, encoding="utf-8")
    leg = legacy.ASTChunker().chunk_file(case_dir, p, repo_key="CASE")
    new = NewASTChunker().chunk_file(case_dir, p, repo_key="CASE")
    # Compare the fields that matter for downstream scoring
    fields = [(c.start_line, c.end_line, c.symbol, c.kind, c.text) for c in leg]
    fields_new = [(c.start_line, c.end_line, c.symbol, c.kind, c.text) for c in new]
    check("ASTChunker: identical chunks (start,end,sym,kind,text)",
          fields == fields_new,
          f"legacy={len(leg)} chunks new={len(new)} chunks")


# ---------------------------------------------------------------------------
# Group 4 — BM25 + rerank (§ BM25 retrieval in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_hybrid_index_identical_scores(tmp: Path):
    case_dir = tmp / "CASE_hybrid"; case_dir.mkdir()
    p = case_dir / "x.py"; p.write_text(SAMPLE_SRC, encoding="utf-8")
    chunks_leg = legacy.ASTChunker().chunk_file(case_dir, p, repo_key="CASE")
    chunks_new = NewASTChunker().chunk_file(case_dir, p, repo_key="CASE")
    idx_leg = legacy.HybridIndex(boost_map=legacy.quantum_boost_map(1.8))
    idx_new = NewHybridIndex(boost_map=new_quantum_boost_map(1.8))
    idx_leg.build(chunks_leg)
    idx_new.build(chunks_new)
    query = "qiskit quantumcircuit measure cx rz dag"
    res_leg = idx_leg.search(query, topk=5)
    res_new = idx_new.search(query, topk=5)
    # Compare the (start, end, symbol) keys and the BM25 scores
    key_leg = [(h["start"], h["end"], h["symbol"], round(h["score"], 6)) for h in res_leg]
    key_new = [(h["start"], h["end"], h["symbol"], round(h["score"], 6)) for h in res_new]
    check("HybridIndex.search: identical ranking + scores",
          key_leg == key_new,
          f"legacy={key_leg} new={key_new}")


# ---------------------------------------------------------------------------
# Group 5 — selectors (§ Selectors in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_syntax_prior_identical():
    h = {"preview": "qc.cx(q[0], q[1])\nassert measure", "symbol": "run"}
    a = legacy.syntax_prior_of(h)
    b = new_syntax_prior_of(h)
    check("syntax_prior_of: identical", math.isclose(a, b, abs_tol=1e-12),
          f"legacy={a} new={b}")


def test_balanced_selector_identical():
    """The `balanced` selector is what the paper's best config uses.
    Ensure byte-identical selections on a pool of 6 synthetic hits."""
    pool = [
        {"score": 1.0, "re_score": 0.5, "file": "a.py", "symbol": "f", "start": 1, "end": 10},
        {"score": 0.9, "re_score": 0.7, "file": "a.py", "symbol": "g", "start": 11, "end": 20},
        {"score": 0.5, "re_score": 0.2, "file": "b.py", "symbol": "h", "start": 1, "end": 10},
        {"score": 0.8, "re_score": 0.4, "file": "b.py", "symbol": "i", "start": 5, "end": 15},
        {"score": 0.3, "re_score": 0.9, "file": "c.py", "symbol": "j", "start": 1, "end": 10},
        {"score": 0.1, "re_score": 0.3, "file": "a.py", "symbol": "k", "start": 21, "end": 30},
    ]
    pool_leg = [dict(h) for h in pool]
    pool_new = [dict(h) for h in pool]
    sel_leg = legacy.select_by_coverage_balanced(pool_leg, topk=2)
    sel_new = new_select_balanced(pool_new, topk=2)
    key_leg = [(h["file"], h["symbol"], h["start"], h["end"]) for h in sel_leg]
    key_new = [(h["file"], h["symbol"], h["start"], h["end"]) for h in sel_new]
    check("select_by_coverage_balanced (paper config): identical picks",
          key_leg == key_new, f"legacy={key_leg} new={key_new}")


def test_old_selector_fuzz_no_divergence():
    """Per REMAPPING.md §3.1: although `select_by_coverage_old` has a scope
    oddity in the legacy (uses `h["file"]` where we believe `best["file"]`
    was intended), the visible output is identical on realistic inputs.

    We prove this by fuzzing: 1,000 random pools, compare both implementations.
    Zero divergences is the pass criterion.
    """
    import random
    from src.retrieval import select_by_coverage_old as new_old
    rng = random.Random(42)
    divergences = 0
    trials = 1000
    for _ in range(trials):
        n = rng.randint(3, 10)
        pool = [{
            "file": rng.choice(["A.py", "B.py", "C.py", "D.py"]),
            "symbol": rng.choice(["a", "b", "c", "d", "e", "f"]),
            "start": rng.randint(1, 50),
            "end": rng.randint(51, 100),
            "score": rng.random(),
            "re_score": rng.random(),
        } for _ in range(n)]
        topk = rng.randint(1, 3)
        a = legacy.select_by_coverage_old([dict(h) for h in pool], topk=topk)
        b = new_old([dict(h) for h in pool], topk=topk)
        key = lambda hs: [(h["file"], h["symbol"], h["start"]) for h in hs]
        if key(a) != key(b):
            divergences += 1
    check(f"select_by_coverage_old: 0 divergences in {trials} random fuzz trials",
          divergences == 0,
          f"found {divergences} divergences")


# ---------------------------------------------------------------------------
# Group 6 — guardrails (§ Guardrail checks in REMAPPING.md)
# ---------------------------------------------------------------------------

def test_ast_ok_identical():
    good = "def f(): return 1\n"
    bad = "def f(): return 1 +\n"
    a_leg, _ = legacy._ast_ok(good)
    b_leg, _ = legacy._ast_ok(bad)
    a_new, _ = new_ast_ok(good)
    b_new, _ = new_ast_ok(bad)
    check("ast_ok: same verdict on good/bad",
          (a_leg, b_leg) == (a_new, b_new), f"legacy={(a_leg,b_leg)} new={(a_new,b_new)}")


def test_enforce_in_region_identical():
    edits = [
        {"file": "buggy.py", "start": 1, "end": 3, "replacement": "a"},
        {"file": "buggy.py", "start": 20, "end": 25, "replacement": "b"},
    ]
    allowed = [(1, 5)]
    a = legacy.enforce_in_region([dict(e) for e in edits], allowed)
    b = new_enforce_in_region([dict(e) for e in edits], allowed)
    check("enforce_in_region: identical filtered list",
          a == b, f"legacy={a} new={b}")


# ---------------------------------------------------------------------------
# Group 7 — dataset split determinism (§ Dataset iteration)
# ---------------------------------------------------------------------------

def test_deterministic_splits_match_legacy():
    """The legacy split ratio is 70/25/5; the new default is 70/15/15.
    We verify that feeding the legacy ratios gives the legacy result."""
    ids = [f"c/{i:02d}" for i in range(42)]
    a_tr, a_va, a_te = legacy.deterministic_splits(ids)
    b_tr, b_va, b_te = new_deterministic_splits(ids, (0.70, 0.25, 0.05))
    check("deterministic_splits @ (0.70, 0.25, 0.05): identical",
          (a_tr, a_va, a_te) == (b_tr, b_va, b_te),
          f"sizes legacy=({len(a_tr)},{len(a_va)},{len(a_te)}) "
          f"new=({len(b_tr)},{len(b_va)},{len(b_te)})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import tempfile
    print("=" * 72)
    print("Behavioral-equivalence tests: legacy/GRAP-Q.py vs new/src/")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Group 1
        test_tokenize_identical()
        test_top_tokens_query_identical()
        test_changed_lines_identical()
        # Group 2
        test_api_drift_identical()
        test_identifier_jaccard_identical()
        test_lines_prf1_matches_legacy_evaluate_candidate(tmp)
        test_distortion_flags_equivalent_per_remapping_3_2()
        # Group 3
        test_ast_chunker_identical(tmp)
        # Group 4
        test_hybrid_index_identical_scores(tmp)
        # Group 5
        test_syntax_prior_identical()
        test_balanced_selector_identical()
        test_old_selector_fuzz_no_divergence()
        # Group 6
        test_ast_ok_identical()
        test_enforce_in_region_identical()
        # Group 7
        test_deterministic_splits_match_legacy()

    print("=" * 72)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"[RESULT] passed={passed}  failed={failed}  total={len(RESULTS)}")
    if failed:
        print("\nFailures:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name}: {detail}")
        sys.exit(1)
    print("\n[OK] Legacy and new are behaviorally equivalent on every checked API.")
    print("     See REMAPPING.md §3 for the three documented intentional differences.")


if __name__ == "__main__":
    main()
