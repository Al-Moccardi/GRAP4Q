"""Generator for the 10 demo cases.

Each case is generated from a per-family template. Buggy versions
combine the four FAIL patterns:

    DeprecatedExecuteAPI:  execute(qc, backend=bk)         -> bk.run(transpile(qc, bk))
    LegacyBackendName:     local_*_simulator               -> *_simulator
    GetDataMisuse:         result.get_data(qc)             -> result.get_counts(qc)
                                                          OR result.get_statevector()
    IdenGateRename:        qc.iden(...)                    -> qc.id(...)

Run:
    python build_cases.py

Writes:
    app/demo_cases/case_NN/{buggy,fixed}.py
    app/demo_cases/case_NN/meta.json
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

OUT_ROOT = Path(__file__).resolve().parent / "app" / "demo_cases"


# ---------------------------------------------------------------------------
# Per-family templates. Each returns (buggy_src, fixed_src, family,
# circuit_name, readout, n_qubits).
# ---------------------------------------------------------------------------
def _bell(readout: str) -> tuple[str, str, dict]:
    """Bell pair circuit. readout in {'counts', 'statevector'}."""
    if readout == "counts":
        backend_old = "local_qasm_simulator"
        backend_new = "qasm_simulator"
        getter_new = "get_counts"
        getter_args_new = "(qc)"
        cr_decl = (
            "    cr = ClassicalRegister(2, name=\"c\")\n"
            "    qc = QuantumCircuit(qr, cr)\n")
        measure_block = "    qc.measure(qr, cr)\n"
        cr_import = ", ClassicalRegister"
    else:
        backend_old = "local_statevector_simulator"
        backend_new = "statevector_simulator"
        getter_new = "get_statevector"
        getter_args_new = "()"
        cr_decl = "    qc = QuantumCircuit(qr)\n"
        measure_block = ""
        cr_import = ""

    buggy = f'''"""Bell-state preparation with {readout} readout.

Prepares the Bell state |Phi+> = (|00> + |11>) / sqrt(2) on a
two-qubit register and returns the {readout}.
"""
from qiskit import QuantumCircuit, QuantumRegister{cr_import}
from qiskit import Aer, execute


def build_bell_circuit() -> QuantumCircuit:
    qr = QuantumRegister(2, name="q")
{cr_decl}
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])

    qc.iden(qr[0])
    qc.iden(qr[1])

{measure_block}    return qc


def run_bell():
    qc = build_bell_circuit()
    backend = Aer.get_backend("{backend_old}")
    job = execute(qc, backend=backend, shots=1024)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_bell())
'''
    fixed = f'''"""Bell-state preparation with {readout} readout.

Prepares the Bell state |Phi+> = (|00> + |11>) / sqrt(2) on a
two-qubit register and returns the {readout}.
"""
from qiskit import QuantumCircuit, QuantumRegister{cr_import}, transpile
from qiskit_aer import Aer


def build_bell_circuit() -> QuantumCircuit:
    qr = QuantumRegister(2, name="q")
{cr_decl}
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])

    qc.id(qr[0])
    qc.id(qr[1])

{measure_block}    return qc


def run_bell():
    qc = build_bell_circuit()
    backend = Aer.get_backend("{backend_new}")
    job = backend.run(transpile(qc, backend), shots=1024)
    result = job.result()
    return result.{getter_new}{getter_args_new}


if __name__ == "__main__":
    print(run_bell())
'''
    meta = {"family": "bell", "circuit": "Bell pair",
            "readout": readout, "n_qubits": 2}
    return buggy, fixed, meta


def _ghz(n_qubits: int, readout: str) -> tuple[str, str, dict]:
    if readout == "counts":
        backend_old = "local_qasm_simulator"
        backend_new = "qasm_simulator"
        getter_new = "get_counts"
        getter_args_new = "(qc)"
        cr_import = ", ClassicalRegister"
        cr_setup = (f"    cr = ClassicalRegister({n_qubits}, name=\"c\")\n"
                    f"    qc = QuantumCircuit(qr, cr)\n")
        measure_block = "    qc.measure(qr, cr)\n"
    else:
        backend_old = "local_statevector_simulator"
        backend_new = "statevector_simulator"
        getter_new = "get_statevector"
        getter_args_new = "()"
        cr_import = ""
        cr_setup = "    qc = QuantumCircuit(qr)\n"
        measure_block = ""

    buggy = f'''"""GHZ-{n_qubits} state preparation with {readout} readout.

