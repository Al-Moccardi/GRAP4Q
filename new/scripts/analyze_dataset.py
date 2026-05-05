#!/usr/bin/env python3
"""
Comprehensive dataset analysis for the Bugs4Q experiments.

Produces a full inventory of every case used in the GRAP-Q evaluation:

  * Which cases are in which split (train / val / test)
  * Buggy source + fixed source side-by-side
  * Line-level diff between buggy and fixed
  * Bug patterns detected by QChecker (rule-level breakdown)
  * Rule-APR's predictions (which rules fire, what F1 is achieved)
  * Aggregate statistics per group, per split, per bug pattern
  * Markdown + CSV + JSON outputs for easy consumption

Usage:

    # From grap4q_package/new/:
    python scripts/analyze_dataset.py \
        --db_root data/bugs4q/Bugs4Q-Database \
        --splits experiments/splits_70_15_15.json \
        --out_dir experiments/dataset_analysis

Produces (inside experiments/dataset_analysis/):
    README.md                     — overview of the analysis
    all_cases.csv                 — one row per case, all metadata
    all_cases.json                — same, richer structure
    per_split_summary.md          — split-level aggregates
    per_group_summary.md          — per-group (Aer, Cirq, Terra-0-4000, ...)
    bug_patterns_breakdown.md     — which QChecker rules hit which cases
    rule_apr_effectiveness.md     — where rule-APR succeeds / fails
    case_details/<case>.md        — one file per case with bug+fix+diff

No LLM, no network, runs in seconds.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines.qchecker import check_file  # noqa: E402
from baselines.rule_based_apr import patch_source, evaluate_patch  # noqa: E402
from src.dataset import iter_cases  # noqa: E402
from src.metrics import api_drift_score, identifier_jaccard  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_diff(buggy: str, fixed: str) -> str:
    """Produce a unified diff between buggy and fixed sources."""
    return "".join(difflib.unified_diff(
        buggy.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile="buggy.py",
        tofile="fixed.py",
        n=2,
    ))


def count_changed_lines(buggy: str, fixed: str) -> tuple[int, int, int]:
    """Return (lines_deleted, lines_added, lines_modified)."""
    a, b = buggy.splitlines(), fixed.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    deleted = added = modified = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete":
            deleted += i2 - i1
        elif tag == "insert":
            added += j2 - j1
        elif tag == "replace":
            modified += max(i2 - i1, j2 - j1)
    return deleted, added, modified


def case_group(case_id: str) -> str:
    """Return the top-level directory (Aer, Cirq, Terra-0-4000, ...)."""
    return case_id.split("/")[0]


def load_splits(path: Path) -> dict[str, str]:
    """Return {case_id: 'train'|'val'|'test'}."""
    data = json.loads(path.read_text())
    out: dict[str, str] = {}
    for c in data["train_ids"]:
        out[c] = "train"
    for c in data["val_ids"]:
        out[c] = "val"
    for c in data["test_ids"]:
        out[c] = "test"
    return out


# ---------------------------------------------------------------------------
# Per-case analysis
# ---------------------------------------------------------------------------

def analyze_case(case_id: str, buggy_path: Path, fixed_path: Path,
                 split_label: str) -> dict:
    buggy_src = buggy_path.read_text(encoding="utf-8", errors="replace")
    fixed_src = fixed_path.read_text(encoding="utf-8", errors="replace")

    # Static analysis
    qc = check_file(buggy_path, case=case_id)
    qc_rules = sorted({f.rule for f in qc.findings})

    # Rule-APR prediction
    apr = patch_source(buggy_src, case=case_id)
    apr_scores = evaluate_patch(buggy_src, apr.patched_src, fixed_src)
    apr_rules = sorted({r.rule for r in apr.rules_applied})

    # Size / drift
    buggy_lines = buggy_src.count("\n") + (1 if buggy_src and not buggy_src.endswith("\n") else 0)
    fixed_lines = fixed_src.count("\n") + (1 if fixed_src and not fixed_src.endswith("\n") else 0)
    deleted, added, modified = count_changed_lines(buggy_src, fixed_src)

    drift = api_drift_score(buggy_src, fixed_src)
    jacc = identifier_jaccard(buggy_src, fixed_src)

    return {
        "case": case_id,
        "group": case_group(case_id),
        "split": split_label,
        "buggy_path": str(buggy_path),
        "fixed_path": str(fixed_path),
        "buggy_lines": buggy_lines,
        "fixed_lines": fixed_lines,
        "lines_deleted": deleted,
        "lines_added": added,
        "lines_modified": modified,
        "total_lines_changed": deleted + added + modified,
        "api_drift": round(float(drift), 4),
        "identifier_jaccard": round(float(jacc), 4),
        "qchecker_findings": len(qc.findings),
        "qchecker_rules": ",".join(qc_rules),
        "qchecker_ast_ok": qc.ast_parse_ok,
        "rule_apr_lines_f1": round(float(apr_scores["lines_f1"]), 4),
        "rule_apr_lines_p": round(float(apr_scores["lines_p"]), 4),
        "rule_apr_lines_r": round(float(apr_scores["lines_r"]), 4),
        "rule_apr_rules": ",".join(apr_rules),
        "rule_apr_num_edits": len(apr.edits),
        "buggy_src": buggy_src,
        "fixed_src": fixed_src,
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def write_per_case_markdown(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:
        safe = r["case"].replace("/", "__")
        path = out_dir / f"{safe}.md"
        lines: list[str] = []
        lines.append(f"# Case `{r['case']}`")
        lines.append("")
        lines.append(f"- **Split**: {r['split']}")
        lines.append(f"- **Group**: {r['group']}")
        lines.append(f"- **Buggy lines**: {r['buggy_lines']}  |  **Fixed lines**: {r['fixed_lines']}")
        lines.append(f"- **Lines changed** (del/add/mod): "
                     f"{r['lines_deleted']} / {r['lines_added']} / {r['lines_modified']}")
        lines.append(f"- **API drift**: {r['api_drift']}  |  **Identifier Jaccard**: {r['identifier_jaccard']}")
        lines.append("")
        lines.append("## QChecker static analysis")
        lines.append("")
        if r["qchecker_findings"] == 0:
            lines.append("No findings.")
        else:
            lines.append(f"{r['qchecker_findings']} finding(s); rules fired: `{r['qchecker_rules']}`")
        lines.append("")
        lines.append("## Rule-based APR result")
        lines.append("")
        lines.append(f"- Lines-F1 = **{r['rule_apr_lines_f1']}** "
                     f"(P={r['rule_apr_lines_p']}, R={r['rule_apr_lines_r']})")
        lines.append(f"- Edits produced: {r['rule_apr_num_edits']}")
        lines.append(f"- Rules fired: `{r['rule_apr_rules'] or '(none)'}`")
        lines.append("")
        lines.append("## Buggy source")
        lines.append("")
        lines.append("```python")
        lines.append(r["buggy_src"].rstrip())
        lines.append("```")
        lines.append("")
        lines.append("## Fixed source (human gold)")
        lines.append("")
        lines.append("```python")
        lines.append(r["fixed_src"].rstrip())
        lines.append("```")
        lines.append("")
        lines.append("## Unified diff")
        lines.append("")
        lines.append("```diff")
        lines.append(build_diff(r["buggy_src"], r["fixed_src"]).rstrip())
        lines.append("```")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


def write_per_split_summary(rows: list[dict], out: Path) -> None:
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("buggy_src", "fixed_src")}
                       for r in rows])
    lines: list[str] = []
    lines.append("# Per-split summary")
    lines.append("")
    lines.append("## Counts by split")
    lines.append("")
    lines.append("| Split | N cases | Groups represented |")
    lines.append("|---|---:|---|")
    for split in ("train", "val", "test"):
        sub = df[df["split"] == split]
        groups = ", ".join(sorted(sub["group"].unique()))
        lines.append(f"| {split} | {len(sub)} | {groups} |")
    lines.append("")
    lines.append("## Aggregate metrics by split")
    lines.append("")
    lines.append("| Split | Mean lines changed | Mean API drift | QChecker det.\\ rate | Rule-APR fire rate | Rule-APR mean F1 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for split in ("train", "val", "test"):
        sub = df[df["split"] == split]
        if len(sub) == 0:
            continue
        mean_lc = sub["total_lines_changed"].mean()
        mean_drift = sub["api_drift"].mean()
        det_rate = (sub["qchecker_findings"] > 0).mean()
        fire_rate = (sub["rule_apr_num_edits"] > 0).mean()
        mean_f1 = sub["rule_apr_lines_f1"].mean()
        lines.append(f"| {split} | {mean_lc:.2f} | {mean_drift:.3f} | "
                     f"{det_rate:.1%} | {fire_rate:.1%} | {mean_f1:.4f} |")
    lines.append("")
    lines.append("## All cases (ordered by split → group → case)")
    lines.append("")
    lines.append("| Split | Group | Case | Buggy | Fixed | LinesChanged | QC rules | APR F1 | APR rules |")
    lines.append("|---|---|---|---:|---:|---:|---|---:|---|")
    df_sorted = df.sort_values(["split", "group", "case"])
    for _, r in df_sorted.iterrows():
        lines.append(
            f"| {r['split']} | {r['group']} | {r['case']} | {r['buggy_lines']} | "
            f"{r['fixed_lines']} | {r['total_lines_changed']} | "
            f"{r['qchecker_rules'] or '—'} | {r['rule_apr_lines_f1']:.3f} | "
            f"{r['rule_apr_rules'] or '—'} |"
        )
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def write_per_group_summary(rows: list[dict], out: Path) -> None:
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("buggy_src", "fixed_src")}
                       for r in rows])
    lines: list[str] = []
    lines.append("# Per-group summary")
    lines.append("")
    lines.append("Groups are the top-level Bugs4Q directories (Aer, Cirq, Terra-0-4000, …).")
    lines.append("")
    lines.append("| Group | N | Mean lines changed | QC det.\\ rate | APR fire rate | APR mean F1 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for group in sorted(df["group"].unique()):
        sub = df[df["group"] == group]
        mean_lc = sub["total_lines_changed"].mean()
        det_rate = (sub["qchecker_findings"] > 0).mean()
        fire_rate = (sub["rule_apr_num_edits"] > 0).mean()
        mean_f1 = sub["rule_apr_lines_f1"].mean()
        lines.append(f"| {group} | {len(sub)} | {mean_lc:.2f} | "
                     f"{det_rate:.1%} | {fire_rate:.1%} | {mean_f1:.4f} |")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def write_bug_patterns_breakdown(rows: list[dict], out: Path) -> None:
    rule_counter: Counter[str] = Counter()
    rule_cases: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if not r["qchecker_rules"]:
            continue
        for rid in r["qchecker_rules"].split(","):
            rule_counter[rid] += 1
            rule_cases[rid].append(r["case"])

    rule_meanings = {
        "QC01": "MissingMeasurement",
        "QC02": "MissingClassicalBits",
        "QC03": "MissingBackendInit",
        "QC04": "DeprecatedExecuteAPI",
        "QC05": "DeprecatedBackendName",
        "QC06": "GetDataMisuse",
        "QC07": "QubitOutOfRange",
        "QC08": "MissingInitialization",
        "QC09": "UnmatchedRegisterSize",
        "QC10": "NonExistentGate",
    }
    lines: list[str] = []
    lines.append("# Bug-pattern breakdown (QChecker rules)")
    lines.append("")
    lines.append("| Rule | Meaning | Cases flagged | Case list |")
    lines.append("|---|---|---:|---|")
    for rid in sorted(rule_counter.keys()):
        cases = rule_cases[rid]
        meaning = rule_meanings.get(rid, "(unknown)")
        lines.append(f"| {rid} | {meaning} | {len(cases)} | "
                     f"{', '.join(cases[:6])}{'…' if len(cases) > 6 else ''} |")
    lines.append("")
    no_findings = [r["case"] for r in rows if r["qchecker_findings"] == 0]
    lines.append(f"## Cases with zero static findings ({len(no_findings)})")
    lines.append("")
    lines.append(", ".join(sorted(no_findings)) or "(none)")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def write_rule_apr_effectiveness(rows: list[dict], out: Path) -> None:
    lines: list[str] = []
    lines.append("# Rule-based APR effectiveness")
    lines.append("")
    scored = [r for r in rows if r["rule_apr_num_edits"] > 0]
    perfect = [r for r in rows if r["rule_apr_lines_f1"] >= 0.999]
    partial = [r for r in rows if 0 < r["rule_apr_lines_f1"] < 0.999]
    zero_but_fired = [r for r in rows
                      if r["rule_apr_num_edits"] > 0 and r["rule_apr_lines_f1"] == 0]
    never_fired = [r for r in rows if r["rule_apr_num_edits"] == 0]

    lines.append(f"- Fired on **{len(scored)}** of {len(rows)} cases "
                 f"({len(scored)/len(rows):.1%})")
    lines.append(f"- **Perfect fixes** (F1 ≥ 0.999): {len(perfect)}")
    lines.append(f"- **Partial fixes** (0 < F1 < 1): {len(partial)}")
    lines.append(f"- **Fired but scored 0** (applied rule missed the intended fix): {len(zero_but_fired)}")
    lines.append(f"- **Never fired** (no rule matched the case): {len(never_fired)}")
    lines.append("")
    lines.append("## Perfect-fix cases")
    lines.append("")
    lines.append("| Case | Split | Rules fired |")
    lines.append("|---|---|---|")
    for r in sorted(perfect, key=lambda x: x["case"]):
        lines.append(f"| {r['case']} | {r['split']} | {r['rule_apr_rules']} |")
    lines.append("")
    lines.append("## Partial-fix cases")
    lines.append("")
    lines.append("| Case | Split | F1 | Rules fired |")
    lines.append("|---|---|---:|---|")
    for r in sorted(partial, key=lambda x: -x["rule_apr_lines_f1"]):
        lines.append(f"| {r['case']} | {r['split']} | "
                     f"{r['rule_apr_lines_f1']:.3f} | {r['rule_apr_rules']} |")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def write_overview_readme(rows: list[dict], out_dir: Path, splits_path: Path) -> None:
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("buggy_src", "fixed_src")}
                       for r in rows])
    total = len(rows)
    by_split = df["split"].value_counts().to_dict()
    by_group = df["group"].value_counts().to_dict()

    lines: list[str] = []
    lines.append("# Dataset analysis — overview")
    lines.append("")
    lines.append(f"- **Total cases analyzed**: {total}")
    lines.append(f"- **Split source**: `{splits_path.name}`")
    lines.append(f"- **Split breakdown**: "
                 + ", ".join(f"{k}={v}" for k, v in sorted(by_split.items())))
    lines.append(f"- **Groups**: "
                 + ", ".join(f"{k} ({v})" for k, v in sorted(by_group.items())))
    lines.append("")
    lines.append("## What's in this folder")
    lines.append("")
    lines.append("| File | Contents |")
    lines.append("|---|---|")
    lines.append("| `all_cases.csv` | One row per case with every field from the analysis |")
    lines.append("| `all_cases.json` | Same data, richer structure (includes full source code) |")
    lines.append("| `per_split_summary.md` | Aggregates by train/val/test split |")
    lines.append("| `per_group_summary.md` | Aggregates by Bugs4Q group (Aer/Cirq/Terra/…) |")
    lines.append("| `bug_patterns_breakdown.md` | Which QChecker rules hit which cases |")
    lines.append("| `rule_apr_effectiveness.md` | Where Rule-APR succeeds/fails, with per-case F1 |")
    lines.append("| `case_details/<case>.md` | One file per case: buggy + fixed + diff + analysis |")
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    mean_lines_changed = df["total_lines_changed"].mean()
    det_rate = (df["qchecker_findings"] > 0).mean()
    fire_rate = (df["rule_apr_num_edits"] > 0).mean()
    mean_apr_f1 = df["rule_apr_lines_f1"].mean()
    lines.append(f"- Mean lines changed between buggy and fixed: **{mean_lines_changed:.1f}**")
    lines.append(f"- QChecker detection rate (case has ≥1 static finding): **{det_rate:.1%}**")
    lines.append(f"- Rule-APR fire rate (case triggers ≥1 rewrite rule): **{fire_rate:.1%}**")
    lines.append(f"- Rule-APR mean Lines-F1 across all cases: **{mean_apr_f1:.4f}**")
    lines.append("")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db_root", type=Path, required=True,
                    help="Path to Bugs4Q-Database/")
    ap.add_argument("--splits", type=Path, required=True,
                    help="Path to splits_70_15_15.json")
    ap.add_argument("--out_dir", type=Path, required=True,
                    help="Output directory (e.g. experiments/dataset_analysis)")
    args = ap.parse_args()

    print(f"[INFO] Loading splits from {args.splits}")
    splits = load_splits(args.splits)

    print(f"[INFO] Walking dataset at {args.db_root}")
    rows: list[dict] = []
    case_count = 0
    for case_id, _dir, buggy, fixed in iter_cases(args.db_root):
        case_count += 1
        split_label = splits.get(case_id, "unassigned")
        row = analyze_case(case_id, buggy, fixed, split_label)
        rows.append(row)

    print(f"[INFO] Analyzed {case_count} cases")

    # Overview
    write_overview_readme(rows, args.out_dir, args.splits)
    # CSV + JSON
    flat = [{k: v for k, v in r.items() if k not in ("buggy_src", "fixed_src")}
            for r in rows]
    pd.DataFrame(flat).to_csv(args.out_dir / "all_cases.csv", index=False)
    (args.out_dir / "all_cases.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )
    # Summaries
    write_per_split_summary(rows, args.out_dir / "per_split_summary.md")
    write_per_group_summary(rows, args.out_dir / "per_group_summary.md")
    write_bug_patterns_breakdown(rows, args.out_dir / "bug_patterns_breakdown.md")
    write_rule_apr_effectiveness(rows, args.out_dir / "rule_apr_effectiveness.md")
    # Per-case details
    write_per_case_markdown(rows, args.out_dir / "case_details")

    print(f"[OK] Analysis written to {args.out_dir}")
    print(f"     • README.md, all_cases.csv, all_cases.json")
    print(f"     • per_split_summary.md, per_group_summary.md")
    print(f"     • bug_patterns_breakdown.md, rule_apr_effectiveness.md")
    print(f"     • case_details/ ({len(rows)} per-case markdown files)")


if __name__ == "__main__":
    main()
