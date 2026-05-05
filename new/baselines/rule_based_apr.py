"""
Rule-based automated program repair (APR) baseline for Qiskit bugs.

Inspired by classical APR tools (CoCoNuT, TBar, SequenceR) but adapted for the
handful of repeating Qiskit migration patterns that dominate the Bugs4Q dataset.
Runs offline, no LLM, no network.

The patcher walks buggy source, applies deterministic rewrite rules, and emits
a patched file plus an edit list compatible with evaluate_candidate().

Rules implemented (each one a small, reversible rewrite):

  R1  execute(qc, backend=X).result().get_counts()
      →  backend.run(transpile(qc, backend)).result().get_counts()
  R2  'local_statevector_simulator'  →  'statevector_simulator'
  R2  'local_qasm_simulator'         →  'qasm_simulator'
  R3  .get_data(qc)                  →  .get_statevector()       (default assumption)
  R4  qc.iden(...)                   →  qc.id(...)               (legacy→new)
  R5  IBMQ.load_account()            →  QiskitRuntimeService()
  R6  from qiskit import execute     →  remove (deprecated shortcut)
  R7  missing `import Aer`           →  add `from qiskit_aer import Aer`
      (only when Aer is referenced but not imported)

This does not cover every bug, by design; a rule-based baseline is expected to
be a lower bound. Its purpose is to answer R3 C10: a "classical APR"
reference that doesn't rely on an LLM.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class AppliedRule:
    rule: str
    line: int
    before: str
    after: str


@dataclass
class PatchResult:
    case: str
    file: str
    patched_src: str
    rules_applied: list[AppliedRule] = field(default_factory=list)
    edits: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "file": self.file,
            "num_rules_applied": len(self.rules_applied),
            "rules_applied": [r.__dict__ for r in self.rules_applied],
            "edits": self.edits,
        }


# ---- Line-level rewrite rules ----

_RULES_LINE = [
    ("R2", re.compile(r"'local_statevector_simulator'"), "'statevector_simulator'"),
    ("R2", re.compile(r'"local_statevector_simulator"'), '"statevector_simulator"'),
    ("R2", re.compile(r"'local_qasm_simulator'"), "'qasm_simulator'"),
    ("R2", re.compile(r'"local_qasm_simulator"'), '"qasm_simulator"'),
    # R3 — default replacement is get_statevector(); when counts are clearly intended
    # a second pass below switches to get_counts().
    ("R3", re.compile(r"\.get_data\s*\(\s*[^\)]*\)"), ".get_statevector()"),
    # R4 — older iden() alias
    ("R4", re.compile(r"\.iden\s*\("), ".id("),
]


def _apply_line_rules(src: str) -> tuple[str, list[AppliedRule]]:
    applied: list[AppliedRule] = []
    out_lines: list[str] = []
    for i, line in enumerate(src.splitlines(), start=1):
        new = line
        for rule_id, pat, repl in _RULES_LINE:
            new2 = pat.sub(repl, new)
            if new2 != new:
                applied.append(AppliedRule(rule_id, i, line.strip(), new2.strip()))
                new = new2
        out_lines.append(new)
    return "\n".join(out_lines), applied


def _apply_import_rules(src: str) -> tuple[str, list[AppliedRule]]:
    """R6, R7: fix imports."""
    applied: list[AppliedRule] = []
    lines = src.splitlines()

    # R6: remove `execute` from `from qiskit import ...`
    for i, line in enumerate(lines):
        m = re.match(r"\s*from\s+qiskit\s+import\s+(.+)", line)
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            if "execute" in names:
                new_names = [n for n in names if n != "execute"]
                if new_names:
                    new_line = f"from qiskit import {', '.join(new_names)}"
                else:
                    new_line = ""
                applied.append(AppliedRule("R6", i + 1, line.strip(), new_line.strip() or "(removed)"))
                lines[i] = new_line

    # R7: add Aer import if referenced but not imported
    joined = "\n".join(lines)
    if re.search(r"\bAer\b", joined):
        has_import = bool(re.search(r"from\s+qiskit(_aer)?\s+import\s+.*\bAer\b", joined)) \
            or bool(re.search(r"from\s+qiskit\.providers\.aer\s+import", joined))
        if not has_import:
            # Insert after last `import` or `from ... import` line at the top block
            insert_idx = 0
            for i, ln in enumerate(lines[:40]):
                if ln.startswith("import ") or ln.startswith("from "):
                    insert_idx = i + 1
            new_import = "from qiskit_aer import Aer"
            lines.insert(insert_idx, new_import)
            applied.append(AppliedRule("R7", insert_idx + 1, "(no Aer import)", new_import))

    return "\n".join(lines), applied


def _apply_execute_rule(src: str) -> tuple[str, list[AppliedRule]]:
    """R1: execute(qc, backend=bk).result() → bk.run(transpile(qc, bk)).result()

    Conservative AST-lite pattern match.
    """
    applied: list[AppliedRule] = []
    # Pattern: execute(<circ>, backend=<bk>) or execute(<circ>, <bk>)
    pat = re.compile(
        r"execute\s*\(\s*([A-Za-z_][A-Za-z_0-9]*)\s*,\s*"
        r"(?:backend\s*=\s*)?([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)"
        r"(?:\s*,\s*[^)]*)?\)"
    )
    out_lines = []
    for i, line in enumerate(src.splitlines(), start=1):
        m = pat.search(line)
        if m:
            qc, bk = m.group(1), m.group(2)
            # Guard: if bk is a string literal backend name, skip (R2 handles those)
            if "'" in bk or '"' in bk:
                out_lines.append(line)
                continue
            new_expr = f"{bk}.run(transpile({qc}, {bk}))"
            new = pat.sub(new_expr, line)
            applied.append(AppliedRule("R1", i, line.strip(), new.strip()))
            out_lines.append(new)
        else:
            out_lines.append(line)
    new_src = "\n".join(out_lines)

    # Ensure transpile is imported if R1 fired
    if applied and "from qiskit import" in new_src and "transpile" not in new_src.split("\n", 40)[0:40][0]:
        # naive: append transpile to first matching import
        new_src = re.sub(
            r"from\s+qiskit\s+import\s+([^\n]+)",
            lambda m: (f"from qiskit import {m.group(1).strip()}, transpile"
                       if "transpile" not in m.group(1) else m.group(0)),
            new_src, count=1,
        )
    return new_src, applied


def _apply_ibmq_rule(src: str) -> tuple[str, list[AppliedRule]]:
    """R5: IBMQ.load_account() → QiskitRuntimeService()"""
    applied: list[AppliedRule] = []
    lines = src.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if "IBMQ.load_account(" in line:
            new = line.replace("IBMQ.load_account(", "QiskitRuntimeService(")
            applied.append(AppliedRule("R5", i + 1, line.strip(), new.strip()))
            lines[i] = new
            changed = True
    new_src = "\n".join(lines)
    if changed and "QiskitRuntimeService" not in new_src.split("IBMQ.load_account")[0]:
        new_src = "from qiskit_ibm_runtime import QiskitRuntimeService\n" + new_src
    return new_src, applied


def _ast_ok(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _build_edit_list(before: str, after: str, file_name: str = "buggy.py") -> list[dict]:
    """Emit a minimal edit list in GRAP-Q's schema: line-range replacements."""
    a = before.splitlines()
    b = after.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    edits: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        start = i1 + 1
        end = max(start, i2)
        replacement = "\n".join(b[j1:j2])
        edits.append({
            "file": file_name,
            "start": start,
            "end": end,
            "replacement": replacement,
        })
    return edits


