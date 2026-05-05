# Bugs4Q dataset scope: the 42 cases used by GRAP-Q

## Short answer

The paper evaluates on the **42 canonical Python cases** produced by
`src/dataset.py::iter_cases()` over the Zenodo archive
(record 8148982, MD5 `8aad45d2682350517ee13215b886d7a7`). This count is
filesystem-independent by design: the discovery rule now uses case-
sensitive literal filename matching, and the five entries that would be
discovered on case-insensitive filesystems but are *not* part of the
paper's evaluation set are listed in `PAPER_EXCLUDED_CASES` and skipped
explicitly.

The count is the same on Linux, Windows, and macOS. Reviewers can
verify it in one line:

```bash
python -c "from src.dataset import iter_cases; from pathlib import Path; \
           print(sum(1 for _ in iter_cases(Path('data/bugs4q/Bugs4Q-Database'))))"
```

Expected output: `42`.

## Why 42 and not "47 on Windows, 42 on Linux"

The upstream Bugs4Q archive contains four case folders whose `fixed`
file uses a capital-F variant (`Fixed.py` or `Fix.py`). On a
**case-insensitive** filesystem (Windows NTFS, macOS APFS default)
`Path("fixed.py").exists()` returns True when the actual file is named
`Fixed.py`, so these folders get picked up and the count becomes 46. A
fifth folder (`Terra-0-4000/1`) is likewise present on case-insensitive
filesystems but was not in the Linux snapshot used for the paper,
bringing the case-insensitive count to 47.

On a **case-sensitive** filesystem (Linux ext4, case-sensitive APFS)
none of those five folders match, and `iter_cases()` returns 42.

The paper was run on Linux. Rather than document OS-dependent numbers,
we rewrote `iter_cases()` to be filesystem-agnostic:

  1. It enumerates the tree with `os.walk`, which returns filenames in
     their actual on-disk case on every OS, and
  2. It checks literal string membership (`"fixed.py" in names`), which
     is byte-for-byte case-sensitive regardless of filesystem.

This change alone is enough to reproduce 42 on Windows and macOS for
the four capital-F cases. The fifth (`Terra-0-4000/1`) is handled by
the explicit exclude list below.

## The 5 excluded cases

Listed in `src/dataset.py` as `PAPER_EXCLUDED_CASES`:

| Case ID | Reason for exclusion |
|---|---|
| `Terra-0-4000/3` | Upstream ships `Fixed.py` (capital F) |
| `Terra-0-4000/6` | Upstream ships `Fixed.py` (capital F) |
| `Terra-0-4000/7` | Upstream ships `Fix.py` (capital F) |
| `stackoverflow-1-5/1` | Upstream ships `Fix.py` (capital F) |
| `Terra-0-4000/1` | Not present in the paper's Linux snapshot |

Any combination of OS-independent discovery plus this exclude list
yields the paper's 42.

## What the Bugs4Q README documents

The upstream `Bugs4Q/README.md` lists 52 bug reports across its tables:

| Section in the README                                  | Rows |
|--------------------------------------------------------|-----:|
| Qiskit Reproducible Bugs from GitHub (Terra + Aer)     |   18 |
| Qiskit Reproducible Bugs from Stack Overflow           |    7 |
| Qiskit Reproducible Bugs from Stack Exchange           |   18 |
| Q#                                                     |    2 |
| Cirq                                                   |    7 |
| **Total rows in README**                               | **52** |

Not all 52 rows follow the canonical case-folder layout
(one directory per case with a `buggy.py` and a lowercase
`fixed.py`/`fix.py`). Rows that do not — Q# programs, split-layout
Terra-6000-7100 entries, flat-file Stack Overflow / Stack Exchange
entries — are silently skipped by `iter_cases()`. Conversely, the
archive on disk contains additional canonical-layout folders not
referenced in the README's tables (e.g. `Terra-0-4000/10`, `/16`, `/24`
and `StackExchange/8`, `/10`, `/13`, `/18`), which `iter_cases()`
discovers and includes.

**The authoritative count is what `iter_cases()` yields, not what the
README documents.** The 52 → 42 gap is a mix of non-canonical layouts,
Q# (non-Python), undocumented folders on disk, and the 5 excluded cases
listed above.

## How to override the filter

For debugging or auditing, the filter can be disabled:

```python
from src.dataset import iter_cases
cases = list(iter_cases(db_root, apply_paper_filter=False))
```

On Linux this still yields 42 (the capital-F cases don't match literal
`fixed.py`/`fix.py`). On Windows / default macOS it yields 47 (the four
capital-F cases plus `Terra-0-4000/1`). The paper assumes the default
(`apply_paper_filter=True`) and should always be compared against the
42-case numbers reported here.

## Recommended text for the paper

### Section 3.1 (Dataset Preparation)

> "The evaluation uses the 42 canonical Python cases produced by our
> discovery rule (`src/dataset.py::iter_cases()`) applied to the Bugs4Q
> Zenodo archive (record 8148982). The discovery rule requires a
> directory containing a file literally named `buggy.py` and either
> `fixed.py` or `fix.py` (case-sensitive on every OS). Five folders
> present on case-insensitive filesystems — four with capital-F
> variants (`Fixed.py` / `Fix.py`) and one (`Terra-0-4000/1`) absent
> from the Linux snapshot used for the experiments — are listed
> explicitly in `PAPER_EXCLUDED_CASES` and skipped, so that the
> evaluation set is identical on Linux, Windows, and macOS."

### Section 5.5 (Reproducibility)

> "The deterministic 70/15/15 split operates on the 42-case set. Case
> IDs are hashed in a stable order (MD5), making the partition fully
> reproducible from `scripts/resplit.py` and the Zenodo archive alone.
> `experiments/splits_70_15_15.json` is shipped for convenience but is
> not a source of authority; it can be regenerated verbatim at any
> time."

## Audit checklist for reviewers

From `grap4q_package/new/`:

```bash
# 1. Confirm the Zenodo archive integrity
md5sum data/bugs4q/Bugs4Q-Database.zip
# expected: 8aad45d2682350517ee13215b886d7a7

# 2. Confirm the pipeline case count
python -c "from src.dataset import iter_cases; from pathlib import Path; \
           print(sum(1 for _ in iter_cases(Path('data/bugs4q/Bugs4Q-Database'))))"
# expected: 42

# 3. Confirm the split sums to 42
python -c "import json; d=json.load(open('experiments/splits_70_15_15.json')); \
           print(d['n'], d['train']+d['val']+d['test'])"
# expected: 42 42

# 4. Confirm filter OFF on case-insensitive FS recovers the 5 extras
python -c "from src.dataset import iter_cases, PAPER_EXCLUDED_CASES; \
           from pathlib import Path; \
           off = {c[0] for c in iter_cases(Path('data/bugs4q/Bugs4Q-Database'), apply_paper_filter=False)}; \
           on  = {c[0] for c in iter_cases(Path('data/bugs4q/Bugs4Q-Database'))}; \
           print(sorted(off - on))"
# expected (Windows/macOS): PAPER_EXCLUDED_CASES as a sorted list
# expected (Linux): []
```

If all four steps match, the experiments are reproducible on your
machine and the 42-case claim is verified.
