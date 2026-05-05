"""Run the GRAP-Q prompt sensitivity ablation.

Standard usage (matches the plan in the conversation):

    # Step 1: ablate on Bugs4Q val (V1, V2, V3, V4)
    python -m ablation.scripts.run_prompt_ablation \\
        --variants v1,v2,v3,v4 --split val --target bugs4q

    # Read the report at experiments/ablation/bugs4q_val_ablation.json
    # Pick the winner (call it Vx).

    # Step 2: evaluate the winner on Bugs4Q test
    python -m ablation.scripts.run_prompt_ablation \\
        --variants vX --split test --target bugs4q

    # Step 3: evaluate the winner on the synthetic stress test
    python -m ablation.scripts.run_prompt_ablation \\
        --variants vX --target synthetic

The orchestrator builds a per-case index (donors + queried case) for
every case, just like run_grap4q.py does for the paper's evaluation
and run_synthetic_benchmark.py does for the synthetic test. Donors
are always TRAIN-only. The split argument selects which Bugs4Q ids
become queries.

For the synthetic target, donors come from the SAME 70/15/15 split's
TRAIN ids; the synthetic cases under experiments/synthetic_test_set/
become the queries.

Outputs:
    experiments/ablation/<target>_<split>_ablation.json
    \u2014 one row per (case, variant), plus an aggregate per variant.
"""
from __future__ import annotations

import argparse
import json
import random
import re as _re
import tempfile
import time
from collections import Counter
from pathlib import Path

from src.dataset import iter_cases
from src.patching.agent import AgentConfig
from src.retrieval import CrossEncoderReranker, HybridIndex
from src.retrieval.bm25 import quantum_boost_map
from src.retrieval.chunkers import WindowChunker

from ablation.agent_variant import run_case_variant
from ablation.prompts.variants import VARIANTS, VARIANT_DESCRIPTIONS


# ---------------------------------------------------------------------------
# TRAIN donor loading (paper-strict; same as run_synthetic_benchmark.py)
# ---------------------------------------------------------------------------
def load_train_donor_chunks(db_root: Path, splits_path: Path,
                            donor_window: int = 20,
                            donor_overlap: int = 5) -> tuple[list, dict]:
    if not splits_path.exists():
        raise SystemExit(
            f"Splits file not found at {splits_path}. The paper-strict "
            "evaluation requires the published 70/15/15 partition.")
    if not db_root.exists():
        raise SystemExit(f"Bugs4Q DB root not found at {db_root}.")

    doc = json.loads(splits_path.read_text(encoding="utf-8"))
    train_ids = (doc.get("train_ids")
                 or (doc.get("splits") or {}).get("train")
                 or doc.get("train"))
    if not isinstance(train_ids, list) or not train_ids:
        raise SystemExit(
            f"Splits file at {splits_path} has no usable TRAIN ids.")

    chunker = WindowChunker(window=donor_window, overlap=donor_overlap)
    chunks: list = []
    cases_loaded = 0
    cases_skipped = 0
    for cid in train_ids:
        case_dir = db_root / str(cid)
        buggy = case_dir / "buggy.py"
        if not buggy.exists():
            cases_skipped += 1
            continue
        try:
            cs = chunker.chunk_file(case_dir=case_dir, file_path=buggy,
                                    repo_key=f"donor:{cid}")
            if not isinstance(cs, list):
                cs = list(cs) if hasattr(cs, "__iter__") else []
            chunks.extend(cs)
            cases_loaded += 1
        except Exception:
            cases_skipped += 1

    return chunks, {
        "donors_active": True,
        "donor_chunks": len(chunks),
        "donor_cases_loaded": cases_loaded,
        "donor_cases_skipped": cases_skipped,
        "donor_window": donor_window,
        "donor_overlap": donor_overlap,
        "splits_path": str(splits_path),
        "db_root": str(db_root),
        "train_ids_count": len(train_ids),
    }


