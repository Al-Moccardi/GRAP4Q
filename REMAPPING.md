# Legacy → New code remapping

This document is the authoritative mapping between the **original monolithic
`GRAP-Q.py`** (the code that produced every number in the paper) and the
**refactored package under `new/src/`**. It exists so reviewers can verify at
a glance that the refactor moved code rather than rewriting it.

## High-level summary

| Legacy file | Size | Refactored location |
|---|---|---|
| `legacy/GRAP-Q.py` | 1,242 lines, 63 KB | split across `new/src/` (see table below) |
| `legacy/loading.py` | dataset downloader | `new/scripts/download_bugs4q.py` (with one bug fix — see §3) |
| `legacy/requirements.txt` | 24 deps | `new/requirements.txt` (same deps, version-pinned) |

## Line-range-to-module mapping

Line numbers below refer to `legacy/GRAP-Q.py`. Functions are listed in the
same order they appear in the monolith.

### Text utilities and tokenization (lines 80–120)

| Legacy symbol | Lines | New location |
|---|---|---|
| `WORD_RE`, `STOPWORDS`, `Q_TOKENS` | 80–88 | `new/src/utils.py` |
| `safe_read()` | 87–91 | `new/src/utils.py` |
| `read_source_strict()` | 93–113 | *not re-exported* — `safe_read()` covers the use case |
| `tokenize()` | 115–116 | `new/src/utils.py` |
| `top_tokens_query_from_text()` | 118–124 | `new/src/utils.py` |
| `changed_lines_in_A()` | 126–133 | `new/src/utils.py` |
| `dcg()`, `ecdf()` | 135–141 | `new/src/utils.py` (plot-only helpers kept) |

### Dataset iteration (lines 143–162)

| Legacy symbol | Lines | New location |
|---|---|---|
| `iter_cases()` | 143–162 | `new/src/dataset.py` (verbatim) |
| `CodeChunk` dataclass | 164–167 | `new/src/retrieval/chunkers.py` |

### Chunking (lines 168–190)

| Legacy symbol | Lines | New location |
|---|---|---|
| `ASTChunker` | 168–190 | `new/src/retrieval/chunkers.py` (verbatim) |
| (inline window fallback logic) | 1180–1193 | `new/src/retrieval/chunkers.py::WindowChunker` (promoted to its own class) |

### BM25 retrieval (lines 192–240)

| Legacy symbol | Lines | New location |
|---|---|---|
| `_MiniBM25` | 192–214 | `new/src/retrieval/bm25.py::MiniBM25` |
| `HybridIndex` | 216–249 | `new/src/retrieval/bm25.py` (verbatim) |
| `quantum_boost_map()` | 251–252 | `new/src/retrieval/bm25.py` |

### Reranking (lines 254–275)

| Legacy symbol | Lines | New location |
|---|---|---|
| `CrossEncoderReranker` | 254–266 | `new/src/retrieval/reranker.py` (verbatim) |
| `apply_rerank()` | 268–275 | `new/src/retrieval/reranker.py` |

### Selectors and span focusing (lines 277–350)

| Legacy symbol | Lines | New location |
|---|---|---|
| `syntax_prior_of()` | 278–286 | `new/src/retrieval/selectors.py` |
| `apply_syntax_prior()` | 288–298 | `new/src/retrieval/selectors.py` |
| `select_by_coverage_balanced()` | 300–324 | `new/src/retrieval/selectors.py` (verbatim) |
| `select_by_coverage_old()` | 326–345 | `new/src/retrieval/selectors.py` ⚠ *see §3 note* |
| `focus_span()` | 805–825 | `new/src/retrieval/selectors.py` |

### Edit helpers and patching (lines 347–470)

| Legacy symbol | Lines | New location |
|---|---|---|
| `enforce_in_region()` | 347–357 | `new/src/patching/guardrails.py` |
| `apply_edits()` (file-based) | 359–372 | `new/src/patching/agent.py::apply_edits_to_file()` (string-based, file I/O lifted to caller) |
| `run_pytest()` | 374–381 | *not carried over* — pytest rc=0/4/5 logic moved into `new/src/patching/agent.py` refinement loop |
| `last_failing_assert()` | 383–386 | inline in `agent.py` refinement loop |

