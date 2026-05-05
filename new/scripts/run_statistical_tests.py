#!/usr/bin/env python3
"""
Statistical tests for GRAP-Q vs Pure-LLM on paired per-case Lines-F1.

Addresses reviewer R3 C12 ("missing statistical tests").

Runs:
  1. Paired Wilcoxon signed-rank test (non-parametric, primary)
  2. Paired t-test (parametric, robustness)
  3. Cliff's delta effect size (non-parametric effect size)
  4. Bootstrap 95% CI for the mean difference
  5. Sign test on wins/losses/ties

Usage:
    python scripts/run_statistical_tests.py \
        --combined results/grap_vs_llm_deep/combined_results_val.csv \
        --out experiments/statistical_tests_report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> tuple[float, str]:
    """Cliff's delta effect size for two independent samples.
    Interpretation: |d|<0.147 negligible, <0.33 small, <0.474 medium, else large.
    """
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return float("nan"), "undefined"
    greater = sum((xi > yj) for xi in x for yj in y)
    less = sum((xi < yj) for xi in x for yj in y)
    d = (greater - less) / (n1 * n2)
    a = abs(d)
    if a < 0.147:
        mag = "negligible"
    elif a < 0.33:
        mag = "small"
    elif a < 0.474:
        mag = "medium"
    else:
        mag = "large"
    return float(d), mag


def bootstrap_mean_diff_ci(diff: np.ndarray, n_boot: int = 10_000,
                           alpha: float = 0.05, seed: int = 7) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n = len(diff)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        sample = rng.choice(diff, size=n, replace=True)
        boots[i] = sample.mean()
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    return float(diff.mean()), lo, hi


def sign_test(grap: np.ndarray, llm: np.ndarray) -> tuple[int, int, int, float]:
    wins = int((grap > llm).sum())
    losses = int((grap < llm).sum())
    ties = int((grap == llm).sum())
    n_effective = wins + losses
    if n_effective == 0:
        return wins, losses, ties, float("nan")
    # Two-sided binomial test under H0: p(win)=0.5
    p_value = float(stats.binomtest(wins, n_effective, p=0.5, alternative="two-sided").pvalue)
    return wins, losses, ties, p_value


def build_paired_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot combined_results_*.csv into one row per case with GRAP and LLM columns."""
    required = {"case", "method", "lines_f1"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df = df.copy()
    df["lines_f1"] = pd.to_numeric(df["lines_f1"], errors="coerce")
    wide = df.pivot_table(index="case", columns="method", values="lines_f1", aggfunc="first")
    wide = wide.dropna(subset=[c for c in ("GRAP", "LLM") if c in wide.columns])
    if "GRAP" not in wide.columns or "LLM" not in wide.columns:
        raise ValueError(f"Expected GRAP and LLM methods, found: {list(wide.columns)}")
    return wide[["GRAP", "LLM"]].copy()


def fmt_p(p: float) -> str:
    if np.isnan(p):
        return "nan"
    if p < 1e-4:
        return f"{p:.2e}"
    return f"{p:.4f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True, help="path to combined_results_*.csv")
    ap.add_argument("--out", required=True, help="output markdown path")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n_boot", type=int, default=10_000)
    args = ap.parse_args()

    df = pd.read_csv(args.combined)
    paired = build_paired_frame(df)

    grap = paired["GRAP"].to_numpy(dtype=float)
    llm = paired["LLM"].to_numpy(dtype=float)
    diff = grap - llm
    n = len(diff)

    # 1. Wilcoxon signed-rank (with zero-handling = 'wilcox')
    nonzero = diff[diff != 0]
    if len(nonzero) == 0:
        wilc_stat, wilc_p = float("nan"), float("nan")
    else:
        res = stats.wilcoxon(grap, llm, zero_method="wilcox", alternative="two-sided",
                             correction=False, mode="auto")
        wilc_stat, wilc_p = float(res.statistic), float(res.pvalue)
    wilc_one = stats.wilcoxon(grap, llm, zero_method="wilcox", alternative="greater",
                              correction=False, mode="auto") if len(nonzero) > 0 else None
    wilc_one_p = float(wilc_one.pvalue) if wilc_one is not None else float("nan")

    # 2. Paired t-test
    t_stat, t_p = stats.ttest_rel(grap, llm, alternative="two-sided")
    t_one = stats.ttest_rel(grap, llm, alternative="greater")
    # 3. Cliff's delta (treating as independent for effect size magnitude)
    delta, delta_mag = cliffs_delta(grap, llm)
    # 4. Bootstrap CI for mean diff
    mean_diff, ci_lo, ci_hi = bootstrap_mean_diff_ci(diff, n_boot=args.n_boot, seed=args.seed)
    # 5. Sign test
    wins, losses, ties, sign_p = sign_test(grap, llm)

    # Means
    m_grap, m_llm = float(np.mean(grap)), float(np.mean(llm))
    sd_grap, sd_llm = float(np.std(grap, ddof=1)) if n > 1 else 0.0, float(np.std(llm, ddof=1)) if n > 1 else 0.0

    alpha = 0.05
    sig_wilc = wilc_p < alpha
    sig_wilc_one = wilc_one_p < alpha
    sig_t = t_p < alpha
    sig_sign = (not np.isnan(sign_p)) and sign_p < alpha

    report = []
    report.append("# Statistical tests: GRAP-Q vs Pure-LLM")
    report.append("")
    report.append(f"**Input**: `{args.combined}`  ")
    report.append(f"**Paired cases**: n = {n}  ")
    report.append(f"**Metric**: Lines-F1 (per case, paired on case ID)  ")
    report.append(f"**Significance threshold**: α = {alpha}")
    report.append("")
    report.append("## 1. Descriptive statistics")
    report.append("")
    report.append("| Method | Mean | SD | Median | Min | Max |")
    report.append("|---|---:|---:|---:|---:|---:|")
    report.append(f"| GRAP-Q | {m_grap:.4f} | {sd_grap:.4f} | {float(np.median(grap)):.4f} | {grap.min():.4f} | {grap.max():.4f} |")
    report.append(f"| Pure-LLM | {m_llm:.4f} | {sd_llm:.4f} | {float(np.median(llm)):.4f} | {llm.min():.4f} | {llm.max():.4f} |")
    report.append("")
    report.append(f"**Mean paired difference (GRAP − LLM)**: {mean_diff:+.4f}  ")
    report.append(f"**Bootstrap 95% CI (10,000 resamples)**: [{ci_lo:+.4f}, {ci_hi:+.4f}]")
    report.append("")

    report.append("## 2. Paired Wilcoxon signed-rank test (primary)")
    report.append("")
    report.append("The Wilcoxon signed-rank test is the appropriate non-parametric test for paired, "
                  "non-normally distributed per-case Lines-F1 scores.")
    report.append("")
    report.append(f"- Two-sided H0: median(GRAP − LLM) = 0 → W = {wilc_stat:.2f}, p = {fmt_p(wilc_p)}")
    report.append(f"- One-sided H1: median(GRAP − LLM) > 0 → p = {fmt_p(wilc_one_p)}")
    report.append(f"- Significant (two-sided, α={alpha})? **{'YES' if sig_wilc else 'NO'}**")
    report.append(f"- Significant (one-sided 'GRAP > LLM', α={alpha})? **{'YES' if sig_wilc_one else 'NO'}**")
    report.append("")

    report.append("## 3. Paired t-test (parametric robustness check)")
    report.append("")
    report.append(f"- Two-sided: t({n-1}) = {float(t_stat):.3f}, p = {fmt_p(float(t_p))}")
    report.append(f"- One-sided 'GRAP > LLM': t = {float(t_one.statistic):.3f}, p = {fmt_p(float(t_one.pvalue))}")
    report.append(f"- Significant (two-sided, α={alpha})? **{'YES' if sig_t else 'NO'}**")
    report.append("")

    report.append("## 4. Cliff's delta (effect size)")
    report.append("")
    report.append(f"- δ = {delta:+.4f}  ({delta_mag})")
    report.append("- Interpretation: |δ|<0.147 negligible · <0.33 small · <0.474 medium · ≥0.474 large")
    report.append("")

    report.append("## 5. Sign test (wins / losses / ties)")
    report.append("")
    report.append(f"- Wins (GRAP > LLM): {wins}  ")
    report.append(f"- Losses (GRAP < LLM): {losses}  ")
    report.append(f"- Ties: {ties}  ")
    report.append(f"- Two-sided binomial p-value on wins vs losses: p = {fmt_p(sign_p)}")
    report.append(f"- Significant (α={alpha})? **{'YES' if sig_sign else 'NO'}**")
    report.append("")

    report.append("## 6. Per-case table (paired)")
    report.append("")
    report.append("| case | GRAP | LLM | Δ (GRAP−LLM) |")
    report.append("|---|---:|---:|---:|")
    for cid, row in paired.iterrows():
        d = row["GRAP"] - row["LLM"]
        report.append(f"| {cid} | {row['GRAP']:.4f} | {row['LLM']:.4f} | {d:+.4f} |")
    report.append("")

    report.append("## 7. Summary")
    report.append("")
    if sig_wilc_one or (sig_sign and mean_diff > 0):
        report.append(f"GRAP-Q shows a statistically significant improvement over Pure-LLM in Lines-F1 "
                      f"on the {n}-case validation split (paired Wilcoxon one-sided p = {fmt_p(wilc_one_p)}; "
                      f"sign test p = {fmt_p(sign_p)}).")
    else:
        report.append(f"On the current {n}-case validation split, the improvement of GRAP-Q over Pure-LLM "
                      f"in Lines-F1 is observable (Δ̄ = {mean_diff:+.4f}, bootstrap 95% CI [{ci_lo:+.4f}, {ci_hi:+.4f}]) "
                      f"but does not reach statistical significance at α=0.05 under the paired Wilcoxon signed-rank test "
                      f"(one-sided p = {fmt_p(wilc_one_p)}). "
                      f"The small sample size (n={n}) and the number of tied zeros limit statistical power; "
                      f"a larger test set (see `scripts/resplit.py` for a 70/15/15 split) is recommended "
                      f"to strengthen the inference.")
    report.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report), encoding="utf-8")

    # Machine-readable JSON next to the markdown
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps({
        "n": n,
        "mean_grap": m_grap, "mean_llm": m_llm,
        "mean_diff": mean_diff, "bootstrap_ci": [ci_lo, ci_hi],
        "wilcoxon_two_sided_p": wilc_p, "wilcoxon_one_sided_greater_p": wilc_one_p,
        "paired_t_two_sided_p": float(t_p), "paired_t_one_sided_greater_p": float(t_one.pvalue),
        "cliffs_delta": delta, "cliffs_delta_magnitude": delta_mag,
        "sign_test": {"wins": wins, "losses": losses, "ties": ties, "p_value": sign_p},
    }, indent=2), encoding="utf-8")

    print(f"[OK] Report written to {out_path}")
    print(f"[OK] JSON summary written to {json_path}")
    print(f"     n={n}, mean delta={mean_diff:+.4f}, Wilcoxon one-sided p={fmt_p(wilc_one_p)}")


if __name__ == "__main__":
    main()
