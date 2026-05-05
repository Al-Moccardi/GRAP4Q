# Bugs4Q comparison tab — integration guide (mixed real + synthetic)

This package adds a new tab to your existing Gradio app
(`app/server.py`). It compares three patching methods on **ten
cases**: five drawn verbatim from the 75/25/5 Bugs4Q validation split,
and five hand-designed synthetic cases that combine logic / interface
bugs with deprecated Qiskit patterns.

The three methods are configured to reproduce the paper exactly:

- **V1**: GRAP4Q production pipeline (retrieval + guardrails + production prompt). Imports `PATCH_SYS` from `src/patching/prompts.py`.
- **V4**: V1 plus a runtime defect localiser in the user payload (the winning ablation variant from Section 6.6). Calls `build_messages_v4` from `ablation/prompts/variants.py`.
- **Pure-LLM**: same V1 system prompt, but no retrieval, no edit-region restriction, and no guardrail validation. Mirrors `scripts/run_purellm.py` from the paper repo (single context covering the first 220 lines, model returns `{edits, rationale}`, edits are applied unfiltered).

## Files in this package

```
app/
├── comparison_tab.py             ← Gradio tab module
└── demo_cases/
    ├── case_real_01/             ← Bugs4Q StackExchange/3 (compatibility imports)
    ├── case_real_02/             ← Bugs4Q StackExchange/7 (missing workflow steps)
    ├── case_real_03/             ← Bugs4Q StackExchange/10 (qubit-ordering logic bug)
    ├── case_real_04/             ← Bugs4Q StackExchange_2/bug_1 (iden-only deprecation)
    ├── case_real_05/             ← Bugs4Q Terra-4001-6000/Bug_11 (terra-internal regression)
    ├── case_syn_01/              ← Synthetic: off-by-one in CNOT chain
    ├── case_syn_02/              ← Synthetic: classical register fed into quantum gate
    ├── case_syn_03/              ← Synthetic: custom transpiler pass with broken interface
    ├── case_syn_04/              ← Synthetic: long file with localised qubit-index typo
    └── case_syn_05/              ← Synthetic: inverse QFT with sign error
        (each: buggy.py, fixed.py, meta.json)
scripts/
└── precompute_demo_patches.py    ← one-time precompute (V1 + V4 + Pure-LLM)
build_synthetic_cases.py          ← regenerator for the 5 synthetic cases
README_comparison_tab.md          ← this file
```

The five real cases are **copied verbatim** from your local
`data/bugs4q/Bugs4Q-Database/` into `app/demo_cases/` so the demo is
self-contained. (Cases that store the gold as `fix.py` are renamed to
`fixed.py` for consistency with the rest of the demo machinery.)

## Step 1 — drop the files into your repo

```powershell
# from your project root (C:\Users\Alberto\Desktop\grap4q_package\new)
# unzip the package; everything lands in the right places
```

The five real cases are already populated. The five synthetic cases
are also already populated. You do **not** need to re-run
`build_synthetic_cases.py` unless you want to modify a synthetic
case template.

## Step 2 — pre-compute the patches (one-time, ~25–40 minutes)

```powershell
.\.venv\Scripts\activate

# Verify Ollama and the model
ollama list
# If qwen2.5-coder:14b-instruct isn't listed:
# ollama pull qwen2.5-coder:14b-instruct

# Generate cached results: 10 cases × 3 methods = 30 LLM calls
python scripts/precompute_demo_patches.py
```

You'll see, for each (case, method):

```
  Running case_real_01 / v1 ... F1=0.667  edits=2  attempts=1  41.3s
  Running case_real_01 / v4 ... F1=0.667  edits=2  attempts=1  46.5s
  Running case_real_01 / purellm ... F1=0.000  edits=1  attempts=1  38.7s
  Running case_real_02 / v1 ... ...
```

Outputs go to:

```
app/demo_cases/case_*/v1_result.json
app/demo_cases/case_*/v4_result.json
app/demo_cases/case_*/purellm_result.json
```

You can re-run a subset:

```powershell
# Just one case, all three methods
python scripts/precompute_demo_patches.py --cases case_syn_03

# Just Pure-LLM across all cases
python scripts/precompute_demo_patches.py --variants purellm

# Just one case + one method
python scripts/precompute_demo_patches.py --cases case_real_03 --variants v4
```

## Step 3 — wire the tab into `app/server.py`

Open `app/server.py`. Make **two edits**.

**Edit A** — top of the file, with the other `from app...` imports (around line 17):

