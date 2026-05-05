"""Gradio UI for GRAP-Q. Research-demo styling with:

- paper masthead (title, authors, affiliation)
- left panel:   buggy input + guardrail verdict on the *original*
- centre panel: six-stage pipeline trace card (query -> BM25 -> re-rank
                -> selector -> focus -> Ollama -> CompositeGuard)
- right panel:  patched output + guardrail verdict on the *patched*
                source. Each row shows the before/after transition so a
                reviewer can see exactly which admissibility checks the
                framework fixed.

Contains NO pipeline logic. All stages delegate to :mod:`app.pipeline`,
which in turn delegates to ``src/``.
"""
from __future__ import annotations

import difflib
import html
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import gradio as gr

from app.pipeline import (
    AgentConfig,
    GuardRow,
    PipelineTrace,
    evaluate_input_guards,
    get_reranker,
    run_interactive,
)


# ---------------------------------------------------------------------------
# Paper masthead
# ---------------------------------------------------------------------------
PAPER_TITLE = "GRAP4Q"
PAPER_SUBTITLE = "An LLM-based Framework for Quantum Coding Assistance"
PAPER_AUTHORS = (
    "Flora Amato &middot; Egidia Cirillo &middot; "
    "Rajib Chandra Ghosh &middot; Alberto Moccardi"
)
PAPER_AFFILIATION = (
    "DIETI, University of Naples Federico II"
)


# ---------------------------------------------------------------------------
# Example buggy programs — each exercises a different paper-documented defect
# ---------------------------------------------------------------------------
EXAMPLES: dict[str, str] = {
    "Terra/8 — deprecated execute + legacy backend name": (
        "from qiskit import *\n"
        "q = QuantumRegister(1)\n"
        "qc = QuantumCircuit(q)\n"
        "job = execute(qc, backend='local_statevector_simulator')\n"
        "data = job.result().get_data(qc)\n"
        "print(data)\n"
    ),
    "StackExchange_2/bug_1 — iden → id rename": (
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(1)\n"
        "qc.iden(0)\n"
        "qc.measure_all()\n"
    ),
    "Aer/bug_7 — Aer referenced without import": (
        "from qiskit import QuantumCircuit, execute\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.h(0)\n"
        "qc.cx(0, 1)\n"
        "qc.measure([0, 1], [0, 1])\n"
        "backend = Aer.get_backend('qasm_simulator')\n"
        "result = execute(qc, backend=backend).result()\n"
        "print(result.get_counts(qc))\n"
    ),
    "Stack Overflow — IBMQ.load_account migration": (
        "from qiskit import IBMQ, QuantumCircuit\n"
        "IBMQ.load_account()\n"
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "qc.cx(0, 1)\n"
    ),
}
DEFAULT_EXAMPLE = "Terra/8 — deprecated execute + legacy backend name"


# ---------------------------------------------------------------------------
# Custom CSS — minimal, research-paper aesthetic
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
:root {
  --accent: #1e3a8a;
  --accent-soft: #e0e7ff;
  --ink: #1f2937;
  --muted: #6b7280;
  --pass: #065f46;
  --pass-bg: #d1fae5;
  --fail: #9a1b1b;
  --fail-bg: #fee2e2;
  --panel: #ffffff;
  --panel-border: #e5e7eb;
  --card: #f9fafb;
}

.gradio-container {
  max-width: 1600px !important;
  margin: 0 auto !important;
}

.grap4q-masthead {
  background: linear-gradient(135deg, #1e3a8a 0%, #3730a3 100%);
  color: white;
  padding: 24px 32px;
  border-radius: 12px;
  margin-bottom: 18px;
  box-shadow: 0 4px 12px rgba(30,58,138,0.15);
}
.grap4q-masthead .mast-title {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin: 0;
}
.grap4q-masthead .mast-sub {
  font-size: 17px;
  opacity: 0.94;
  margin: 6px 0 14px 0;
  font-weight: 400;
}
.grap4q-masthead .mast-authors {
  font-size: 14px;
  opacity: 0.88;
  margin: 0;
}
.grap4q-masthead .mast-aff {
  font-size: 13px;
  opacity: 0.70;
  margin: 2px 0 0 0;
  font-style: italic;
}
.grap4q-masthead .mast-badge {
  display: inline-block;
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.25);
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  margin-top: 10px;
}