Prepares |GHZ_{n_qubits}> = (|0...0> + |1...1>) / sqrt(2) on a
{n_qubits}-qubit register and returns the {readout}.
"""
from qiskit import QuantumCircuit, QuantumRegister{cr_import}
from qiskit import Aer, execute


def build_ghz_circuit(n_qubits: int = {n_qubits}) -> QuantumCircuit:
    qr = QuantumRegister(n_qubits, name="q")
{cr_setup}
    qc.h(qr[0])
    for k in range(1, n_qubits):
        qc.cx(qr[0], qr[k])

    for k in range(n_qubits):
        qc.iden(qr[k])

{measure_block}    return qc


def run_ghz():
    qc = build_ghz_circuit()
    backend = Aer.get_backend("{backend_old}")
    job = execute(qc, backend=backend, shots=1024)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_ghz())
'''
    fixed = f'''"""GHZ-{n_qubits} state preparation with {readout} readout.

Prepares |GHZ_{n_qubits}> = (|0...0> + |1...1>) / sqrt(2) on a
{n_qubits}-qubit register and returns the {readout}.
"""
from qiskit import QuantumCircuit, QuantumRegister{cr_import}, transpile
from qiskit_aer import Aer


def build_ghz_circuit(n_qubits: int = {n_qubits}) -> QuantumCircuit:
    qr = QuantumRegister(n_qubits, name="q")
{cr_setup}
    qc.h(qr[0])
    for k in range(1, n_qubits):
        qc.cx(qr[0], qr[k])

    for k in range(n_qubits):
        qc.id(qr[k])

{measure_block}    return qc


def run_ghz():
    qc = build_ghz_circuit()
    backend = Aer.get_backend("{backend_new}")
    job = backend.run(transpile(qc, backend), shots=1024)
    result = job.result()
    return result.{getter_new}{getter_args_new}


if __name__ == "__main__":
    print(run_ghz())
'''
    meta = {"family": "ghz", "circuit": f"GHZ-{n_qubits}",
            "readout": readout, "n_qubits": n_qubits}
    return buggy, fixed, meta


def _qft(inverse: bool, readout: str) -> tuple[str, str, dict]:
    if readout == "counts":
        backend_old = "local_qasm_simulator"
        backend_new = "qasm_simulator"
        getter_new = "get_counts"
        getter_args_new = "(qc)"
        cr_import = ", ClassicalRegister"
        cr_setup = ("    cr = ClassicalRegister(3, name=\"c\")\n"
                    "    qc = QuantumCircuit(qr, cr)\n")
        measure_block = "    qc.measure(qr, cr)\n"
    else:
        backend_old = "local_statevector_simulator"
        backend_new = "statevector_simulator"
        getter_new = "get_statevector"
        getter_args_new = "()"
        cr_import = ""
        cr_setup = "    qc = QuantumCircuit(qr)\n"
        measure_block = ""

    direction = "Inverse QFT" if inverse else "QFT"
    sign = "" if not inverse else "-"

    buggy = f'''"""{direction} on a 3-qubit register with {readout} readout.

Applies the {direction} circuit to a 3-qubit register
prepared in a uniform superposition.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister{cr_import}
from qiskit import Aer, execute


def build_qft_circuit() -> QuantumCircuit:
    n = 3
    qr = QuantumRegister(n, name="q")
{cr_setup}
    # Prepare a uniform superposition on the input register.
    for k in range(n):
        qc.h(qr[k])
        qc.iden(qr[k])

    # {direction} body.
    for j in range(n):
        qc.h(qr[j])
        for m in range(j + 1, n):
            qc.cp({sign}np.pi / 2 ** (m - j), qr[m], qr[j])

    # Reverse qubit order at the output.
    for k in range(n // 2):
        qc.swap(qr[k], qr[n - 1 - k])

{measure_block}    return qc


def run_qft():
    qc = build_qft_circuit()
    backend = Aer.get_backend("{backend_old}")
    job = execute(qc, backend=backend, shots=1024)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_qft())
