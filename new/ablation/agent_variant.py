"""Variant-aware ``run_case`` wrapper for the prompt ablation.

This module mirrors ``src/patching/agent.py::run_case`` step for step.
The only difference: the LLM call (``llm_patch_once``) is replaced
with a variant-aware one that selects which prompt template to use
(V1, V2, V3, V4) based on the ``prompt_variant`` parameter.

We do not edit ``src/patching/agent.py``. We re-implement the
orchestration here so the original code path (used by your published
Bugs4Q evaluation in ``scripts/run_grap4q.py``) is untouched.

Functions exposed:

    run_case_variant(case_id, buggy_path, fixed_path, index, rr,
                     config, work_dir, prompt_variant, donor_exemplars=None)
                     -> dict[str, Any]

    pick_donor_exemplars(buggy_source, donor_chunks, db_root, k=2)
                     -> list[DonorExemplar]
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.metrics import distortion_flags, evaluate_candidate
from src.ollama_client import (
    MODEL_PATCH, NUM_CTX_PATCH, TEMP_PATCH, extract_json, ollama_chat)
from src.patching.agent import AgentConfig, apply_edits_to_file, select_fn
from src.patching.guardrails import enforce_in_region, validate_patch
from src.retrieval import (
    CrossEncoderReranker, HybridIndex, apply_rerank, apply_syntax_prior,
    focus_span)
from src.utils import safe_read, top_tokens_query_from_text

from ablation.prompts.variants import (
    DonorExemplar, build_messages_v1, build_messages_v2,
    build_messages_v3, build_messages_v4, build_messages_v5,
    build_messages_v6, USES_DONOR_EXEMPLARS)


MAX_REFINES = 2


# ---------------------------------------------------------------------------
# Variant-aware single-shot LLM call. Returns the parsed JSON proposal
# or raises if both attempts fail.
# ---------------------------------------------------------------------------
def llm_patch_once_variant(case_id: str, focused_ctx: list[dict],
                           allowed_ranges: list[tuple[int, int]],
                           buggy_source: str,
                           prompt_variant: str,
                           donor_exemplars: list[DonorExemplar] | None = None,
                           retrieval_hits: list[dict] | None = None,
                           extra_feedback: str = "") -> dict:
    if prompt_variant == "v1":
        msgs = build_messages_v1(case_id, focused_ctx, allowed_ranges,
                                 extra_feedback=extra_feedback)
    elif prompt_variant == "v2":
        msgs = build_messages_v2(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_source,
                                 extra_feedback=extra_feedback)
    elif prompt_variant == "v3":
        msgs = build_messages_v3(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_source,
                                 extra_feedback=extra_feedback)
    elif prompt_variant == "v4":
        msgs = build_messages_v4(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_source,
                                 extra_feedback=extra_feedback)
    elif prompt_variant == "v5":
        msgs = build_messages_v5(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_source,
                                 donor_exemplars=donor_exemplars or [],
                                 extra_feedback=extra_feedback)
    elif prompt_variant == "v6":
        msgs = build_messages_v6(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_source,
                                 extra_feedback=extra_feedback)
    else:
        raise ValueError(f"Unknown prompt_variant: {prompt_variant}")

    out = ollama_chat(msgs, model=MODEL_PATCH,
                      temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
    try:
        return extract_json(out)
    except Exception:
        msgs.append({
            "role": "system",
            "content": "Your previous output was not valid JSON. Return "
                       "ONLY JSON now.",
        })
        out2 = ollama_chat(msgs, model=MODEL_PATCH,
                           temperature=0.0, num_ctx=NUM_CTX_PATCH)
        return extract_json(out2)


# ---------------------------------------------------------------------------
# Donor exemplar selection for V3.
#
# The orchestrator passes us the post-rerank pool so we can pick the
# top donor hits by score. For each, we fetch the matching span from
# the donor's fixed.py to construct (buggy_chunk, fixed_chunk) pairs.
# If the donor's fixed.py is missing or the span doesn't translate
# cleanly, we skip that donor and move on.
# ---------------------------------------------------------------------------
def pick_donor_exemplars(pool: list[dict], db_root: Path,
                         k: int = 2) -> list[DonorExemplar]:
    """Pick the top-k donor hits from `pool` and produce DonorExemplar
    objects with their buggy + fixed chunk text.

    `pool` is the full reranked pool from the retrieval stage. Donors
    are chunks whose `file` field starts with 'donor:'. Non-donor hits
    (the queried case's own chunks) are skipped.
    """
    out: list[DonorExemplar] = []
    seen_cases: set[str] = set()
    for h in pool:
        if len(out) >= k:
            break
        file_field = str(h.get("file", ""))
        if not file_field.startswith("donor:"):
            continue
        # 'donor:CaseDir/CaseId' \u2014 strip the prefix
        case_id = file_field.split(":", 1)[1]
        if case_id in seen_cases:
            continue
        case_dir = db_root / case_id
        buggy_path = case_dir / "buggy.py"
        fixed_path = case_dir / "fixed.py"
        if not fixed_path.exists():
            # Some Bugs4Q cases use 'fix.py' instead.
            fixed_path = case_dir / "fix.py"
        if not buggy_path.exists() or not fixed_path.exists():
            continue
        try:
            buggy_lines = buggy_path.read_text(encoding="utf-8").splitlines()
            fixed_lines = fixed_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        lo = max(1, int(h.get("start", 1)))
        hi = min(len(buggy_lines), int(h.get("end", lo)))
        # The chunk's start/end refer to the donor's buggy.py. We use
        # the same line range for fixed.py, clipped to its length.
        # Cases where buggy.py and fixed.py have very different line
        # counts produce noisy exemplars; we accept that as the cost
        # of a simple alignment.
        fix_lo = max(1, lo)
        fix_hi = min(len(fixed_lines), hi)
        buggy_chunk = "\n".join(buggy_lines[lo - 1:hi])
        fixed_chunk = "\n".join(fixed_lines[fix_lo - 1:fix_hi])
        if not buggy_chunk.strip() or not fixed_chunk.strip():
            continue
        out.append(DonorExemplar(
            case_id=case_id,
            buggy_chunk=buggy_chunk,
            fixed_chunk=fixed_chunk,
        ))
        seen_cases.add(case_id)
    return out


# ---------------------------------------------------------------------------
# Variant-aware run_case. Mirrors src/patching/agent.py::run_case.
# Differences:
#   * Uses llm_patch_once_variant instead of llm_patch_once.
#   * For V3, picks donor exemplars from the post-rerank pool.
#   * Records prompt_variant in the returned row for downstream
#     aggregation.
# ---------------------------------------------------------------------------
def run_case_variant(cid: str, buggy_path: Path, fixed_path: Path,
                     index: HybridIndex, rr: CrossEncoderReranker | None,
                     config: AgentConfig, work_dir: Path,
                     prompt_variant: str,
                     donor_db_root: Path | None = None) -> dict[str, Any]:
    """Run GRAP-Q on one case using the specified prompt variant."""
    src = safe_read(buggy_path)
    seed = top_tokens_query_from_text(src, k=6)
    q = (seed + " cx rz dag") if config.use_hints else seed

    pool = index.search(q, topk=max(config.overretrieve, 6 * config.topk))
    pool = apply_rerank(q, pool, rr)
    if config.use_syntax_prior:
        pool = apply_syntax_prior(pool)

    # For V3, pick donor exemplars from the post-rerank pool BEFORE
    # the selector trims it to top-K. This ensures we can still find
    # donor hits even if the selector picked only own-file spans.
    donor_exemplars: list[DonorExemplar] = []
    if (USES_DONOR_EXEMPLARS.get(prompt_variant, False)
            and donor_db_root is not None):
        donor_exemplars = pick_donor_exemplars(pool, donor_db_root, k=2)

    selected = select_fn(config.selector)(pool, config.topk)

    # Filter selected to own-file spans only (the focused-edit region
    # cannot point at donor lines, which would IndexError later in
    # focus_span). This mirrors what app/pipeline.py::run_interactive
    # does for the demo path.
    own_selected = [h for h in selected
                    if not str(h.get("file", "")).startswith("donor:")]
    if len(own_selected) < config.topk:
        own_pool = [h for h in pool
                    if not str(h.get("file", "")).startswith("donor:")]
        own_selected = own_pool[:config.topk]
    selected = own_selected

    allowed: list[tuple[int, int]] = []
    focused_ctx: list[dict] = []
    retrieval_hits: list[dict] = []
    src_lines = src.splitlines()
    for i, h in enumerate(selected, start=1):
        lo, hi, _ = focus_span(h, src)
        allowed.append((lo, hi))
        snippet = src_lines[lo - 1:hi]
        focused_ctx.append({
            "rank": i, "file": h["file"], "span": f"{lo}-{hi}",
            "symbol": h["symbol"], "code": "\n".join(snippet),
        })
        retrieval_hits.append({
            "rank": i,
            "score": h.get("score", 0.0),
            "re_score": h.get("re_score"),
        })

    # Refinement loop \u2014 same shape as the original run_case.
    feedback = ""
    patch: dict = {"edits": [], "rationale": ""}
    cand_src = ""
    guard_notes: list[str] = []
    attempts = 0
    for _it in range(MAX_REFINES + 1):
        attempts = _it + 1
        try:
            proposal = llm_patch_once_variant(
                cid, focused_ctx, allowed, src,
                prompt_variant=prompt_variant,
                donor_exemplars=donor_exemplars,
                retrieval_hits=retrieval_hits,
                extra_feedback=feedback)
        except Exception as e:
            return _empty_row(cid, prompt_variant, allowed,
                              error=f"LLM call failed: {type(e).__name__}: {e}")

        if not isinstance(proposal.get("rationale"), str) \
                or not proposal["rationale"].strip():
            proposal["rationale"] = (
                "Autofill: minimal, localized fix within allowed span; "
                "keep APIs/layout/register semantics.")
        edits = enforce_in_region(proposal.get("edits", []), allowed)
        ok, reasons = validate_patch(src, edits)
        if not ok:
            guard_notes.extend(reasons)
            feedback = ("Guardrail violations:\n- "
                        + "\n- ".join(reasons)
                        + "\nFix minimally within allowed ranges.")
            continue
        patch = {"edits": edits, "rationale": proposal.get("rationale", "")}
        cand_src = apply_edits_to_file(src, edits)
        break

    fixed_src = safe_read(fixed_path)
    work_dir.mkdir(parents=True, exist_ok=True)
    case_work = work_dir / cid.replace("/", "__")
    bug_dir = case_work / "bug"
    fix_dir = case_work / "fix"
    cand_dir = case_work / "cand"
    for d in (bug_dir, fix_dir, cand_dir):
        d.mkdir(parents=True, exist_ok=True)
    (bug_dir / "buggy.py").write_text(src, encoding="utf-8")
    (fix_dir / "buggy.py").write_text(fixed_src, encoding="utf-8")
    (cand_dir / "buggy.py").write_text(cand_src or src, encoding="utf-8")
    scores = evaluate_candidate(bug_dir / "buggy.py", fix_dir / "buggy.py",
                                cand_dir / "buggy.py")
    touched = sum(max(0, int(e["end"]) - int(e["start"]) + 1)
                  for e in patch["edits"])
    delta_abs = sum(abs(len(str(e.get("replacement", "")).splitlines())
                        - (int(e["end"]) - int(e["start"]) + 1))
                    for e in patch["edits"])
    flags = distortion_flags(src, cand_src or src, delta_abs,
                             scores["lines_f1"])
    shutil.rmtree(case_work, ignore_errors=True)

    return {
        "case": cid,
        "method": "GRAP",
        "prompt_variant": prompt_variant,
        **scores,
        "num_edits": len(patch["edits"]),
        "lines_touched": touched,
        "delta_abs_lines": delta_abs,
        "guard_notes": "; ".join(guard_notes),
        "rationale": patch["rationale"],
        "n_donor_exemplars": len(donor_exemplars),
        "attempts": attempts,
        **flags,
    }


def _empty_row(cid: str, variant: str,
               allowed: list[tuple[int, int]],
               error: str) -> dict[str, Any]:
    return {
        "case": cid, "method": "GRAP", "prompt_variant": variant,
        "lines_f1": 0.0, "lines_p": 0.0, "lines_r": 0.0,
        "hit_at_1": 0, "hit_at_3": 0, "hit_at_5": 0,
        "mrr": 0.0, "line_recall": 0.0, "ndcg": 0.0,
        "num_edits": 0, "lines_touched": 0, "delta_abs_lines": 0,
        "guard_notes": "", "rationale": "",
        "n_donor_exemplars": 0, "attempts": 0,
        "error": error,
    }
