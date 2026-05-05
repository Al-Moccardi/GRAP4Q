#!/usr/bin/env python3
"""
GRAP-Q CLI: diagnostic / test / single modes.

This is a thin orchestrator — all business logic lives in src/. Use this as
the reproduction entry point for the paper.

    # Reproduce the paper's val results (12 cases, 70/25/5 split):
    python scripts/run_grap4q.py --mode diagnostic
    # → loads experiments/splits_70_25_5.json by default

    # Reproduce on the wider 70/15/15 robustness split (R3 C9):
    python scripts/run_grap4q.py --mode test --splits experiments/splits_70_15_15.json

    # Patch a single file:
    python scripts/run_grap4q.py --mode single --single_file bug.py --gold_fixed fix.py

Provenance note
---------------
The `experiments/splits_70_25_5.json` file is a *frozen* artifact of the
paper's 47-case raw discovery → 70/25/5 hash-stable split (33 train /
12 val / 2 test). It is the partition that produced
`experiments/combined_results_val.csv` and every val-based number in the
paper. Do not regenerate it from filesystem discovery — the OS-portable
discovery rule introduced after the paper would yield 42 cases instead of
47, producing a different partition. The JSON file is the canonical source
of truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dataset import iter_cases  # noqa: E402
from src.patching import AgentConfig, run_case  # noqa: E402
from src.retrieval import (  # noqa: E402
    ASTChunker, CrossEncoderReranker, HybridIndex, WindowChunker, quantum_boost_map,
)


# Default split file: the frozen 47-case 70/25/5 partition that produced
# the paper's published val numbers (Tables 3-4, Figs 13-17).
PAPER_SPLIT = Path(__file__).resolve().parents[1] / "experiments" / "splits_70_25_5.json"


def load_split(path: Path) -> dict:
    """Load a frozen split JSON. Refuses to silently fall back to filesystem
    discovery, because that would silently change the partition.
    """
    if not path.exists():
        raise SystemExit(
            f"[ERROR] Split file not found: {path}\n"
            f"        The paper's results are tied to a frozen split JSON. "
            f"If you intend to compute a new split from filesystem discovery, "
            f"run scripts/resplit.py first."
        )
    with open(path) as f:
        d = json.load(f)
    n_total = d.get("n", len(d["train_ids"]) + len(d["val_ids"]) + len(d["test_ids"]))
    print(
        f"[INFO] Loaded split: {path.name} "
        f"(n={n_total}, train={len(d['train_ids'])}, "
        f"val={len(d['val_ids'])}, test={len(d['test_ids'])})"
    )
    return d


def build_index(db_root: Path, chunking: str) -> HybridIndex:
    """Build a single global index over all buggy.py files.

    NOTE: This iterates over all on-disk discoverable cases via iter_cases,
    NOT over the split file. The split file determines which cases are
    *evaluated*, not which cases are indexed (the index is a property of
    retrieval, not of evaluation).
    """
    chunks = []
    chunker = ASTChunker() if chunking.startswith("AST") else WindowChunker(window=80, overlap=10)
    for cid, case_dir, bug_f, _fix_f in iter_cases(db_root):
        for ch in chunker.chunk_file(case_dir, bug_f, repo_key=cid):
            ch.file_path = f"{cid}/{ch.file_path}"
            chunks.append(ch)
    boost = quantum_boost_map(1.8) if chunking.endswith("_q") else {}
    idx = HybridIndex(boost_map=boost)
    idx.build(chunks)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reproduce GRAP-Q paper results, or run on a different split."
    )
    ap.add_argument("--mode", choices=["diagnostic", "test", "single"], required=True,
                    help="diagnostic: full GRAP vs Pure-LLM comparison + plots. "
                         "test: GRAP only. single: one file at a time.")
    ap.add_argument("--db_root", type=Path, default=Path("data/bugs4q/Bugs4Q-Database"),
                    help="Root of the Bugs4Q-Database extract.")
    ap.add_argument(
        "--splits", type=Path, default=PAPER_SPLIT,
        help=f"Frozen split JSON. Default = {PAPER_SPLIT.name} (the paper's "
             f"33/12/2 partition that generated combined_results_val.csv). "
             f"Pass splits_70_15_15.json for the wider robustness split."
    )
    ap.add_argument("--which", choices=["val", "test", "train"], default=None,
                    help="Which partition to evaluate. Default: val for "
                         "diagnostic, test for test mode.")
    ap.add_argument("--best_config", type=Path,
                    default=Path("results/qeval_ablation_plus/best_config.txt"))
    ap.add_argument("--out_dir", type=Path, default=Path("results/infer"))
    ap.add_argument("--work_dir", type=Path, default=Path(".work/infer"))
    ap.add_argument("--single_file", type=Path, default=None)
    ap.add_argument("--gold_fixed", type=Path, default=None)
    args = ap.parse_args()

    # Load best retrieval config
    try:
        cfg_name = args.best_config.read_text(encoding="utf-8").strip().splitlines()[0]
    except Exception:
        cfg_name = "WIN_base__hint__balanced__rerank__nosyntax"
    config = AgentConfig.from_name(cfg_name)
    print(f"[INFO] Using retrieval config: {cfg_name}")

    # Single-file mode is independent of any split
    if args.mode == "single":
        if args.single_file is None:
            raise SystemExit("--single_file required in single mode")
        idx = build_index(args.db_root, config.chunking)
        rr = CrossEncoderReranker() if config.use_rerank else None
        bug = args.single_file
        fix = args.gold_fixed if args.gold_fixed and args.gold_fixed.exists() else bug
        row = run_case("SINGLE/CASE", bug, fix, idx, rr, config, args.work_dir)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "single_report.json").write_text(
            json.dumps(row, indent=2, default=str), encoding="utf-8"
        )
        print(f"[DONE] {args.out_dir / 'single_report.json'}")
        return

    # Load the frozen split
    splits = load_split(args.splits)

    # Pick which partition to evaluate
    which = args.which or ("val" if args.mode == "diagnostic" else "test")
    case_ids = splits[f"{which}_ids"]
    print(f"[INFO] Evaluating on the {which.upper()} partition ({len(case_ids)} cases)")

    # Build index over all on-disk cases (not just the partition)
    idx = build_index(args.db_root, config.chunking)
    rr = CrossEncoderReranker() if config.use_rerank else None

    # Map case_id -> (case_dir, buggy.py, fixed.py)
    case_map = {cid: (d, b, f) for cid, d, b, f in iter_cases(args.db_root)}

    rows = []
    missing = []
    for cid in case_ids:
        if cid not in case_map:
            # This is the symptom of a discovery / split mismatch.
            # Most commonly: the split JSON was generated on a different
            # filesystem (case-sensitive vs case-insensitive) or before/after
            # the PAPER_EXCLUDED_CASES filter was added.
            missing.append(cid)
            print(f"[WARN] Case in split but not on disk: {cid}")
            continue
        _d, bug, fix = case_map[cid]
        row = run_case(cid, bug, fix, idx, rr, config, args.work_dir)
        rows.append(row)
        print(f"  {cid}: Lines-F1={row['lines_f1']:.3f} edits={row['num_edits']}")

    if missing:
        print(
            f"\n[WARN] {len(missing)} case(s) listed in the split but not "
            f"discovered on disk. This usually means the split JSON was "
            f"generated against a different discovery rule (47-case raw vs "
            f"42-case filtered). The paper's split (splits_70_25_5.json) was "
            f"generated against the 47-case raw discovery; today's discovery "
            f"applies PAPER_EXCLUDED_CASES, returning 42. The 12 val cases "
            f"are present under both, so val should always run cleanly. "
            f"Missing: {missing}"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / f"grap_results_{args.mode}_{which}.json"
    out_json.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    if rows:
        m = sum(r["lines_f1"] for r in rows) / len(rows)
        print(f"\n[DONE] {len(rows)} cases, mean Lines-F1 = {m:.4f}")
        print(f"       Written: {out_json}")


if __name__ == "__main__":
    main()