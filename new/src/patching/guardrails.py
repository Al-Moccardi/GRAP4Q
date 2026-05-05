"""Deterministic guardrail checks on proposed patches.

These are the safety invariants from Section 4.4 of the paper:

  G1  AST parseability (post-patch)
  G2  Pass interface preservation (e.g., run(self, dag) signatures)
  G3  No classical/quantum register mixing
  G4  Qubit order heuristic (no silent arg flips)
  G5  Edit region bounds (edits stay inside allowed line ranges)
"""
from __future__ import annotations

import ast
import re


def ast_ok(src: str) -> tuple[bool, str]:
    try:
        ast.parse(src)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}"


def _find_registers(src: str) -> tuple[set[str], set[str]]:
    q_regs: set[str] = set()
    c_regs: set[str] = set()
    for m in re.finditer(r"(\w+)\s*=\s*QuantumRegister\(", src):
        q_regs.add(m.group(1))
    for m in re.finditer(r"(\w+)\s*=\s*ClassicalRegister\(", src):
        c_regs.add(m.group(1))
    return q_regs, c_regs


def pass_interface_ok(before_src: str, after_src: str) -> tuple[bool, str]:
    def _sigs(s: str) -> set[tuple]:
        out: set[tuple] = set()
        try:
            t = ast.parse(s)
        except Exception:
            return out
        for n in ast.walk(t):
            if isinstance(n, ast.FunctionDef) and n.name == "run":
                out.add(tuple(a.arg for a in n.args.args))
        return out

    b = _sigs(before_src)
    a = _sigs(after_src)
    if not b:
        return True, ""
    if b != a:
        return False, f"Pass interface changed: {b} -> {a}"
    return True, ""


def no_reg_mix_ok(src: str) -> tuple[bool, str]:
    _q, c_regs = _find_registers(src)
    for m in re.finditer(r"measure\s*\(\s*([A-Za-z_]\w*)", src):
        if m.group(1) in c_regs:
            return False, f"measure() uses classical register '{m.group(1)}' as quantum"
    for m in re.finditer(r"(cx|cz|rz|rx|ry|swap)\s*\(\s*([A-Za-z_]\w*)", src):
        if m.group(2) in c_regs:
            return False, f"{m.group(1)}() uses classical register '{m.group(2)}' as quantum"
    return True, ""


def qubit_order_heuristic_ok(before_src: str, after_src: str,
                             edited_ranges: list[tuple[int, int]]) -> tuple[bool, str]:
    def _slice(lines: list[str], ranges: list[tuple[int, int]]) -> str:
        out: list[str] = []
        for s, e in ranges:
            s = max(1, s)
            e = min(len(lines), max(s, e))
            out.extend(lines[s - 1:e])
        return "\n".join(out)

    b = _slice(before_src.splitlines(), edited_ranges)
    a = _slice(after_src.splitlines(), edited_ranges)
    if re.search(r"\bq\[\s*1\s*\]\s*,\s*q\[\s*0\s*\]", a) and \
       re.search(r"\bq\[\s*0\s*\]\s*,\s*q\[\s*1\s*\]", b):
        return False, "Potential qubit order swap in edited lines"
    return True, ""


def enforce_in_region(edits: list[dict], allowed: list[tuple[int, int]]) -> list[dict]:
    """Drop any proposed edit whose [start,end] is outside the allowed focus."""
    ok: list[dict] = []
    for e in edits or []:
        st = int(e.get("start", 1))
        en = int(e.get("end", st))
        repl = e.get("replacement", "")
        for (a, b) in allowed:
            if st >= a and en <= b:
                ok.append({
                    "file": e.get("file", "buggy.py"),
                    "start": st, "end": en, "replacement": repl,
                })
                break
    return ok


def validate_patch(before_src: str, edits: list[dict]) -> tuple[bool, list[str]]:
    """Run the full guardrail suite on proposed edits. Returns (ok, reasons)."""
    after = before_src.splitlines()
    ranges: list[tuple[int, int]] = []
    for e in edits or []:
        s = max(1, int(e.get("start", 1)))
        en = int(e.get("end", s))
        replacement = str(e.get("replacement", "")).splitlines()
        after = after[:s - 1] + replacement + after[en:]
        ranges.append((s, en))
    after_src = "\n".join(after)

    msgs: list[str] = []
    for check_fn in (
        lambda: ast_ok(after_src),
        lambda: pass_interface_ok(before_src, after_src),
        lambda: no_reg_mix_ok(after_src),
        lambda: qubit_order_heuristic_ok(before_src, after_src, ranges),
    ):
        ok, msg = check_fn()
        if not ok:
            msgs.append(msg)
    return (len(msgs) == 0), msgs
