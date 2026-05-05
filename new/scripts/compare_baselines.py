#!/usr/bin/env python3
"""
Combine GRAP-Q, Pure-LLM, Rule-APR, and QChecker into one comparison table.

For per-case patching metrics (GRAP-Q, Pure-LLM, Rule-APR) we report Lines-F1.
QChecker is a detector not a patcher; for it we report "bug detected (Y/N)"
and the count of findings — since there is no patch, Lines-F1 is N/A.

Usage:
    python scripts/compare_baselines.py \
        --grap_llm experiments/combined_results_val.csv \
        --rule_apr experiments/rule_apr_val.csv \
        --qchecker experiments/qchecker_findings_all.json \
        --out experiments/baselines_comparison_val.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _coerce(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def build_grap_llm(df_combined: pd.DataFrame) -> pd.DataFrame:
    """Pivot combined_results_*.csv into case -> {GRAP_F1, LLM_F1}."""
    w = df_combined.pivot_table(index="case", columns="method",
                                values="lines_f1", aggfunc="first")
    w.columns = [f"{c}_F1" for c in w.columns]
    return w


def build_rule_apr(df_apr: pd.DataFrame) -> pd.DataFrame:
    x = df_apr.set_index("case")[["lines_f1", "num_edits", "rules_applied"]]
    x = x.rename(columns={"lines_f1": "RuleAPR_F1",
                          "num_edits": "RuleAPR_edits",
                          "rules_applied": "RuleAPR_rules"})
    return x


def build_qchecker(findings: list) -> pd.DataFrame:
    rows = []
    for f in findings:
        rows.append({
            "case": f["case"],
            "QChecker_detected": int(f["num_findings"] > 0),
            "QChecker_findings": f["num_findings"],
            "QChecker_rules": ",".join(sorted({fn["rule"] for fn in f["findings"]})),
        })
    return pd.DataFrame(rows).set_index("case") if rows else pd.DataFrame()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grap_llm", type=Path, required=True)
    ap.add_argument("--rule_apr", type=Path, required=True)
    ap.add_argument("--qchecker", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    df_combined = pd.read_csv(args.grap_llm)
    df_apr = pd.read_csv(args.rule_apr)
    qc_list = json.loads(args.qchecker.read_text())

    grap_llm = build_grap_llm(df_combined)
    apr = build_rule_apr(df_apr)
    qchecker = build_qchecker(qc_list)

    # Align on cases that appear in grap_llm (the paired VAL set)
    out = grap_llm.join(apr, how="left").join(qchecker, how="left")
    # Fill NAs for readability
    out["RuleAPR_F1"] = out["RuleAPR_F1"].fillna(0.0)
    out["RuleAPR_edits"] = out["RuleAPR_edits"].fillna(0).astype(int)
    out["QChecker_detected"] = out["QChecker_detected"].fillna(0).astype(int)
    out["QChecker_findings"] = out["QChecker_findings"].fillna(0).astype(int)

    # Summary aggregates
    n = len(out)
    mean_grap = float(out["GRAP_F1"].mean()) if "GRAP_F1" in out else float("nan")
    mean_llm = float(out["LLM_F1"].mean()) if "LLM_F1" in out else float("nan")
    mean_apr = float(out["RuleAPR_F1"].mean())
    det_rate = float(out["QChecker_detected"].mean())

    lines: list[str] = []
    lines.append("# Baseline comparison on validation set")
    lines.append("")
    lines.append(f"**N cases**: {n}")
    lines.append("")
    lines.append("## Summary (mean Lines-F1, higher is better)")
    lines.append("")
    lines.append("| Method | Mean Lines-F1 | Notes |")
    lines.append("|---|---:|---|")
    lines.append(f"| **GRAP-Q** (ours) | **{mean_grap:.4f}** | retrieval-augmented, guardrailed, LLM patcher |")
    lines.append(f"| Pure-LLM | {mean_llm:.4f} | qwen2.5-coder:14b, no retrieval, no guardrails |")
    lines.append(f"| Rule-based APR | {mean_apr:.4f} | 7 deterministic Qiskit-migration rules, no LLM |")
    lines.append(f"| QChecker (detector) | n/a | bug-detection rate: {det_rate:.2%} of cases |")
    lines.append("")
    lines.append("*Rule-based APR and QChecker are offline, LLM-free baselines. "
                 "Rule-APR produces patches; QChecker flags suspect code but does not repair.*")
    lines.append("")

    lines.append("## Per-case comparison")
    lines.append("")
    cols = ["GRAP_F1", "LLM_F1", "RuleAPR_F1", "RuleAPR_edits",
            "QChecker_detected", "QChecker_findings", "QChecker_rules"]
    cols = [c for c in cols if c in out.columns]
    header = "| case | " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] + ["---:" if out[c].dtype != object else "---" for c in cols]) + "|"
    lines.append(header)
    lines.append(sep)
    for cid, row in out.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                vals.append(f"{v:.3f}")
            else:
                vals.append(str(v) if not (isinstance(v, float) and np.isnan(v)) else "")
        lines.append(f"| {cid} | " + " | ".join(vals) + " |")
    lines.append("")

    lines.append("## Reading guide")
    lines.append("")
    lines.append("- **GRAP-Q > RuleAPR ≥ PureLLM**: the case needed domain reasoning (retrieval + guardrails helped).")
    lines.append("- **RuleAPR ≈ GRAP-Q (both 1.0)**: the case was a textbook migration pattern. "
                 "GRAP-Q's gain over LLM here is not the interesting signal.")
    lines.append("- **QChecker_detected=1 & RuleAPR_F1=0**: QChecker identifies the bug but rule-APR lacks a rule for it. "
                 "Good candidate for GRAP-Q to shine.")
    lines.append("- **All F1s = 0**: the case is hard or the gold change does not appear in the buggy file "
                 "(check data quality).")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    # CSV twin
    csv_path = args.out.with_suffix(".csv")
    out.to_csv(csv_path)
    print(f"[OK] Wrote {args.out}")
    print(f"[OK] Wrote {csv_path}")
    print(f"     Means: GRAP={mean_grap:.4f} | LLM={mean_llm:.4f} | RuleAPR={mean_apr:.4f} | QChecker-detect-rate={det_rate:.2%}")


if __name__ == "__main__":
    main()
