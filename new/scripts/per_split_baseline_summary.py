#!/usr/bin/env python3
"""
Per-split baseline summary: runs QChecker + Rule-APR across every split
(TRAIN / VAL / TEST under 70/15/15) and tabulates detection + repair rates.

This is the fully offline table the paper can cite without retriggering Ollama.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.qchecker import check_file  # noqa: E402
from baselines.rule_based_apr import run_on_cases  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db_root", type=Path, required=True)
    ap.add_argument("--splits", type=Path, required=True)
    ap.add_argument("--out_md", type=Path, required=True)
    args = ap.parse_args()

    data = json.loads(args.splits.read_text())
    splits = {
        "TRAIN": data["train_ids"],
        "VAL": data["val_ids"],
        "TEST": data["test_ids"],
    }
    rows = []
    detail = {name: [] for name in splits}
    for name, ids in splits.items():
        # QChecker
        qc_rows = []
        for cid in ids:
            p = args.db_root / cid / "buggy.py"
            if not p.exists():
                continue
            r = check_file(p, case=cid)
            qc_rows.append({
                "case": cid,
                "qchecker_findings": len(r.findings),
                "qchecker_rules": ",".join(sorted({f.rule for f in r.findings})),
            })
        df_qc = pd.DataFrame(qc_rows)
        det_rate = (df_qc["qchecker_findings"] > 0).mean() if len(df_qc) else 0.0

        # Rule-APR
        apr = run_on_cases(args.db_root, ids)
        df_apr = pd.DataFrame(apr) if apr else pd.DataFrame(
            columns=["case", "lines_f1", "num_edits", "rules_applied"]
        )
        mean_f1 = df_apr["lines_f1"].mean() if len(df_apr) else 0.0
        fire_rate = (df_apr["num_edits"] > 0).mean() if len(df_apr) else 0.0

        rows.append({
            "split": name,
            "n": len(ids),
            "qchecker_detection_rate": det_rate,
            "rule_apr_fire_rate": fire_rate,
            "rule_apr_mean_f1": mean_f1,
        })
        # Save per-split CSVs next to the report
        out_dir = args.out_md.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        if len(df_apr):
            df_apr.to_csv(out_dir / f"per_split_{name.lower()}_rule_apr.csv", index=False)
        if len(df_qc):
            df_qc.to_csv(out_dir / f"per_split_{name.lower()}_qchecker.csv", index=False)
        detail[name] = qc_rows

    df_sum = pd.DataFrame(rows)

    md = []
    md.append("# Per-split offline baselines (QChecker + Rule-APR)")
    md.append("")
    md.append(f"Split source: `{args.splits}`")
    md.append("")
    md.append("## Aggregate summary")
    md.append("")
    md.append("| Split | N | QChecker detection rate | Rule-APR fire rate | Rule-APR mean Lines-F1 |")
    md.append("|---|---:|---:|---:|---:|")
    for r in rows:
        md.append(f"| {r['split']} | {r['n']} | {r['qchecker_detection_rate']:.2%} | "
                  f"{r['rule_apr_fire_rate']:.2%} | {r['rule_apr_mean_f1']:.4f} |")
    md.append("")
    md.append("- **Detection rate** = fraction of cases where QChecker flags ≥1 bug pattern.")
    md.append("- **Fire rate** = fraction where at least one Rule-APR rewrite rule applied.")
    md.append("- **Mean Lines-F1** = per-case paper metric, averaged across the split.")
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("QChecker alone covers a substantial slice of Bugs4Q as pure static patterns; "
              "Rule-APR further repairs a subset of those. Cases flagged by QChecker but not "
              "repaired by Rule-APR are the natural territory for an LLM-based patcher such as "
              "GRAP-Q — which supports the paper's thesis that retrieval + guardrails are needed "
              "beyond what classical static analysis / rule APR can achieve.")

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(md), encoding="utf-8")
    df_sum.to_csv(args.out_md.with_suffix(".csv"), index=False)
    print(f"[OK] Wrote {args.out_md} and {args.out_md.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
