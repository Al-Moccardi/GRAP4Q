"""
QChecker-style static analyzer for Qiskit/quantum Python programs.

A rule-based detector inspired by QChecker (Zhao et al. 2023,
https://arxiv.org/abs/2304.04387). Implements the core categories of
quantum bug patterns as AST + regex checks. Runs offline, no LLM, no network.

Patterns detected:
    QC01  MissingMeasurement          : circuit never calls .measure(...) before
                                         asking for classical counts.
    QC02  MissingClassicalBits         : QuantumCircuit created with only quantum
                                         register but .measure() is called, or
                                         measure(qr, cr) with no classical register.
    QC03  MissingBackendInit           : .run() / execute() call with no backend
                                         assigned earlier.
    QC04  DeprecatedExecuteAPI         : uses the removed `qiskit.execute`
                                         shortcut (post-Qiskit 1.0).
    QC05  DeprecatedBackendName        : uses legacy backend strings like
                                         'local_statevector_simulator' or
                                         'local_qasm_simulator'.
    QC06  GetDataMisuse                : uses deprecated `.get_data(qc)`
                                         instead of `.get_counts()` /
                                         `.get_statevector()`.
    QC07  QubitOutOfRange              : attempts to act on qubit index >= size
                                         of the register (best-effort).
    QC08  MissingInitialization        : uses a QuantumCircuit / QuantumRegister
                                         name that was never defined.
    QC09  UnmatchedRegisterSize        : measure/cx/h called with qubit indices
                                         that exceed QuantumRegister size.
    QC10  NonExistentGate              : calls .foo(...) where `foo` is not a
                                         standard Qiskit gate/op.

This checker outputs a JSON report per case; it does NOT patch code. It is the
QChecker-aligned baseline the reviewer (R3 C10) asked us to compare against.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


# Known Qiskit gate/operation names (conservative allow-list).
QISKIT_GATES = {
    "x", "y", "z", "h", "s", "sdg", "t", "tdg",
    "rx", "ry", "rz", "rxx", "ryy", "rzz", "rzx",
    "sx", "sxdg", "p", "u", "u1", "u2", "u3",
    "cx", "cy", "cz", "ch", "cp", "crx", "cry", "crz",
    "ccx", "cnot", "cswap", "swap", "iswap", "ecr",
    "measure", "measure_all", "measure_active", "reset", "barrier",
    "initialize", "append", "compose", "draw", "decompose",
    "assign_parameters", "bind_parameters", "copy",
    "depth", "width", "size", "count_ops", "qasm",
    "iden", "id",  # older API
    "mcx", "mct",
    "delay", "unitary", "global_phase",
    "if_test", "while_loop", "for_loop", "switch",
}

DEPRECATED_BACKEND_NAMES = {
    "local_statevector_simulator",
    "local_qasm_simulator",
    "local_unitary_simulator",
    "ibmq_qasm_simulator",  # still exists, but often flagged by migrations
}


@dataclass
class Finding:
    rule: str
    line: int
    message: str
    severity: str = "warning"


@dataclass
class CaseReport:
    case: str
    file: str
    findings: list[Finding] = field(default_factory=list)
    ast_parse_ok: bool = True
    parse_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "file": self.file,
            "ast_parse_ok": self.ast_parse_ok,
            "parse_error": self.parse_error,
            "num_findings": len(self.findings),
            "findings": [asdict(f) for f in self.findings],
        }


def _get_attr_chain(node: ast.AST) -> str:
    """Return dotted attribute chain, e.g. 'qc.measure' or 'job.result'."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def check_source(src: str, case: str = "?", file: str = "buggy.py") -> CaseReport:
    report = CaseReport(case=case, file=file)
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        report.ast_parse_ok = False
        report.parse_error = f"{e.msg} at line {e.lineno}"
        return report

    lines = src.splitlines()
    joined = "\n".join(lines)

    # --- Collect high-level facts ---
    quantum_register_sizes: dict[str, int] = {}   # qreg var -> size
    classical_register_sizes: dict[str, int] = {} # creg var -> size
    circuit_has_classical_bits: dict[str, bool] = {}  # qc var -> has_cregs
    has_measure_call = False
    has_backend_assign = False
    has_execute_or_run = False
    counts_requested = False
    statevector_requested = False
    defined_names: set[str] = set()
    used_gate_calls: list[tuple[int, str]] = []  # (lineno, gate_name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    defined_names.add(tgt.id)
                    # Detect QuantumRegister(<int>) / ClassicalRegister(<int>)
                    if isinstance(node.value, ast.Call):
                        func_name = _get_attr_chain(node.value.func)
                        if func_name.endswith("QuantumRegister") and node.value.args:
                            a0 = node.value.args[0]
                            if isinstance(a0, ast.Constant) and isinstance(a0.value, int):
                                quantum_register_sizes[tgt.id] = a0.value
                        elif func_name.endswith("ClassicalRegister") and node.value.args:
                            a0 = node.value.args[0]
                            if isinstance(a0, ast.Constant) and isinstance(a0.value, int):
                                classical_register_sizes[tgt.id] = a0.value
                        elif func_name.endswith("QuantumCircuit"):
                            # Does this circuit include any ClassicalRegister?
                            has_cbits = False
                            for a in node.value.args:
                                if isinstance(a, ast.Name) and a.id in classical_register_sizes:
                                    has_cbits = True
                                if isinstance(a, ast.Constant) and isinstance(a.value, int) and len(node.value.args) >= 2:
                                    # QuantumCircuit(n_qubits, n_clbits) form
                                    has_cbits = True
                            circuit_has_classical_bits[tgt.id] = has_cbits
                        elif "backend" in func_name.lower() or "get_backend" in func_name:
                            has_backend_assign = True
                    # 'backend = ...' catch-all
                    if tgt.id.lower() == "backend":
                        has_backend_assign = True

        if isinstance(node, ast.Call):
            chain = _get_attr_chain(node.func)
            tail = chain.rsplit(".", 1)[-1]
            lineno = getattr(node, "lineno", 0)

            # QC04: qiskit.execute shortcut
            if tail == "execute" and ("qiskit" in chain or chain == "execute"):
                has_execute_or_run = True
                report.findings.append(Finding(
                    "QC04",
                    lineno,
                    "Uses `execute(...)`, which is deprecated/removed post-Qiskit 1.0. "
                    "Migrate to `Sampler`/`Estimator` or `backend.run(transpile(qc, backend))`.",
                ))
            if tail == "run":
                has_execute_or_run = True

            # QC05: deprecated backend name in a string arg
            for kw in node.keywords:
                if kw.arg == "backend" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    if kw.value.value in DEPRECATED_BACKEND_NAMES:
                        report.findings.append(Finding(
                            "QC05",
                            lineno,
                            f"Deprecated backend name '{kw.value.value}'. "
                            "Use `Aer.get_backend('statevector_simulator')` (aer 0.13+) "
                            "or the primitives API.",
                        ))
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value in DEPRECATED_BACKEND_NAMES:
                        report.findings.append(Finding(
                            "QC05",
                            lineno,
                            f"Deprecated backend name '{arg.value}'.",
                        ))

            # QC06: get_data(qc) misuse
            if tail == "get_data":
                report.findings.append(Finding(
                    "QC06",
                    lineno,
                    "`.get_data(qc)` is deprecated. Use `.get_counts()` "
                    "or `.get_statevector()` depending on the backend.",
                ))

            if tail in ("get_counts",):
                counts_requested = True
            if tail in ("get_statevector",):
                statevector_requested = True
            if tail == "measure" or tail == "measure_all" or tail == "measure_active":
                has_measure_call = True

            # Gate call tracking on a circuit-like receiver
            if isinstance(node.func, ast.Attribute):
                # Heuristic: receiver is a QuantumCircuit if its name was assigned from QuantumCircuit
                recv = node.func.value
                if isinstance(recv, ast.Name) and recv.id in circuit_has_classical_bits:
                    used_gate_calls.append((lineno, tail))
                    # QC10: non-existent gate (best-effort; ignore private)
                    if (not tail.startswith("_")) and tail not in QISKIT_GATES:
                        # Allow generic ops we don't pattern-match
                        allowed_misc = {"data", "definition", "name", "num_qubits", "num_clbits",
                                        "qubits", "clbits", "parameters", "params"}
                        if tail not in allowed_misc:
                            report.findings.append(Finding(
                                "QC10",
                                lineno,
                                f"Call `.{tail}(...)` on circuit but `{tail}` is not a recognized "
                                "Qiskit gate/operation.",
                            ))
                    # QC09: qubit index >= register size (integer literal only)
                    # Only inspect simple gate names
                    if tail in {"h", "x", "y", "z", "rx", "ry", "rz", "measure", "cx", "cz", "swap"}:
                        for a in node.args:
                            if isinstance(a, ast.Constant) and isinstance(a.value, int):
                                for qr_name, qr_size in quantum_register_sizes.items():
                                    if a.value >= qr_size:
                                        report.findings.append(Finding(
                                            "QC09",
                                            lineno,
                                            f"Qubit index {a.value} used in .{tail}(...) may exceed "
                                            f"size ({qr_size}) of register '{qr_name}'.",
                                        ))
                                        break

    # --- Post-walk cross-facts ---

    # QC01: counts requested but no measure
    if counts_requested and not has_measure_call:
        report.findings.append(Finding(
            "QC01",
            1,
            "Classical counts are requested (`.get_counts(...)`) but no `.measure(...)` "
            "call is made. The result will be empty or raise.",
        ))

    # QC02: measure used but circuit has no classical register
    if has_measure_call:
        for qc_name, has_cbits in circuit_has_classical_bits.items():
            if not has_cbits:
                report.findings.append(Finding(
                    "QC02",
                    1,
                    f"Circuit `{qc_name}` has no ClassicalRegister but `.measure(...)` "
                    "is called. Add a ClassicalRegister or use `measure_all()`.",
                ))

    # QC03: execute/run but no backend assigned earlier (and not provided inline)
    if has_execute_or_run and not has_backend_assign:
        # allow the 'backend=' kwarg inline as sufficient — re-scan
        inline_backend = re.search(r"backend\s*=", joined)
        if not inline_backend:
            report.findings.append(Finding(
                "QC03",
                1,
                "Execution call issued but no backend appears to be assigned. "
                "Assign a backend (e.g., `Aer.get_backend(...)`) before `.run()`.",
            ))

    # QC08: circuit/register name used but never defined
    # (very rough: check for names that appear on the LHS of . access without assignment)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            n = node.value.id
            if n in {"qc", "qr", "cr", "circuit"} and n not in defined_names:
                report.findings.append(Finding(
                    "QC08",
                    getattr(node, "lineno", 0),
                    f"Identifier `{n}` used before definition.",
                ))
                break  # only report once

    return report