### Guardrail checks (lines 388–436)

| Legacy symbol | Lines | New location |
|---|---|---|
| `_ast_ok()` | 389–393 | `new/src/patching/guardrails.py::ast_ok()` |
| `_find_registers()` | 395–399 | `new/src/patching/guardrails.py` |
| `_pass_interface_ok()` | 401–413 | `new/src/patching/guardrails.py::pass_interface_ok()` |
| `_no_reg_mix_ok()` | 415–422 | `new/src/patching/guardrails.py::no_reg_mix_ok()` |
| `_qubit_order_heuristic_ok()` | 424–435 | `new/src/patching/guardrails.py::qubit_order_heuristic_ok()` |
| `guardrail_validate_patch()` | 437–451 | `new/src/patching/guardrails.py::validate_patch()` |

### Metrics (lines 453–500)

| Legacy symbol | Lines | New location |
|---|---|---|
| `evaluate_candidate()` | 453–470 | `new/src/metrics.py` (verbatim) |
| `count_lines_edited()` | 472–482 | inline in `new/src/patching/agent.py::run_case()` |
| `api_drift_score()` | 484–497 | `new/src/metrics.py` (verbatim) |
| `identifier_jaccard()` | 499–502 | `new/src/metrics.py` (verbatim) |
| `distortion_flags()` | 504–524 | `new/src/metrics.py` ⚠ *see §3 note* |

### Ollama client (lines 562–598)

| Legacy symbol | Lines | New location |
|---|---|---|
| `run()`, `have_ollama_cli()` | 563–566 | `new/src/ollama_client.py` (internal) |
| `_to_prompt()`, `_http_json()`, `_ollama_cli()` | 568–582 | `new/src/ollama_client.py` |
| `ollama_chat()` | 584–597 | `new/src/ollama_client.py` (verbatim) |
| `extract_json()` | 616–619 | `new/src/ollama_client.py` |

### Prompts (lines 600–615)

| Legacy symbol | Lines | New location |
|---|---|---|
| `REWRITE_SYS` | 600–605 | `new/src/patching/prompts.py` (verbatim) |
| `PATCH_SYS` | 606–614 | `new/src/patching/prompts.py` (verbatim) |

### LLM helpers (lines 621–650)

| Legacy symbol | Lines | New location |
|---|---|---|
| `llm_rewrite_queries()` | 621–632 | not re-exported (unused in current pipeline) |
| `llm_patch_once()` | 634–650 | `new/src/patching/agent.py` (verbatim) |

### Config / selection (lines 652–666)

| Legacy symbol | Lines | New location |
|---|---|---|
| `parse_cfg_name()` | 652–660 | `new/src/patching/agent.py::AgentConfig.from_name()` (dataclass form) |
| `pick_index()`, `select_fn_from_name()` | 662–666 | `new/src/patching/agent.py::select_fn()` + caller logic |

### Orchestrators (lines 668–790)

| Legacy symbol | Lines | New location |
|---|---|---|
| `run_grap_on_cases()` | 668–758 | `new/src/patching/agent.py::run_case()` (per-case); batch loop lifted to `new/scripts/run_grap4q.py` |
| `run_llm_on_cases()` | 760–795 | `new/scripts/run_purellm.py::run_pure_llm()` |

### Plotting (lines 827–940)

| Legacy symbol | Lines | New location |
|---|---|---|
| `savefig()`, `mean_ci95()`, `plots_for_set()` | 827–940 | `new/scripts/plots.py` *(optional — not required to regenerate metrics; the legacy code remains the reference for every Figure in the paper)* |

### Single-file + main (lines 942–1240)

| Legacy symbol | Lines | New location |
|---|---|---|
| `run_single_file()` | 942–1100 | `new/scripts/run_grap4q.py --mode single` |
| `main()` | 1102–1240 | `new/scripts/run_grap4q.py::main()` |

## 3. Behavioral differences between legacy and new (full disclosure)

