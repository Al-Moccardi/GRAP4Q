"""GRAP-Q patching agent: retrieval → selection → guarded refinement loop.

This is the refactored entry point for the agent in Section 4.4 of the paper.
It no longer duplicates dataset scanning, plotting, or CLI code — those live
in their own modules (src/dataset.py, scripts/*.py).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..dataset import iter_cases
from ..metrics import distortion_flags, evaluate_candidate
from ..ollama_client import MODEL_PATCH, NUM_CTX_PATCH, TEMP_PATCH, extract_json, ollama_chat
from ..retrieval import (
    CrossEncoderReranker, HybridIndex, apply_rerank, apply_syntax_prior,
    focus_span, select_by_coverage_balanced, select_by_coverage_old,
)
from ..utils import safe_read, top_tokens_query_from_text
from .guardrails import enforce_in_region, validate_patch
from .prompts import PATCH_SYS


MAX_REFINES = 2


@dataclass
class AgentConfig:
    chunking: str = "WIN_base"     # {AST_base, AST_q, WIN_base, WIN_q}
    use_hints: bool = True
    selector: str = "balanced"     # {balanced, old}
    use_rerank: bool = True
    use_syntax_prior: bool = False
    topk: int = 2
    overretrieve: int = 80

    @classmethod
    def from_name(cls, name: str) -> "AgentConfig":
        """Parse names like 'WIN_base__hint__balanced__rerank__nosyntax'."""
        parts = name.split("__")
        return cls(
            chunking=parts[0],
            use_hints=(parts[1] == "hint"),
            selector=parts[2],
            use_rerank=(parts[3] == "rerank"),
            use_syntax_prior=(parts[4] == "syntax") if len(parts) > 4 else False,
        )


def select_fn(name: str):
    return select_by_coverage_old if name == "old" else select_by_coverage_balanced


def llm_patch_once(cid: str, focused_ctx: list[dict],
                   allowed_ranges: list[tuple[int, int]],
                   extra_feedback: str = "") -> dict:
    payload = {
        "case": cid,
        "allowed_ranges": allowed_ranges,
        "context": focused_ctx,
        "instruction": "Return strict JSON only. No markdown fences.",
        "feedback": extra_feedback,
    }
    msgs = [
        {"role": "system", "content": PATCH_SYS},
        {"role": "user", "content": json.dumps(payload)},
    ]
    out = ollama_chat(msgs, model=MODEL_PATCH, temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
    try:
        return extract_json(out)
    except Exception:
        msgs.append({
            "role": "system",
            "content": "Your previous output was not valid JSON. Return ONLY JSON now.",
        })
        out2 = ollama_chat(msgs, model=MODEL_PATCH, temperature=0.0, num_ctx=NUM_CTX_PATCH)
        return extract_json(out2)


def apply_edits_to_file(src: str, edits: list[dict]) -> str:
    lines = src.splitlines()
    for e in edits or []:
        st = max(1, int(e["start"]))
        en = min(len(lines), int(e["end"]))
        new = lines[:st - 1] + str(e.get("replacement", "")).splitlines() + lines[en:]
        lines = new
    return "\n".join(lines)


def run_case(cid: str, buggy_path: Path, fixed_path: Path,
             index: HybridIndex, rr: CrossEncoderReranker | None,
             config: AgentConfig, work_dir: Path) -> dict[str, Any]:
    """Run GRAP-Q on one case; return a result row (no plotting)."""
    src = safe_read(buggy_path)
    seed = top_tokens_query_from_text(src, k=6)
    q = (seed + " cx rz dag") if config.use_hints else seed

    pool = index.search(q, topk=max(config.overretrieve, 6 * config.topk))
    pool = apply_rerank(q, pool, rr)
    if config.use_syntax_prior:
        pool = apply_syntax_prior(pool)
    selected = select_fn(config.selector)(pool, config.topk)

    # Build allowed ranges via focus
    allowed: list[tuple[int, int]] = []
    focused_ctx: list[dict] = []
    for i, h in enumerate(selected, start=1):
        lo, hi, _ = focus_span(h, src)
        allowed.append((lo, hi))
        snippet = src.splitlines()[lo - 1:hi]
        focused_ctx.append({
            "rank": i, "file": h["file"], "span": f"{lo}-{hi}",
            "symbol": h["symbol"], "code": "\n".join(snippet),
        })

    # Refinement loop
    feedback = ""
    patch: dict = {"edits": [], "rationale": ""}
    cand_src = ""
    guard_notes: list[str] = []
    for _it in range(MAX_REFINES + 1):
        proposal = llm_patch_once(cid, focused_ctx, allowed, extra_feedback=feedback)
        if not isinstance(proposal.get("rationale"), str) or not proposal["rationale"].strip():
            proposal["rationale"] = (
                "Autofill: minimal, localized fix within allowed span; "
                "keep APIs/layout/register semantics."
            )
        edits = enforce_in_region(proposal.get("edits", []), allowed)
        ok, reasons = validate_patch(src, edits)
        if not ok:
            guard_notes.extend(reasons)
            feedback = ("Guardrail violations:\n- " + "\n- ".join(reasons)
                        + "\nFix minimally within allowed ranges.")
            continue
        patch = {"edits": edits, "rationale": proposal.get("rationale", "")}
        cand_src = apply_edits_to_file(src, edits)
        break

    # Evaluate (vs human-fixed gold)
    fixed_src = safe_read(fixed_path)
    # Use temp dirs for evaluate_candidate's file-based API
    work_dir.mkdir(parents=True, exist_ok=True)
    case_work = work_dir / cid.replace("/", "__")
    bug_dir = case_work / "bug"
    fix_dir = case_work / "fix"
    cand_dir = case_work / "cand"
    for d in (bug_dir, fix_dir, cand_dir):
        d.mkdir(parents=True, exist_ok=True)
    (bug_dir / "buggy.py").write_text(src, encoding="utf-8")
    (fix_dir / "buggy.py").write_text(fixed_src, encoding="utf-8")
    (cand_dir / "buggy.py").write_text(cand_src, encoding="utf-8")
    scores = evaluate_candidate(bug_dir / "buggy.py", fix_dir / "buggy.py",
                                cand_dir / "buggy.py")
    # Delta abs lines
    touched = sum(max(0, int(e["end"]) - int(e["start"]) + 1) for e in patch["edits"])
    delta_abs = sum(abs(len(str(e.get("replacement", "")).splitlines())
                        - (int(e["end"]) - int(e["start"]) + 1))
                    for e in patch["edits"])
    flags = distortion_flags(src, cand_src, delta_abs, scores["lines_f1"])

    # Cleanup
    shutil.rmtree(case_work, ignore_errors=True)

    return {
        "case": cid, "method": "GRAP",
        **scores,
        "num_edits": len(patch["edits"]),
        "lines_touched": touched,
        "delta_abs_lines": delta_abs,
        "guard_notes": "; ".join(guard_notes),
        "rationale": patch["rationale"],
        **flags,
    }
