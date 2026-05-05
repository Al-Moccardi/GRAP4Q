"""Generator for 5 hard synthetic Bugs4Q-style cases.

Each case is designed to be HARDER than naive deprecated-pattern
recipes. The intent: a full-file rewrite (Pure-LLM strategy) is
unlikely to fix the structural / logic bug while also touching only
the right lines, so Pure-LLM should score low on Lines-F1 even when
it produces parseable code.

Bug profiles:
  case_syn_01  Off-by-one qubit indexing in a CNOT chain (logic
               bug); plus deprecated `iden`. The fix touches only
               2 lines but a full rewrite touches >30.
  case_syn_02  Classical-register-as-quantum bug: a measurement
               result is fed into a quantum gate. Triggers the
               paper's QuantumRegisterSanityOK guardrail when run
               under GRAP-Q; Pure-LLM has no such check.
  case_syn_03  Custom transpiler-pass with subtly broken `run(self,
               dag)` interface (extra positional arg). Triggers the
               PassInterfaceOK guardrail. Pure-LLM tends to "fix" by
               rewriting the whole pass which usually changes the
               signature again.
  case_syn_04  Long file (~120 lines) with a localised qubit-index
               typo deep inside one helper function. Plus 2
               deprecated patterns elsewhere. Tests whether the
               method actually localises the defect or just rewrites
               broadly.
  case_syn_05  Inverse QFT with a sign error in one rotation
               (algorithmic bug, no syntax problem) plus a
               deprecated `execute(qc, backend=...)` call. The
               algorithmic bug requires understanding the algorithm.

Run:
    python build_synthetic_cases.py
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

OUT_ROOT = Path(__file__).resolve().parent / "app" / "demo_cases"


# ---------------------------------------------------------------------------
def case_syn_01() -> tuple[str, str, dict]:
    """Off-by-one qubit indexing in CNOT chain + deprecated iden."""
    buggy = '''"""Linear cluster state on a 4-qubit register.

Builds a 1D cluster state by Hadamarding all qubits then applying a
chain of CZ gates between neighbouring qubits. Includes identity
"wait" gates at the end.
"""
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def build_cluster() -> QuantumCircuit:
    n = 4
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    for k in range(n):
        qc.h(qr[k])

    # Off-by-one: should be range(n-1) for qubits (k, k+1).
    for k in range(n):
        qc.cz(qr[k], qr[k + 1])

    for k in range(n):
        qc.iden(qr[k])

    qc.measure(qr, cr)
    return qc


def run_cluster():
    qc = build_cluster()
    backend = Aer.get_backend("qasm_simulator")
    job = execute(qc, backend=backend, shots=1024)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_cluster())
'''
    fixed = '''"""Linear cluster state on a 4-qubit register.

Builds a 1D cluster state by Hadamarding all qubits then applying a
chain of CZ gates between neighbouring qubits. Includes identity
"wait" gates at the end.
"""
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


def build_cluster() -> QuantumCircuit:
    n = 4
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    for k in range(n):
        qc.h(qr[k])

    for k in range(n - 1):
        qc.cz(qr[k], qr[k + 1])

    for k in range(n):
        qc.id(qr[k])

    qc.measure(qr, cr)
    return qc


def run_cluster():
    qc = build_cluster()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=1024)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_cluster())
'''
    return buggy, fixed, {
        "family": "syn_logic_offbyone",
        "circuit": "Linear cluster state",
        "summary": "Off-by-one in CNOT chain (range(n) iterates past last "
                   "qubit). Plus deprecated iden. Fix: range(n-1).",
        "n_qubits": 4,
        "expected_difficulty": "high for Pure-LLM (logic bug needs "
                               "understanding the chain semantics)",
    }


def case_syn_02() -> tuple[str, str, dict]:
    """Classical register fed into a quantum gate (register-misuse bug)."""
    buggy = '''"""Conditioned single-qubit rotation using a measurement outcome.

