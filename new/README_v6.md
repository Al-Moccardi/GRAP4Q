# GRAP-Q: Guarded Retrieval-Augmented Patching for Quantum Code (refactored)

> **Note**: this is the `new/` folder of the two-folder reproducibility
> package. The original, untouched code that produced the paper's results
> lives in the sibling `../legacy/` folder. See `../REMAPPING.md` for the
> line-by-line mapping and `tests/test_equivalence_with_legacy.py` for the
> behavioral-equivalence proof (17 tests, all passing).

GRAP-Q is an LLM-based program-repair framework for quantum Python programs
(Qiskit, Cirq, Amazon Braket, PennyLane). It combines domain-aware code
retrieval (BM25 + optional cross-encoder re-ranking) with a guarded patching
agent that proposes minimal, span-localized edits and validates them against
quantum-aware guardrails before applying.

This repository is the reproducibility package for the paper
**"GRAP4Q: An LLM-based Framework for Quantum Coding Assistance"**
(Amato, Cirillo, Ghosh, Moccardi — University of Naples Federico II).

---

## What's new in this revision (v0.2.0)

- Monolithic `GRAP-Q.py` (1,242 lines) refactored into a proper package under
  `src/` with separate modules for retrieval, patching, guardrails, metrics,
  dataset handling, and the Ollama client.
- **Two new offline baselines** (no LLM required): a QChecker-style static
  analyzer and a rule-based classical APR patcher. Both are run end-to-end
  against Bugs4Q with per-case Lines-F1 scores.
- **Statistical tests**: paired Wilcoxon signed-rank + paired t-test +
  Cliff's delta + bootstrap 95% CI on per-case Lines-F1.
- **Wider robustness split**: new `70/15/15` deterministic split (the paper's
  primary split is **70/25/5** — see "Reproducing the paper's numbers" below).
- Two bug fixes in the original code: a variable-scope bug in
  `select_by_coverage_old`'s diversity accounting, and a broken NaN guard
  in `distortion_flags`.
- Full developer documentation under `docs/`.

---

## Reproducing the paper's numbers — read this first

The paper's val results (Tables 3–4, Figs 13–17, every Lines-F1 number in
Sect. 6.3) were generated on the deterministic **70/25/5** hash-stable split
of the original 47-case discovery: **33 train / 12 val / 2 test**. The exact
partition is frozen in `experiments/splits_70_25_5.json` and is loaded by
default by `scripts/run_grap4q.py`.

### Why a frozen split file is necessary

The post-paper OS-portability fix added a `PAPER_EXCLUDED_CASES` filter to
`src/dataset.py::iter_cases`, returning **42 cases on every OS** (Linux had
always returned 42; Windows / macOS had returned 47 because of
case-insensitive filesystem matching). If you ran `scripts/resplit.py
--ratios 0.70 0.25 0.05` against today's discovery, you would get a
**29 / 10 / 3** partition rather than the paper's 33 / 12 / 2.

The 12 val cases themselves are unaffected — none of the 5 filtered cases
were ever in the val partition. The val cases are stable. Only the
train/test allocation would shift.

To make the published numbers reproducible on any filesystem regardless of
the discovery method, the partition is stored as a flat JSON file. Scripts
load it instead of recomputing.

### Two split files, two purposes

| File | Cases | Split | Purpose |
|---|---|---|---|
| `experiments/splits_70_25_5.json` | 47 | 33 / 12 / 2 | **Primary — produced every paper number on val** |
| `experiments/splits_70_15_15.json` | 42 | 29 / 6 / 7 | Robustness sweep added for reviewer R3 C9 |

Both files are deterministic and reproducible from the dataset. The first
loads on every paper-reproducing script by default; the second is opt-in via
`--splits experiments/splits_70_15_15.json`.

---

## Quickstart

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Download the Bugs4Q dataset

```bash
python scripts/download_bugs4q.py
# → data/bugs4q/Bugs4Q-Database/
```

### 3. Set up Ollama (for LLM-backed modes only)

See [`docs/ollama_setup.md`](docs/ollama_setup.md) for full instructions.
Summary:

```bash
# Install ollama from https://ollama.com
ollama serve &                              # start the daemon
ollama pull qwen2.5-coder:14b-instruct      # ~9 GB
ollama pull llama3.1:8b                     # ~5 GB (for query rewriting)
```

### 4. Run things