'''
    fixed = f'''"""{direction} on a 3-qubit register with {readout} readout.

Applies the {direction} circuit to a 3-qubit register
prepared in a uniform superposition.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister{cr_import}, transpile
from qiskit_aer import Aer


def build_qft_circuit() -> QuantumCircuit:
    n = 3
    qr = QuantumRegister(n, name="q")
{cr_setup}
    # Prepare a uniform superposition on the input register.
    for k in range(n):
        qc.h(qr[k])
        qc.id(qr[k])

    # {direction} body.
    for j in range(n):
        qc.h(qr[j])
        for m in range(j + 1, n):
            qc.cp({sign}np.pi / 2 ** (m - j), qr[m], qr[j])

    # Reverse qubit order at the output.
    for k in range(n // 2):
        qc.swap(qr[k], qr[n - 1 - k])

{measure_block}    return qc


def run_qft():
    qc = build_qft_circuit()
    backend = Aer.get_backend("{backend_new}")
    job = backend.run(transpile(qc, backend), shots=1024)
    result = job.result()
    return result.{getter_new}{getter_args_new}


if __name__ == "__main__":
    print(run_qft())
'''
    meta = {"family": "qft", "circuit": direction,
            "readout": readout, "n_qubits": 3}
    return buggy, fixed, meta


def _teleportation(readout: str) -> tuple[str, str, dict]:
    if readout == "counts":
        backend_old = "local_qasm_simulator"
        backend_new = "qasm_simulator"
        getter_new = "get_counts"
        getter_args_new = "(qc)"
    else:
        backend_old = "local_statevector_simulator"
        backend_new = "statevector_simulator"
        getter_new = "get_statevector"
        getter_args_new = "()"

    buggy = f'''"""Single-qubit teleportation with {readout} readout.

Teleports |psi> = cos(theta/2)|0> + sin(theta/2)|1> from qubit 0
to qubit 2 using a Bell pair on qubits 1 and 2.
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister,
                    ClassicalRegister)
from qiskit import Aer, execute


def build_teleport_circuit(theta: float = np.pi / 3) -> QuantumCircuit:
    qr = QuantumRegister(3, name="q")
    cr_a = ClassicalRegister(2, name="alice")
    cr_b = ClassicalRegister(1, name="bob")
    qc = QuantumCircuit(qr, cr_a, cr_b)

    # Encode |psi> on qubit 0.
    qc.ry(theta, qr[0])
    qc.iden(qr[1])
    qc.iden(qr[2])
    qc.barrier()

    # Bell pair on qubits 1 and 2.
    qc.h(qr[1])
    qc.cx(qr[1], qr[2])
    qc.iden(qr[0])
    qc.barrier()

    # Alice's Bell measurement on qubits 0 and 1.
    qc.cx(qr[0], qr[1])
    qc.h(qr[0])
    qc.measure(qr[0], cr_a[0])
    qc.measure(qr[1], cr_a[1])
    qc.barrier()

    # Bob applies Pauli corrections and measures.
    qc.x(qr[2]).c_if(cr_a, 2)
    qc.z(qr[2]).c_if(cr_a, 1)
    qc.measure(qr[2], cr_b[0])

    return qc


def run_teleport():
    qc = build_teleport_circuit()
    backend = Aer.get_backend("{backend_old}")
    job = execute(qc, backend=backend, shots=2048)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_teleport())