.grap4q-section-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--muted);
  margin: 16px 0 6px 0;
}
.grap4q-col-heading {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  margin: 0 0 10px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--accent);
}

.guard-panel {
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  background: var(--panel);
  overflow: hidden;
}
.guard-row {
  display: flex;
  align-items: flex-start;
  padding: 8px 12px;
  border-bottom: 1px solid var(--panel-border);
  font-size: 13px;
}
.guard-row:last-child { border-bottom: none; }
.guard-pill {
  flex: 0 0 auto;
  width: 64px;
  font-weight: 700;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  text-align: center;
  margin-right: 10px;
  letter-spacing: 0.5px;
}
.guard-pill.pass { background: var(--pass-bg); color: var(--pass); }
.guard-pill.fail { background: var(--fail-bg); color: var(--fail); }
.guard-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  margin-right: 8px;
}
.guard-detail { color: var(--muted); }

.stage-card {
  background: var(--card);
  border-left: 3px solid var(--accent);
  border-radius: 4px 8px 8px 4px;
  padding: 10px 14px;
  margin-bottom: 10px;
}
.stage-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 6px 0;
}
.stage-body {
  font-size: 13px;
  color: var(--ink);
  line-height: 1.5;
}
.stage-body code {
  background: #eef2ff;
  color: #312e81;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.stage-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.diff-box {
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: #fafafa;
  max-height: 360px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}
