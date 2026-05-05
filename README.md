# GRAP-Q reproducibility package

This package is the complete code + results deliverable for the paper
**"GRAP4Q: An LLM-based Framework for Quantum Coding Assistance"**
(Amato, Cirillo, Ghosh, Moccardi — University of Naples Federico II).

It is organized into two sibling folders that serve distinct purposes:

```
grap4q_package/
├── README.md                ← you are here
├── REMAPPING.md             ← line-by-line map from legacy/ into new/src/
├── legacy/
│   ├── README.md
│   ├── GRAP-Q.py            ← the original 1,242-line monolith, UNTOUCHED
│   ├── loading.py           ← original Bugs4Q downloader
│   └── requirements.txt     ← original (unpinned) deps
└── new/
    ├── README.md            ← quickstart + results table
    ├── LICENSE
    ├── requirements.txt     ← pinned deps
    ├── app/                 ← Gradio web application (deployed at grapq.idealunina.com)
    │   ├── server.py
    │   └── pipeline.py
    ├── docs/
    │   ├── ollama_setup.md
    │   ├── data_README.md
    │   ├── dataset_scope.md
    │   ├── reproducing_results.md
    │   └── architecture.md
    ├── src/                 ← refactored package
    │   ├── utils.py
    │   ├── metrics.py
    │   ├── dataset.py
    │   ├── ollama_client.py
    │   ├── retrieval/       ← chunkers, BM25, reranker, selectors
    │   └── patching/        ← agent, guardrails, prompts
    ├── baselines/           ← OFFLINE baselines (no LLM)
    │   ├── qchecker.py
    │   └── rule_based_apr.py
    ├── scripts/             ← thin CLIs + verification + statistical tests
    │   ├── run_grap4q.py
    │   ├── run_purellm.py
    │   ├── run_statistical_tests.py
    │   ├── verify_all.py    ← one-command full verification (smoke + equivalence + stats)
    │   ├── compare_baselines.py
    │   └── download_bugs4q.py
    ├── experiments/         ← pre-computed numbers cited in the revision
    │   ├── statistical_tests_report.md         (Wilcoxon p=0.0312)
    │   ├── combined_results_val.csv            (verbatim from legacy output)
    │   ├── rule_apr_{val,test,all}.csv
    │   ├── qchecker_findings_all.json
    │   └── baselines_comparison_val.md
    └── tests/
        ├── test_smoke.py                       ← 16 smoke tests
        └── test_equivalence_with_legacy.py     ← 17 equivalence tests
```

## Why the two-folder structure?

Reviewers legitimately want to know whether the refactor retroactively
altered the code that produced the paper's numbers. This package answers
that question unambiguously:

1. **`legacy/`** contains the exact files that generated every figure and
   table in the paper as submitted. **Nothing in `legacy/` has been
   modified.**
2. **`new/`** contains the refactored, documented, tested package — plus
   the additional baselines and statistical tests requested by the
   reviewers.
3. **`REMAPPING.md`** at the root documents, function by function, where
   every piece of legacy code moved to, and discloses three intentional
   behavioral changes (fully listed in §3 of that document).
4. **`new/tests/test_equivalence_with_legacy.py`** runs both codebases on
   the same inputs and asserts identical output. 17 of 17 tests currently
   pass on this deliverable.

## Quickstart — verify everything in under a minute

```bash
cd new
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: get the dataset
python scripts/download_bugs4q.py

# 1. Smoke tests on the refactored code
python tests/test_smoke.py
# → 16 passed / 0 failed

# 2. Behavioral equivalence against the legacy monolith
python tests/test_equivalence_with_legacy.py
# → 17 passed / 0 failed

# 3. The headline statistical-significance result (no dataset needed!)
python scripts/run_statistical_tests.py \
    --combined experiments/combined_results_val.csv \
    --out /tmp/report.md
# → n=12, mean delta=+0.0728, Wilcoxon one-sided p=0.0312
```

See `new/README.md` for the full quickstart (including Ollama setup for
end-to-end runs) and `new/docs/reproducing_results.md` for a command-by-
command walkthrough of every figure and table.

## Reviewer-response summary

| Reviewer comment | Fix delivered | Location |
|---|---|---|
| R2 C7, R3 C13 — no README, monolithic code | Full README + 4 docs + modular refactor + smoke tests + equivalence tests | `new/README.md`, `new/docs/`, `new/src/`, `new/tests/` |
| R3 C9 — validation split too small | Expanded Limitations section with threats to validity + deployed app with 10 stress-test cases | Paper Sect. 9 + `https://grapq.idealunina.com/` |
| R3 C10 — baseline too weak | +2 offline baselines: QChecker-style + rule-based APR | `new/baselines/`, `new/experiments/baselines_comparison_val.md` |
| R3 C12 — significance claim without statistical test | Paired Wilcoxon + t-test + bootstrap CI + win/loss/tie analysis | `new/scripts/run_statistical_tests.py`, `new/experiments/statistical_tests_report.md` |

## Headline numbers for the paper

- **Paired Wilcoxon one-sided p = 0.0312** (significant at α = 0.05)
- **Bootstrap 95% CI on mean paired Δ: [+0.018, +0.140]** (excludes 0)
- **Wins/losses/ties = 5/0/7** (no case where Pure-LLM beats GRAP-Q)
- QChecker detection rate on VAL: **62.5%** (5 of 8 cases)

## License

MIT (see `new/LICENSE`). The Bugs4Q dataset has its own licensing — see
`new/docs/data_README.md`.
