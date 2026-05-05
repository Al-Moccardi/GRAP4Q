# Bugs4Q dataset layout & usage

GRAP-Q reuses the public
[Bugs4Q dataset](https://zenodo.org/records/8148982) (Pengzhan et al. 2023)
with no modifications. This document explains the directory layout that
GRAP-Q expects after download.

> **See also**: [`dataset_scope.md`](dataset_scope.md) explains precisely
> which cases are included in the evaluation (47 canonical Python cases on
> Windows) and which of the 52 entries in the upstream Bugs4Q README are
> excluded and why.

## Download

```bash
python scripts/download_bugs4q.py
```

This fetches `Bugs4Q-Database.zip` from Zenodo record `8148982`, verifies
its MD5 checksum (`8aad45d2682350517ee13215b886d7a7`), and extracts it to
`data/bugs4q/Bugs4Q-Database/`.

## Expected on-disk layout

After extraction you should see:

```
data/bugs4q/Bugs4Q-Database/
├── README.md                 (the original Bugs4Q README)
├── Aer/
│   ├── bug_1/
│   │   ├── buggy.py          ← always present
│   │   └── fixed.py          ← always present (or fix.py; both accepted)
│   ├── bug_7/
│   │   ├── buggy.py
│   │   └── fix.py
│   └── ...
├── Cirq/
├── Program/                  (not used by GRAP-Q — Q# samples)
├── Q#/                       (not used by GRAP-Q — Q# samples)
├── StackExchange/
├── StackExchange-page-1-25/
├── StackExchange_2/
├── Terra-0-4000/
├── Terra-4001-6000/
├── Terra-6000-7100/
├── stackoverflow-1-5/
└── stackoverflow-6-10/
```

## Case discovery rule

`src/dataset.py::iter_cases()` walks the database looking for directories
containing **both** of:

1. `buggy.py` — the buggy source (non-empty, valid UTF-8 or decodable)
2. `fixed.py` **or** `fix.py` — the human-corrected source

Directories missing either file are silently skipped (with a `[WARN]` line
in verbose mode). This yields **42 reproducible cases** for the paper's
evaluation, matching Table 1 of the manuscript and the `n=42` in
`experiments/splits_70_15_15.json`.

## Case naming convention

The case ID is the directory's relative path from `Bugs4Q-Database/`, with
forward slashes on all platforms. Examples:

- `Terra-0-4000/8` — Terra issue #8 from the first thousand-issue window
- `StackExchange/17` — question 17 in the StackExchange subset
- `Aer/bug_1` — first Aer-tagged bug
- `Cirq/5` — fifth Cirq-tagged bug

These IDs are used verbatim as keys in the splits JSON, in all CSV output,
and in the per-case plots.

## Fix file conventions

Bugs4Q is internally inconsistent about whether the corrected file is named
`fixed.py` or `fix.py`. GRAP-Q accepts either, but prefers `fixed.py` when
both exist. Some cases additionally contain `mod.py`, `modify.py`, or
scratch files that GRAP-Q ignores.

## What GRAP-Q does NOT require

- No `test_*.py` files — Bugs4Q cases generally have no unit tests, and
  the paper's `pytest` oracle (Section 4.4) is descriptive of capability,
  not of the dataset. See `docs/reproducing_results.md` §4 for caveats.
- No `requirements.txt` per case — GRAP-Q runs the LLM on source as-is
  without executing the buggy program against a live interpreter.

## License of the dataset

The Bugs4Q benchmark is released under the license declared in its own
`README.md`. Please consult
<https://github.com/Z-928/Bugs4Q> and
<https://zenodo.org/records/8148982> for current terms.