.diff-row {
  padding: 2px 10px;
  white-space: pre;
}
.diff-del { background: #fef2f2; color: #991b1b; }
.diff-add { background: #ecfdf5; color: #065f46; }
.diff-eq  { color: #4b5563; }

.rationale-card {
  background: #eff6ff;
  border-left: 3px solid #2563eb;
  padding: 10px 14px;
  border-radius: 4px 8px 8px 4px;
  font-size: 13px;
  color: #1e3a8a;
  line-height: 1.55;
  margin-bottom: 10px;
}
.rationale-card b { color: #1e3a8a; }

.selected-span {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  background: #fff;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  padding: 6px 10px;
  margin: 4px 0;
  color: var(--ink);
}
.selected-span .sp-rank {
  color: var(--accent);
  font-weight: 700;
  margin-right: 6px;
}

.summary-banner {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 10px;
}
.summary-banner.ok { background: var(--pass-bg); color: var(--pass); }
.summary-banner.warn { background: #fef3c7; color: #92400e; }
.summary-banner.err  { background: var(--fail-bg); color: var(--fail); }

.compile-output {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--card);
}
"""


# ---------------------------------------------------------------------------
# Masthead HTML
# ---------------------------------------------------------------------------
MASTHEAD_HTML = f"""
<div class="grap4q-masthead">
  <div class="mast-badge">Interactive Research Demo</div>
  <h1 class="mast-title">{PAPER_TITLE}</h1>
  <p class="mast-sub">{PAPER_SUBTITLE}</p>
  <p class="mast-authors">{PAPER_AUTHORS}</p>
  <p class="mast-aff">{PAPER_AFFILIATION}</p>
</div>
"""


# ---------------------------------------------------------------------------
# HTML rendering (UI-only helpers, no pipeline logic)
# ---------------------------------------------------------------------------
def _cell(text: str, cls: str) -> str:
    return f'<div class="diff-row {cls}">{html.escape(text)}</div>'


def render_diff(before: str, after: str) -> str:
    b_lines = before.splitlines()
    a_lines = after.splitlines()
    sm = difflib.SequenceMatcher(None, b_lines, a_lines)
    rows: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in a_lines[j1:j2]:
                rows.append(_cell("  " + line, "diff-eq"))
        elif tag == "delete":
            for line in b_lines[i1:i2]:
                rows.append(_cell("- " + line, "diff-del"))
        elif tag == "insert":
            for line in a_lines[j1:j2]:
                rows.append(_cell("+ " + line, "diff-add"))
        elif tag == "replace":
            for line in b_lines[i1:i2]:
                rows.append(_cell("- " + line, "diff-del"))
            for line in a_lines[j1:j2]:
                rows.append(_cell("+ " + line, "diff-add"))
    return f'<div class="diff-box">{"".join(rows)}</div>'


def render_guards(guards: list[GuardRow]) -> str:
    """Guardrail panel — one row per admissibility check."""
    if not guards:
        return ('<div class="guard-panel"><div class="guard-row">'
                '<span class="guard-detail">No checks run yet.</span>'
                '</div></div>')
    rows: list[str] = []
    for g in guards:
        pill_cls = "pass" if g.passed else "fail"
        pill_label = "PASS" if g.passed else "FAIL"
        rows.append(
            f'<div class="guard-row">'
            f'  <span class="guard-pill {pill_cls}">{pill_label}</span>'
            f'  <div>'
            f'    <span class="guard-name">{html.escape(g.name)}</span>'
            f'    <span class="guard-detail">{html.escape(g.detail)}</span>'
            f'  </div>'
            f'</div>'
        )
    return f'<div class="guard-panel">{"".join(rows)}</div>'


def render_guard_summary(guards: list[GuardRow], label: str) -> str:
    passed = sum(1 for g in guards if g.passed)
    total = len(guards)
    if total == 0:
        return ""
    failing = total - passed
    if failing == 0:
        cls = "ok"
        msg = (f"All {total} admissibility checks pass on the {label} "
               f"source.")
    else:
        cls = "warn" if label == "buggy" else "err"
        msg = (f"{failing} of {total} admissibility checks fail on the "
               f"{label} source.")
    return f'<div class="summary-banner {cls}">{msg}</div>'


def render_trace(trace: PipelineTrace) -> str:
    """Pipeline trace: one card per stage of the paper's Algorithm 1."""
    if trace.error:
        return (
            '<div class="summary-banner err"><b>Pipeline error</b><br>'
            f'{html.escape(trace.error)}</div>')

    cards: list[str] = []

    # Stage 1: query
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">① Query construction</div>'
        '<div class="stage-body">'
        f'Seed tokens (top-6 from buggy source + quantum hints): '
        f'<code>{html.escape(trace.query)}</code>'
        '</div></div>')

    # Stage 2: BM25 retrieval
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">② BM25 retrieval</div>'
        '<div class="stage-body">'
        f'Over-retrieved <b>{trace.pool_size}</b> candidate span(s) '
        f'(Okapi BM25 with quantum-token boost per paper Sect. 4.2).'
        '</div></div>')

    # Stage 3: cross-encoder re-rank + selector
    sel_rows: list[str] = []
    for i, h in enumerate(trace.selected, start=1):
        rr = h.get("re_score", 0.0)
        bm = h.get("score", 0.0)
        sym = str(h.get("symbol", "?"))
        s, e = h.get("start", "?"), h.get("end", "?")
        sel_rows.append(
            f'<div class="selected-span">'
            f'<span class="sp-rank">rank {i}</span>'
            f'<code>{html.escape(sym)}</code> @ lines [{s}, {e}] '
            f'&nbsp;BM25={bm:.3f}'
            f'{"; rerank=%.3f" % rr if rr else ""}'
            f'</div>')
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">③ Cross-encoder re-rank + coverage selector</div>'
        '<div class="stage-body">'
        f'Selected top-<b>{len(trace.selected)}</b> spans using the '
        f'balanced coverage objective.'
        f'{"".join(sel_rows) if sel_rows else ""}'
        '</div></div>')

    # Stage 4: span focus
    ranges = (", ".join(f"[{lo},{hi}]" for lo, hi in trace.allowed_ranges)
              if trace.allowed_ranges else "—")
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">④ Span focusing</div>'
        '<div class="stage-body">'
        f'Focus windows tightened to salient lines. '
        f'Allowed edit region(s): <code>{ranges}</code>'
        '</div></div>')

    # Stage 5: Ollama patch
    meta_bits = []
    if trace.llm_latency_s:
        meta_bits.append(f"latency: {trace.llm_latency_s:.1f}s")
    if trace.attempts:
        meta_bits.append(f"attempts: {trace.attempts}")
    if trace.edits:
        meta_bits.append(f"edits applied: {len(trace.edits)}")
    meta = (f'<div class="stage-meta">{" · ".join(meta_bits)}</div>'
            if meta_bits else "")
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">⑤ Ollama patch (qwen2.5-coder)</div>'
        '<div class="stage-body">'
        'LLM generated a constrained edit within the allowed ranges, '
        'followed by guardrail-driven refinement (up to N retries).'
        f'{meta}'
        '</div></div>')

    # Stage 6: CompositeGuard
    passed = sum(1 for g in trace.guards if g.passed)
    total = len(trace.guards)
    cards.append(
        '<div class="stage-card">'
        '<div class="stage-head">⑥ CompositeGuard (paper Sect. 4.5)</div>'
        '<div class="stage-body">'
        f'Final patched source passed <b>{passed}/{total}</b> admissibility '
        f'checks. Detailed verdict in the right panel.'
        '</div></div>')

    # Rationale (if any)
    if trace.rationale:
        cards.append(
            '<div class="rationale-card">'
            '<b>LLM rationale</b><br>'
            f'{html.escape(trace.rationale)}'
            '</div>')

    return "".join(cards)