Measures qubit 0 into a classical register, then applies a controlled
rotation conditional on the classical outcome. The implementation
incorrectly uses the classical register as a control wire for the
RY gate, instead of using c_if for classical conditioning.
"""
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    Aer, execute)
import numpy as np


def build_conditioned():
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(1, name="c")
    qc = QuantumCircuit(qr, cr)

    qc.h(qr[0])
    qc.measure(qr[0], cr[0])

    # BUG: cr is a classical register; cannot be used as a control
    # qubit for cry. The intended behavior is to apply ry(pi/2) only
    # if the measurement was 1.
    qc.cry(np.pi / 2, cr[0], qr[1])

    qc.iden(qr[1])
    qc.measure(qr[1], cr[0])
    return qc


def run_conditioned():
    qc = build_conditioned()
    backend = Aer.get_backend("local_qasm_simulator")
    job = execute(qc, backend=backend, shots=512)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    print(run_conditioned())
'''
    fixed = '''"""Conditioned single-qubit rotation using a measurement outcome.

Measures qubit 0 into a classical register, then applies a controlled
rotation conditional on the classical outcome. The implementation
incorrectly uses the classical register as a control wire for the
RY gate, instead of using c_if for classical conditioning.
"""
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer
import numpy as np


def build_conditioned():
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(1, name="c")
    qc = QuantumCircuit(qr, cr)

    qc.h(qr[0])
    qc.measure(qr[0], cr[0])

    qc.ry(np.pi / 2, qr[1]).c_if(cr, 1)

    qc.id(qr[1])
    qc.measure(qr[1], cr[0])
    return qc


def run_conditioned():
    qc = build_conditioned()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=512)
    result = job.result()
    return result.get_counts(qc)


if __name__ == "__main__":
    print(run_conditioned())
'''
    return buggy, fixed, {
        "family": "syn_register_misuse",
        "circuit": "Classically-conditioned rotation",
        "summary": "Uses classical register as control for cry gate. "
                   "Triggers QuantumRegisterSanityOK guardrail under "
                   "GRAP-Q. Plus all 4 deprecated patterns.",
        "n_qubits": 2,
        "expected_difficulty": "high for Pure-LLM (no guardrail to "
                               "catch register misuse).",
    }


def case_syn_03() -> tuple[str, str, dict]:
    """Custom transpiler pass with broken interface (PassInterface drift)."""
    buggy = '''"""Custom transpiler pass that counts CX gates in a DAG.

Implements a TransformationPass-style class with a `run` method.
Used as part of a small custom pass manager to instrument circuits
before execution on the simulator.
"""
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute
from qiskit.transpiler.basepasses import TransformationPass


class CountCXPass(TransformationPass):
    """A pass that should preserve the DAG verbatim and stash the CX
    count on a property attribute. The base TransformationPass
    contract is `run(self, dag)`."""

    def __init__(self):
        super().__init__()
        self.cx_count = 0

    # BUG: extra positional argument breaks the pass interface.
    def run(self, dag, options):
        self.cx_count = sum(1 for node in dag.op_nodes()
                            if node.name == "cx")
        return dag


def build_circuit() -> QuantumCircuit:
    qr = QuantumRegister(3, name="q")
    cr = ClassicalRegister(3, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    qc.cx(qr[1], qr[2])
    qc.iden(qr[0])
    qc.iden(qr[1])
    qc.iden(qr[2])
    qc.measure(qr, cr)
    return qc


def run_demo():
    qc = build_circuit()
    backend = Aer.get_backend("local_qasm_simulator")
    job = execute(qc, backend=backend, shots=1024)
    return job.result().get_data(qc)


if __name__ == "__main__":
    print(run_demo())
'''
    fixed = '''"""Custom transpiler pass that counts CX gates in a DAG.