# ---------------------------------------------------------------------------
# Per-case index assembly (donors + queried case).
# ---------------------------------------------------------------------------
def build_per_case_index(buggy_path: Path, donor_chunks: list,
                         use_quantum_boost: bool = True) -> HybridIndex:
    src = buggy_path.read_text(encoding="utf-8")
    n_lines = max(1, len(src.splitlines()))
    win = max(6, min(40, n_lines // 3 + 2))
    overlap = max(2, win // 4)
    chunker = WindowChunker(window=win, overlap=overlap)

    own_chunks = []
    with tempfile.TemporaryDirectory(prefix="grap4q_ablation_") as d:
        case_dir = Path(d)
        file_path = case_dir / "buggy.py"
        file_path.write_text(src, encoding="utf-8")
        cs = chunker.chunk_file(case_dir=case_dir, file_path=file_path,
                                repo_key="query")
        if not isinstance(cs, list):
            cs = list(cs) if hasattr(cs, "__iter__") else []
        own_chunks = cs

    boost = quantum_boost_map() if use_quantum_boost else None
    idx = HybridIndex(boost_map=boost)
    idx.build(list(own_chunks) + list(donor_chunks))
    return idx


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------
def bootstrap_mean_ci(values: list[float], n_resamples: int = 10_000,
                      ci: float = 0.95, seed: int = 42
                      ) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1 - ci) / 2
    lo = means[int(alpha * n_resamples)]
    hi = means[int((1 - alpha) * n_resamples) - 1]
    return sum(values) / n, lo, hi


# ---------------------------------------------------------------------------
# Bugs4Q split filtering. iter_cases() yields all 42 paper-filtered
# cases; we restrict to the requested split using splits_70_15_15.json.
# ---------------------------------------------------------------------------
def get_split_ids(splits_path: Path, split: str) -> set[str]:
    doc = json.loads(splits_path.read_text(encoding="utf-8"))
    if split == "val":
        ids = (doc.get("val_ids") or (doc.get("splits") or {}).get("val")
               or doc.get("val"))
    elif split == "test":
        ids = (doc.get("test_ids") or (doc.get("splits") or {}).get("test")
               or doc.get("test"))
    elif split == "train":
        ids = (doc.get("train_ids") or (doc.get("splits") or {}).get("train")
               or doc.get("train"))
    else:
        raise ValueError(f"Unknown split: {split}")
    if not isinstance(ids, list) or not ids:
        raise SystemExit(f"Splits file has no '{split}_ids' list.")
    return set(str(x) for x in ids)


# ---------------------------------------------------------------------------
# Build the (case_id, buggy, fixed, template) tuples for a given target.
# ---------------------------------------------------------------------------
def collect_query_cases(target: str, split: str,
                        db_root: Path, splits_path: Path,
                        synthetic_manifest: Path) -> list[dict]:
    cases: list[dict] = []
    if target == "bugs4q":
        if split not in ("val", "test"):
            raise SystemExit(
                f"--split must be val or test for target=bugs4q, got {split!r}")
        keep = get_split_ids(splits_path, split)
        for cid, case_dir, buggy_path, fixed_path in iter_cases(
                db_root, apply_paper_filter=True):
            if cid in keep:
                cases.append({
                    "id": cid,
                    "buggy_path": buggy_path,
                    "fixed_path": fixed_path,
                    "template": "bugs4q",
                    "n_injected": -1,  # unknown for real cases
                    "defects": [],
                })
    elif target == "synthetic":
        if not synthetic_manifest.exists():
            raise SystemExit(
                f"Synthetic manifest not found at {synthetic_manifest}. "
                "Run scripts/generate_test_set first.")
        m = json.loads(synthetic_manifest.read_text(encoding="utf-8"))
        for c in m["cases"]:
            cdir = synthetic_manifest.parent / c["id"]
            cases.append({
                "id": c["id"],
                "buggy_path": cdir / "buggy.py",
                "fixed_path": cdir / "fixed.py",
                "template": c.get("template", ""),
                "n_injected": len(c.get("defects", [])),
                "defects": c.get("defects", []),
            })
    else:
        raise SystemExit(f"Unknown target: {target}")
    return cases


# ---------------------------------------------------------------------------
# Variant aggregation (the columns of the comparison table)
# ---------------------------------------------------------------------------
def aggregate_variant(rows: list[dict],
                      n_resamples: int = 10_000) -> dict:
    f1 = [r["lines_f1"] for r in rows if "lines_f1" in r]
    f1_pos = [v for v in f1 if v > 0]
    n = len(rows)
    mean_f1, lo, hi = bootstrap_mean_ci(f1, n_resamples=n_resamples)
    return {
        "n_cases": n,
        "mean_lines_f1": mean_f1,
        "ci_lower": lo,
        "ci_upper": hi,
        "mean_lines_f1_conditional": (
            sum(f1_pos) / len(f1_pos)) if f1_pos else 0.0,
        "n_lines_f1_pos": len(f1_pos),
        "lines_f1_pos_rate": len(f1_pos) / n if n else 0.0,
        "mean_delta_abs_lines": (
            sum(r.get("delta_abs_lines", 0) for r in rows) / n) if n else 0.0,
        "error_count": sum(1 for r in rows if r.get("error")),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v1,v2,v3,v4",
                    help="Comma-separated list of variants to run.")
    ap.add_argument("--target", choices=("bugs4q", "synthetic"),
                    required=True)
    ap.add_argument("--split", default="val",
                    help="For target=bugs4q: val | test. Ignored for "
                         "target=synthetic.")
    ap.add_argument("--db-root", default="data/bugs4q/Bugs4Q-Database",
                    type=Path)
    ap.add_argument("--splits", default="experiments/splits_70_15_15.json",
                    type=Path)
    ap.add_argument("--synthetic-manifest",
                    default="experiments/synthetic_test_set/manifest.json",
                    type=Path)
    ap.add_argument("--out-dir", default="experiments/ablation", type=Path)
    ap.add_argument("--work-dir", default="experiments/ablation_work",
                    type=Path)
    ap.add_argument("--config-name",
                    default="WIN_base__hint__balanced__rerank")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--bootstrap-n", type=int, default=10_000)
    ap.add_argument("--donor-window", type=int, default=20)
    ap.add_argument("--donor-overlap", type=int, default=5)
    args = ap.parse_args()

    requested = [v.strip().lower() for v in args.variants.split(",")
                 if v.strip()]
    bad = [v for v in requested if v not in VARIANTS]
    if bad:
        raise SystemExit(
            f"Unknown variants: {bad}. Available: {VARIANTS}")

    # Load donors.
    print(f"Loading TRAIN donors from {args.splits} "
          f"(window={args.donor_window}, overlap={args.donor_overlap}) ...")
    donor_chunks, donor_report = load_train_donor_chunks(
        args.db_root, args.splits,
        donor_window=args.donor_window,
        donor_overlap=args.donor_overlap)
    print(f"  {donor_report['donor_chunks']} chunks from "
          f"{donor_report['donor_cases_loaded']} TRAIN cases.")

    # Reranker.
    if args.no_rerank:
        rr = None
        print("Cross-encoder reranker disabled.")
    else:
        try:
            rr = CrossEncoderReranker()
            print("Cross-encoder reranker loaded.")
        except Exception as e:
            rr = None
            print(f"Cross-encoder reranker unavailable: {e}")

    cfg = AgentConfig.from_name(args.config_name)
    cfg.use_rerank = not args.no_rerank

    # Collect cases.
    cases = collect_query_cases(
        target=args.target, split=args.split,
        db_root=args.db_root, splits_path=args.splits,
        synthetic_manifest=args.synthetic_manifest)
    if args.limit:
        cases = cases[:args.limit]
    print(f"\nTarget: {args.target} | Split: {args.split} | "
          f"Cases: {len(cases)}")
    print(f"Variants: {requested}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    # Run each (case, variant) combination.
    rows_by_variant: dict[str, list[dict]] = {v: [] for v in requested}
    total_runs = len(cases) * len(requested)
    run_no = 0

    for ci, case in enumerate(cases, start=1):
        # Per-case index built once and reused across variants \u2014
        # the index doesn't depend on the prompt variant.
        try:
            index = build_per_case_index(
                case["buggy_path"], donor_chunks,
                use_quantum_boost=cfg.chunking.endswith("_q"))
        except Exception as e:
            for v in requested:
                run_no += 1
                row = {
                    "case": case["id"], "prompt_variant": v,
                    "lines_f1": 0.0, "num_edits": 0,
                    "delta_abs_lines": 0, "wall_time_s": 0.0,
                    "error": f"index build failed: "
                             f"{type(e).__name__}: {e}",
                    "n_injected": case["n_injected"],
                    "template": case["template"],
                }
                rows_by_variant[v].append(row)
                print(_progress(run_no, total_runs, case["id"], v, row),
                      flush=True)
            continue

        for v in requested:
            run_no += 1
            t0 = time.time()
            try:
                result = run_case_variant(
                    cid=case["id"],
                    buggy_path=case["buggy_path"],
                    fixed_path=case["fixed_path"],
                    index=index, rr=rr, config=cfg,
                    work_dir=args.work_dir,
                    prompt_variant=v,
                    donor_db_root=args.db_root)
                error = result.pop("error", None)
            except Exception as e:
                result = {
                    "lines_f1": 0.0, "lines_p": 0.0, "lines_r": 0.0,
                    "num_edits": 0, "delta_abs_lines": 0,
                }
                error = f"{type(e).__name__}: {e}"
            elapsed = time.time() - t0

            row = {
                "case": case["id"],
                "prompt_variant": v,
                "template": case["template"],
                "n_injected": case["n_injected"],
                **result,
                "wall_time_s": elapsed,
                "error": error,
            }
            rows_by_variant[v].append(row)
            print(_progress(run_no, total_runs, case["id"], v, row),
                  flush=True)

    # Aggregate per variant.
    per_variant_summary: dict[str, dict] = {}
    for v in requested:
        per_variant_summary[v] = aggregate_variant(
            rows_by_variant[v], n_resamples=args.bootstrap_n)
        per_variant_summary[v]["description"] = VARIANT_DESCRIPTIONS[v]

    # Choose best variant by mean Lines-F1 (ties broken by F1>0 rate).
    if requested:
        ranked = sorted(
            requested,
            key=lambda v: (per_variant_summary[v]["mean_lines_f1"],
                           per_variant_summary[v]["lines_f1_pos_rate"]),
            reverse=True)
        winner = ranked[0]
    else:
        winner = None

    report = {
        "config": {
            "config_name": args.config_name,
            "rerank_enabled": cfg.use_rerank,
            "target": args.target,
            "split": args.split,
            "scoring": "paper-protocol (src/metrics.py::evaluate_candidate)",
            "bootstrap_n_resamples": args.bootstrap_n,
            "bootstrap_ci": 0.95,
            "per_case_index": "donors + queried case (paper-style)",
            **donor_report,
        },
        "variants_requested": requested,
        "variant_descriptions": VARIANT_DESCRIPTIONS,
        "per_variant_summary": per_variant_summary,
        "winner": winner,
        "rows_by_variant": rows_by_variant,
    }

    out_path = (args.out_dir /
                f"{args.target}_{args.split}_ablation.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nWrote report to {out_path}\n")
    print(f"Target: {args.target} | Split: {args.split} | "
          f"N cases: {len(cases)}\n")
    print(f"{'Variant':<6} {'Mean Lines-F1':<22} {'Cond F1':<10} "
          f"{'F1>0':<10} {'Errors':<8}")
    print("-" * 70)
    for v in requested:
        s = per_variant_summary[v]
        marker = " *" if v == winner else ""
        print(f"{v:<6} "
              f"{s['mean_lines_f1']:.3f} [{s['ci_lower']:.3f}, "
              f"{s['ci_upper']:.3f}]  "
              f"{s['mean_lines_f1_conditional']:.3f}     "
              f"{s['n_lines_f1_pos']}/{s['n_cases']} "
              f"({s['lines_f1_pos_rate']:.0%})  "
              f"{s['error_count']}/{s['n_cases']}{marker}")
    print()
    print(f"Winner (highest mean Lines-F1): {winner}")
    if winner:
        print(f"  -> {VARIANT_DESCRIPTIONS[winner]}")


def _progress(run_no: int, total: int, case_id: str,
              variant: str, row: dict) -> str:
    msg = (f"[{run_no:3d}/{total}] {case_id:30s} "
           f"variant={variant} "
           f"Lines-F1={row.get('lines_f1', 0):.3f} "
           f"edits={row.get('num_edits', 0)} "
           f"\u0394abs={row.get('delta_abs_lines', 0)} "
           f"latency={row.get('wall_time_s', 0):.1f}s")
    if row.get("error"):
        msg += f" ERROR={row['error']}"
    return msg


if __name__ == "__main__":
    main()
