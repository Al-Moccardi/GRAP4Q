#!/usr/bin/env python3
"""
Deterministic re-split of Bugs4Q cases.

Addresses reviewer R3 C9: the original 70/25/5 split left only 3 TEST cases,
which the reviewer correctly called out as too small. This script produces
70/15/15 using the same hash-stable ordering used in GRAP-Q.py so results
stay reproducible.

Usage:
    python scripts/resplit.py \
        --db_root path/to/Bugs4Q-Database \
        --out experiments/splits_70_15_15.json \
        --ratios 0.70 0.15 0.15
"""
from __future__ import annotations

import argparse
import json
import os
from hashlib import md5
from pathlib import Path


# Must stay in sync with src/dataset.py::PAPER_EXCLUDED_CASES
PAPER_EXCLUDED_CASES = frozenset({
    "Terra-0-4000/1",
    "Terra-0-4000/3",
    "Terra-0-4000/6",
    "Terra-0-4000/7",
    "stackoverflow-1-5/1",
})


def iter_case_ids(db_root: Path, apply_paper_filter: bool = True):
    """Yield case IDs using the same rule as src/dataset.py::iter_cases.

    OS-independent: uses os.walk + literal filename membership.
    """
    for dirpath, _dirnames, filenames in os.walk(db_root):
        if "buggy.py" not in filenames:
            continue
        fixed_name = None
        for nm in ("fixed.py", "fix.py"):
            if nm in filenames:
                fixed_name = nm
                break
        if fixed_name is None:
            continue
        d = Path(dirpath)
        try:
            txt = (d / "buggy.py").read_text(encoding="utf-8", errors="replace")
            if not txt.strip():
                continue
        except Exception:
            continue
        cid = str(d.relative_to(db_root)).replace(os.sep, "/").replace("\\", "/")
        if apply_paper_filter and cid in PAPER_EXCLUDED_CASES:
            continue
        yield cid


def hash_stable_sort(case_ids: list[str]) -> list[str]:
    """Sort case IDs by MD5 hash — identical logic to GRAP-Q.py deterministic_splits."""
    return [c for c, _ in sorted(((c, md5(c.encode()).hexdigest()) for c in case_ids),
                                 key=lambda t: t[1])]


def split(ordered: list[str], ratios: tuple[float, float, float]) -> dict:
    r_tr, r_va, r_te = ratios
    if abs(r_tr + r_va + r_te - 1.0) > 1e-6:
        raise ValueError(f"Ratios must sum to 1.0, got {r_tr + r_va + r_te}")
    n = len(ordered)
    n_tr = int(round(r_tr * n))
    n_va = int(round(r_va * n))
    n_te = max(0, n - n_tr - n_va)
    train = ordered[:n_tr]
    val = ordered[n_tr:n_tr + n_va]
    test = ordered[n_tr + n_va:]
    return {
        "n": n,
        "train": len(train), "val": len(val), "test": len(test),
        "train_ids": train, "val_ids": val, "test_ids": test,
        "ratios": {"train": r_tr, "val": r_va, "test": r_te},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db_root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ratios", nargs=3, type=float, default=[0.70, 0.15, 0.15],
                    help="train val test ratios (must sum to 1.0)")
    args = ap.parse_args()

    ids = list(iter_case_ids(args.db_root))
    if not ids:
        raise SystemExit(f"[ERROR] No cases found under {args.db_root}")
    ordered = hash_stable_sort(ids)
    out = split(ordered, tuple(args.ratios))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[OK] Split written to {args.out}")
    print(f"     n={out['n']}, train={out['train']}, val={out['val']}, test={out['test']}")


if __name__ == "__main__":
    main()