Implements a TransformationPass-style class with a `run` method.
Used as part of a small custom pass manager to instrument circuits
before execution on the simulator.
"""
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer
from qiskit.transpiler.basepasses import TransformationPass


class CountCXPass(TransformationPass):
    """A pass that should preserve the DAG verbatim and stash the CX
    count on a property attribute. The base TransformationPass
    contract is `run(self, dag)`."""

    def __init__(self):
        super().__init__()
        self.cx_count = 0

    def run(self, dag):
        self.cx_count = sum(1 for node in dag.op_nodes()
                            if node.name == "cx")
        return dag


def build_circuit() -> QuantumCircuit:
    qr = QuantumRegister(3, name="q")
    cr = ClassicalRegister(3, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    qc.cx(qr[1], qr[2])
    qc.id(qr[0])
    qc.id(qr[1])
    qc.id(qr[2])
    qc.measure(qr, cr)
    return qc


def run_demo():
    qc = build_circuit()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=1024)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_demo())
'''
    return buggy, fixed, {
        "family": "syn_pass_interface",
        "circuit": "Custom pass + 3-qubit GHZ-like demo",
        "summary": "Custom TransformationPass.run() has an extra "
                   "argument (breaks interface contract). Triggers "
                   "PassInterfaceOK guardrail. Plus all 4 deprecated "
                   "patterns.",
        "n_qubits": 3,
        "expected_difficulty": "high for Pure-LLM (no PassInterface check; "
                               "rewrites tend to introduce other drift).",
    }


def case_syn_04() -> tuple[str, str, dict]:
    """Long file with a deeply localised qubit-index typo."""
    buggy = '''"""Multi-stage variational protocol for a 4-qubit problem.

This module assembles a parameterised ansatz across multiple helper
functions, runs it on a simulator, and extracts a sample-mean
expectation value. The structure mirrors a small VQE driver script.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


N_QUBITS = 4


def hadamard_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Place a Hadamard on every qubit in the register."""
    for k in range(N_QUBITS):
        qc.h(qr[k])


def rotation_layer(qc: QuantumCircuit, qr: QuantumRegister,
                   thetas: list) -> None:
    """Apply Y-rotations parameterised by `thetas`."""
    if len(thetas) != N_QUBITS:
        raise ValueError(
            f"Expected {N_QUBITS} angles, got {len(thetas)}.")
    for k in range(N_QUBITS):
        qc.ry(thetas[k], qr[k])


def entangle_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Linear chain of CNOTs between neighbouring qubits.

    Should target every pair (k, k+1) for k in range(N_QUBITS - 1).
    The current implementation has a typo on the second iteration.
    """
    for k in range(N_QUBITS - 1):
        if k == 1:
            # BUG: should be qc.cx(qr[k], qr[k + 1]) like every
            # other iteration. Operand order is swapped here only,
            # which makes the controlled-target relationship
            # different on this one bond.
            qc.cx(qr[k + 1], qr[k])
        else:
            qc.cx(qr[k], qr[k + 1])


def wait_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Idle every qubit for one cycle using an identity gate."""
    for k in range(N_QUBITS):
        qc.iden(qr[k])


def measurement_layer(qc: QuantumCircuit, qr: QuantumRegister,
                      cr: ClassicalRegister) -> None:
    """Measure every qubit into the matching classical bit."""
    for k in range(N_QUBITS):
        qc.measure(qr[k], cr[k])


def build_protocol(thetas_layer1: list, thetas_layer2: list
                   ) -> QuantumCircuit:
    """Assemble the full two-layer protocol on N_QUBITS qubits."""
    qr = QuantumRegister(N_QUBITS, name="q")
    cr = ClassicalRegister(N_QUBITS, name="c")
    qc = QuantumCircuit(qr, cr)
    hadamard_layer(qc, qr)
    rotation_layer(qc, qr, thetas_layer1)
    entangle_layer(qc, qr)
    wait_layer(qc, qr)
    rotation_layer(qc, qr, thetas_layer2)
    entangle_layer(qc, qr)
    wait_layer(qc, qr)
    measurement_layer(qc, qr, cr)
    return qc


def run_protocol(thetas_layer1: list, thetas_layer2: list,
                 shots: int = 4096):
    """Build and execute the protocol; return the raw counts dict."""
    qc = build_protocol(thetas_layer1, thetas_layer2)
    backend = Aer.get_backend("local_qasm_simulator")
    job = execute(qc, backend=backend, shots=shots)
    result = job.result()
    return result.get_data(qc)


if __name__ == "__main__":
    th1 = list(np.linspace(0, np.pi, N_QUBITS))
    th2 = list(np.linspace(np.pi / 4, np.pi / 2, N_QUBITS))
    print(run_protocol(th1, th2))
'''
    fixed = '''"""Multi-stage variational protocol for a 4-qubit problem.