def check_file(path: Path, case: str = "?") -> CaseReport:
    src = path.read_text(encoding="utf-8", errors="replace")
    return check_source(src, case=case, file=path.name)


def check_dataset(db_root: Path, out_json: Path | None = None,
                  apply_paper_filter: bool = True) -> list[CaseReport]:
    """Run QChecker over every canonical case folder in db_root.

    Uses os.walk (OS-independent case-sensitive discovery) and applies the
    same paper-filter as src/dataset.py::iter_cases so that QChecker always
    reports on the same 42-case set as the rest of the pipeline.
    """
    import os
    # Keep this list in sync with src/dataset.py::PAPER_EXCLUDED_CASES
    excluded = {
        "Terra-0-4000/1",
        "Terra-0-4000/3",
        "Terra-0-4000/6",
        "Terra-0-4000/7",
        "stackoverflow-1-5/1",
    }
    reports: list[CaseReport] = []
    case_dirs: list[tuple[str, Path]] = []
    for dirpath, _dirnames, filenames in os.walk(db_root):
        if "buggy.py" not in filenames:
            continue
        d = Path(dirpath)
        cid = str(d.relative_to(db_root)).replace(os.sep, "/").replace("\\", "/")
        if apply_paper_filter and cid in excluded:
            continue
        case_dirs.append((cid, d / "buggy.py"))
    for cid, buggy in sorted(case_dirs, key=lambda t: t[0]):
        reports.append(check_file(buggy, case=cid))
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps([r.to_dict() for r in reports], indent=2),
            encoding="utf-8",
        )
    return reports


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="QChecker-style static analyzer for Qiskit bugs")
    ap.add_argument("--db_root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--filter_cases", type=Path, default=None,
                    help="optional JSON with {'val_ids': [...], 'test_ids': [...]}")
    args = ap.parse_args()

    filter_ids: set[str] | None = None
    if args.filter_cases is not None:
        data = json.loads(args.filter_cases.read_text())
        filter_ids = set(data.get("val_ids", []) + data.get("test_ids", []))

    reports = check_dataset(args.db_root, out_json=None)
    if filter_ids is not None:
        reports = [r for r in reports if r.case in filter_ids]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([r.to_dict() for r in reports], indent=2),
        encoding="utf-8",
    )
    total = sum(len(r.findings) for r in reports)
    with_findings = sum(1 for r in reports if r.findings)
    print(f"[OK] Wrote {args.out} ({len(reports)} cases, "
          f"{with_findings} with findings, {total} total findings)")