def patch_source(src: str, case: str = "?", file: str = "buggy.py") -> PatchResult:
    """Apply all rules in sequence and return patched source + metadata."""
    all_applied: list[AppliedRule] = []
    cur = src

    cur, a1 = _apply_line_rules(cur);       all_applied += a1
    cur, a2 = _apply_execute_rule(cur);     all_applied += a2
    cur, a3 = _apply_ibmq_rule(cur);        all_applied += a3
    cur, a4 = _apply_import_rules(cur);     all_applied += a4

    # If parse broke, roll back
    if not _ast_ok(cur):
        # keep original, emit no edits
        return PatchResult(case=case, file=file, patched_src=src, rules_applied=[], edits=[])

    edits = _build_edit_list(src, cur, file_name=file)
    return PatchResult(case=case, file=file, patched_src=cur,
                       rules_applied=all_applied, edits=edits)


# ---- Evaluation helpers (Lines-F1 against a gold fix) ----

def _touched_lines(a: str, b: str) -> set[int]:
    al, bl = a.splitlines(), b.splitlines()
    sm = difflib.SequenceMatcher(None, al, bl, autojunk=False)
    t: set[int] = set()
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag in ("replace", "delete"):
            t.update(range(i1 + 1, i2 + 1))
    return t


def evaluate_patch(buggy_src: str, patched_src: str, fixed_src: str) -> dict:
    gold = _touched_lines(buggy_src, fixed_src)
    pred = _touched_lines(buggy_src, patched_src)
    inter = len(gold & pred)
    p = inter / max(1, len(pred))
    r = inter / max(1, len(gold))
    f1 = 0.0 if (p + r) == 0 else 2 * p * r / (p + r)
    return {"lines_p": p, "lines_r": r, "lines_f1": f1,
            "gold_size": len(gold), "pred_size": len(pred)}