This module assembles a parameterised ansatz across multiple helper
functions, runs it on a simulator, and extracts a sample-mean
expectation value. The structure mirrors a small VQE driver script.
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


N_QUBITS = 4


def hadamard_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Place a Hadamard on every qubit in the register."""
    for k in range(N_QUBITS):
        qc.h(qr[k])


def rotation_layer(qc: QuantumCircuit, qr: QuantumRegister,
                   thetas: list) -> None:
    """Apply Y-rotations parameterised by `thetas`."""
    if len(thetas) != N_QUBITS:
        raise ValueError(
            f"Expected {N_QUBITS} angles, got {len(thetas)}.")
    for k in range(N_QUBITS):
        qc.ry(thetas[k], qr[k])


def entangle_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Linear chain of CNOTs between neighbouring qubits.

    Should target every pair (k, k+1) for k in range(N_QUBITS - 1).
    The current implementation has a typo on the second iteration.
    """
    for k in range(N_QUBITS - 1):
        qc.cx(qr[k], qr[k + 1])


def wait_layer(qc: QuantumCircuit, qr: QuantumRegister) -> None:
    """Idle every qubit for one cycle using an identity gate."""
    for k in range(N_QUBITS):
        qc.id(qr[k])


def measurement_layer(qc: QuantumCircuit, qr: QuantumRegister,
                      cr: ClassicalRegister) -> None:
    """Measure every qubit into the matching classical bit."""
    for k in range(N_QUBITS):
        qc.measure(qr[k], cr[k])


def build_protocol(thetas_layer1: list, thetas_layer2: list
                   ) -> QuantumCircuit:
    """Assemble the full two-layer protocol on N_QUBITS qubits."""
    qr = QuantumRegister(N_QUBITS, name="q")
    cr = ClassicalRegister(N_QUBITS, name="c")
    qc = QuantumCircuit(qr, cr)
    hadamard_layer(qc, qr)
    rotation_layer(qc, qr, thetas_layer1)
    entangle_layer(qc, qr)
    wait_layer(qc, qr)
    rotation_layer(qc, qr, thetas_layer2)
    entangle_layer(qc, qr)
    wait_layer(qc, qr)
    measurement_layer(qc, qr, cr)
    return qc


def run_protocol(thetas_layer1: list, thetas_layer2: list,
                 shots: int = 4096):
    """Build and execute the protocol; return the raw counts dict."""
    qc = build_protocol(thetas_layer1, thetas_layer2)
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    result = job.result()
    return result.get_counts(qc)


if __name__ == "__main__":
    th1 = list(np.linspace(0, np.pi, N_QUBITS))
    th2 = list(np.linspace(np.pi / 4, np.pi / 2, N_QUBITS))
    print(run_protocol(th1, th2))
