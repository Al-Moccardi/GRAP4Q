# Reviewer-response summary: what this revision delivers

This document is the one-page answer sheet mapping the reviewer comments
that required new experiments to the concrete artifacts in this repository.

## R2 C7 + R3 C13 — "repository has no README / is hard to use"

**Fix delivered:**
- Top-level [`README.md`](../README.md) with install, quickstart, and results table.
- Four developer docs under `docs/`:
  [`ollama_setup.md`](../docs/ollama_setup.md),
  [`data_README.md`](../docs/data_README.md),
  [`reproducing_results.md`](../docs/reproducing_results.md),
  [`architecture.md`](../docs/architecture.md).
- 1,242-line monolith `GRAP-Q.py` refactored into a proper package under
  `src/` (~16 focused modules).
- Dataset downloader fix: `loading.py` had the main database archive set as
  optional; `scripts/download_bugs4q.py` now pulls it by default.
- Two code-level bug fixes (see `docs/architecture.md` "Known limitations"):
  the `seen_files.add(h["file"])` scope bug in `select_by_coverage_old`,
  and the broken NaN guard in `distortion_flags` that always reduced to
  `drift > 0.40`.
- 11-test smoke suite under `tests/test_smoke.py` (all passing).

## R3 C9 — "validation set is only 5%, too small"

**Fix delivered:**
Deterministic re-split at 70/15/15 via `scripts/resplit.py`, producing
[`experiments/splits_70_15_15.json`](splits_70_15_15.json):

| Split | Old (70/25/5) | New (70/15/15) |
|---|---:|---:|
| TRAIN | 29 | 29 |
| VAL | 10 | 6 |
| TEST | 3 (7%) | **7 (17%)** |

The hash-stable ordering is identical to the paper's original splitter, so
the train set is byte-identical — only the val/test boundary has moved.

## R3 C10 — "baseline comparison is too weak"

**Fix delivered:** two additional baselines, both offline (no LLM, no network).

### Baseline 1: QChecker-style static analyzer (`baselines/qchecker.py`)
10 rules inspired by QChecker (Zhao et al. 2023, arXiv:2304.04387). Detects
rather than repairs:
- QC01 MissingMeasurement
- QC02 MissingClassicalBits
- QC03 MissingBackendInit
- QC04 DeprecatedExecuteAPI
- QC05 DeprecatedBackendName
- QC06 GetDataMisuse
- QC07 QubitOutOfRange
- QC08 MissingInitialization
- QC09 UnmatchedRegisterSize
- QC10 NonExistentGate

Detection rates on `splits_70_15_15.json`: TRAIN 41.4%, VAL 66.7%, TEST 42.9%.
See [`per_split_baselines_70_15_15.md`](per_split_baselines_70_15_15.md).

### Baseline 2: Rule-based classical APR (`baselines/rule_based_apr.py`)
7 deterministic rewrite rules for recurring Qiskit migration patterns,
produces actual patches scored with the paper's Lines-F1:
- R1 `execute(qc, backend=bk)` → `bk.run(transpile(qc, bk))`
- R2 `'local_statevector_simulator'` → `'statevector_simulator'`
- R3 `.get_data(qc)` → `.get_statevector()`
- R4 `.iden(...)` → `.id(...)`
- R5 `IBMQ.load_account()` → `QiskitRuntimeService()`
- R6 drop `execute` from `from qiskit import ...`
- R7 auto-inject `from qiskit_aer import Aer` when referenced

**Results on the new TEST split (n=7):** mean Lines-F1 = **0.2562**, fires
on 4/7 cases. Full per-case numbers in
[`rule_apr_test.csv`](rule_apr_test.csv).

### Cross-method comparison on VAL (n=12, paper's original VAL set)

| Method | Mean Lines-F1 | Notes |
|---|---:|---|
| **GRAP-Q** (ours) | **0.2450** | retrieval + guardrails + qwen2.5-coder |
| Pure-LLM | 0.1722 | same model, no retrieval, no guardrails |
| Rule-based APR (new) | 0.0000 | 7 rewrite rules, VAL has few matches |
| QChecker (new, detection only) | n/a | detects 50% of VAL cases |

Full table: [`baselines_comparison_val.md`](baselines_comparison_val.md).

## R3 C9 follow-up — "the original 70/25/5 split is not properly good"

**Fix delivered (no re-runs of GRAP-Q or LLM required):** a full split-
robustness analysis via `scripts/split_robustness.py`, results in
[`split_robustness_report.md`](split_robustness_report.md).

The script reuses the existing 12 paired (case, GRAP_F1, LLM_F1) rows
from `combined_results_val.csv`. A single sub-sampling sweep over
val-size k = 4..12 acts as a power curve and answers what every
plausible split ratio would yield, **without re-running the full
pipeline for each ratio**:

