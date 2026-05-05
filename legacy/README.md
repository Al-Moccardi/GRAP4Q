# `legacy/` — the original code that produced the paper's results

This folder contains the source files used to generate every number,
figure, and table in the paper as submitted. **Nothing in this folder has
been modified**; the files are byte-identical to the original repository.

## Files

| File | Purpose |
|---|---|
| `GRAP-Q.py` | The monolithic 1,242-line entry point that ran all three modes (diagnostic / test / single) for the paper's experiments. |
| `loading.py` | Original Zenodo downloader for the Bugs4Q dataset. |
| `requirements.txt` | Original (unpinned) Python dependencies. |
| `splits_70_25_5.json` | **Frozen** train / val / test partition that produced the paper's val results. See "Split provenance" below. |

## Why this folder exists

Reviewers legitimately want to verify that the refactor in `../new/` did not
retroactively change the code that produced Figs 13–17 or Section 6.3's
headline numbers (mean Lines-F1 = 0.245 vs 0.172, +42% relative). Keeping
`legacy/` untouched makes the provenance chain explicit:

1. `legacy/GRAP-Q.py` + the original `data/bugs4q/Bugs4Q-Database/` →
   `results/grap_vs_llm_deep/combined_results_val.csv` (the source of every
   validation-set number in the paper).
2. `new/experiments/combined_results_val.csv` is a **byte-for-byte copy** of
   the file in (1). It is not a re-run.
3. `new/scripts/run_statistical_tests.py` reads (2) and computes Wilcoxon
   p = 0.0312. It never regenerates (1).

## Split provenance — the single most important thing to understand

The paper reports results on **12 paired validation cases**. These come from
the deterministic 70/25/5 hash-stable split of the **47 raw discovery cases**
returned by the original `iter_cases()` function on the dev machine on which
the experiments ran:

```
47 raw cases  →  hash-stable MD5 sort  →  70 / 25 / 5 split  →  33 train / 12 val / 2 test
```

All val numbers in the paper trace to those exact 12 cases, frozen here in
`splits_70_25_5.json`.

### What changed after the paper was written

Two things happened **after** the val results were already in the can:

1. **OS-portability fix.** The original `iter_cases()` matched filenames in
   a way that returned 47 cases on case-insensitive filesystems but 42 on
   case-sensitive Linux. To make discovery byte-for-byte identical on every
   OS, `iter_cases()` was rewritten with `os.walk` + literal string match,
   plus a `PAPER_EXCLUDED_CASES = {Terra-0-4000/{1,3,6,7}, stackoverflow-1-5/1}`
   filter applied by default. Today, both `legacy/GRAP-Q.py` and
   `new/src/dataset.py` ship with this filter on, so a fresh
   filesystem-discovery run returns **42 cases**, not 47.
2. **Wider test split for reviewer R3 C9.** A separate `splits_70_15_15.json`
   was added (29 / 6 / 7) so the test partition reports more than 2 cases.
   This sweep is independent of the paper's primary split.

### Why this does NOT change any val numbers

- None of the 5 cases in `PAPER_EXCLUDED_CASES` were ever in the val
  partition. The 12 val cases are stable under both the 47-case and the
  42-case discovery.
- The frozen `splits_70_25_5.json` records the exact 33/12/2 partition. As
  long as scripts load it instead of recomputing the split from filesystem
  discovery, the published numbers reproduce byte-for-byte on any OS.

### Why the split file is necessary

If you delete `splits_70_25_5.json` and re-run `GRAP-Q.py`, the script will
fall back to recomputing the split via `deterministic_splits()`. With the
post-fix discovery (42 cases) and the legacy 70/25/5 ratio, that gives a
**29 / 10 / 3** partition — different from the paper's 33 / 12 / 2. The
JSON is the canonical source of truth; do not delete it.

## Running the legacy code

Exactly as in the paper's original README:

```bash
cd legacy
pip install -r requirements.txt
python loading.py                  # download Bugs4Q (note: this version marks
                                   # the main archive optional — see bug fix
                                   # in new/scripts/download_bugs4q.py)

# All paper modes load splits_70_25_5.json by default:
python GRAP-Q.py --mode diagnostic --best_config results/qeval_ablation_plus/best_config.txt
python GRAP-Q.py --mode test --best_config ...
python GRAP-Q.py --mode single --single_file bug.py --gold_fixed fix.py
```

Ollama must be running locally with the models `qwen2.5-coder:14b-instruct`
and `llama3.1:8b` pulled — see `../new/docs/ollama_setup.md`.

## Known issues in the legacy code (kept as-is for provenance)

Documented but **not patched** here, because patching would alter the very
code whose outputs are cited:

1. **`select_by_coverage_old` diversity bonus oddity.**
   `seen_files.add(h["file"])` after the inner loop references the
   last-iterated hit, not the selected `best` hit. See `../REMAPPING.md`
   §3.1. Verified empirically to be observationally invisible: a 1,000-trial
   random fuzz found zero divergences between the legacy and cleaned-up
   versions. The paper's headline configuration uses the `balanced`
   selector, not `old`, so the oddity cannot affect the +0.073 F1 claim.
2. **`distortion_flags` NaN expression.** `bool(drift!=drift and False or
   (drift>0.40))` collapses to `bool(drift>0.40)`. Behaviorally equivalent
   to the cleaner form used in `../new/`, just harder to read.
3. **`loading.py` requirement flag.** The main dataset archive is marked
   `required=False`. A fresh clone downloads nothing unless you flip the
   flag.
4. **Discovery method.** `iter_cases()` already includes the OS-portability
   fix (`os.walk` + literal string match + `PAPER_EXCLUDED_CASES` filter).
   The version that originally produced the 47-case discovery on the dev
   machine has been superseded; the frozen `splits_70_25_5.json` preserves
   the resulting partition.

All four are fully disclosed in `../REMAPPING.md` and verified equivalent
(or scoped) by `../new/tests/test_equivalence_with_legacy.py`.

## If you want the exact figures from the paper

Run `legacy/GRAP-Q.py --mode diagnostic`. The refactored `../new/` code
focuses on metrics reproducibility and new baselines; it does not attempt
to re-render the exact plots. The legacy code is and remains the canonical
figure generator.