```python
from app.comparison_tab import build_comparison_tab
```

**Edit B** — inside the existing `with gr.Tabs():` block in
`build_ui()`. Replace the existing `Synthetic stress test` tab with
the new comparison tab. Find this block (around line 846):

```python
with gr.Tab("Synthetic stress test"):
    ...
```

Replace it with:

```python
with gr.Tab("Bugs4Q comparison: V1 vs V4 vs Pure-LLM"):
    build_comparison_tab()
```

If you want to **keep** the synthetic stress test tab and add this
as a third tab, just insert the new block after the existing one.

## Step 4 — launch the app

```powershell
python -m app.server
```

Open `http://127.0.0.1:7860` in your browser. The new comparison tab
is the second one.

## What the tab shows per case

1. **Case header** — REAL or SYNTHETIC badge, family label, original Bugs4Q source ID (for real cases), summary of the bug.
2. **3-method metrics table** — V1 / V4 / Pure-LLM with status badge, Lines-F1, precision, recall, edits emitted, lines touched, refinement attempts, wall-time.
3. **Buggy + gold panels** — original buggy source and the gold target (read-only, syntax-highlighted).
4. **Three patched-source panels** — V1 / V4 / Pure-LLM patches in three side-by-side `gr.Code` blocks.
5. **Three diff panels** — color-coded unified diff of each patch against the gold target (red for missing/wrong, green for correct).
6. **Three rationales** — the natural-language rationale produced by each method.

## Aggregate section (below the per-case panels)

The aggregate table is split into two sections:

- **REAL Bugs4Q val cases** — one row per family (compatibility, workflow, logic, iden-only, terra-internal), plus a "Subtotal: real" row.
- **SYNTHETIC hard cases** — one row per family (off-by-one, register misuse, pass interface, long localised, algorithmic), plus a "Subtotal: synthetic" row.

Each row reports:
- N (cases in that family)
- Mean Lines-F1 for V1, V4, Pure-LLM (best per row highlighted in green)
- Mean wall-time for V1 / V4 / Pure-LLM in seconds

A final **"Overall (real + synthetic)"** row aggregates over all 10
cases. The "Refresh aggregate" button re-reads the cached JSONs
without restarting the app.

## Why the mixed real + synthetic split

The five real cases anchor the demo to the paper's actual evaluation.
Their Pure-LLM scores will reproduce (within run-to-run noise) the
paper's reported per-case Pure-LLM numbers. This protects against the
trap of designing a demo where Pure-LLM accidentally looks too good.

The five synthetic cases extend the demo to bug profiles where
Pure-LLM has a structural disadvantage:

- `case_syn_01` (off-by-one): the bug is a single character; Pure-LLM tends to rewrite broadly and lose precision against the gold's single-line edit footprint.
- `case_syn_02` (register misuse): Pure-LLM has no QuantumRegisterSanityOK guardrail; rewrites can preserve the bug or introduce different ones.
- `case_syn_03` (transpiler pass interface): Pure-LLM has no PassInterfaceOK guardrail; the bug is at the function-signature level.
- `case_syn_04` (long file, localised typo): forces methods to localise the defect rather than rewrite broadly.
- `case_syn_05` (algorithmic): the bug is a sign error in an inverse QFT; requires understanding the algorithm, not just syntax.

Together the ten cases give the visitor a fair view: "here is what
the methods do on the paper's evaluation set" + "here is what they do
on cases specifically designed to show where the framework helps."

## When to re-run the precompute script

- After editing `build_synthetic_cases.py` and regenerating cases
- After editing the production prompt (`src/patching/prompts.py`)
- After editing the V4 prompt (`ablation/prompts/variants.py::build_messages_v4`)
- After upgrading the Ollama model

The Gradio app does not need to be restarted between precompute runs;
just refresh the browser tab and click "Refresh aggregate."

## Important: how to read Pure-LLM's per-case numbers

Pure-LLM under temperature 0 is mostly deterministic, but the model
can return malformed JSON or out-of-bounds edit ranges. When that
happens, `apply_edits_to_file` either rejects the edit (yielding F1=0)
or applies it and produces nonsense (also typically F1=0). This is
**not a bug in the precompute script** — it is exactly how the paper's
`scripts/run_purellm.py` behaves, and it is part of why the paper's
Pure-LLM baseline scores below GRAP4Q. If you see Pure-LLM scoring
F1=0 on multiple cases while V1/V4 succeed, that is the expected
demonstration of the framework's value.