'''
    fixed = f'''"""Single-qubit teleportation with {readout} readout.

Teleports |psi> = cos(theta/2)|0> + sin(theta/2)|1> from qubit 0
to qubit 2 using a Bell pair on qubits 1 and 2.
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister,
                    ClassicalRegister, transpile)
from qiskit_aer import Aer


def build_teleport_circuit(theta: float = np.pi / 3) -> QuantumCircuit:
    qr = QuantumRegister(3, name="q")
    cr_a = ClassicalRegister(2, name="alice")
    cr_b = ClassicalRegister(1, name="bob")
    qc = QuantumCircuit(qr, cr_a, cr_b)

    # Encode |psi> on qubit 0.
    qc.ry(theta, qr[0])
    qc.id(qr[1])
    qc.id(qr[2])
    qc.barrier()

    # Bell pair on qubits 1 and 2.
    qc.h(qr[1])
    qc.cx(qr[1], qr[2])
    qc.id(qr[0])
    qc.barrier()

    # Alice's Bell measurement on qubits 0 and 1.
    qc.cx(qr[0], qr[1])
    qc.h(qr[0])
    qc.measure(qr[0], cr_a[0])
    qc.measure(qr[1], cr_a[1])
    qc.barrier()

    # Bob applies Pauli corrections and measures.
    qc.x(qr[2]).c_if(cr_a, 2)
    qc.z(qr[2]).c_if(cr_a, 1)
    qc.measure(qr[2], cr_b[0])

    return qc


def run_teleport():
    qc = build_teleport_circuit()
    backend = Aer.get_backend("{backend_new}")
    job = backend.run(transpile(qc, backend), shots=2048)
    result = job.result()
    return result.{getter_new}{getter_args_new}


if __name__ == "__main__":
    print(run_teleport())
'''
    meta = {"family": "teleportation", "circuit": "Single-qubit teleport",
            "readout": readout, "n_qubits": 3}
    return buggy, fixed, meta


def _vqe(layers: int, readout: str) -> tuple[str, str, dict]:
    if readout == "counts":
        backend_old = "local_qasm_simulator"
        backend_new = "qasm_simulator"
        getter_new = "get_counts"
        getter_args_new = "(qc)"
        cr_import = ", ClassicalRegister"
        cr_setup = ("    cr = ClassicalRegister(3, name=\"c\")\n"
                    "    qc = QuantumCircuit(qr, cr)\n")
        measure_block = "    qc.measure(qr, cr)\n"
    else:
        backend_old = "local_statevector_simulator"
        backend_new = "statevector_simulator"
        getter_new = "get_statevector"
        getter_args_new = "()"
        cr_import = ""
        cr_setup = "    qc = QuantumCircuit(qr)\n"
        measure_block = ""

    rotation_block = (
        "        for k in range(n):\n"
        "            qc.ry(params[2 * k + 0], qr[k])\n"
        "            qc.rz(params[2 * k + 1], qr[k])\n"
    ) if layers == 2 else (
        "        for k in range(n):\n"
        "            qc.ry(params[k], qr[k])\n"
    )
    n_params_per_layer = "2 * n" if layers == 2 else "n"
    layer_label = "RY-RZ" if layers == 2 else "RY-only"

    buggy = f'''"""{layer_label} variational ansatz on 3 qubits with {readout} readout.

Builds a {layers}-layer variational ansatz with linear entanglement
and runs it for a fixed parameter assignment.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister{cr_import}
from qiskit import Aer, execute


def build_vqe_ansatz(params: list) -> QuantumCircuit:
    n = 3
    n_layers = {layers}
    if len(params) != n_layers * ({n_params_per_layer}):
        raise ValueError(
            f"Expected {{n_layers * ({n_params_per_layer})}} params, "
            f"got {{len(params)}}.")

    qr = QuantumRegister(n, name="q")
{cr_setup}
    for layer in range(n_layers):
        params_layer = params[layer * ({n_params_per_layer}):
                              (layer + 1) * ({n_params_per_layer})]
{rotation_block}        for k in range(n - 1):
            qc.cx(qr[k], qr[k + 1])
        for k in range(n):
            qc.iden(qr[k])

{measure_block}    return qc


def run_vqe():
    n = 3
    n_params = {layers} * ({n_params_per_layer})
    params = list(np.linspace(0, np.pi, n_params))
    qc = build_vqe_ansatz(params)
    backend = Aer.get_backend("{backend_old}")
    job = execute(qc, backend=backend, shots=1024)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_vqe())