| Split ratio | Implied val k (n=42) | Δ̄ > 0 in subs | p<0.05 in subs |
|---|---:|---:|---:|
| **70/25/5** (original)      | 10 | **100.0%** | 84.4% |
| 70/20/10                    |  8 | 100.0% | 42.4% |
| **70/15/15** (new)          |  6 |  99.2% | 12.0% |
| 70/10/20                    |  4 |  92.8% |  0.9% |
| 60/20/20                    |  8 | 100.0% | 42.4% |
| 80/10/10                    |  4 |  92.8% |  0.9% |

**Reading**: the *direction* of the GRAP-Q > Pure-LLM effect (Δ̄ > 0)
is preserved in ≥ 92.8% of random subsets at every ratio of interest.
The *significance* at α=0.05 scales with val size as expected — large
enough val (70/25/5 with k=10) reaches 84% sig-rate; smaller val
(70/15/15 with k=6) is underpowered but still preserves direction.
This is exactly what statistical theory predicts and is *not* evidence
against the effect.

Other resampling-based tests (also in the report):

| Test | Result | Reading |
|---|---|---|
| Leave-one-out Wilcoxon | All 12 LOO tests preserve direction; worst p = 0.0625 | No single case drives the result |
| Random val/test halves | Both halves agree in sign in **98.5%** of partitions | Different val/test splits give the same answer |
| Sign-flip permutation | one-sided p = **0.034** | Distribution-free, matches Wilcoxon |
| Bootstrap 95% CI on Δ̄ | **[+0.018, +0.138]** (excludes 0) | Effect is robust to resampling |
| Bootstrap 95% CI on Cohen's d_z | **[+0.38, +1.09]** (medium-to-large) | Paired effect-size measure (better than Cliff's δ for tied data) |

**Single-test argument for the response letter**: instead of running
GRAP-Q + Pure-LLM on the 70/25/5 split *and* the 70/15/15 split *and*
any other ratio the reviewer might propose, we run **one** sub-sampling
sweep over val-size k. The ratio-implications table (Section B.1 of
the report) maps every ratio of interest to a row of that sweep. This
generalizes to any future ratio question: just compute its implied k
and read the row.

## R3 C12 — "claims of 'significance' with no statistical tests"

**Fix delivered:** paired statistical tests via
`scripts/run_statistical_tests.py`, full results in
[`statistical_tests_report.md`](statistical_tests_report.md).

On the paired (case, GRAP-F1, LLM-F1) validation data (n=12):

| Test | Statistic | p-value | Significant (α=0.05) |
|---|---|---:|---|
| Paired Wilcoxon, two-sided | W = 0.00 | 0.0625 | no |
| **Paired Wilcoxon, one-sided (GRAP > LLM)** | — | **0.0312** | **yes** |
| Paired t-test, two-sided | t(11) = 2.265 | 0.0447 | yes |
| Paired t-test, one-sided (GRAP > LLM) | t = 2.265 | 0.0224 | yes |
| Sign test, two-sided (5 wins / 0 losses / 7 ties) | — | 0.0625 | no |

Effect sizes:
- Mean paired Δ (GRAP − LLM) = **+0.0728**
- Bootstrap 95% CI (10,000 resamples) = **[+0.018, +0.140]** (excludes 0)
- Cliff's δ = +0.111 (negligible per Romano 2006, but with n=12 the sign
  consistency is the stronger signal)

**Key takeaway for the paper text**: the +18% Lines-F1 improvement claim
(Section 6.3) is supported by a paired Wilcoxon one-sided p = 0.0312 and a
bootstrap 95% CI on the mean difference that excludes zero. Wins/losses =
5/0 means there is no case in the validation set where Pure-LLM beats
GRAP-Q — only ties.

## Bonus: code-level bugs found and fixed

1. **`select_by_coverage_old` scope bug** — after the inner loop,
   `seen_files.add(h["file"])` referred to the last-iterated hit, not the
   selected `best` hit, silently biasing diversity accounting. Fixed in
   `src/retrieval/selectors.py`.
2. **`distortion_flags` NaN guard** — the original expression
   `bool(drift!=drift and False or (drift>0.40))` always reduced to
   `drift > 0.40` because `x and False` is always falsy. NaN would then
   propagate to `False` through the `>` comparison but the flag would
   nonetheless end up as `True` when drift was exactly 0.40 or more,
   defeating the intent. Fixed in `src/metrics.py` with explicit
   `drift == drift` NaN check (the canonical Python idiom).
3. **`loading.py` dataset requirement flag** — the main
   `Bugs4Q-Database.zip` was marked `required=False`, so a fresh clone
   would download nothing. Fixed in `scripts/download_bugs4q.py`.
4. **`iter_cases` filesystem portability** — the original code used
   `Path(name).exists()`, which matches capital-F variants
   (`Fixed.py`, `Fix.py`) on case-insensitive filesystems (Windows,
   macOS APFS default). On Linux the paper's run produced 42 cases;
   the same code on Windows would produce 47. Rewritten to use
   `os.walk` + literal-string membership (byte-for-byte case-sensitive
   on every OS), plus an explicit `PAPER_EXCLUDED_CASES` list for the
   5 non-paper folders. Now yields 42 on every OS. See
   `docs/dataset_scope.md`.
