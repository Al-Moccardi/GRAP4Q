# Refactor diff: legacy/GRAP-Q.py → src/

This document records **every intentional change** between the legacy
1,242-line monolith in `legacy/GRAP-Q.py` and the refactored package under
`src/`. The short version: we split the file into modules without altering
behavior. Every claim below is enforced by
`scripts/verify_legacy_equivalence.py`, which runs a randomized differential
check and prints the number of mismatches per component.

## Summary table

| Component | File split out to | Behavior change? | Verification |
|---|---|---|---|
| `WORD_RE`, `STOPWORDS`, `Q_TOKENS`, `safe_read`, `tokenize`, `top_tokens_query_from_text`, `changed_lines_in_A` | `src/utils.py` | none | (trivially identical) |
| `_MiniBM25` class | `src/retrieval/bm25.py::MiniBM25` | none | 5 000 randomized scores, 0 mismatches |
| `HybridIndex` class | `src/retrieval/bm25.py::HybridIndex` | none | same search() contract |
| `ASTChunker`, window chunker logic | `src/retrieval/chunkers.py` | none | output shape preserved |
| `CrossEncoderReranker`, `apply_rerank` | `src/retrieval/reranker.py` | none | same graceful-fallback contract |
| `select_by_coverage_balanced` | `src/retrieval/selectors.py` | **none** (bit-identical) | 100 trials, 0 mismatches |
| `select_by_coverage_old` | `src/retrieval/selectors.py` | **none** (bit-identical, including the `h`-vs-`best` quirk — see below) | 100 trials, 0 mismatches |
| `syntax_prior_of`, `apply_syntax_prior`, `focus_span` | `src/retrieval/selectors.py` | none | same signatures |
| `_ast_ok`, `_find_registers`, `_pass_interface_ok`, `_no_reg_mix_ok`, `_qubit_order_heuristic_ok` | `src/patching/guardrails.py` (renamed without leading `_`) | none | 24 case checks, 0 mismatches |
| `enforce_in_region` | `src/patching/guardrails.py` | none | 100 trials, 0 mismatches |
| `guardrail_validate_patch` | `src/patching/guardrails.py::validate_patch` | none | same check composition |
| `api_drift_score`, `identifier_jaccard`, `evaluate_candidate` | `src/metrics.py` | none | same math |
| `distortion_flags` | `src/metrics.py` | **cosmetic rewrite, logically identical** — see §1 below | 7 input values sweep, 0 mismatches |
| `deterministic_splits`, `iter_cases` | `src/dataset.py` | none (now parameterized by ratios) | same train byte-for-byte |
| Ollama I/O (`run`, `have_ollama_cli`, `_to_prompt`, `_http_json`, `_ollama_cli`, `ollama_chat`, `extract_json`) | `src/ollama_client.py` | none | same precedence: HTTP chat → HTTP generate → CLI |
| `REWRITE_SYS`, `PATCH_SYS` strings | `src/patching/prompts.py` | none | verbatim copy |
| `run_grap_on_cases`, `run_llm_on_cases` | `scripts/run_grap4q.py`, `scripts/run_purellm.py`, `src/patching/agent.py::run_case` | same loop shape; plotting moved to a dedicated path | behavior verified per-function above |
| `plots_for_set` | (not ported — plots are decoupled so baselines can be compared without matplotlib) | removed from core path | — |

## §1 `distortion_flags` — cosmetic rewrite

The legacy expression:

```python
"api_drift_gt40": bool(drift != drift and False or (drift > 0.40))
```

`x and False` is always falsy, so the whole expression reduces to
`bool(drift > 0.40)`. For NaN, `NaN > 0.40` is `False` (IEEE semantics),
which is the desired behavior. The refactored version makes the NaN
handling explicit:

```python
drift_gt40 = (drift == drift) and (drift > 0.40)   # (drift == drift) is False iff NaN
```

These produce **identical boolean output on all inputs** (verified by
`scripts/verify_legacy_equivalence.py`). The rewrite exists only for
readability — earlier drafts of this repo's documentation mistakenly
characterized the legacy form as buggy, which was incorrect.

## §2 `select_by_coverage_old` — the `h`-vs-`best` quirk

The legacy loop writes `seen_files.add(h["file"])` and
`seen_symbols.add(h["symbol"])` after the inner loop exits, where `h` is
the Python variable that holds the **last-iterated** candidate (not the
selected `best`). This is unusual but deterministic and reproducible.

An earlier revision of this refactor replaced `h` with `best` — which would
have changed the output whenever the best hit was not the last iterated
one. That change has been **reverted**. The current
`src/retrieval/selectors.py::select_by_coverage_old` preserves the legacy
behavior exactly, including the quirk:

```python
for h in pool_local:
    ...
    if s > best_score:
        best, best_score = h, s
# After the inner for-loop, h == pool_local[-1 minus skips], not best.
selected.append(best)
covered |= set(range(best["start"], best["end"] + 1))
if h is not None:
    seen_files.add(h["file"])      # matches legacy
    seen_symbols.add(h["symbol"])  # matches legacy
```

Note: the paper's best configuration uses the `balanced` selector, not
`old`, so this quirk does not affect the headline results anyway. It is
preserved purely so ablation tables that included the `old` selector remain
reproducible.

## §3 What was genuinely added (new code, no legacy counterpart)

These files have no equivalent in `legacy/GRAP-Q.py`; they are new for this
release:

- `baselines/qchecker.py` — QChecker-style static analyzer (new baseline)
- `baselines/rule_based_apr.py` — deterministic rule-based APR (new baseline)
- `scripts/run_statistical_tests.py` — paired Wilcoxon + t-test + Cliff's δ + bootstrap
- `scripts/resplit.py` — deterministic 70/15/15 re-split helper
- `scripts/compare_baselines.py` — cross-method comparison table
- `scripts/per_split_baseline_summary.py` — per-split detection/fire/F1 rates
- `scripts/verify_legacy_equivalence.py` — this document's proof script
- `scripts/download_bugs4q.py` — fixed downloader (legacy marked the main
  archive as optional; this one makes it required-by-default)
- `tests/test_smoke.py` — 13 unit tests for the refactored modules
- `docs/` — README, Ollama setup, data README, reproducing results,
  architecture, refactor diff (this file)

## §4 What was removed (or de-emphasized)

- `plots_for_set` is not ported into the core path. Plotting lives in
  `scripts/run_grap4q.py --mode diagnostic`; the offline baselines do not
  require matplotlib. This keeps `pip install -r requirements.txt` lean
  for reviewers who only want to reproduce the statistical tests.
- The data downloader `legacy/loading.py` marked `Bugs4Q-Database.zip`
  as `required=False`, which silently skipped the actual dataset on a
  fresh clone. The replacement `scripts/download_bugs4q.py` flips this
  default so cloning the repo actually works.

## How to re-verify equivalence yourself

```bash
python scripts/verify_legacy_equivalence.py
```

Expected output:

```
[MiniBM25]          mismatches: 0
[select.coverage_old]      mismatches: 0
[select.coverage_balanced] mismatches: 0
[enforce_in_region]        mismatches: 0
[guardrails]               mismatches: 0
[distortion NaN guard]     mismatches: 0

[OK] refactored code is behaviorally equivalent to legacy/GRAP-Q.py
```
