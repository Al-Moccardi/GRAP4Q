"""Bugs4Q-style 3-method patch comparison tab for the Gradio UI.

Replaces the existing `Synthetic stress test` tab. Shows ten
generated Bugs4Q-style cases derived from the four FAIL patterns
in Section 6.5 of the paper:

    DeprecatedExecuteAPI    execute(qc, backend=bk)
    LegacyBackendName       local_*_simulator
    GetDataMisuse           Result.get_data(qc)
    IdenGateRename          QuantumCircuit.iden(...)

For each case, the tab presents three patches side-by-side:

    V1       GRAP4Q production prompt (retrieval + guardrails)
    V4       V1 + runtime defect localiser (winning ablation)
    Pure-LLM same V1 system prompt, no retrieval, no edit-region
             restriction, no guardrail validation; mirrors
             scripts/run_purellm.py from the paper repo

Below the per-case panels, an aggregate table reports per-family
mean Lines-F1 for each method, plus an overall row across all 10
cases.

Patches are pre-computed by `scripts/precompute_demo_patches.py`
and read from cache; no LLM calls happen at app runtime.

Usage in app/server.py:

    from app.comparison_tab import build_comparison_tab

    with gr.Tabs():
        with gr.Tab("Interactive demo"):
            ...
        with gr.Tab("Bugs4Q comparison: V1 vs V4 vs Pure-LLM"):
            build_comparison_tab()
"""
from __future__ import annotations

import difflib
import html
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import gradio as gr


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "app" / "demo_cases"

METHODS = ["v1", "v4", "purellm"]
METHOD_LABELS = {
    "v1": "V1 (production)",
    "v4": "V4 (+ localiser)",
    "purellm": "Pure-LLM (no retrieval, no guardrails)",
}
METHOD_SHORT = {"v1": "V1", "v4": "V4", "purellm": "Pure-LLM"}


# Friendly labels for each family. Real cases use family ids prefixed
# with `real_`; synthetic cases use family ids prefixed with `syn_`.
FAMILY_LABELS = {
    # Real Bugs4Q val cases
    "real_compatibility":   "Real \u00b7 library-version compatibility",
    "real_workflow":        "Real \u00b7 missing workflow steps",
    "real_logic":           "Real \u00b7 qubit-ordering logic bug",
    "real_iden_only":       "Real \u00b7 iden-only deprecation",
    "real_terra_internal":  "Real \u00b7 terra-internal regression",
    # Synthetic-hard cases
    "syn_logic_offbyone":   "Synthetic \u00b7 off-by-one logic",
    "syn_register_misuse":  "Synthetic \u00b7 register misuse",
    "syn_pass_interface":   "Synthetic \u00b7 transpiler pass drift",
    "syn_long_localised":   "Synthetic \u00b7 long-file localised typo",
    "syn_algorithmic":      "Synthetic \u00b7 algorithmic sign error",
}


# ---------------------------------------------------------------------------
@dataclass
class CaseBundle:
    case_id: str
    family: str
    kind: str        # "real" or "synthetic"
    source: str      # original Bugs4Q case id, or "synthetic"
    title: str
    summary: str
    buggy_src: str
    fixed_src: str
    results: dict[str, dict | None]   # method -> result dict


def _list_cases() -> list[str]:
    if not DEMO_DIR.exists():
        return []
    return sorted(d.name for d in DEMO_DIR.iterdir() if d.is_dir())


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback


def _load_case(case_id: str) -> CaseBundle:
    case_dir = DEMO_DIR / case_id
    meta = _load_json(case_dir / "meta.json") or {}
    family = str(meta.get("family", "?"))
    kind = str(meta.get("kind", "synthetic"))
    source = str(meta.get("source", "synthetic"))
    circuit = str(meta.get("circuit", case_id))
    n_qubits = meta.get("n_qubits", "?")
    n_lines = meta.get("n_lines", "?")
    short_summary = str(meta.get("summary", ""))

    if kind == "real":
        kind_badge = ('<span style="display:inline-block;padding:2px 8px;'
                      'border-radius:10px;background:#dbeafe;color:#1e40af;'
                      'font-size:11px;font-weight:600;'
                      'margin-right:6px;">REAL Bugs4Q</span>')
        provenance = (f' <span style="font-size:12px;color:#6b7280;">'
                      f'(source: <code>{html.escape(source)}</code>)</span>')
    else:
        kind_badge = ('<span style="display:inline-block;padding:2px 8px;'
                      'border-radius:10px;background:#fef3c7;color:#92400e;'
                      'font-size:11px;font-weight:600;'
                      'margin-right:6px;">SYNTHETIC</span>')
        provenance = ''

    title = f"{case_id} \u2014 {circuit}"
    summary = (
        f'{kind_badge}'
        f'<b>Family:</b> {html.escape(FAMILY_LABELS.get(family, family))} '
        f'&middot; <b>Qubits:</b> {html.escape(str(n_qubits))} '
        f'&middot; <b>Lines:</b> {html.escape(str(n_lines))}'
        f'{provenance}<br>'
        f'{html.escape(short_summary)}'
    )

    return CaseBundle(
        case_id=case_id, family=family, kind=kind, source=source,
        title=title, summary=summary,
        buggy_src=_read_text(case_dir / "buggy.py", "# (missing)\n"),
        fixed_src=_read_text(case_dir / "fixed.py", "# (missing)\n"),
        results={m: _load_json(case_dir / f"{m}_result.json")
                 for m in METHODS},
    )


# ---------------------------------------------------------------------------
# Aggregate computation
# ---------------------------------------------------------------------------
def _all_bundles() -> list[CaseBundle]:
    return [_load_case(cid) for cid in _list_cases()]