'''
    return buggy, fixed, {
        "family": "syn_long_localised",
        "circuit": "Two-layer 4-qubit variational protocol",
        "summary": "Long file (~100 lines). Localised CNOT operand-flip "
                   "in entangle_layer (only on iteration k==1). Plus all "
                   "4 deprecated patterns. Tests defect localisation.",
        "n_qubits": 4,
        "expected_difficulty": "high for Pure-LLM (long file forces full "
                               "rewrite, which dilutes the score against "
                               "the gold's small edit footprint).",
    }


def case_syn_05() -> tuple[str, str, dict]:
    """Inverse QFT with sign error on one rotation."""
    buggy = '''"""Inverse QFT on a 3-qubit register.

Applies the inverse QFT circuit to a register prepared in the |001>
basis state. Includes identity wait gates between phases.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def build_iqft() -> QuantumCircuit:
    n = 3
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    # Prepare |001>.
    qc.x(qr[0])
    qc.iden(qr[1])
    qc.iden(qr[2])

    # Reverse qubit order at the input.
    for k in range(n // 2):
        qc.swap(qr[k], qr[n - 1 - k])

    # Inverse QFT body. The conditional phases should have NEGATIVE
    # angles for the inverse direction.
    for j in reversed(range(n)):
        qc.h(qr[j])
        for m in range(j):
            # BUG: positive sign for inverse QFT is wrong; should be
            # negative.
            qc.cp(np.pi / 2 ** (j - m), qr[m], qr[j])

    qc.measure(qr, cr)
    return qc


def run_iqft():
    qc = build_iqft()
    backend = Aer.get_backend("local_qasm_simulator")
    job = execute(qc, backend=backend, shots=2048)
    return job.result().get_data(qc)


if __name__ == "__main__":
    print(run_iqft())
'''
    fixed = '''"""Inverse QFT on a 3-qubit register.

Applies the inverse QFT circuit to a register prepared in the |001>
basis state. Includes identity wait gates between phases.
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


def build_iqft() -> QuantumCircuit:
    n = 3
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    qc.x(qr[0])
    qc.id(qr[1])
    qc.id(qr[2])

    for k in range(n // 2):
        qc.swap(qr[k], qr[n - 1 - k])

    for j in reversed(range(n)):
        qc.h(qr[j])
        for m in range(j):
            qc.cp(-np.pi / 2 ** (j - m), qr[m], qr[j])

    qc.measure(qr, cr)
    return qc


def run_iqft():
    qc = build_iqft()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=2048)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_iqft())
'''
    return buggy, fixed, {
        "family": "syn_algorithmic",
        "circuit": "Inverse QFT with sign error",
        "summary": "Inverse QFT body uses positive rotation angles; "
                   "should be negative for the inverse direction. "
                   "Algorithmic bug, not syntax. Plus all 4 deprecated "
                   "patterns.",
        "n_qubits": 3,
        "expected_difficulty": "high for Pure-LLM (algorithmic bug "
                               "requires understanding the QFT direction).",
    }


# ---------------------------------------------------------------------------
ROSTER = [
    ("case_syn_01", case_syn_01),
    ("case_syn_02", case_syn_02),
    ("case_syn_03", case_syn_03),
    ("case_syn_04", case_syn_04),
    ("case_syn_05", case_syn_05),
]


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for case_id, builder in ROSTER:
        case_dir = OUT_ROOT / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        buggy, fixed, family_info = builder()
        # Audit: both must parse.
        try:
            ast.parse(buggy)
        except SyntaxError as e:
            raise AssertionError(f"{case_id} buggy.py does not parse: {e}")
        try:
            ast.parse(fixed)
        except SyntaxError as e:
            raise AssertionError(f"{case_id} fixed.py does not parse: {e}")
        (case_dir / "buggy.py").write_text(buggy, encoding="utf-8")
        (case_dir / "fixed.py").write_text(fixed, encoding="utf-8")
        meta = {
            "case_id": case_id,
            "kind": "synthetic",
            "source": "synthetic",
            "n_lines": len(buggy.splitlines()),
            **family_info,
        }
        (case_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8")
        print(f"  {case_id}: family={family_info['family']:25s} "
              f"buggy={len(buggy.splitlines())} lines")
    print(f"\nWrote {len(ROSTER)} synthetic cases to {OUT_ROOT}")


if __name__ == "__main__":
    main()
