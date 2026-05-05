#!/usr/bin/env python3
"""One-shot verification script — runs both test suites and the statistical
test, prints a clean summary. No Ollama, no GPU, no dataset required.

Usage:
    cd new/
    python scripts/verify_all.py
"""
from __future__ import annotations

import inspect
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_ROOT = HERE.parent
sys.path.insert(0, str(NEW_ROOT))


def run_smoke() -> tuple[int, int, int]:
    import tests.test_smoke as T
    passed = failed = skipped = 0
    for name in [n for n in dir(T) if n.startswith("test_")]:
        fn = getattr(T, name)
        try:
            sig = inspect.signature(fn)
            if "tmp_path" in sig.parameters:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            passed += 1
        except Exception as e:
            if type(e).__name__ in ("Skipped", "_Skip"):
                skipped += 1
            else:
                failed += 1
                print(f"    FAIL {name}: {e}")
    return passed, skipped, failed


def run_equivalence() -> int:
    p = subprocess.run([sys.executable,
                        str(NEW_ROOT / "tests" / "test_equivalence_with_legacy.py")],
                       capture_output=True, text=True)
    print(p.stdout, end="")
    if p.returncode != 0:
        print(p.stderr, end="")
    return p.returncode


def run_stats() -> int:
    combined = NEW_ROOT / "experiments" / "combined_results_val.csv"
    out = Path(tempfile.gettempdir()) / "grap4q_stat_report.md"
    p = subprocess.run(
        [sys.executable, str(NEW_ROOT / "scripts" / "run_statistical_tests.py"),
         "--combined", str(combined), "--out", str(out)],
        capture_output=True, text=True)
    print(p.stdout, end="")
    if p.returncode != 0:
        print(p.stderr, end="")
    return p.returncode


def main() -> None:
    print("=" * 72)
    print("GRAP-Q verification — smoke + equivalence + statistical significance")
    print("=" * 72)
    print()
    print("[1/3] Smoke tests (refactored modules work in isolation)")
    sp, ss, sf = run_smoke()
    print(f"      passed={sp}  skipped={ss}  failed={sf}")
    print()
    print("[2/3] Behavioral equivalence (legacy vs new, 17 checks + 1,000-trial fuzz)")
    rc_eq = run_equivalence()
    print()
    print("[3/3] Statistical significance of +0.08 F1 claim (Wilcoxon on VAL)")
    rc_st = run_stats()
    print()
    print("=" * 72)
    if sf == 0 and rc_eq == 0 and rc_st == 0:
        print("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED — see output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
