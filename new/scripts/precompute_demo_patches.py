#!/usr/bin/env python3
"""Precompute V1, V4, and Pure-LLM patches for the 10 demo cases.

For each case directory under app/demo_cases/, run the patcher
under three configurations:

    v1       - GRAP4Q production prompt + retrieval + guardrails
    v4       - V1 + runtime defect localiser (best ablation variant)
    purellm  - same V1 prompt but NO retrieval and NO guardrails;
               the LLM rewrites the entire file

Captures the patched source code, the rationale, edit metadata,
the resulting Lines-F1 against the gold fixed.py, and the wall-time.
Writes one JSON per (case, method) under:

    app/demo_cases/<case>/<method>_result.json

Usage:
    python scripts/precompute_demo_patches.py
    python scripts/precompute_demo_patches.py --cases case_01 case_02
    python scripts/precompute_demo_patches.py --variants v4 purellm

Total runtime: 25-40 minutes (10 cases * 3 methods * ~30-80s).
Requires Ollama running locally with the model pulled.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.metrics import evaluate_candidate
from src.ollama_client import (
    MODEL_PATCH, NUM_CTX_PATCH, TEMP_PATCH, extract_json, ollama_chat)
from src.patching.agent import (
    AgentConfig, apply_edits_to_file, select_fn)
from src.patching.guardrails import (
    enforce_in_region, validate_patch)
from src.retrieval import (
    HybridIndex, apply_rerank, apply_syntax_prior, focus_span)
from src.retrieval.bm25 import quantum_boost_map
from src.retrieval.chunkers import WindowChunker
from src.utils import top_tokens_query_from_text

from src.patching.prompts import PATCH_SYS

from ablation.prompts.variants import (
    build_messages_v1, build_messages_v4)


DEMO_DIR = REPO_ROOT / "app" / "demo_cases"
MAX_REFINES = 2

# Pure-LLM mirrors scripts/run_purellm.py: same V1 system prompt
# (PATCH_SYS), single context window covering the first PURELLM_MAX_LINES
# lines of the buggy file, no allowed_ranges, no guardrails, no
# refinement loop. Matches the apples-to-apples baseline reported in
# the paper.
PURELLM_MAX_LINES = 220


# ---------------------------------------------------------------------------
@dataclass
class CaseResult:
    case_id: str
    variant: str
    family: str = ""
    patched_src: str = ""
    rationale: str = ""
    edits: list[dict[str, Any]] = field(default_factory=list)
    allowed_ranges: list[tuple[int, int]] = field(default_factory=list)
    lines_f1: float = 0.0
    lines_p: float = 0.0
    lines_r: float = 0.0
    num_edits: int = 0
    lines_touched: int = 0
    delta_abs_lines: int = 0
    attempts: int = 0
    wall_time_s: float = 0.0
    guard_notes: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
def _build_per_case_index(buggy_src: str) -> HybridIndex:
    n_lines = max(1, len(buggy_src.splitlines()))
    win = max(6, min(40, n_lines // 3 + 2))
    overlap = max(2, win // 4)
    chunker = WindowChunker(window=win, overlap=overlap)
    chunks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="grap4q_demo_") as d:
        case_dir = Path(d)
        fp = case_dir / "buggy.py"
        fp.write_text(buggy_src, encoding="utf-8")
        produced = chunker.chunk_file(
            case_dir=case_dir, file_path=fp, repo_key="query")
        chunks.extend(produced if isinstance(produced, list)
                      else list(produced))
    idx = HybridIndex(boost_map=quantum_boost_map())
    idx.build(chunks)
    return idx


def _llm_patch_grap_variant(variant: str, case_id: str,
                            focused_ctx: list[dict],
                            allowed_ranges: list[tuple[int, int]],
                            buggy_src: str,
                            extra_feedback: str = "") -> dict:
    if variant == "v1":
        msgs = build_messages_v1(case_id, focused_ctx, allowed_ranges,
                                 extra_feedback=extra_feedback)
    elif variant == "v4":
        msgs = build_messages_v4(case_id, focused_ctx, allowed_ranges,
                                 buggy_source=buggy_src,
                                 extra_feedback=extra_feedback)
    else:
        raise ValueError(f"Unknown GRAP variant: {variant}")
    out = ollama_chat(msgs, model=MODEL_PATCH,
                      temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
    try:
        return extract_json(out)
    except Exception:
        msgs.append({
            "role": "user",
            "content": ("Your previous reply was not strict JSON. "
                        "Return ONLY the JSON object as specified, "
                        "no markdown fences."),
        })
        out2 = ollama_chat(msgs, model=MODEL_PATCH,
                           temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
        return extract_json(out2)


# ---------------------------------------------------------------------------
# Pure-LLM: same V1 system prompt (PATCH_SYS), single context spanning
# the buggy file (capped at PURELLM_MAX_LINES), no edit-region restriction,
# no guardrails, no refinement. Mirrors scripts/run_purellm.py from the
# paper repo so the metrics here are directly comparable to the paper's
# Pure-LLM baseline.
# ---------------------------------------------------------------------------
def _llm_patch_purellm(case_id: str, buggy_src: str) -> dict:
    src_lines = buggy_src.splitlines()
    capped = "\n".join(src_lines[:PURELLM_MAX_LINES])
    last_line = min(len(src_lines), PURELLM_MAX_LINES)
    ctx = [{
        "rank": 1,
        "file": f"{case_id}/buggy.py",
        "span": f"1-{last_line}",
        "symbol": "<file>",
        "code": capped,
    }]
    msgs = [
        {"role": "system", "content": PATCH_SYS},
        {"role": "user", "content": json.dumps({
            "case": case_id,
            "context": ctx,
            "instruction": "Return strict JSON only.",
        })},
    ]
    out = ollama_chat(msgs, model=MODEL_PATCH,
                      temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
    try:
        return extract_json(out)
    except Exception:
        msgs.append({
            "role": "user",
            "content": ("Your previous reply was not strict JSON. "
                        "Return ONLY the JSON object."),
        })
        out2 = ollama_chat(msgs, model=MODEL_PATCH,
                           temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
        return extract_json(out2)


# ---------------------------------------------------------------------------
def _score_against_gold(src: str, cand_src: str,
                        fixed_src: str) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="grap4q_score_") as d:
        bug_dir = Path(d) / "bug"
        fix_dir = Path(d) / "fix"
        cand_dir = Path(d) / "cand"
        for sub in (bug_dir, fix_dir, cand_dir):
            sub.mkdir(parents=True, exist_ok=True)
        (bug_dir / "buggy.py").write_text(src, encoding="utf-8")
        (fix_dir / "buggy.py").write_text(fixed_src, encoding="utf-8")
        (cand_dir / "buggy.py").write_text(cand_src, encoding="utf-8")
        return evaluate_candidate(
            bug_dir / "buggy.py",
            fix_dir / "buggy.py",
            cand_dir / "buggy.py")


def _load_meta(case_dir: Path) -> dict:
    p = case_dir / "meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
def run_case_grap(case_dir: Path, variant: str) -> CaseResult:
    """Run GRAP4Q pipeline (retrieval + guardrails) under a prompt variant."""
    cid = case_dir.name
    meta = _load_meta(case_dir)
    family = str(meta.get("family", ""))
    src = (case_dir / "buggy.py").read_text(encoding="utf-8")
    fixed_src = (case_dir / "fixed.py").read_text(encoding="utf-8")

    cfg = AgentConfig.from_name("WIN_base__hint__balanced__rerank")
    seed = top_tokens_query_from_text(src, k=6)
    q = (seed + " cx rz dag") if cfg.use_hints else seed

    try:
        index = _build_per_case_index(src)
    except Exception as e:
        return CaseResult(case_id=cid, variant=variant, family=family,
                          error=f"Index build failed: {type(e).__name__}: {e}")

    pool = index.search(q, topk=max(cfg.overretrieve, 6 * cfg.topk))
    pool = apply_rerank(q, pool, None)
    if cfg.use_syntax_prior:
        pool = apply_syntax_prior(pool)
    selected = select_fn(cfg.selector)(pool, cfg.topk)
    if not selected:
        return CaseResult(case_id=cid, variant=variant, family=family,
                          error="Selector returned empty pool.")

    src_lines = src.splitlines()
    allowed: list[tuple[int, int]] = []
    focused_ctx: list[dict] = []
    for i, h in enumerate(selected, start=1):
        lo, hi, _ = focus_span(h, src)
        allowed.append((lo, hi))
        focused_ctx.append({
            "rank": i, "file": h.get("file", "buggy.py"),
            "span": f"{lo}-{hi}", "symbol": h.get("symbol", "?"),
            "code": "\n".join(src_lines[lo - 1:hi]),
        })

    feedback = ""
    cand_src = src
    edits: list[dict[str, Any]] = []
    rationale = ""
    guard_notes: list[str] = []
    attempts = 0
    t0 = time.time()
    for refine in range(MAX_REFINES + 1):
        attempts = refine + 1
        try:
            proposal = _llm_patch_grap_variant(
                variant, cid, focused_ctx, allowed, src,
                extra_feedback=feedback)
        except Exception as e:
            elapsed = time.time() - t0
            return CaseResult(case_id=cid, variant=variant, family=family,
                              attempts=attempts, wall_time_s=elapsed,
                              error=f"LLM call failed: {type(e).__name__}: {e}")

        cand_edits = enforce_in_region(
            proposal.get("edits", []) or [], allowed)
        ok, reasons = validate_patch(src, cand_edits)
        rationale = (proposal.get("rationale") or "").strip() or rationale
        if not ok:
            guard_notes.extend(reasons or [])
            feedback = "; ".join(reasons or [])
            continue
        try:
            cand_src = apply_edits_to_file(src, cand_edits)
        except Exception as e:
            guard_notes.append(
                f"apply_edits failed: {type(e).__name__}: {e}")
            feedback = "Edits could not be applied; revisit ranges."
            continue
        edits = cand_edits
        break
    elapsed = time.time() - t0

    scores = _score_against_gold(src, cand_src, fixed_src)
    touched = sum(max(0, int(e["end"]) - int(e["start"]) + 1) for e in edits)
    delta_abs = sum(
        abs(len(str(e.get("replacement", "")).splitlines())
            - (int(e["end"]) - int(e["start"]) + 1))
        for e in edits)

    return CaseResult(
        case_id=cid, variant=variant, family=family,
        patched_src=cand_src, rationale=rationale,
        edits=edits, allowed_ranges=allowed,
        lines_f1=float(scores.get("lines_f1", 0.0)),
        lines_p=float(scores.get("lines_p", 0.0)),
        lines_r=float(scores.get("lines_r", 0.0)),
        num_edits=len(edits), lines_touched=touched,
        delta_abs_lines=delta_abs,
        attempts=attempts, wall_time_s=elapsed,
        guard_notes=guard_notes,
    )


def run_case_purellm(case_dir: Path) -> CaseResult:
    """Pure-LLM: same V1 prompt, no retrieval, no guardrails, no
    refinement. Mirrors scripts/run_purellm.py from the paper repo."""
    cid = case_dir.name
    meta = _load_meta(case_dir)
    family = str(meta.get("family", ""))
    src = (case_dir / "buggy.py").read_text(encoding="utf-8")
    fixed_src = (case_dir / "fixed.py").read_text(encoding="utf-8")
    src_lines = src.splitlines()
    last_line = min(len(src_lines), PURELLM_MAX_LINES)

    t0 = time.time()
    try:
        proposal = _llm_patch_purellm(cid, src)
    except Exception as e:
        elapsed = time.time() - t0
        return CaseResult(case_id=cid, variant="purellm", family=family,
                          attempts=1, wall_time_s=elapsed,
                          error=f"LLM call failed: {type(e).__name__}: {e}")
    elapsed = time.time() - t0

    edits = proposal.get("edits", []) or []
    rationale = (proposal.get("rationale") or "").strip()

    # No guardrails, no enforce_in_region. Just try to apply.
    cand_src = ""
    apply_error = None
    if edits:
        try:
            cand_src = apply_edits_to_file(src, edits)
        except Exception as e:
            apply_error = f"apply_edits failed: {type(e).__name__}: {e}"

    scores = _score_against_gold(src, cand_src or "", fixed_src)

    touched = sum(max(0, int(e.get("end", 0)) - int(e.get("start", 0)) + 1)
                  for e in edits)
    delta_abs = sum(
        abs(len(str(e.get("replacement", "")).splitlines())
            - (int(e.get("end", 0)) - int(e.get("start", 0)) + 1))
        for e in edits)

    notes: list[str] = ["pure-LLM: no retrieval, no guardrails, "
                        f"single context span 1-{last_line}, no refinement"]
    if apply_error:
        notes.append(apply_error)

    return CaseResult(
        case_id=cid, variant="purellm", family=family,
        patched_src=cand_src, rationale=rationale,
        edits=edits,
        allowed_ranges=[(1, last_line)],
        lines_f1=float(scores.get("lines_f1", 0.0)),
        lines_p=float(scores.get("lines_p", 0.0)),
        lines_r=float(scores.get("lines_r", 0.0)),
        num_edits=len(edits),
        lines_touched=touched,
        delta_abs_lines=delta_abs,
        attempts=1, wall_time_s=elapsed,
        guard_notes=notes,
        error=None,
    )


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", nargs="*", default=None,
                    help="Case folder names to run (default: all).")
    ap.add_argument("--variants", nargs="+",
                    default=["v1", "v4", "purellm"],
                    help="Methods to run (subset of v1, v4, purellm).")
    ap.add_argument("--demo-dir", type=Path, default=DEMO_DIR,
                    help="Path to app/demo_cases/.")
    args = ap.parse_args()

    if not args.demo_dir.exists():
        raise SystemExit(f"Demo directory not found: {args.demo_dir}")
    cases = args.cases or sorted(
        d.name for d in args.demo_dir.iterdir() if d.is_dir())
    if not cases:
        raise SystemExit(f"No cases found in {args.demo_dir}")

    print(f"Demo dir:  {args.demo_dir}")
    print(f"Cases:     {cases}")
    print(f"Variants:  {args.variants}")
    print(f"Model:     {MODEL_PATCH}")
    print()

    for case_id in cases:
        case_dir = args.demo_dir / case_id
        if not case_dir.is_dir():
            print(f"  [SKIP] {case_id}: not a directory")
            continue
        for variant in args.variants:
            print(f"  Running {case_id} / {variant} ...",
                  end="", flush=True)
            if variant == "purellm":
                result = run_case_purellm(case_dir)
            elif variant in {"v1", "v4"}:
                result = run_case_grap(case_dir, variant)
            else:
                print(f" SKIP (unknown variant: {variant})")
                continue
            out_path = case_dir / f"{variant}_result.json"
            out_path.write_text(json.dumps(asdict(result), indent=2),
                                encoding="utf-8")
            if result.error:
                print(f" ERROR ({str(result.error)[:60]})")
            else:
                print(f" F1={result.lines_f1:.3f}"
                      f"  edits={result.num_edits}"
                      f"  attempts={result.attempts}"
                      f"  {result.wall_time_s:.1f}s")
    print()
    print("Done. Wrote per-case results to", args.demo_dir)


if __name__ == "__main__":
    main()