'''
    fixed = f'''"""{layer_label} variational ansatz on 3 qubits with {readout} readout.

Builds a {layers}-layer variational ansatz with linear entanglement
and runs it for a fixed parameter assignment.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister{cr_import}, transpile
from qiskit_aer import Aer


def build_vqe_ansatz(params: list) -> QuantumCircuit:
    n = 3
    n_layers = {layers}
    if len(params) != n_layers * ({n_params_per_layer}):
        raise ValueError(
            f"Expected {{n_layers * ({n_params_per_layer})}} params, "
            f"got {{len(params)}}.")

    qr = QuantumRegister(n, name="q")
{cr_setup}
    for layer in range(n_layers):
        params_layer = params[layer * ({n_params_per_layer}):
                              (layer + 1) * ({n_params_per_layer})]
{rotation_block}        for k in range(n - 1):
            qc.cx(qr[k], qr[k + 1])
        for k in range(n):
            qc.id(qr[k])

{measure_block}    return qc


def run_vqe():
    n = 3
    n_params = {layers} * ({n_params_per_layer})
    params = list(np.linspace(0, np.pi, n_params))
    qc = build_vqe_ansatz(params)
    backend = Aer.get_backend("{backend_new}")
    job = backend.run(transpile(qc, backend), shots=1024)
    result = job.result()
    return result.{getter_new}{getter_args_new}


if __name__ == "__main__":
    print(run_vqe())
'''
    meta = {"family": "vqe", "circuit": f"{layer_label} ansatz",
            "readout": readout, "n_qubits": 3}
    return buggy, fixed, meta


# ---------------------------------------------------------------------------
# Case roster
# ---------------------------------------------------------------------------
ROSTER = [
    ("case_01", _bell, ("counts",)),
    ("case_02", _bell, ("statevector",)),
    ("case_03", _ghz, (3, "counts")),
    ("case_04", _ghz, (4, "statevector")),
    ("case_05", _qft, (False, "counts")),
    ("case_06", _qft, (True, "statevector")),
    ("case_07", _teleportation, ("counts",)),
    ("case_08", _teleportation, ("statevector",)),
    ("case_09", _vqe, (1, "counts")),
    ("case_10", _vqe, (2, "statevector")),
]


# ---------------------------------------------------------------------------
# Audit checks
# ---------------------------------------------------------------------------
DEPRECATED_PATTERNS = {
    "iden": r"\biden\s*\(",
    "local_*_simulator": r"\blocal_\w+_simulator\b",
    "execute(qc, backend=)": r"\bexecute\s*\([^)]*backend\s*=",
    "get_data(qc)": r"\.get_data\s*\(",
}


def _audit(buggy: str, fixed: str, case_id: str) -> None:
    # Both must parse.
    try:
        ast.parse(buggy)
    except SyntaxError as e:
        raise AssertionError(f"{case_id} buggy.py does not parse: {e}")
    try:
        ast.parse(fixed)
    except SyntaxError as e:
        raise AssertionError(f"{case_id} fixed.py does not parse: {e}")
    # Buggy must contain ALL four deprecated patterns.
    missing = [name for name, pat in DEPRECATED_PATTERNS.items()
               if not re.search(pat, buggy)]
    if missing:
        raise AssertionError(
            f"{case_id} buggy.py missing patterns: {missing}")
    # Fixed must contain NONE.
    present = [name for name, pat in DEPRECATED_PATTERNS.items()
               if re.search(pat, fixed)]
    if present:
        raise AssertionError(
            f"{case_id} fixed.py still contains patterns: {present}")


# ---------------------------------------------------------------------------
def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for case_id, builder, args in ROSTER:
        case_dir = OUT_ROOT / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        buggy, fixed, meta = builder(*args)
        meta["case_id"] = case_id
        meta["patterns_combined"] = list(DEPRECATED_PATTERNS.keys())
        _audit(buggy, fixed, case_id)
        (case_dir / "buggy.py").write_text(buggy, encoding="utf-8")
        (case_dir / "fixed.py").write_text(fixed, encoding="utf-8")
        (case_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8")
        n_lines_buggy = len(buggy.splitlines())
        print(f"  {case_id}  family={meta['family']:14s} "
              f"readout={meta['readout']:11s} "
              f"n_qubits={meta['n_qubits']}  buggy={n_lines_buggy} lines")
    print(f"\nWrote {len(ROSTER)} cases to {OUT_ROOT}")


if __name__ == "__main__":
    main()
