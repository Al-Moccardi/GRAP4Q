# Architecture overview

This document explains how the modules under `src/` and `baselines/` compose
into the pipeline described in Section 4 of the paper.

---

## High-level data flow

```
                 buggy.py                                fixed.py  (human gold)
                     │                                       │
                     ▼                                       │
         ┌─────────────────────────┐                         │
         │ src.retrieval.chunkers  │                         │
         │  AST or Window chunker  │                         │
         └────────────┬────────────┘                         │
                      │ list[CodeChunk]                      │
                      ▼                                      │
         ┌─────────────────────────┐                         │
         │ src.retrieval.bm25      │                         │
         │  HybridIndex (+boost)   │                         │
         └────────────┬────────────┘                         │
                      │ pool[dict]                           │
                      ▼                                      │
         ┌─────────────────────────┐                         │
         │ src.retrieval.reranker  │   (optional)            │
         │  CrossEncoderReranker   │                         │
         └────────────┬────────────┘                         │
                      │                                      │
                      ▼                                      │
         ┌─────────────────────────┐                         │
         │ src.retrieval.selectors │                         │
         │  balanced / old         │                         │
         └────────────┬────────────┘                         │
                      │ top-K focused spans                  │
                      ▼                                      │
         ┌─────────────────────────┐   ┌────────────────┐   │
         │ src.patching.agent      │──▶│ Ollama via     │   │
         │  constrained prompt     │◀──│ ollama_client  │   │
         └────────────┬────────────┘   └────────────────┘   │
                      │ proposal (edits + rationale)         │
                      ▼                                      │
         ┌─────────────────────────┐                         │
         │ src.patching.guardrails │                         │
         │  AST / iface / reg /    │                         │
         │  qubit-order checks     │                         │
         └────────────┬────────────┘                         │
                      │ accept / retry (up to MAX_REFINES)   │
                      ▼                                      │
                patched_src  ───────────► src.metrics.evaluate_candidate
                                                    │
                                                    ▼
                                            Lines-F1 / P / R
```

---

## Module responsibilities

### `src/utils.py`
Shared primitives. `tokenize`, `safe_read`, `Q_TOKENS` (the quantum lexicon),
`top_tokens_query_from_text` (seed query builder), `changed_lines_in_A`
(line-diff helper used by the scorer).

### `src/dataset.py`
`iter_cases(db_root)` yields `(case_id, case_dir, buggy_path, fixed_path)`
for every valid Bugs4Q case. `deterministic_splits(case_ids, ratios)` does
the MD5-hash-stable sort + ratio carve. Used by `scripts/resplit.py`.

### `src/metrics.py`
`lines_prf1`, `evaluate_candidate`, `api_drift_score`, `identifier_jaccard`,
`distortion_flags`. **This is where the NaN-guard bug from the original
`GRAP-Q.py::distortion_flags` is fixed** (the original reduced to
`drift > 0.40` regardless of NaN; here we check `drift == drift` explicitly).

### `src/ollama_client.py`
Everything that touches Ollama. HTTP chat API → HTTP generate API → CLI
fallback, in that order. Exposes `ollama_chat`, `extract_json`, and the
env-var-driven constants (`MODEL_PATCH`, `NUM_CTX_PATCH`, etc.).
**Nothing else in the codebase imports `requests` or spawns subprocesses**
— this isolation is deliberate so the rest of the pipeline stays testable
without a running LLM.

### `src/retrieval/`
- `chunkers.py` — `ASTChunker` and `WindowChunker`. Both return
  `list[CodeChunk]`.
- `bm25.py` — `MiniBM25` (zero-dependency Okapi BM25), plus `HybridIndex`
  which tokenizes, applies the quantum-boost additive term, and searches.
- `reranker.py` — `CrossEncoderReranker` wraps
  `sentence_transformers.CrossEncoder`. Graceful degradation: if the
  library isn't installed or the model can't be fetched, `enabled=False`
  and re-ranking becomes a no-op. Prints a `[WARN]` rather than crashing.
- `selectors.py` — `select_by_coverage_balanced` (paper's "balanced"
  objective in Eq. 7), `select_by_coverage_old` (the legacy coverage-first
  objective in Eq. 6), and `focus_span` which tightens a hit's line range
  to the fault-salient zone. **This is where the `seen_files.add(h["file"])`
  scope bug from the original is fixed** (it now correctly uses the
  selected `best` hit).

### `src/patching/`
- `prompts.py` — `PATCH_SYS` (strict-JSON system prompt with hard
  constraints and quantum guardrails) and `REWRITE_SYS`.
- `guardrails.py` — `ast_ok`, `pass_interface_ok`, `no_reg_mix_ok`,
  `qubit_order_heuristic_ok`, `enforce_in_region`, `validate_patch`.
  All deterministic, no LLM.
- `agent.py` — `AgentConfig` (parses the best-config string into typed
  fields), `run_case` (one case end-to-end: retrieve → rerank →
  select → focus → LLM propose → guardrail validate → refine).
  Refinement budget is `MAX_REFINES = 2`.

### `baselines/`
- `qchecker.py` — 10-rule static analyzer. Pure AST + regex, no LLM.
  Useful as a detection baseline (R3 C10).
- `rule_based_apr.py` — 7 deterministic rewrite rules for the most common
  Qiskit migration patterns. Produces actual patches and scores them with
  the same Lines-F1 as the paper. Answers R3 C10's demand for a
  non-LLM APR comparator.

---

## Config flow

The retrieval configuration is encoded as a single string (the same scheme
the original `GRAP-Q.py` used):

```
WIN_base__hint__balanced__rerank__nosyntax
│         │     │         │       │
│         │     │         │       └─ syntax prior: nosyntax | syntax
│         │     │         └─ cross-encoder: rerank | noR
│         │     └─ selector:       balanced | old
│         └─ query hints:          hint | nohint
└─ chunking:                        AST_base | AST_q | WIN_base | WIN_q
```

`AgentConfig.from_name(...)` parses this into a typed dataclass.
`results/qeval_ablation_plus/best_config.txt` holds the winning string from
the ablation.

---

## Known limitations

1. **`pytest` oracle is mostly vestigial.** `run_pytest` in the original
   code treats `rc ∈ {4, 5}` (no tests collected) as "just continue";
   Bugs4Q cases rarely have test files, so the oracle rarely exercises.
   The paper's claim rests on Lines-F1 against human gold, not on test
   execution.

2. **Split sizes are small.** Even with the 70/15/15 re-split, TEST = 7
   cases. Statistical power is limited. The paired Wilcoxon one-sided
   result on n=12 VAL (p=0.0312) is a small-sample inference — reviewers
   should interpret accordingly.

3. **Reranker needs network on first run.** `sentence-transformers` fetches
   model weights on first use. In CI or air-gapped settings, pre-populate
   `~/.cache/huggingface/`.

4. **Rule-based APR covers ~7 canonical patterns.** It is intentionally a
   conservative lower bound. Cases outside its rule set score 0.