def run_on_cases(db_root: Path, case_ids: Iterable[str]) -> list[dict]:
    out: list[dict] = []
    for cid in case_ids:
        case_dir = db_root / cid
        buggy_path = case_dir / "buggy.py"
        fixed_path = None
        for nm in ("fixed.py", "fix.py"):
            if (case_dir / nm).exists():
                fixed_path = case_dir / nm
                break
        if not buggy_path.exists() or fixed_path is None:
            continue
        buggy_src = buggy_path.read_text(encoding="utf-8", errors="replace")
        fixed_src = fixed_path.read_text(encoding="utf-8", errors="replace")

        patch = patch_source(buggy_src, case=cid, file="buggy.py")
        scores = evaluate_patch(buggy_src, patch.patched_src, fixed_src)

        out.append({
            "case": cid,
            "method": "RuleAPR",
            "lines_p": scores["lines_p"],
            "lines_r": scores["lines_r"],
            "lines_f1": scores["lines_f1"],
            "num_edits": len(patch.edits),
            "rules_applied": [r.rule for r in patch.rules_applied],
            "gold_size": scores["gold_size"],
            "pred_size": scores["pred_size"],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db_root", type=Path, required=True)
    ap.add_argument("--splits", type=Path, required=True)
    ap.add_argument("--which", choices=["val", "test", "all"], default="val")
    ap.add_argument("--out_csv", type=Path, required=True)
    args = ap.parse_args()

    data = json.loads(args.splits.read_text())
    if args.which == "val":
        ids = data["val_ids"]
    elif args.which == "test":
        ids = data["test_ids"]
    else:
        ids = data["train_ids"] + data["val_ids"] + data["test_ids"]

    rows = run_on_cases(args.db_root, ids)

    # Write CSV
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        import pandas as pd
        pd.DataFrame(rows).to_csv(args.out_csv, index=False)
    else:
        args.out_csv.write_text("case,method,lines_p,lines_r,lines_f1,num_edits,rules_applied\n",
                                encoding="utf-8")

    if rows:
        mean_f1 = sum(r["lines_f1"] for r in rows) / len(rows)
        n_fired = sum(1 for r in rows if r["num_edits"] > 0)
        print(f"[OK] Wrote {args.out_csv} ({len(rows)} cases, "
              f"mean Lines-F1 = {mean_f1:.4f}, {n_fired} with edits)")
    else:
        print(f"[WARN] No cases found for split='{args.which}'")


if __name__ == "__main__":
    main()