def _aggregate_html(bundles: list[CaseBundle]) -> str:
    """Per-family mean Lines-F1 grouped by kind (real / synthetic)."""
    if not bundles:
        return ""

    def _mean(rows: list[dict | None], key: str) -> float | None:
        vals = [float(r[key]) for r in rows
                if r is not None and key in r and r.get("error") is None]
        return statistics.mean(vals) if vals else None

    def _fmt(v: float | None) -> str:
        if v is None:
            return "\u2014"
        return f"{v:.3f}"

    def _cell(v: float | None, best: float | None) -> str:
        if v is None:
            return ('<td style="padding:6px 10px;border-bottom:1px solid '
                    '#f3f4f6;text-align:right;color:#9ca3af;">\u2014</td>')
        is_best = best is not None and abs(v - best) < 1e-9
        bg = "#dcfce7" if is_best else "transparent"
        weight = "600" if is_best else "400"
        return (f'<td style="padding:6px 10px;border-bottom:1px solid '
                f'#f3f4f6;text-align:right;background:{bg};'
                f'font-weight:{weight};font-family:ui-monospace,Menlo,'
                f'monospace;">{_fmt(v)}</td>')

    def _wt_cell(v1: float | None, v4: float | None,
                 pl: float | None) -> str:
        return (f'<td style="padding:6px 10px;border-bottom:1px solid '
                f'#f3f4f6;text-align:right;color:#6b7280;font-family:'
                f'ui-monospace,Menlo,monospace;font-size:12px;">'
                f'{_fmt(v1)} / {_fmt(v4)} / {_fmt(pl)}'
                f'</td>')

    def _family_row(family_label: str, family_bundles: list[CaseBundle]
                    ) -> str:
        n = len(family_bundles)
        per_method = {m: _mean(
            [b.results.get(m) for b in family_bundles], "lines_f1")
            for m in METHODS}
        wt_means = {m: _mean(
            [b.results.get(m) for b in family_bundles], "wall_time_s")
            for m in METHODS}
        present = [v for v in per_method.values() if v is not None]
        best = max(present) if present else None
        return (
            '<tr>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #f3f4f6;'
            f'padding-left:24px;">{family_label}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #f3f4f6;'
            f'text-align:center;color:#6b7280;">{n}</td>'
            + _cell(per_method["v1"], best)
            + _cell(per_method["v4"], best)
            + _cell(per_method["purellm"], best)
            + _wt_cell(wt_means["v1"], wt_means["v4"], wt_means["purellm"])
            + '</tr>')

    def _subtotal_row(label: str, group_bundles: list[CaseBundle],
                      bg_color: str) -> str:
        n = len(group_bundles)
        per_method = {m: _mean(
            [b.results.get(m) for b in group_bundles], "lines_f1")
            for m in METHODS}
        wt_means = {m: _mean(
            [b.results.get(m) for b in group_bundles], "wall_time_s")
            for m in METHODS}
        present = [v for v in per_method.values() if v is not None]
        best = max(present) if present else None
        return (
            f'<tr style="background:{bg_color};">'
            f'<td style="padding:8px 10px;font-weight:600;'
            f'border-top:1px solid #cbd5e1;">{html.escape(label)}</td>'
            f'<td style="padding:8px 10px;text-align:center;'
            f'font-weight:600;border-top:1px solid #cbd5e1;">{n}</td>'
            + _cell(per_method["v1"], best).replace(
                "border-bottom:1px solid #f3f4f6",
                "border-top:1px solid #cbd5e1")
            + _cell(per_method["v4"], best).replace(
                "border-bottom:1px solid #f3f4f6",
                "border-top:1px solid #cbd5e1")
            + _cell(per_method["purellm"], best).replace(
                "border-bottom:1px solid #f3f4f6",
                "border-top:1px solid #cbd5e1")
            + f'<td style="padding:8px 10px;text-align:right;color:#374151;'
            f'font-family:ui-monospace,Menlo,monospace;font-size:12px;'
            f'border-top:1px solid #cbd5e1;">'
            f'{_fmt(wt_means["v1"])} / '
            f'{_fmt(wt_means["v4"])} / '
            f'{_fmt(wt_means["purellm"])}</td>'
            f'</tr>')

    def _section_header(label: str, color: str) -> str:
        return (
            f'<tr style="background:{color};">'
            f'<td colspan="6" style="padding:8px 12px;font-weight:600;'
            f'font-size:13px;border-top:2px solid #94a3b8;'
            f'border-bottom:1px solid #94a3b8;">{html.escape(label)}</td>'
            f'</tr>')

    real_bundles = [b for b in bundles if b.kind == "real"]
    syn_bundles = [b for b in bundles if b.kind == "synthetic"]

    rows_html: list[str] = []
    if real_bundles:
        rows_html.append(
            _section_header("REAL Bugs4Q val cases", "#dbeafe"))
        by_family: dict[str, list[CaseBundle]] = defaultdict(list)
        for b in real_bundles:
            by_family[b.family].append(b)
        for family in sorted(by_family.keys()):
            rows_html.append(_family_row(
                FAMILY_LABELS.get(family, family), by_family[family]))
        rows_html.append(_subtotal_row(
            "Subtotal: real", real_bundles, "#eff6ff"))

    if syn_bundles:
        rows_html.append(
            _section_header("SYNTHETIC hard cases", "#fef3c7"))
        by_family = defaultdict(list)
        for b in syn_bundles:
            by_family[b.family].append(b)
        for family in sorted(by_family.keys()):
            rows_html.append(_family_row(
                FAMILY_LABELS.get(family, family), by_family[family]))
        rows_html.append(_subtotal_row(
            "Subtotal: synthetic", syn_bundles, "#fffbeb"))

    if real_bundles and syn_bundles:
        rows_html.append(_subtotal_row(
            "Overall (real + synthetic)", bundles, "#f1f5f9"))

    return (
        '<div style="margin:18px 0 8px 0;">'
        '<div style="font-size:14px;font-weight:600;margin-bottom:6px;">'
        'Per-family aggregate \u2014 mean Lines-F1, grouped by case kind'
        '</div>'
        '<div style="font-size:12px;color:#6b7280;margin-bottom:8px;'
        'line-height:1.5;">'
        'Real cases are drawn verbatim from the 75/25/5 Bugs4Q '
        'validation split (the same cases reported in Section\u00a06.3 '
        'of the paper). Synthetic cases are hand-designed combinations '
        'of common Qiskit defects with logic / interface complications, '
        'intended to stress test methods that lack the GRAP4Q '
        'guardrail and span-focusing layers. Best mean per row '
        'highlighted in green. Wall-time column reports mean per-case '
        'latency for V1 / V4 / Pure-LLM in seconds.'
        '</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;'
        'font-family:system-ui,sans-serif;">'
        '<thead><tr style="background:#f1f5f9;">'
        '<th style="padding:8px 10px;text-align:left;border-bottom:2px '
        'solid #94a3b8;">Family</th>'
        '<th style="padding:8px 10px;text-align:center;border-bottom:2px '
        'solid #94a3b8;">N</th>'
        '<th style="padding:8px 10px;text-align:right;border-bottom:2px '
        'solid #94a3b8;">V1</th>'
        '<th style="padding:8px 10px;text-align:right;border-bottom:2px '
        'solid #94a3b8;">V4</th>'
        '<th style="padding:8px 10px;text-align:right;border-bottom:2px '
        'solid #94a3b8;">Pure-LLM</th>'
        '<th style="padding:8px 10px;text-align:right;border-bottom:2px '
        'solid #94a3b8;">wall-time (s)</th>'
        '</tr></thead><tbody>'
        + "".join(rows_html)
        + '</tbody></table></div>')


