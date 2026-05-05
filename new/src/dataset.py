"""Dataset iteration + deterministic splits.

The discovery rule used throughout GRAP-Q is intentionally strict and now
filesystem-independent:

    A case is yielded iff its directory contains a file literally named
    `buggy.py` AND a file literally named `fixed.py` or `fix.py`
    (case-sensitive on every OS), and `buggy.py` is non-empty UTF-8.

Previously we used `Path.exists()` which, on case-insensitive filesystems
(Windows NTFS and macOS APFS default), would match capital-F variants such
as `Fixed.py` / `Fix.py`. That silently inflated the case count to 47 on
Windows/macOS while Linux gave 42. The paper's experiments were run on
Linux and report 42. To guarantee the same 42 on every OS we now:

  1. Enumerate the filesystem with `os.walk`, which returns filenames in
     their actual on-disk case, and
  2. Check literal string membership (`"fixed.py" in names`), which is
     byte-for-byte case-sensitive.

Additionally, we maintain `PAPER_EXCLUDED_CASES`: the five case IDs that
are present on case-insensitive filesystems but not in the paper's
evaluation set. These are excluded by default so that every downstream
script (splits, analysis, baselines, statistical tests) operates on the
same 42-case set as the paper.
"""
from __future__ import annotations

import os
from hashlib import md5
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# The five case folders present in the upstream Bugs4Q archive that are
# NOT part of the paper's 42-case evaluation set. Four of them ship with
# capital-F filename variants (`Fixed.py` / `Fix.py`) that do not match our
# lowercase discovery rule on Linux; the fifth (`Terra-0-4000/1`) is
# likewise absent from the Linux snapshot used for the paper.
#
# Keeping them listed explicitly makes the paper's case set the single
# source of truth across every OS.
# ---------------------------------------------------------------------------
PAPER_EXCLUDED_CASES: frozenset[str] = frozenset({
    "Terra-0-4000/1",
    "Terra-0-4000/3",
    "Terra-0-4000/6",
    "Terra-0-4000/7",
    "stackoverflow-1-5/1",
})


def iter_cases(
    db_root: Path,
    apply_paper_filter: bool = True,
) -> Iterator[tuple[str, Path, Path, Path]]:
    """Yield ``(case_id, case_dir, buggy_path, fixed_path)`` for each valid case.

    Parameters
    ----------
    db_root
        Root of the extracted ``Bugs4Q-Database`` archive.
    apply_paper_filter
        When True (default) cases listed in :data:`PAPER_EXCLUDED_CASES` are
        skipped. Set to False to obtain the raw discovery set - useful
        only for debugging / auditing; all paper numbers assume True.

    Notes
    -----
    Uses ``os.walk`` rather than ``Path.rglob`` to obtain filenames in their
    actual on-disk case. Filename comparisons are then literal string
    equality, making discovery identical on case-sensitive (Linux) and
    case-insensitive (Windows, default macOS APFS) filesystems.
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
        buggy = d / "buggy.py"
        fixed = d / fixed_name

        try:
            txt = buggy.read_text(encoding="utf-8", errors="replace")
            if not txt.strip():
                continue
        except Exception:
            continue

        cid = str(d.relative_to(db_root)).replace(os.sep, "/").replace("\\", "/")
        if apply_paper_filter and cid in PAPER_EXCLUDED_CASES:
            continue
        yield cid, d, buggy, fixed


def hash_stable_sort(case_ids: list[str]) -> list[str]:
    """Return ``case_ids`` sorted by MD5 hash of the id (same as legacy code)."""
    return [c for c, _ in sorted(((c, md5(c.encode()).hexdigest()) for c in case_ids),
                                 key=lambda t: t[1])]


def deterministic_splits(
    case_ids: list[str],
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> tuple[list[str], list[str], list[str]]:
    """Hash-stable split: train / val / test. Identical ordering to GRAP-Q.py."""
    r_tr, r_va, _r_te = ratios
    ordered = hash_stable_sort(case_ids)
    n = len(ordered)
    n_tr = int(round(r_tr * n))
    n_va = int(round(r_va * n))
    return ordered[:n_tr], ordered[n_tr:n_tr + n_va], ordered[n_tr + n_va:]
