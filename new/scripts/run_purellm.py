#!/usr/bin/env python3
"""
Pure-LLM baseline: same prompt & guardrails as GRAP-Q but no retrieval.

Model sees only the first 220 lines of the buggy file; no retrieved spans,
no enforced edit region. This is the apples-to-apples baseline in the paper.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dataset import iter_cases  # noqa: E402
from src.metrics import distortion_flags, evaluate_candidate  # noqa: E402
from src.ollama_client import (  # noqa: E402
    MODEL_PATCH, NUM_CTX_PATCH, TEMP_PATCH, extract_json, ollama_chat,
)
from src.patching.agent import apply_edits_to_file  # noqa: E402
from src.patching.prompts import PATCH_SYS  # noqa: E402
from src.utils import safe_read  # noqa: E402


def run_pure_llm(cid: str, buggy_path: Path, fixed_path: Path,
                 work_dir: Path) -> dict:
    src = safe_read(buggy_path)
    ctx = [{
        "rank": 1, "file": f"{cid}/buggy.py", "span": "1-220",
        "symbol": "<file>", "code": "\n".join(src.splitlines()[:220]),
    }]
    msgs = [
        {"role": "system", "content": PATCH_SYS},
        {"role": "user", "content": json.dumps({
            "case": cid, "context": ctx,
            "instruction": "Return strict JSON only.",
        })},
    ]
    try:
        out = ollama_chat(msgs, model=MODEL_PATCH, temperature=TEMP_PATCH,
                          num_ctx=NUM_CTX_PATCH)
        patch = extract_json(out)
    except Exception as e:
        patch = {"edits": [], "rationale": f"error: {e}"}
    edits = patch.get("edits", []) or []
    cand_src = apply_edits_to_file(src, edits) if edits else ""

    work_dir.mkdir(parents=True, exist_ok=True)
    case_work = work_dir / cid.replace("/", "__")
    bug_dir = case_work / "bug"
    fix_dir = case_work / "fix"
    cand_dir = case_work / "cand"
    for d in (bug_dir, fix_dir, cand_dir):
        d.mkdir(parents=True, exist_ok=True)
    (bug_dir / "buggy.py").write_text(src, encoding="utf-8")
    (fix_dir / "buggy.py").write_text(safe_read(fixed_path), encoding="utf-8")
    if cand_src:
        (cand_dir / "buggy.py").write_text(cand_src, encoding="utf-8")
    scores = evaluate_candidate(
        bug_dir / "buggy.py", fix_dir / "buggy.py",
        cand_dir / "buggy.py" if cand_src else None,
    )
    touched = sum(max(0, int(e["end"]) - int(e["start"]) + 1) for e in edits)
    delta_abs = sum(abs(len(str(e.get("replacement", "")).splitlines())
                        - (int(e["end"]) - int(e["start"]) + 1)) for e in edits)
    flags = distortion_flags(src, cand_src, delta_abs, scores["lines_f1"])
    return {
        "case": cid, "method": "LLM",
        **scores,
        "num_edits": len(edits),
        "lines_touched": touched,
        "delta_abs_lines": delta_abs,
        "rationale": patch.get("rationale", ""),
        **flags,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db_root", type=Path, default=Path("data/bugs4q/Bugs4Q-Database"))
    ap.add_argument("--splits", type=Path, default=Path("experiments/splits_70_15_15.json"))
    ap.add_argument("--which", choices=["val", "test", "all"], default="test")
    ap.add_argument("--out", type=Path, default=Path("results/pure_llm/pure_llm_results.json"))
    ap.add_argument("--work_dir", type=Path, default=Path(".work/pure_llm"))
    args = ap.parse_args()

    data = json.loads(args.splits.read_text())
    ids = (data["val_ids"] if args.which == "val"
           else data["test_ids"] if args.which == "test"
           else data["train_ids"] + data["val_ids"] + data["test_ids"])
    case_map = {cid: (d, b, f) for cid, d, b, f in iter_cases(args.db_root)}
    rows = []
    for cid in ids:
        if cid not in case_map:
            continue
        _d, bug, fix = case_map[cid]
        row = run_pure_llm(cid, bug, fix, args.work_dir)
        rows.append(row)
        print(f"  {cid}: F1={row['lines_f1']:.3f}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"[DONE] Wrote {args.out}")


if __name__ == "__main__":
    main()