# ---------------------------------------------------------------------------
# py_compile verification for the "Verify" button
# ---------------------------------------------------------------------------
def py_compile_check(source: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0:
            cls = "compile-output"
            return (f'<div class="{cls}" style="background:#d1fae5;'
                    'color:#065f46;">✓ py_compile: OK</div>')
        return (f'<div class="compile-output" style="background:#fee2e2;'
                f'color:#9a1b1b;">✗ py_compile FAIL\n'
                f'{html.escape(proc.stderr.strip())}</div>')
    except Exception as e:
        return (f'<div class="compile-output" style="background:#fee2e2;'
                f'color:#9a1b1b;">Compile check raised: '
                f'{html.escape(str(e))}</div>')
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
def _on_check_input(source: str):
    """Runs on every buggy-code edit — evaluates guards on the INPUT."""
    guards = evaluate_input_guards(source or "")
    summary = render_guard_summary(guards, label="buggy")
    return summary + render_guards(guards)


def _on_run(source: str, config_name: str, use_rerank: bool,
            max_refines: int):
    cfg = AgentConfig.from_name(config_name)
    cfg.use_rerank = use_rerank
    rr = get_reranker(enable=use_rerank)
    trace = run_interactive(source or "", config=cfg, reranker=rr,
                            max_refines=int(max_refines))

    # Re-run input guards (left panel).
    input_guards = evaluate_input_guards(source or "")
    input_html = (render_guard_summary(input_guards, "buggy")
                  + render_guards(input_guards))

    # Patched guards (right panel) — use the full-source defect scan
    # again so the reviewer sees the same named checks flip from FAIL
    # to PASS. We also include the three CompositeGuard rows from the
    # trace so nothing is hidden.
    patched_src = trace.patched or source or ""
    patched_guards = evaluate_input_guards(patched_src)
    # Merge in the CompositeGuard-specific rows that evaluate_input_guards
    # doesn't cover (EditRegionOK), so the right panel is a superset.
    cg_extra = [g for g in trace.guards
                if g.name not in {gr.name for gr in patched_guards}]
    patched_guards = cg_extra + patched_guards
    patched_html = (render_guard_summary(patched_guards, "patched")
                    + render_guards(patched_guards))

    diff_html = render_diff(source or "", patched_src)
    trace_html = render_trace(trace)

    return (input_html, trace_html, diff_html,
            patched_html, patched_src, "")


def _on_load_example(name: str):
    src = EXAMPLES[name]
    input_html = _on_check_input(src)
    return src, input_html


def _on_compile(source: str) -> str:
    return py_compile_check(source or "")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def build_ui() -> gr.Blocks:
    with gr.Blocks(title=f"{PAPER_TITLE} — {PAPER_SUBTITLE}",
                   css=CUSTOM_CSS,
                   theme=gr.themes.Soft(
                       primary_hue="indigo",
                       neutral_hue="slate",
                       font=("Inter", "ui-sans-serif", "system-ui",
                             "sans-serif"),
                   )) as demo:

        gr.HTML(MASTHEAD_HTML)

        with gr.Row(equal_height=False):

            # ======== LEFT COLUMN: buggy input + input guards =========
            with gr.Column(scale=5):
                gr.HTML('<div class="grap4q-col-heading">'
                        '① Original (buggy) source</div>')
                example = gr.Dropdown(
                    label="Load an example",
                    choices=list(EXAMPLES.keys()),
                    value=DEFAULT_EXAMPLE,
                    info="Each example exercises a different defect class from the Bugs4Q benchmark.",
                )
                buggy = gr.Code(
                    label="buggy.py",
                    language="python",
                    value=EXAMPLES[DEFAULT_EXAMPLE],
                    lines=20,
                )
                gr.HTML('<div class="grap4q-section-label">'
                        'Admissibility verdict — on the original</div>')
                input_guards_html = gr.HTML(
                    _on_check_input(EXAMPLES[DEFAULT_EXAMPLE]))

                with gr.Accordion("Pipeline configuration", open=False):
                    config_name = gr.Textbox(
                        label="Configuration string",
                        value=os.environ.get(
                            "GRAP4Q_CONFIG",
                            "WIN_base__hint__balanced__rerank"),
                        info="Paper's selected config (Sect. 6.2): "
                             "WIN_base__hint__balanced__rerank",
                    )
                    use_rerank = gr.Checkbox(
                        label="Enable cross-encoder re-ranker",
                        value=True,
                    )
                    max_refines = gr.Slider(
                        label="Max guardrail refinement attempts",
                        minimum=0, maximum=4, step=1, value=2,
                    )

                with gr.Row():
                    run_btn = gr.Button("Run GRAP-Q", variant="primary",
                                        size="lg")
                    compile_btn = gr.Button("Verify (py_compile)",
                                            size="lg")

            # ======== CENTRE COLUMN: pipeline trace =========
            with gr.Column(scale=4):
                gr.HTML('<div class="grap4q-col-heading">'
                        '② GRAP-Q pipeline</div>')
                trace_out = gr.HTML(
                    '<div style="padding:20px;color:#6b7280;'
                    'font-style:italic;">Click <b>Run GRAP-Q</b> to execute '
                    'the six-stage pipeline on the input.</div>')

            # ======== RIGHT COLUMN: patched output + patched guards =========
            with gr.Column(scale=5):
                gr.HTML('<div class="grap4q-col-heading">'
                        '③ GRAP-Q output</div>')
                diff_out = gr.HTML(
                    '<div style="padding:20px;color:#6b7280;'
                    'font-style:italic;">Diff will appear here after a run.'
                    '</div>')
                gr.HTML('<div class="grap4q-section-label">'
                        'Admissibility verdict — on the patched source</div>')
                patched_guards_html = gr.HTML(
                    '<div style="padding:20px;color:#6b7280;'
                    'font-style:italic;">Run the pipeline to see which '
                    'checks now pass.</div>')
                gr.HTML('<div class="grap4q-section-label">'
                        'Patched source (editable — copy from here)</div>')
                patched_code = gr.Code(
                    label="",
                    language="python",
                    lines=16,
                    interactive=True,
                )
                compile_out = gr.HTML("")

        # ---- event bindings ----
        example.change(
            _on_load_example, inputs=example,
            outputs=[buggy, input_guards_html])

        buggy.change(
            _on_check_input, inputs=buggy,
            outputs=input_guards_html)

        run_btn.click(
            _on_run,
            inputs=[buggy, config_name, use_rerank, max_refines],
            outputs=[input_guards_html, trace_out, diff_out,
                     patched_guards_html, patched_code, compile_out],
        )

        compile_btn.click(
            _on_compile, inputs=patched_code,
            outputs=compile_out)

        # Footer — paper reference
        gr.HTML(
            '<div style="text-align:center;padding:20px;color:#6b7280;'
            'font-size:12px;margin-top:24px;border-top:1px solid #e5e7eb;">'
            f'<b>{PAPER_TITLE}</b>: {PAPER_SUBTITLE}<br>'
            f'{PAPER_AUTHORS}<br>'
            f'{PAPER_AFFILIATION}'
            '</div>')

    return demo


def main() -> None:
    host = os.environ.get("GRAP4Q_HOST", "127.0.0.1")
    port = int(os.environ.get("GRAP4Q_PORT", "7860"))
    share = os.environ.get("GRAP4Q_SHARE", "false").lower() == "true"
    build_ui().launch(server_name=host, server_port=port, share=share)


if __name__ == "__main__":
    main()
