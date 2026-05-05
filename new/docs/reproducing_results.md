# Reproducing the paper's results

This document walks through every figure and table in the paper and the
reviewer-response artifacts, pointing at the exact script that produces them.

All commands assume `pwd` is the repository root, with the dataset already
extracted to `data/bugs4q/Bugs4Q-Database/` (see
[`docs/data_README.md`](data_README.md)).

---

## 0. One-time setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_bugs4q.py
# Optional, only if you want to run LLM-backed modes:
# See docs/ollama_setup.md
```

---

## 1. Offline analyses (no Ollama, no network, ~30 s total)

These reproduce every artifact required for reviewers R3 C9, R3 C10, R3 C12
without any LLM call. All run against the shipped
`experiments/splits_70_15_15.json`.

### 1.1 Rebuild the 70/15/15 split (R3 C9)

```bash
python scripts/resplit.py \
    --db_root data/bugs4q/Bugs4Q-Database \
    --out experiments/splits_70_15_15.json \
    --ratios 0.70 0.15 0.15
# → TRAIN=29, VAL=6, TEST=7 (same hash-stable ordering as the paper's script)
```

### 1.2 Rule-based APR baseline (R3 C10)

```bash
python baselines/rule_based_apr.py \
    --db_root data/bugs4q/Bugs4Q-Database \
    --splits experiments/splits_70_15_15.json \
    --which test \
    --out_csv experiments/rule_apr_test.csv

# Also: --which val   → experiments/rule_apr_val.csv
#       --which all   → experiments/rule_apr_all.csv
```

**Expected output on TEST (n=7)**: mean Lines-F1 = 0.2562, fires on 4/7 cases.

### 1.3 QChecker-style static analyzer (R3 C10)

```bash
python baselines/qchecker.py \
    --db_root data/bugs4q/Bugs4Q-Database \
    --out experiments/qchecker_findings_all.json \
    --filter_cases experiments/splits_70_15_15.json
```

**Expected**: 13 cases scanned (VAL+TEST), 7 with findings, 20 total findings.

### 1.4 Per-split aggregates

```bash
python scripts/per_split_baseline_summary.py \
    --db_root data/bugs4q/Bugs4Q-Database \
    --splits experiments/splits_70_15_15.json \
    --out_md experiments/per_split_baselines_70_15_15.md
```

### 1.5 Paired statistical tests on GRAP-Q vs Pure-LLM (R3 C12)

```bash
python scripts/run_statistical_tests.py \
    --combined experiments/combined_results_val.csv \
    --out experiments/statistical_tests_report.md
```

**Expected output**:
- Mean paired Δ = +0.0728, bootstrap 95% CI [+0.018, +0.140]
- Paired Wilcoxon one-sided p = **0.0312** → significant at α = 0.05
- Paired t-test two-sided p = **0.0447** → significant
- Wins/losses/ties: 5/0/7

### 1.6 Cross-method comparison table

```bash
python scripts/compare_baselines.py \
    --grap_llm experiments/combined_results_val.csv \
    --rule_apr experiments/rule_apr_val.csv \
    --qchecker experiments/qchecker_findings_all.json \
    --out experiments/baselines_comparison_val.md
```

---

## 2. LLM-backed runs (requires Ollama, ~15–30 min)

### 2.1 GRAP-Q on TEST

```bash
python scripts/run_grap4q.py \
    --mode test \
    --splits experiments/splits_70_15_15.json \
    --best_config results/qeval_ablation_plus/best_config.txt \
    --db_root data/bugs4q/Bugs4Q-Database \
    --out_dir results/infer
```

### 2.2 Pure-LLM baseline on TEST

```bash
python scripts/run_purellm.py \
    --which test \
    --splits experiments/splits_70_15_15.json \
    --db_root data/bugs4q/Bugs4Q-Database \
    --out results/pure_llm/pure_llm_test.json
```

### 2.3 Diagnostic (GRAP-Q vs Pure-LLM, plots + timing)

```bash
python scripts/run_grap4q.py \
    --mode diagnostic \
    --splits experiments/splits_70_15_15.json
```

This yields:
- `combined_results_test.csv` (pair of (case, method, Lines-F1, …))
- `ecdf_linesf1_test.png`, `winrate_test.png`, `distortion_rates_stacked_test.png`
- `timing_summary_test.json`

Then re-run the statistical tests on the new CSV:

```bash
python scripts/run_statistical_tests.py \
    --combined results/infer/combined_results_test.csv \
    --out results/infer/statistical_tests_report_test.md
```

---

## 3. Mapping paper artifacts → commands

| Paper artifact | Reviewer addressed | Command |
|---|---|---|
| Fig. 15 ECDF (Lines-F1) | — | `scripts/run_grap4q.py --mode diagnostic` |
| Fig. 16 per-case slopegraph | — | same |
| Fig. 17 minimality vs correctness | — | same |
| Fig. 18 distortion/failure modes | — | same |
| Fig. 19 precision/recall box | — | same |
| Fig. 20 per-case runtime | — | same |
| Table 2 retrieval ablation settings | — | (see original `Retrival & Agent.ipynb` or `scripts/run_ablation.py` if added) |
| Statistical significance claim (new paragraph) | R3 C12 | §1.5 above |
| Rule-APR comparison (new paragraph) | R3 C10 | §1.2 + §1.6 above |
| QChecker comparison (new paragraph) | R3 C10 | §1.3 + §1.6 above |
| 70/15/15 split justification (new paragraph) | R3 C9 | §1.1 above |

---

## 4. Caveats and known limitations

- The paper describes a `pytest` oracle (Section 4.4). In practice, the
  Bugs4Q cases rarely ship with runnable tests, so the oracle mostly falls
  through with `rc ∈ {4, 5}` (no tests collected). The guardrails carry
  most of the verification weight. This is acknowledged in the paper's
  Limitations section and discussed further in
  `docs/architecture.md` under "Known limitations".
- The cross-encoder re-ranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
  requires a network fetch the first time it's used, or an offline cache
  (`~/.cache/huggingface/`). If the download fails, GRAP-Q falls back to
  lexical-only ranking — this is printed as a `[WARN]` line at startup.
- Running GRAP-Q on a GPU-less laptop takes ~2 min per case. Budget
  accordingly, or use a quantized model (see `docs/ollama_setup.md` §4).
