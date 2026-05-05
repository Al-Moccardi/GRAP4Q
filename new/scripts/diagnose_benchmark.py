"""Inspect the synthetic benchmark report to localise why edits were
or weren't applied. Run from the repo root:

    python scripts/diagnose_benchmark.py
"""
import json
from pathlib import Path

REPORT = Path("experiments/synthetic_benchmark_report.json")
TEST_SET = Path("experiments/synthetic_test_set")


def main():
    r = json.loads(REPORT.read_text(encoding="utf-8"))
    for row in r["rows"]:
        cid = row["id"]
        injected = row["injected"]
        remaining = row["remaining"]
        fixed = row.get("fixed", [])
        attempts = row["attempts"]
        edits = row["edits_applied"]
        ranges = row.get("allowed_ranges", [])
        err = row.get("error")
        latency = row.get("llm_latency_s", 0)

        print("=" * 70)
        print("CASE      : " + cid)
        print("INJECTED  : " + ", ".join(injected))
        print("FIXED     : " + (", ".join(fixed) if fixed else "(none)"))
        print("REMAINING : " + (", ".join(remaining) if remaining else "(none)"))
        print("ATTEMPTS  : " + str(attempts) + "  (1 = first proposal accepted, 3 = max; gave up)")
        print("EDITS     : " + str(edits))
        print("RANGES    : " + str(ranges))
        print("LATENCY   : " + ("%.1fs" % latency))
        if err:
            print("ERROR     : " + str(err))

        # Compare patched vs original to detect "no-op" patches.
        original_path = TEST_SET / cid / "buggy.py"
        if original_path.exists():
            original = original_path.read_text(encoding="utf-8")
            patched = row.get("patched_source", original)
            if patched == original:
                print("PATCHED   : *** identical to input (no edits took effect) ***")
            else:
                # Show the diff.
                import difflib
                diff = list(difflib.unified_diff(
                    original.splitlines(),
                    patched.splitlines(),
                    fromfile="buggy.py",
                    tofile="patched.py",
                    lineterm="",
                    n=1,
                ))
                if diff:
                    print("PATCH DIFF:")
                    for line in diff[:30]:
                        print("    " + line)
        print()


if __name__ == "__main__":
    main()