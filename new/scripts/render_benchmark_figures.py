"""Render paper-style figures from the synthetic benchmark report.

Reads:
    experiments/synthetic_benchmark_report.json

Writes (to --out, default experiments/figures/):
    fig_a_boxplot_by_density.png        Lines-F1 box plot by defect density
    fig_b_latency_histogram.png         Latency distribution
    fig_c_scatter_f1_vs_density.png     F1 vs defect-count with regression
    fig_d_per_defect_outcomes.png       Per-defect stacked outcome bars
    fig_e_bootstrap_ci.png              Bootstrap CI of mean Lines-F1
                                        (overall + per defect-density)
    fig_f_per_template.png              Per-template mean F1 (bonus)

Usage:
    python -m scripts.render_benchmark_figures
    python -m scripts.render_benchmark_figures --out experiments/figures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
import numpy as np


# Paper-friendly styling: clean serif text, colourblind-friendly palette.
ACCENT = "#1e3a8a"
ACCENT_LIGHT = "#3730a3"
PASS = "#065f46"
PARTIAL = "#d97706"
FAIL = "#9a1b1b"
GREY = "#6b7280"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 110,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})


# ---------------------------------------------------------------------------
# Figure A: Box plot of Lines-F1 by defect density
# ---------------------------------------------------------------------------
def fig_boxplot_by_density(rows: list[dict], out_path: Path):
    by_count: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    for r in rows:
        k = r.get("n_injected", 0)
        if k in by_count and not r.get("error"):
            by_count[k].append(r.get("lines_f1", 0.0))

    keys = [k for k in (1, 2, 3, 4) if by_count[k]]
    data = [by_count[k] for k in keys]
    labels = [f"{k}\nn={len(by_count[k])}" for k in keys]

    fig, ax = plt.subplots(figsize=(6, 4))
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True,
                    showmeans=True, meanline=False,
                    boxprops=dict(facecolor="#dbeafe", edgecolor=ACCENT,
                                  linewidth=1.2),
                    medianprops=dict(color=ACCENT, linewidth=2),
                    meanprops=dict(marker="o", markerfacecolor=PASS,
                                   markeredgecolor=PASS, markersize=6),
                    whiskerprops=dict(color=ACCENT),
                    capprops=dict(color=ACCENT),
                    flierprops=dict(marker="o", markerfacecolor=FAIL,
                                    markeredgecolor=FAIL, markersize=4,
                                    alpha=0.7))
    # Overlay individual points for small N visibility.
    for i, vals in enumerate(data, start=1):
        x = np.random.normal(i, 0.04, size=len(vals))
        ax.scatter(x, vals, alpha=0.35, color=ACCENT, s=18,
                   zorder=3, linewidths=0)

    ax.set_xlabel("Defects injected per case")
    ax.set_ylabel("Lines-F1")
    ax.set_title("Lines-F1 stratified by defect density")
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0, color=GREY, linewidth=0.5)

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure B: Latency histogram with median + p95 lines
# ---------------------------------------------------------------------------
def fig_latency_histogram(rows: list[dict], summary: dict, out_path: Path):
    latencies = [r.get("wall_time_s", 0) for r in rows
                 if not r.get("error") and r.get("wall_time_s", 0) > 0]
    if not latencies:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    n_bins = max(8, min(20, len(latencies) // 2))
    ax.hist(latencies, bins=n_bins, color="#dbeafe", edgecolor=ACCENT,
            linewidth=1.0)

    lat = summary.get("latency_stats", {})
    median = lat.get("median", np.median(latencies))
    p95 = lat.get("p95", np.percentile(latencies, 95))
    mean_v = lat.get("mean", np.mean(latencies))

    ax.axvline(median, color=PASS, linewidth=2, linestyle="--",
               label=f"median = {median:.1f}s")
    ax.axvline(mean_v, color=ACCENT_LIGHT, linewidth=1.5, linestyle="-",
               label=f"mean = {mean_v:.1f}s")
    ax.axvline(p95, color=FAIL, linewidth=2, linestyle="--",
               label=f"p95 = {p95:.1f}s")

    ax.set_xlabel("Wall time per case (s)")
    ax.set_ylabel("Number of cases")
    ax.set_title("Per-case latency distribution")
    ax.legend(frameon=False, loc="upper right")

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure C: Scatter Lines-F1 vs defect count with linear regression line
# ---------------------------------------------------------------------------
def fig_scatter_f1_vs_density(rows: list[dict], out_path: Path):
    xs, ys, templates = [], [], []
    for r in rows:
        if r.get("error"):
            continue
        xs.append(r.get("n_injected", 0))
        ys.append(r.get("lines_f1", 0.0))
        templates.append(r.get("template", "?"))
    if len(xs) < 3:
        return

    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)

    # Linear fit
    slope, intercept = np.polyfit(xs_arr, ys_arr, 1)
    fit_x = np.linspace(0.7, 4.3, 100)
    fit_y = slope * fit_x + intercept

    # Pearson correlation
    if xs_arr.std() > 0 and ys_arr.std() > 0:
        r_corr = np.corrcoef(xs_arr, ys_arr)[0, 1]
    else:
        r_corr = 0.0

    fig, ax = plt.subplots(figsize=(6, 4))
    # Jitter x slightly so overlapping points are visible.
    jitter = np.random.normal(0, 0.07, size=len(xs))
    ax.scatter(xs_arr + jitter, ys_arr, alpha=0.55, s=42,
               color=ACCENT, edgecolors="white", linewidths=0.5)
    ax.plot(fit_x, fit_y, color=FAIL, linewidth=2, linestyle="--",
            label=f"y = {slope:.3f}x + {intercept:.3f}\nPearson r = {r_corr:.2f}")

    ax.set_xlabel("Defects injected per case")
    ax.set_ylabel("Lines-F1")
    ax.set_title("Lines-F1 vs defect density (per-case)")
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xlim(0.5, 4.5)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(frameon=False, loc="upper right")

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure D: Per-defect stacked outcome bars (fixed / not fixed / introduced)
# ---------------------------------------------------------------------------
def fig_per_defect_outcomes(summary: dict, out_path: Path):
    per_defect = summary.get("per_defect", {})
    if not per_defect:
        return

    names = list(per_defect.keys())
    inj = [per_defect[n].get("injected", 0) for n in names]
    fixed = [per_defect[n].get("fixed_regex", 0) for n in names]
    not_fixed = [inj[i] - fixed[i] for i in range(len(names))]
    introduced = [per_defect[n].get("introduced", 0) for n in names]

    # Display as percentage of total appearances (injected + introduced).
    n_cat = len(names)
    x = np.arange(n_cat)
    width = 0.65

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    bar_fixed = ax.bar(x, fixed, width, label="Fixed (regex proxy)",
                       color=PASS)
    bar_unfixed = ax.bar(x, not_fixed, width, bottom=fixed,
                         label="Not fixed", color=FAIL)
    # Introduced is shown as a separate offset bar on the right side.
    width2 = 0.25
    bar_intro = ax.bar(x + width / 2 + width2 / 2 + 0.02, introduced,
                       width2, label="Introduced (newly\ncreated by patch)",
                       color=PARTIAL)

    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("Misuse", "Misuse").replace("Rename", "Rename")
                        for n in names], rotation=18, ha="right")
    ax.set_ylabel("Number of cases")
    ax.set_title("Per-defect outcomes")
    ax.legend(frameon=False, loc="upper right")

    for rect, val in zip(bar_fixed, fixed):
        if val > 0:
            ax.text(rect.get_x() + rect.get_width() / 2,
                    rect.get_height() / 2, str(val),
                    ha="center", va="center", color="white",
                    fontweight="bold", fontsize=9)

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure E: Bootstrap CI plot (overall + by defect density)
# ---------------------------------------------------------------------------
def fig_bootstrap_ci(summary: dict, out_path: Path):
    rows_to_plot = []
    rows_to_plot.append(("Overall",
                         summary.get("mean_lines_f1", 0.0),
                         summary.get("mean_lines_f1_ci_lower", 0.0),
                         summary.get("mean_lines_f1_ci_upper", 0.0),
                         summary.get("n_cases", 0)))
    by_count = summary.get("by_injected_count", {})
    for k in (1, 2, 3, 4):
        d = by_count.get(str(k)) or by_count.get(k)
        if d:
            rows_to_plot.append((f"{k}-defect",
                                 d["mean_lines_f1"],
                                 d.get("ci_lower", d["mean_lines_f1"]),
                                 d.get("ci_upper", d["mean_lines_f1"]),
                                 d["n_cases"]))

    labels = [r[0] for r in rows_to_plot]
    means = [r[1] for r in rows_to_plot]
    los = [r[2] for r in rows_to_plot]
    his = [r[3] for r in rows_to_plot]
    ns = [r[4] for r in rows_to_plot]

    err_lower = [max(0.0, means[i] - los[i]) for i in range(len(means))]
    err_upper = [max(0.0, his[i] - means[i]) for i in range(len(means))]

    y_pos = np.arange(len(labels))
    colours = [ACCENT] + [ACCENT_LIGHT] * (len(labels) - 1)

    fig, ax = plt.subplots(figsize=(6.5, 0.6 + 0.55 * len(labels)))
    ax.errorbar(means, y_pos,
                xerr=[err_lower, err_upper],
                fmt="o", color=ACCENT, ecolor=ACCENT,
                capsize=5, markersize=8, linewidth=1.6,
                markerfacecolor="white", markeredgewidth=1.6)
    for i, (m, lo, hi, n) in enumerate(zip(means, los, his, ns)):
        ax.text(m + 0.03, i,
                f"{m:.3f}  [{lo:.3f}, {hi:.3f}]  n={n}",
                va="center", fontsize=9, color="#1f2937")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Mean Lines-F1 (bootstrap 95% CI)")
    ax.set_title("Mean Lines-F1 with bootstrap confidence intervals")
    ax.set_xlim(-0.05, 1.05)
    ax.axvline(0, color=GREY, linewidth=0.5)

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure F (bonus): Per-template mean Lines-F1
# ---------------------------------------------------------------------------
def fig_per_template(summary: dict, out_path: Path):
    by_tpl = summary.get("by_template", {})
    if not by_tpl:
        return

    items = sorted(by_tpl.items(), key=lambda kv: kv[1]["mean_lines_f1"],
                   reverse=True)
    names = [k for k, _ in items]
    means = [v["mean_lines_f1"] for _, v in items]
    counts = [v["n_cases"] for _, v in items]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(6.5, 0.5 + 0.45 * len(names)))
    bars = ax.barh(y, means, color=ACCENT, edgecolor="white", linewidth=0.8)
    for i, (m, n) in enumerate(zip(means, counts)):
        ax.text(m + 0.01, i, f" {m:.3f}  (n={n})",
                va="center", fontsize=9, color="#1f2937")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("Mean Lines-F1")
    ax.set_title("Mean Lines-F1 by template family")
    ax.set_xlim(0, max(0.6, max(means) + 0.15))

    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report",
                    default="experiments/synthetic_benchmark_report.json",
                    type=Path)
    ap.add_argument("--out", default="experiments/figures", type=Path)
    args = ap.parse_args()

    if not args.report.exists():
        raise SystemExit(
            f"Report not found at {args.report}. "
            "Run scripts/run_synthetic_benchmark.py first.")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    rows = report.get("rows", [])

    args.out.mkdir(parents=True, exist_ok=True)

    fig_boxplot_by_density(rows, args.out / "fig_a_boxplot_by_density.png")
    print(f"  fig_a_boxplot_by_density.png")

    fig_latency_histogram(rows, summary, args.out / "fig_b_latency_histogram.png")
    print(f"  fig_b_latency_histogram.png")

    fig_scatter_f1_vs_density(rows, args.out / "fig_c_scatter_f1_vs_density.png")
    print(f"  fig_c_scatter_f1_vs_density.png")

    fig_per_defect_outcomes(summary, args.out / "fig_d_per_defect_outcomes.png")
    print(f"  fig_d_per_defect_outcomes.png")

    fig_bootstrap_ci(summary, args.out / "fig_e_bootstrap_ci.png")
    print(f"  fig_e_bootstrap_ci.png")

    fig_per_template(summary, args.out / "fig_f_per_template.png")
    print(f"  fig_f_per_template.png")

    print(f"\nWrote 6 figures to {args.out}")


if __name__ == "__main__":
    main()