The refactor is intended to be behavior-identical for the paper's configuration
(`WIN_base__hint__balanced__rerank__nosyntax`). Three changes nonetheless exist
and are disclosed here for full transparency.

### 3.1 `select_by_coverage_old` — diversity-bonus scope difference

**Legacy (lines 341–343):**
```python
selected.append(best)
covered |= set(range(best["start"], best["end"] + 1))
seen_files.add(h["file"])       # ← h is the last-iterated hit
seen_symbols.add(h["symbol"])   # ← same
```

**New (`new/src/retrieval/selectors.py`):**
```python
selected.append(best)
covered |= set(range(best["start"], best["end"] + 1))
seen_files.add(best["file"])    # ← use the selected hit
seen_symbols.add(best["symbol"])
```

**Impact on paper results:** **none**, and empirically the change is
observationally invisible in practice.

We verified this with two tests in
`new/tests/test_smoke.py::test_select_by_coverage_old_matches_legacy` and
in a 1,000-trial random fuzz (seed 42): the legacy and new implementations
produced **identical** picks on every single trial. The semantic oddity in
the legacy code is real (the `h` in `seen_files.add(h["file"])` refers to
the last-iterated candidate, not the selected `best`), but because the
`w_new_file = 10.0` diversity bonus is only one term in a sum where
`w_rerank * re_score` typically dominates the ranking, the incorrect
`seen_files` contents in round 1 rarely flip the winner in round 2.

On top of that, the paper's `best_config.txt` is
`WIN_base__hint__balanced__rerank__nosyntax`, which uses the **balanced**
selector, not `old`. So even if the oddity did cause a difference, it
could not affect the +0.08 F1 headline claim.

We nonetheless use the `best` variant in `new/` because it is what the
code was clearly intended to do. Reviewers who wish to preserve
bit-perfect legacy behavior can substitute the two `best[...]` lines with
`h[...]` in `new/src/retrieval/selectors.py::select_by_coverage_old`.

### 3.2 `distortion_flags` — NaN expression simplification

**Legacy (lines 514–515):**
```python
"api_drift_gt40": bool(drift!=drift and False or (drift>0.40)),
"id_jacc_lt60":   bool(jacc!=jacc and False or (jacc<0.60)),
```

**New (`new/src/metrics.py`):**
```python
drift_gt40 = (drift == drift) and (drift > 0.40)    # NaN-safe
jacc_lt60  = (jacc  == jacc ) and (jacc  < 0.60)
```

**Impact on paper results:** none — the two expressions produce **identical
booleans** on every input. `x and False` is always falsy, so the legacy
expression collapses to `bool(drift > 0.40)`. For NaN, `NaN > 0.40` is
`False`, same as `(NaN == NaN) and ...`. The refactored form is semantically
equivalent but readable. This is verified by
`new/tests/test_equivalence_with_legacy.py`.

### 3.3 `loading.py` → `scripts/download_bugs4q.py` — dataset required by default

**Legacy (`legacy/loading.py`):**
```python
{"name": "Bugs4Q-Database.zip", "required": False}
```

**New:** `required=True` by default. A fresh clone of the refactored repo will
now download the dataset automatically; the legacy version would silently
skip it. This is a UX fix, not a behavioral change in any experiment.

## 4. What is NOT carried over

- **`GRAP-Q.py`'s plotting code.** Reproducing the paper's figures is the job
  of the legacy code, which is kept intact. The new code concentrates on
  metrics reproducibility; if you want the exact figures, run
  `legacy/GRAP-Q.py --mode diagnostic`.
- **`Retrival & Agent.ipynb`.** The 1,727-line notebook is kept in the legacy
  zip layout (not re-uploaded here, see `legacy/README.md` for context).
- **`run_pytest` logic.** The original pytest-based oracle is unused in
  practice (Bugs4Q cases lack test files). The refactor removes it to match
  observed behavior rather than stated behavior.

## 5. Verifying the equivalence

From the repo root (with the dataset in place), run:

```bash
cd new
python tests/test_equivalence_with_legacy.py
```

See `new/tests/test_equivalence_with_legacy.py` for what this verifies.