# ---------------------------------------------------------------------------
# Per-case rendering helpers
# ---------------------------------------------------------------------------
_PLACEHOLDER_NOTICE = (
    '<div style="padding:14px 18px;border-radius:8px;'
    'background:#fff7ed;border:1px solid #fdba74;color:#9a3412;'
    'font-size:13px;line-height:1.6;">'
    '<b>No cached patch found for this case.</b><br>'
    'Run <code>python scripts/precompute_demo_patches.py</code> '
    'to generate <code>v1_result.json</code>, '
    '<code>v4_result.json</code>, and <code>purellm_result.json</code> '
    'for the demo cases. The script takes about 25\u201340 minutes total.'
    '</div>'
)


def _format_diff(reference: str, candidate: str,
                 reference_label: str, candidate_label: str) -> str:
    diff = list(difflib.unified_diff(
        reference.splitlines(keepends=False),
        candidate.splitlines(keepends=False),
        fromfile=reference_label, tofile=candidate_label, lineterm=""))
    if not diff:
        return ('<div style="padding:8px;color:#16a34a;font-style:italic;'
                'font-size:13px;">Identical to gold.</div>')
    out = ['<pre style="font-family:ui-monospace,Menlo,Consolas,monospace;'
           'font-size:11.5px;line-height:1.45;padding:10px;'
           'background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;'
           'overflow-x:auto;white-space:pre;max-height:340px;">']
    for line in diff:
        if line.startswith('+++') or line.startswith('---'):
            out.append(f'<span style="color:#1d4ed8;font-weight:600;">'
                       f'{html.escape(line)}</span>')
        elif line.startswith('@@'):
            out.append(f'<span style="color:#7c3aed;">{html.escape(line)}'
                       f'</span>')
        elif line.startswith('+'):
            out.append(f'<span style="background:#dcfce7;color:#166534;">'
                       f'{html.escape(line)}</span>')
        elif line.startswith('-'):
            out.append(f'<span style="background:#fee2e2;color:#991b1b;">'
                       f'{html.escape(line)}</span>')
        else:
            out.append(html.escape(line))
        out.append("\n")
    out.append('</pre>')
    return "".join(out)


def _format_metrics_table(bundle: CaseBundle) -> str:
    methods = METHODS
    labels = [METHOD_LABELS[m] for m in methods]
    res = [bundle.results[m] for m in methods]

    def _f(d: dict | None, key: str, fmt: str = "{:.3f}") -> str:
        if d is None or key not in d or d[key] is None:
            return "\u2014"
        try:
            return fmt.format(d[key])
        except Exception:
            return str(d[key])

    def _badge(d: dict | None) -> str:
        if d is None:
            return ('<span style="display:inline-block;padding:2px 8px;'
                    'border-radius:10px;background:#f3f4f6;color:#6b7280;'
                    'font-size:11px;font-weight:600;">no cache</span>')
        if d.get("error"):
            return ('<span style="display:inline-block;padding:2px 8px;'
                    'border-radius:10px;background:#fee2e2;color:#991b1b;'
                    'font-size:11px;font-weight:600;" title="{}">error</span>'
                    .format(html.escape(str(d["error"])[:200])))
        return ('<span style="display:inline-block;padding:2px 8px;'
                'border-radius:10px;background:#dcfce7;color:#166534;'
                'font-size:11px;font-weight:600;">ok</span>')

    rows = [
        ("Status",) + tuple(_badge(r) for r in res),
        ("Lines-F1",) + tuple(_f(r, "lines_f1") for r in res),
        ("Lines precision",) + tuple(_f(r, "lines_p") for r in res),
        ("Lines recall",) + tuple(_f(r, "lines_r") for r in res),
        ("Edits emitted",) + tuple(_f(r, "num_edits", "{:d}") for r in res),
        ("Lines touched",) + tuple(_f(r, "lines_touched", "{:d}") for r in res),
        ("Refinement attempts",) + tuple(_f(r, "attempts", "{:d}")
                                         for r in res),
        ("Wall-time",) + tuple(_f(r, "wall_time_s", "{:.1f} s") for r in res),
    ]

    parts = ['<table style="width:100%;border-collapse:collapse;'
             'font-size:13px;font-family:system-ui,sans-serif;">'
             '<thead><tr>'
             '<th style="text-align:left;padding:6px 8px;'
             'border-bottom:2px solid #d1d5db;">Metric</th>']
    for lab in labels:
        parts.append(f'<th style="text-align:left;padding:6px 8px;'
                     f'border-bottom:2px solid #d1d5db;">{html.escape(lab)}</th>')
    parts.append('</tr></thead><tbody>')

    for row in rows:
        name, *cells = row
        parts.append(
            '<tr>'
            f'<td style="padding:5px 8px;border-bottom:1px solid #f3f4f6;'
            f'color:#4b5563;">{html.escape(name)}</td>')
        for c in cells:
            parts.append(
                f'<td style="padding:5px 8px;border-bottom:1px solid '
                f'#f3f4f6;font-family:ui-monospace,Menlo,monospace;">'
                f'{c}</td>')
        parts.append('</tr>')
    parts.append("</tbody></table>")
    return "".join(parts)