```bash
# === Reproduce the paper's val numbers (default) ===
# Loads experiments/splits_70_25_5.json automatically.
python scripts/run_grap4q.py --mode diagnostic
python scripts/run_purellm.py --which val

# === Run on the wider 70/15/15 robustness split (R3 C9) ===
python scripts/run_grap4q.py --mode test \
    --splits experiments/splits_70_15_15.json
python scripts/run_purellm.py --which test \
    --splits experiments/splits_70_15_15.json

# === Offline baselines (no LLM, no network) ===
python baselines/rule_based_apr.py --db_root data/bugs4q/Bugs4Q-Database \
    --splits experiments/splits_70_25_5.json --which val \
    --out_csv experiments/rule_apr_val.csv
python baselines/qchecker.py --db_root data/bugs4q/Bugs4Q-Database \
    --filter_cases experiments/splits_70_25_5.json \
    --out experiments/qchecker_findings.json

# === Statistical tests on the published val results ===
python scripts/run_statistical_tests.py \
    --combined experiments/combined_results_val.csv \
    --out experiments/statistical_tests_report.md
# → n=12, mean Δ=+0.0728, Wilcoxon one-sided p=0.0312

# === Regenerate a split (advanced — not needed for paper reproduction) ===
python scripts/resplit.py \
    --db_root data/bugs4q/Bugs4Q-Database \
    --out experiments/splits_70_15_15_fresh.json \
    --ratios 0.70 0.15 0.15
# Note: this uses the post-fix discovery (42 cases). To regenerate the
# 47-case paper split you would need to disable PAPER_EXCLUDED_CASES.
```

---

## Results on the VAL split (12 cases, from `experiments/`)

| Method | Mean Lines-F1 | Notes |
|---|---|---|
| **GRAP-Q (ours)** | **0.245** | retrieval + guardrails + qwen2.5-coder |
| Pure-LLM | 0.172 | same model, no retrieval, no guardrails |
| Rule-based APR | 0.000 | 7 deterministic rules, no LLM |
| QChecker (detection only) | — | 50.0% detection rate (6/12 cases) |

Per-case win/loss/tie (GRAP-Q vs Pure-LLM): **5 / 0 / 7**
Paired Wilcoxon one-sided: **p = 0.0312**
Bootstrap 95% CI on Δ: **[+0.018, +0.140]**

Source: `experiments/combined_results_val.csv` (12 rows × 2 methods).

---

## Project layout

```
new/
├── README.md                     ← you are here
├── LICENSE
├── requirements.txt
├── docs/
│   ├── ollama_setup.md
│   ├── data_README.md
│   ├── reproducing_results.md
│   └── architecture.md
├── src/
│   ├── utils.py
│   ├── metrics.py
│   ├── dataset.py                ← discovery + filter + split helpers
│   ├── ollama_client.py
│   ├── retrieval/                ← chunkers, BM25, reranker, selectors
│   └── patching/                 ← agent, guardrails, prompts
├── baselines/
│   ├── qchecker.py
│   └── rule_based_apr.py
├── scripts/
│   ├── run_grap4q.py             ← loads splits_70_25_5.json by default
│   ├── run_purellm.py
│   ├── run_statistical_tests.py
│   ├── resplit.py                ← regenerate a split from disk (advanced)
│   ├── compare_baselines.py
│   ├── per_split_baseline_summary.py
│   └── download_bugs4q.py
├── experiments/
│   ├── splits_70_25_5.json       ← FROZEN paper split (33/12/2 of 47)
│   ├── splits_70_15_15.json      ← robustness sweep (29/6/7 of 42)
│   ├── combined_results_val.csv  ← byte-for-byte from legacy run
│   ├── statistical_tests_report.md
│   ├── baselines_comparison_val.md
│   ├── rule_apr_{val,test,all}.csv
│   ├── qchecker_findings_all.json
│   └── per_split_baselines_70_15_15.md
└── tests/
    ├── test_smoke.py             ← 11 smoke tests
    └── test_equivalence_with_legacy.py  ← 17 equivalence tests
```

---

## Verifying everything in under a minute

```bash
cd new
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Smoke tests on the refactored code
python tests/test_smoke.py
# → 11 passed / 0 failed

# 2. Behavioral equivalence against the legacy monolith
python tests/test_equivalence_with_legacy.py
# → 17 passed / 0 failed

# 3. The headline statistical-significance result (no dataset needed!)
python scripts/run_statistical_tests.py \
    --combined experiments/combined_results_val.csv \
    --out /tmp/report.md
# → n=12, mean Δ=+0.0728, Wilcoxon one-sided p=0.0312
```

---

## Reviewer-response summary

| Reviewer comment | Fix delivered | Location |
|---|---|---|
| R2 C7, R3 C13 — no README, monolithic code | Full README + 4 docs + modular refactor + smoke tests + equivalence tests | `README.md`, `docs/`, `src/`, `tests/` |
| R3 C9 — validation split too small | Deterministic 70/15/15 re-split (TEST 2 → 7 cases) | `scripts/resplit.py`, `experiments/splits_70_15_15.json` |
| R3 C10 — baseline too weak | +2 offline baselines: QChecker-style + rule-based APR | `baselines/`, `experiments/baselines_comparison_val.md` |
| R3 C12 — significance claim without statistical test | Paired Wilcoxon + t-test + Cliff's δ + bootstrap CI | `scripts/run_statistical_tests.py`, `experiments/statistical_tests_report.md` |

---

## License

MIT (see `LICENSE`). The Bugs4Q dataset has its own licensing — see
`docs/data_README.md`.