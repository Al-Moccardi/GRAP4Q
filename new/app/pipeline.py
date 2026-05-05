"""Interactive orchestration of the GRAP-Q pipeline for the Gradio app.

This module is deliberately thin. Every pipeline stage delegates to an
existing function in ``src/`` — we do NOT re-implement tokenisation,
chunking, BM25, cross-encoder re-ranking, selector objectives, span
focusing, Ollama protocol, or guardrails here. The only job of this file
is to orchestrate those stages for an *interactive* input (raw buggy
source the user pastes) instead of the file-based batch API that
``src/patching/agent.py::run_case`` expects.

The single function exposed is :func:`run_interactive`, which returns a
:class:`PipelineTrace` containing every intermediate artefact the UI
needs to render.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- imports from the real pipeline (no duplication) --------------------
from src.patching.agent import (
    AgentConfig,
    apply_edits_to_file,
    llm_patch_once,
    select_fn,
)
from src.patching.guardrails import (
    ast_ok,
    enforce_in_region,
    no_reg_mix_ok,
    pass_interface_ok,
    qubit_order_heuristic_ok,
    validate_patch,
)
from src.retrieval import (
    CrossEncoderReranker,
    HybridIndex,
    apply_rerank,
    apply_syntax_prior,
    focus_span,
)
from src.retrieval.bm25 import quantum_boost_map
from src.retrieval.chunkers import ASTChunker, WindowChunker
from src.utils import top_tokens_query_from_text


# ---------------------------------------------------------------------------
# Result object (purely a data carrier for the UI)
# ---------------------------------------------------------------------------
@dataclass
class GuardRow:
    name: str
    passed: bool
    detail: str


@dataclass
class PipelineTrace:
    query: str = ""
    pool_size: int = 0
    selected: list[dict[str, Any]] = field(default_factory=list)
    allowed_ranges: list[tuple[int, int]] = field(default_factory=list)
    patched: str = ""
    rationale: str = ""
    edits: list[dict[str, Any]] = field(default_factory=list)
    guards: list[GuardRow] = field(default_factory=list)
    attempts: int = 0
    llm_latency_s: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Index construction — same contract as src/patching/agent.py::run_case
# but operates on a user-pasted buggy file instead of a case directory.
# ---------------------------------------------------------------------------
def _build_index(buggy_src: str, config: AgentConfig) -> HybridIndex:
    """Chunk the user's buggy source and wrap it in a HybridIndex.

    Uses the same chunkers, the same boost map, and the same BM25
    implementation as the batch pipeline. The only difference from
    ``run_case`` is that the chunk corpus is a single interactive paste
    rather than a case directory with cross-case donors. To keep the
    chunkers untouched, we materialise the paste as a temp file and call
    the same ``chunk_file`` method the batch pipeline uses.
    """
    import tempfile
    chunker = (WindowChunker() if config.chunking.startswith("WIN")
               else ASTChunker())
    boost = quantum_boost_map() if config.chunking.endswith("_q") else None
    with tempfile.TemporaryDirectory(prefix="grap4q_interactive_") as d:
        case_dir = Path(d)
        file_path = case_dir / "buggy.py"
        file_path.write_text(buggy_src, encoding="utf-8")
        chunks = chunker.chunk_file(
            case_dir=case_dir,
            file_path=file_path,
            repo_key="interactive",
        )
    idx = HybridIndex(boost_map=boost)
    idx.build(chunks)
    return idx


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_interactive(buggy_src: str,
                    *,
                    config: AgentConfig | None = None,
                    reranker: CrossEncoderReranker | None = None,
                    max_refines: int = 2) -> PipelineTrace:
    """Run the GRAP-Q pipeline on a user-pasted buggy source.

    Mirrors ``src/patching/agent.py::run_case`` stage for stage:

      1. seed query from top tokens + optional quantum hints
      2. chunk + index the buggy source
      3. BM25 search over-retrieves the pool
      4. cross-encoder re-rank (if enabled)
      5. optional syntax prior
      6. coverage-aware selector keeps top-K spans
      7. focus_span() tightens each span to the salient lines
      8. LLM patch with guardrail refinement loop
      9. CompositeGuard on the final patched source

    The returned trace contains every intermediate artefact so the UI can
    render the query, the selected spans, the allowed-region contract,
    the LLM rationale, the guardrail verdicts, and the final diff.
    """
    trace = PipelineTrace()
    config = config or AgentConfig()

    if not buggy_src or not buggy_src.strip():
        trace.error = "Paste buggy Qiskit code in the left cell first."
        return trace

    # --- Stages 1–3: query, index, search -------------------------------
    try:
        seed = top_tokens_query_from_text(buggy_src, k=6)
        query = (seed + " cx rz dag") if config.use_hints else seed
        trace.query = query

        index = _build_index(buggy_src, config)
        pool = index.search(
            query,
            topk=max(config.overretrieve, 6 * config.topk),
        )
        trace.pool_size = len(pool)
    except Exception as e:
        trace.error = f"Retrieval stage failed: {type(e).__name__}: {e}"
        return trace

    # --- Stage 4–5: re-rank + optional prior ----------------------------
    try:
        pool = apply_rerank(query, pool, reranker if config.use_rerank else None)
        if config.use_syntax_prior:
            pool = apply_syntax_prior(pool)
    except Exception as e:
        trace.error = f"Re-rank stage failed: {type(e).__name__}: {e}"
        return trace

    # --- Stage 6: selection --------------------------------------------
    selected = select_fn(config.selector)(pool, config.topk)
    trace.selected = selected

    # --- Stage 7: span focusing ----------------------------------------
    allowed: list[tuple[int, int]] = []
    focused_ctx: list[dict[str, Any]] = []
    for i, h in enumerate(selected, start=1):
        lo, hi, _ = focus_span(h, buggy_src)
        allowed.append((lo, hi))
        snippet = buggy_src.splitlines()[lo - 1:hi]
        focused_ctx.append({
            "rank": i,
            "file": h["file"],
            "span": f"{lo}-{hi}",
            "symbol": h["symbol"],
            "code": "\n".join(snippet),
        })
    trace.allowed_ranges = allowed

    # --- Stage 8: LLM patch with refinement loop -----------------------
    feedback = ""
    patched_src = buggy_src
    edits: list[dict[str, Any]] = []
    rationale = ""
    t0 = time.time()

    for attempt in range(1, max_refines + 2):
        trace.attempts = attempt
        try:
            proposal = llm_patch_once(
                cid="user_paste",
                focused_ctx=focused_ctx,
                allowed_ranges=allowed,
                extra_feedback=feedback,
            )
        except Exception as e:
            trace.error = (
                f"Ollama call failed on attempt {attempt}: "
                f"{type(e).__name__}: {e}")
            trace.llm_latency_s = time.time() - t0
            return trace

        if not isinstance(proposal.get("rationale"), str) \
                or not proposal["rationale"].strip():
            proposal["rationale"] = (
                "Autofill: minimal, localized fix within the allowed span; "
                "keep APIs/layout/register semantics.")

        cand_edits = enforce_in_region(proposal.get("edits", []), allowed)
        ok, reasons = validate_patch(buggy_src, cand_edits)
        if not ok:
            feedback = ("Guardrail violations:\n- "
                        + "\n- ".join(reasons)
                        + "\nFix minimally within allowed ranges.")
            continue

        edits = cand_edits
        rationale = proposal.get("rationale", "")
        patched_src = apply_edits_to_file(buggy_src, edits)
        break

    trace.llm_latency_s = time.time() - t0
    trace.edits = edits
    trace.rationale = rationale
    trace.patched = patched_src if edits else buggy_src

    # --- Stage 9: final guardrail verdict ------------------------------
    trace.guards = _final_guard_rows(buggy_src, trace.patched, allowed, edits)
    return trace


# ---------------------------------------------------------------------------
# Guardrail summary (wraps the five real checks from src/patching/guardrails)
# ---------------------------------------------------------------------------
def _final_guard_rows(before: str,
                      after: str,
                      allowed: list[tuple[int, int]],
                      edits: list[dict[str, Any]]) -> list[GuardRow]:
    rows: list[GuardRow] = []

    ok_region = all(
        any(lo <= int(e.get("start", 0)) and int(e.get("end", 0)) <= hi
            for (lo, hi) in allowed)
        for e in edits
    )
    rows.append(GuardRow(
        "EditRegionOK",
        bool(edits == [] or ok_region),
        (f"All edits confined to allowed ranges {allowed}."
         if edits else "No edits applied; vacuously within allowed ranges."),
    ))

    ok, detail = ast_ok(after)
    rows.append(GuardRow("ASTSyntaxOK", ok, detail))

    ok, detail = pass_interface_ok(before, after)
    rows.append(GuardRow("PassInterfaceOK", ok, detail))

    ok, detail = no_reg_mix_ok(after)
    rows.append(GuardRow("QuantumRegisterSanityOK", ok, detail))

    # qubit_order_heuristic_ok wants the edited line ranges
    edited_ranges = [(int(e.get("start", 1)), int(e.get("end", 1)))
                     for e in edits]
    ok, detail = qubit_order_heuristic_ok(before, after, edited_ranges)
    rows.append(GuardRow("QubitOrderHeuristicOK", ok, detail))

    return rows


# ---------------------------------------------------------------------------
# One-shot reranker loader (cached at module level to avoid reloading
# the cross-encoder weights on every request)
# ---------------------------------------------------------------------------
_RERANKER_CACHE: CrossEncoderReranker | None = None


def get_reranker(enable: bool = True) -> CrossEncoderReranker | None:
    """Lazy-loaded cross-encoder. Returns None when the model is unavailable
    (e.g. no network at install time) so the app degrades gracefully."""
    global _RERANKER_CACHE
    if not enable:
        return None
    if _RERANKER_CACHE is not None:
        return _RERANKER_CACHE
    try:
        _RERANKER_CACHE = CrossEncoderReranker()
    except Exception:
        _RERANKER_CACHE = None
    return _RERANKER_CACHE


# ---------------------------------------------------------------------------
# Guards applied to the *original* buggy source alone.
#
# This mirrors what CompositeGuard would report if the pipeline's candidate
# were the unchanged buggy input. Used by the UI to show reviewers which
# admissibility checks the user's input already fails — that is, what
# GRAP-Q's guardrail layer has to fix before a patch can be accepted.
# ---------------------------------------------------------------------------
import re as _re


# Patterns drawn from the rule-based APR (paper Table `tab:rule_based_repair`)
# and from CompositeGuard. These detect the defect classes GRAP-Q targets.
_DEFECT_PATTERNS: list[tuple[str, str, str]] = [
    ("DeprecatedExecuteAPI",
     r"\bexecute\s*\(\s*\w+\s*,\s*backend\s*=",
     "The deprecated convenience function "
     "`execute(qc, backend=bk)` is used. Modern Qiskit expects "
     "`bk.run(transpile(qc, bk))`."),
    ("LegacyBackendName",
     r"['\"]local_statevector_simulator['\"]",
     "Legacy backend id `local_statevector_simulator`. "
     "The current name is `statevector_simulator`."),
    ("GetDataMisuse",
     r"\.get_data\s*\(",
     "`Result.get_data(qc)` was removed. "
     "Use `Result.get_statevector()` for statevector backends."),
    ("IdenGateRename",
     r"\.iden\s*\(",
     "The identity-gate method was renamed from `iden` to `id`."),
    ("IBMQMigration",
     r"\bIBMQ\.load_account\s*\(",
     "`IBMQ.load_account()` is obsolete. "
     "Use `QiskitRuntimeService()` instead."),
    ("AerReferencedWithoutImport",
     r"\bAer\.",
     # This one is only a failure when Aer is referenced but not imported;
     # the check function below verifies both conditions.
     "`Aer` is referenced but not imported from `qiskit_aer`. "
     "Missing imports cause NameError at runtime."),
]


def evaluate_input_guards(source: str) -> list[GuardRow]:
    """Return the guard rows for the *original* buggy source.

    Each row reports one admissibility check. A failing row means the
    paper's pipeline has something real to do; a passing row means
    GRAP-Q would recognise the input as already-admissible.
    """
    source = source or ""
    rows: list[GuardRow] = []

    # --- 1. AST parse --------------------------------------------------
    ok, detail = ast_ok(source)
    rows.append(GuardRow(
        "ASTSyntaxOK", ok,
        detail if detail else
        ("Source parses cleanly." if ok else "Source has a syntax error.")
    ))

    # --- 2. PassInterfaceOK -------------------------------------------
    # Compare the input to itself: any "run(self, dag)" interface is
    # trivially preserved when no edit is made, so this always passes on
    # the original. We still report it for visual parity with the patched
    # side.
    ok, detail = pass_interface_ok(source, source)
    rows.append(GuardRow(
        "PassInterfaceOK", ok,
        detail or "No pass-interface drift in the unchanged source."
    ))

    # --- 3. QuantumRegisterSanityOK -----------------------------------
    ok, detail = no_reg_mix_ok(source)
    rows.append(GuardRow(
        "QuantumRegisterSanityOK", ok,
        detail or ("No classical register used in quantum operations."
                   if ok else "A classical register appears in a quantum op.")
    ))

    # --- 4. QubitOrderHeuristicOK -------------------------------------
    # Again, no edits -> vacuously no order flip.
    ok, detail = qubit_order_heuristic_ok(source, source, [])
    rows.append(GuardRow(
        "QubitOrderHeuristicOK", ok,
        detail or "No qubit-order flip detected in the original source."
    ))

    # --- 5..N. Defect-pattern checks ----------------------------------
    # These are NOT part of CompositeGuard but they detect exactly the
    # patterns the paper's rule-based APR and the LLM patcher target.
    # Surfacing them on the "input" side gives reviewers a concrete
    # before-picture of what GRAP-Q's guardrail + patcher layer has to
    # fix.
    aer_imported = bool(_re.search(
        r"from\s+qiskit_aer\s+import\s+.*\bAer\b", source))
    for name, pat, detail in _DEFECT_PATTERNS:
        hit = bool(_re.search(pat, source))
        if name == "AerReferencedWithoutImport":
            failed = hit and not aer_imported
        else:
            failed = hit
        rows.append(GuardRow(
            name,
            passed=not failed,
            detail=(detail if failed
                    else f"No {name} pattern in the input."),
        ))

    return rows