def _format_rationales(bundle: CaseBundle) -> str:
    parts = []
    for m in METHODS:
        d = bundle.results.get(m)
        label = METHOD_LABELS[m]
        if d is None:
            parts.append(
                f'<div style="font-size:12px;color:#6b7280;margin-bottom:6px;">'
                f'<b>{html.escape(label)}</b>: no cached result.</div>')
            continue
        if d.get("error"):
            parts.append(
                f'<div style="font-size:12px;color:#991b1b;margin-bottom:6px;">'
                f'<b>{html.escape(label)}</b>: error \u2014 '
                f'{html.escape(str(d["error"])[:300])}</div>')
            continue
        rat = (d.get("rationale") or "").strip() or "(no rationale)"
        parts.append(
            f'<div style="font-size:13px;line-height:1.5;'
            f'padding:8px 12px;background:#f9fafb;border-left:3px solid '
            f'#6366f1;border-radius:4px;margin-bottom:6px;">'
            f'<b>{html.escape(label)} rationale:</b><br>'
            f'{html.escape(rat)}</div>')
    return "".join(parts)


def _format_summary_html(bundle: CaseBundle) -> str:
    return (
        f'<div style="font-size:14px;line-height:1.55;'
        f'padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;'
        f'border-radius:6px;margin-bottom:8px;">'
        f'<div style="font-weight:600;font-size:15px;margin-bottom:6px;">'
        f'{html.escape(bundle.title)}</div>'
        f'{bundle.summary}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
def _render_for_case(case_id: str
                     ) -> tuple[str, str, str, str, str, str, str, str, str,
                                str, str]:
    bundle = _load_case(case_id)
    summary_html = _format_summary_html(bundle)

    if all(bundle.results[m] is None for m in METHODS):
        metrics_html = _PLACEHOLDER_NOTICE
    else:
        metrics_html = _format_metrics_table(bundle)

    def _patched(m: str) -> str:
        d = bundle.results.get(m)
        if d is None:
            return "# (no cached patch)\n"
        return d.get("patched_src") or "# (no patched source)\n"

    v1_src = _patched("v1")
    v4_src = _patched("v4")
    pl_src = _patched("purellm")

    v1_diff = _format_diff(bundle.fixed_src, v1_src,
                           "gold (fixed.py)", "V1 patch")
    v4_diff = _format_diff(bundle.fixed_src, v4_src,
                           "gold (fixed.py)", "V4 patch")
    pl_diff = _format_diff(bundle.fixed_src, pl_src,
                           "gold (fixed.py)", "Pure-LLM patch")

    rationales = _format_rationales(bundle)

    return (summary_html, metrics_html,
            bundle.buggy_src, bundle.fixed_src,
            v1_src, v4_src, pl_src,
            v1_diff, v4_diff, pl_diff,
            rationales)


def _refresh_aggregate() -> str:
    return _aggregate_html(_all_bundles())


# ---------------------------------------------------------------------------
def build_comparison_tab() -> None:
    cases = _list_cases()
    if not cases:
        gr.HTML(
            '<div style="padding:18px;color:#991b1b;background:#fef2f2;'
            'border:1px solid #fecaca;border-radius:6px;font-size:14px;">'
            'No demo cases found under <code>app/demo_cases/</code>. '
            'Run <code>python build_cases.py</code> first.'
            '</div>')
        return

    default_case = cases[0]
    initial = _render_for_case(default_case)

    gr.HTML('<div class="grap4q-col-heading">'
            'Bugs4Q-style comparison \u2014 V1 vs V4 vs Pure-LLM</div>')
    gr.HTML(
        '<p style="font-size:13px;color:#475569;margin:0 0 14px 0;'
        'line-height:1.55;">'
        'Ten cases comparing three patching methods. '
        '<b>Five real cases</b> are drawn verbatim from the 75/25/5 '
        'Bugs4Q validation split (the same cases reported in '
        'Section\u00a06.3 of the paper); they reproduce the paper\u2019s '
        'Pure-LLM behaviour. '
        '<b>Five synthetic cases</b> are hand-designed combinations of '
        'logic / interface bugs with deprecated Qiskit patterns, intended '
        'to stress-test methods that lack the GRAP4Q guardrail and '
        'span-focusing layers. '
        'Each case is patched by three methods: '
        '<b>V1</b> is the GRAP4Q production pipeline (retrieval + '
        'guardrails + production prompt); '
        '<b>V4</b> is the leading prompt variant from the ablation '
        '(V1 plus a runtime defect localiser in the user payload); '
        '<b>Pure-LLM</b> uses the same V1 system prompt but disables '
        'retrieval, edit-region restrictions, and guardrail validation '
        '(mirrors <code>scripts/run_purellm.py</code> from the paper '
        'repo). Patches are pre-computed by '
        '<code>scripts/precompute_demo_patches.py</code>; the app makes '
        'no live LLM calls.</p>')

    case_dropdown = gr.Dropdown(
        label="Demo case",
        choices=cases, value=default_case)

    summary_box = gr.HTML(initial[0])
    metrics_box = gr.HTML(initial[1])

    with gr.Row(equal_height=False):
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">'
                    'Original (buggy) source</div>')
            buggy_box = gr.Code(label="buggy.py", language="python",
                                value=initial[2], lines=18,
                                interactive=False)
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">'
                    'Gold (fixed.py)</div>')
            fixed_box = gr.Code(label="fixed.py", language="python",
                                value=initial[3], lines=18,
                                interactive=False)

    with gr.Row(equal_height=False):
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">V1 patched</div>')
            v1_box = gr.Code(label="V1 patch", language="python",
                             value=initial[4], lines=16,
                             interactive=False)
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">V4 patched</div>')
            v4_box = gr.Code(label="V4 patch", language="python",
                             value=initial[5], lines=16,
                             interactive=False)
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">Pure-LLM patched</div>')
            pl_box = gr.Code(label="Pure-LLM patch", language="python",
                             value=initial[6], lines=16,
                             interactive=False)

    with gr.Row(equal_height=False):
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">'
                    'Diff: V1 vs gold</div>')
            v1_diff_box = gr.HTML(initial[7])
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">'
                    'Diff: V4 vs gold</div>')
            v4_diff_box = gr.HTML(initial[8])
        with gr.Column():
            gr.HTML('<div class="grap4q-section-label">'
                    'Diff: Pure-LLM vs gold</div>')
            pl_diff_box = gr.HTML(initial[9])

    gr.HTML('<div class="grap4q-section-label">Rationales</div>')
    rationale_box = gr.HTML(initial[10])

    # Aggregate section
    gr.HTML('<div style="height:18px;"></div>')
    aggregate_box = gr.HTML(_refresh_aggregate())
    refresh_btn = gr.Button("Refresh aggregate", size="sm")
    refresh_btn.click(_refresh_aggregate, outputs=aggregate_box)

    case_dropdown.change(
        fn=_render_for_case,
        inputs=case_dropdown,
        outputs=[summary_box, metrics_box,
                 buggy_box, fixed_box,
                 v1_box, v4_box, pl_box,
                 v1_diff_box, v4_diff_box, pl_diff_box,
                 rationale_box],
    )
