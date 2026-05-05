"""Generator for 5 additional synthetic-hard cases (06-10).

Each case implements a well-known quantum algorithm with a realistic
algorithmic bug PLUS one or two deprecated Qiskit patterns. The
algorithmic bugs are inspired by real failure modes documented in
the quantum-software-engineering literature.

  06  Grover 2-qubit search        : off-by-one in iteration count
                                     + execute(qc, backend=)
  07  Phase estimation             : counting register bit-reversal
                                     omitted + iden
  08  QAOA single-layer MaxCut     : cost-Hamiltonian sign error
                                     + local_*_simulator
  09  CHSH inequality measurement  : wrong basis-rotation angle
                                     + get_data(qc) misuse
  10  VQE expectation value        : sign convention error in counts
                                     -> eigenvalue mapping
                                     + iden + local_*_simulator

Each case is auditable: buggy + fixed must parse, deprecated patterns
appear in buggy and not in fixed, and the gold fix touches a small
number of specific lines (so a full-file rewrite by Pure-LLM has to
touch a much larger surface, hurting precision).

Run:
    python build_cases_06_10.py
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

OUT_ROOT = Path(__file__).resolve().parent / "app" / "demo_cases"


# ---------------------------------------------------------------------------
def case_06_grover_search() -> tuple[str, str, dict]:
    """Grover with wrong iteration count + deprecated execute()."""
    buggy = '''"""Grover amplitude amplification on a 2-qubit search space.

Searches for the marked basis state |11> using a phase oracle and a
diffusion operator. The optimal number of Grover iterations for an
N=4 unstructured search with a single marked element is k=1.
"""
import math
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def build_phase_oracle_for_11() -> QuantumCircuit:
    """Phase oracle that flips the sign of |11>."""
    qr = QuantumRegister(2, name="q")
    oracle = QuantumCircuit(qr, name="oracle_11")
    oracle.cz(qr[0], qr[1])
    return oracle


def build_diffusion_operator() -> QuantumCircuit:
    """Standard Grover diffusion operator D = 2|psi><psi| - I on 2 qubits."""
    qr = QuantumRegister(2, name="q")
    diff = QuantumCircuit(qr, name="diffusion")
    diff.h(qr[0]); diff.h(qr[1])
    diff.x(qr[0]); diff.x(qr[1])
    diff.cz(qr[0], qr[1])
    diff.x(qr[0]); diff.x(qr[1])
    diff.h(qr[0]); diff.h(qr[1])
    return diff


def grover_amplitude_amplification(n_marked: int = 1) -> QuantumCircuit:
    """Build the full Grover circuit for a 2-qubit search space.

    For N=4 and a single marked element the optimal iteration count
    is k = floor(pi/4 * sqrt(N/n_marked)) = 1.
    """
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)

    # Initial uniform superposition.
    qc.h(qr[0]); qc.h(qr[1])

    # BUG: the optimal count is 1, not 2. Two iterations over-rotate
    # past the marked state and reduce success probability.
    n_iterations = round(math.pi / 4 * math.sqrt(4 / n_marked)) + 1
    for _ in range(n_iterations):
        qc.compose(build_phase_oracle_for_11(), qubits=[qr[0], qr[1]],
                   inplace=True)
        qc.compose(build_diffusion_operator(), qubits=[qr[0], qr[1]],
                   inplace=True)

    qc.measure(qr, cr)
    return qc


def measure_grover_success_rate(shots: int = 4096) -> float:
    """Return the empirical probability of measuring the marked |11> state."""
    qc = grover_amplitude_amplification()
    backend = Aer.get_backend("qasm_simulator")
    job = execute(qc, backend=backend, shots=shots)
    counts = job.result().get_counts(qc)
    return counts.get("11", 0) / shots


if __name__ == "__main__":
    p = measure_grover_success_rate()
    print(f"Empirical success probability for |11>: {p:.3f}")
'''
    fixed = '''"""Grover amplitude amplification on a 2-qubit search space.

Searches for the marked basis state |11> using a phase oracle and a
diffusion operator. The optimal number of Grover iterations for an
N=4 unstructured search with a single marked element is k=1.
"""
import math
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


def build_phase_oracle_for_11() -> QuantumCircuit:
    """Phase oracle that flips the sign of |11>."""
    qr = QuantumRegister(2, name="q")
    oracle = QuantumCircuit(qr, name="oracle_11")
    oracle.cz(qr[0], qr[1])
    return oracle


def build_diffusion_operator() -> QuantumCircuit:
    """Standard Grover diffusion operator D = 2|psi><psi| - I on 2 qubits."""
    qr = QuantumRegister(2, name="q")
    diff = QuantumCircuit(qr, name="diffusion")
    diff.h(qr[0]); diff.h(qr[1])
    diff.x(qr[0]); diff.x(qr[1])
    diff.cz(qr[0], qr[1])
    diff.x(qr[0]); diff.x(qr[1])
    diff.h(qr[0]); diff.h(qr[1])
    return diff


def grover_amplitude_amplification(n_marked: int = 1) -> QuantumCircuit:
    """Build the full Grover circuit for a 2-qubit search space.

    For N=4 and a single marked element the optimal iteration count
    is k = floor(pi/4 * sqrt(N/n_marked)) = 1.
    """
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)

    # Initial uniform superposition.
    qc.h(qr[0]); qc.h(qr[1])

    n_iterations = round(math.pi / 4 * math.sqrt(4 / n_marked))
    for _ in range(n_iterations):
        qc.compose(build_phase_oracle_for_11(), qubits=[qr[0], qr[1]],
                   inplace=True)
        qc.compose(build_diffusion_operator(), qubits=[qr[0], qr[1]],
                   inplace=True)

    qc.measure(qr, cr)
    return qc


def measure_grover_success_rate(shots: int = 4096) -> float:
    """Return the empirical probability of measuring the marked |11> state."""
    qc = grover_amplitude_amplification()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    counts = job.result().get_counts(qc)
    return counts.get("11", 0) / shots
'''
    return buggy, fixed, {
        "family": "syn_grover_iterations",
        "circuit": "Grover 2-qubit amplitude amplification",
        "summary": "Iteration count is over-shot by +1 (over-rotation past "
                   "the marked state). Plus deprecated execute().",
        "n_qubits": 2,
        "expected_difficulty": "high for Pure-LLM (algorithmic; the bug is "
                               "a single integer in a formula).",
    }


# ---------------------------------------------------------------------------
def case_07_phase_estimation() -> tuple[str, str, dict]:
    """Phase estimation with omitted bit-reversal + iden."""
    buggy = '''"""Quantum phase estimation for the T-gate eigenstate.

Estimates phase phi such that T|1> = exp(i*pi/4)|1>, i.e., phi = 1/8.
Uses three counting qubits, giving a 1/8 quantization grid; the
expected most-frequent outcome corresponds to the binary fraction
0.001 = 1/8.
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


N_COUNTING = 3


def build_inverse_qft(n_qubits: int) -> QuantumCircuit:
    """Standard inverse QFT on `n_qubits` qubits.

    Convention: this implementation does NOT include the SWAPs that
    reverse the qubit order at the output. The caller is responsible
    for reversing the qubit order before reading out the counting
    register.
    """
    qr = QuantumRegister(n_qubits, name="q")
    iqft = QuantumCircuit(qr, name="iqft")
    for j in reversed(range(n_qubits)):
        iqft.h(qr[j])
        for m in range(j):
            iqft.cp(-np.pi / 2 ** (j - m), qr[m], qr[j])
    return iqft


def estimate_t_gate_phase() -> QuantumCircuit:
    """Build the QPE circuit for the T-gate eigenstate."""
    counting = QuantumRegister(N_COUNTING, name="ctr")
    target = QuantumRegister(1, name="tgt")
    cr = ClassicalRegister(N_COUNTING, name="meas")
    qc = QuantumCircuit(counting, target, cr)

    qc.x(target[0])
    for k in range(N_COUNTING):
        qc.h(counting[k])
        qc.iden(target[0])

    for k in range(N_COUNTING):
        repetitions = 2 ** k
        for _ in range(repetitions):
            qc.cp(np.pi / 4, counting[k], target[0])

    qc.compose(build_inverse_qft(N_COUNTING),
               qubits=list(counting), inplace=True)

    # BUG: the inverse-QFT implementation deliberately omits the
    # final SWAPs (see its docstring). The caller MUST reverse the
    # counting qubits before measurement; otherwise the counts come
    # out bit-reversed and the phase reading is wrong.
    qc.measure(counting, cr)
    return qc


def run_phase_estimation(shots: int = 4096) -> dict:
    qc = estimate_t_gate_phase()
    backend = Aer.get_backend("qasm_simulator")
    job = execute(qc, backend=backend, shots=shots)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(run_phase_estimation())
'''
    fixed = '''"""Quantum phase estimation for the T-gate eigenstate.

Estimates phase phi such that T|1> = exp(i*pi/4)|1>, i.e., phi = 1/8.
Uses three counting qubits, giving a 1/8 quantization grid; the
expected most-frequent outcome corresponds to the binary fraction
0.001 = 1/8.
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


N_COUNTING = 3


def build_inverse_qft(n_qubits: int) -> QuantumCircuit:
    """Standard inverse QFT on `n_qubits` qubits.

    Convention: this implementation does NOT include the SWAPs that
    reverse the qubit order at the output. The caller is responsible
    for reversing the qubit order before reading out the counting
    register.
    """
    qr = QuantumRegister(n_qubits, name="q")
    iqft = QuantumCircuit(qr, name="iqft")
    for j in reversed(range(n_qubits)):
        iqft.h(qr[j])
        for m in range(j):
            iqft.cp(-np.pi / 2 ** (j - m), qr[m], qr[j])
    return iqft


def estimate_t_gate_phase() -> QuantumCircuit:
    """Build the QPE circuit for the T-gate eigenstate."""
    counting = QuantumRegister(N_COUNTING, name="ctr")
    target = QuantumRegister(1, name="tgt")
    cr = ClassicalRegister(N_COUNTING, name="meas")
    qc = QuantumCircuit(counting, target, cr)

    qc.x(target[0])
    for k in range(N_COUNTING):
        qc.h(counting[k])
        qc.id(target[0])

    for k in range(N_COUNTING):
        repetitions = 2 ** k
        for _ in range(repetitions):
            qc.cp(np.pi / 4, counting[k], target[0])

    qc.compose(build_inverse_qft(N_COUNTING),
               qubits=list(counting), inplace=True)

    for k in range(N_COUNTING // 2):
        qc.swap(counting[k], counting[N_COUNTING - 1 - k])

    qc.measure(counting, cr)
    return qc


def run_phase_estimation(shots: int = 4096) -> dict:
    qc = estimate_t_gate_phase()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    return job.result().get_counts(qc)
'''
    return buggy, fixed, {
        "family": "syn_endianness",
        "circuit": "T-gate phase estimation, 3 counting qubits",
        "summary": "Counting register read in wrong endianness (final "
                   "SWAPs omitted before measurement). Plus deprecated iden.",
        "n_qubits": 4,
        "expected_difficulty": "high for Pure-LLM (the bug is the absence "
                               "of code; full rewrites tend to overlook).",
    }


# ---------------------------------------------------------------------------
def case_08_qaoa_maxcut() -> tuple[str, str, dict]:
    """QAOA single-layer with sign error + local_*_simulator."""
    buggy = '''"""Single-layer QAOA for MaxCut on a triangle graph.

Uses the standard QAOA ansatz with depth p=1 to find an approximate
MaxCut on the 3-vertex triangle K3. The cost Hamiltonian is
    H_C = sum over edges (1/2)(I - Z_i Z_j)
which we want to MAXIMIZE. The unitary corresponding to evolving
under H_C for time gamma is
    U_C(gamma) = exp(-i * gamma * H_C)
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import Aer
from qiskit import transpile


TRIANGLE_EDGES = [(0, 1), (1, 2), (0, 2)]


def apply_cost_unitary(qc: QuantumCircuit, qr: QuantumRegister,
                       gamma: float) -> None:
    """Apply U_C(gamma) = exp(-i * gamma * H_C) for a triangle graph."""
    for (i, j) in TRIANGLE_EDGES:
        qc.cx(qr[i], qr[j])
        # BUG: the coefficient should be -gamma (we want exp(-i*gamma*H_C),
        # and H_C contains a -Z_i Z_j term per edge, so the rotation
        # angle on Z_j after the CNOT conjugation is -gamma). Using
        # +gamma here implements the WRONG sign of the cost evolution
        # and the optimizer will chase the minimum-cut, not maximum.
        qc.rz(gamma, qr[j])
        qc.cx(qr[i], qr[j])


def apply_mixer_unitary(qc: QuantumCircuit, qr: QuantumRegister,
                        beta: float) -> None:
    """Apply U_M(beta) = exp(-i * beta * sum_i X_i)."""
    for k in range(len(qr)):
        qc.rx(2 * beta, qr[k])


def qaoa_maxcut_single_layer(gamma: float = 0.7,
                             beta: float = 0.4) -> QuantumCircuit:
    """Build a depth-1 QAOA circuit for MaxCut on the triangle."""
    n = 3
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    for k in range(n):
        qc.h(qr[k])

    apply_cost_unitary(qc, qr, gamma)
    apply_mixer_unitary(qc, qr, beta)

    qc.measure(qr, cr)
    return qc


def estimate_cut_distribution(shots: int = 4096) -> dict:
    qc = qaoa_maxcut_single_layer()
    backend = Aer.get_backend("local_qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    return job.result().get_counts(qc)


if __name__ == "__main__":
    print(estimate_cut_distribution())
'''
    fixed = '''"""Single-layer QAOA for MaxCut on a triangle graph.

Uses the standard QAOA ansatz with depth p=1 to find an approximate
MaxCut on the 3-vertex triangle K3. The cost Hamiltonian is
    H_C = sum over edges (1/2)(I - Z_i Z_j)
which we want to MAXIMIZE. The unitary corresponding to evolving
under H_C for time gamma is
    U_C(gamma) = exp(-i * gamma * H_C)
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import Aer
from qiskit import transpile


TRIANGLE_EDGES = [(0, 1), (1, 2), (0, 2)]


def apply_cost_unitary(qc: QuantumCircuit, qr: QuantumRegister,
                       gamma: float) -> None:
    """Apply U_C(gamma) = exp(-i * gamma * H_C) for a triangle graph."""
    for (i, j) in TRIANGLE_EDGES:
        qc.cx(qr[i], qr[j])
        qc.rz(-gamma, qr[j])
        qc.cx(qr[i], qr[j])


def apply_mixer_unitary(qc: QuantumCircuit, qr: QuantumRegister,
                        beta: float) -> None:
    """Apply U_M(beta) = exp(-i * beta * sum_i X_i)."""
    for k in range(len(qr)):
        qc.rx(2 * beta, qr[k])


def qaoa_maxcut_single_layer(gamma: float = 0.7,
                             beta: float = 0.4) -> QuantumCircuit:
    """Build a depth-1 QAOA circuit for MaxCut on the triangle."""
    n = 3
    qr = QuantumRegister(n, name="q")
    cr = ClassicalRegister(n, name="c")
    qc = QuantumCircuit(qr, cr)

    for k in range(n):
        qc.h(qr[k])

    apply_cost_unitary(qc, qr, gamma)
    apply_mixer_unitary(qc, qr, beta)

    qc.measure(qr, cr)
    return qc


def estimate_cut_distribution(shots: int = 4096) -> dict:
    qc = qaoa_maxcut_single_layer()
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    return job.result().get_counts(qc)
'''
    return buggy, fixed, {
        "family": "syn_qaoa_sign",
        "circuit": "Single-layer QAOA on triangle MaxCut",
        "summary": "Cost-Hamiltonian rotation has wrong sign (+gamma "
                   "instead of -gamma); QAOA optimizes MIN-cut instead of "
                   "MAX-cut. Plus local_qasm_simulator legacy backend name.",
        "n_qubits": 3,
        "expected_difficulty": "high for Pure-LLM (sign convention; "
                               "requires algorithm understanding).",
    }


# ---------------------------------------------------------------------------
def case_09_chsh_test() -> tuple[str, str, dict]:
    """CHSH inequality with wrong basis-rotation angle + get_data misuse."""
    buggy = '''"""CHSH inequality measurement on a Bell pair.

Computes the CHSH correlator
    S = E(a, b) - E(a, b') + E(a', b) + E(a', b')
which is bounded above by 2 in any local hidden-variable theory and
reaches the Tsirelson bound 2*sqrt(2) ~ 2.828 in quantum mechanics
when Alice measures along {Z, X} and Bob measures along the rotated
bases at angles {pi/8, -pi/8} (i.e., (Z+X)/sqrt(2) and (Z-X)/sqrt(2)).
"""
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def prepare_singlet_state() -> QuantumCircuit:
    """Prepare the entangled singlet state (|01> - |10>) / sqrt(2)."""
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.x(qr[0]); qc.x(qr[1])
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    return qc


def apply_bob_basis_rotation(qc: QuantumCircuit,
                             qubit_index: int,
                             which: str) -> None:
    """Rotate Bob's qubit so that a Z measurement projects onto the
    specified rotated basis.

    Bob's two measurement settings are
        b  = (Z + X) / sqrt(2)   <=> rotate by +pi/8 about Y
        b' = (Z - X) / sqrt(2)   <=> rotate by -pi/8 about Y
    """
    qr = qc.qregs[0]
    if which == "b":
        # BUG: the standard CHSH protocol uses pi/8 here. pi/4 is the
        # angle for the {X, Y} measurement combination, not {b, b'}.
        qc.ry(np.pi / 4, qr[qubit_index])
    elif which == "b_prime":
        qc.ry(-np.pi / 4, qr[qubit_index])
    else:
        raise ValueError(f"Unknown Bob setting: {which!r}")


def measure_chsh_correlator(alice_setting: str,
                            bob_setting: str,
                            shots: int = 4096) -> float:
    """Single-pair correlator E(alice, bob) on the singlet state."""
    qc = prepare_singlet_state()
    qr = qc.qregs[0]; cr = qc.cregs[0]

    if alice_setting == "x":
        qc.h(qr[0])
    apply_bob_basis_rotation(qc, qubit_index=1, which=bob_setting)

    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])

    backend = Aer.get_backend("qasm_simulator")
    job = execute(qc, backend=backend, shots=shots)
    counts = job.result().get_data(qc)

    expectation = 0.0
    for bitstr, n in counts.items():
        a_bit = int(bitstr[-1]); b_bit = int(bitstr[-2])
        sign = (+1) if (a_bit == b_bit) else (-1)
        expectation += sign * (n / shots)
    return expectation


def compute_chsh_value() -> float:
    """Compute S = E(z,b) - E(z,b') + E(x,b) + E(x,b')."""
    e_zb  = measure_chsh_correlator("z", "b")
    e_zbp = measure_chsh_correlator("z", "b_prime")
    e_xb  = measure_chsh_correlator("x", "b")
    e_xbp = measure_chsh_correlator("x", "b_prime")
    return e_zb - e_zbp + e_xb + e_xbp


if __name__ == "__main__":
    s = compute_chsh_value()
    print(f"CHSH S value: {s:.3f}  (Tsirelson bound: 2*sqrt(2) ~ 2.828)")
'''
    fixed = '''"""CHSH inequality measurement on a Bell pair.

Computes the CHSH correlator
    S = E(a, b) - E(a, b') + E(a', b) + E(a', b')
which is bounded above by 2 in any local hidden-variable theory and
reaches the Tsirelson bound 2*sqrt(2) ~ 2.828 in quantum mechanics
when Alice measures along {Z, X} and Bob measures along the rotated
bases at angles {pi/8, -pi/8} (i.e., (Z+X)/sqrt(2) and (Z-X)/sqrt(2)).
"""
import numpy as np
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


def prepare_singlet_state() -> QuantumCircuit:
    """Prepare the entangled singlet state (|01> - |10>) / sqrt(2)."""
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.x(qr[0]); qc.x(qr[1])
    qc.h(qr[0])
    qc.cx(qr[0], qr[1])
    return qc


def apply_bob_basis_rotation(qc: QuantumCircuit,
                             qubit_index: int,
                             which: str) -> None:
    """Rotate Bob's qubit so that a Z measurement projects onto the
    specified rotated basis.

    Bob's two measurement settings are
        b  = (Z + X) / sqrt(2)   <=> rotate by +pi/8 about Y
        b' = (Z - X) / sqrt(2)   <=> rotate by -pi/8 about Y
    """
    qr = qc.qregs[0]
    if which == "b":
        qc.ry(np.pi / 8, qr[qubit_index])
    elif which == "b_prime":
        qc.ry(-np.pi / 8, qr[qubit_index])
    else:
        raise ValueError(f"Unknown Bob setting: {which!r}")


def measure_chsh_correlator(alice_setting: str,
                            bob_setting: str,
                            shots: int = 4096) -> float:
    """Single-pair correlator E(alice, bob) on the singlet state."""
    qc = prepare_singlet_state()
    qr = qc.qregs[0]; cr = qc.cregs[0]

    if alice_setting == "x":
        qc.h(qr[0])
    apply_bob_basis_rotation(qc, qubit_index=1, which=bob_setting)

    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])

    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    counts = job.result().get_counts(qc)

    expectation = 0.0
    for bitstr, n in counts.items():
        a_bit = int(bitstr[-1]); b_bit = int(bitstr[-2])
        sign = (+1) if (a_bit == b_bit) else (-1)
        expectation += sign * (n / shots)
    return expectation


def compute_chsh_value() -> float:
    """Compute S = E(z,b) - E(z,b') + E(x,b) + E(x,b')."""
    e_zb  = measure_chsh_correlator("z", "b")
    e_zbp = measure_chsh_correlator("z", "b_prime")
    e_xb  = measure_chsh_correlator("x", "b")
    e_xbp = measure_chsh_correlator("x", "b_prime")
    return e_zb - e_zbp + e_xb + e_xbp
'''
    return buggy, fixed, {
        "family": "syn_chsh_basis",
        "circuit": "CHSH inequality test on a Bell pair",
        "summary": "Bob's measurement basis rotation uses pi/4 instead of "
                   "pi/8; the CHSH bound cannot be saturated. Plus "
                   "deprecated get_data() and execute().",
        "n_qubits": 2,
        "expected_difficulty": "high for Pure-LLM (subtle algorithmic; "
                               "the wrong angle still parses).",
    }


# ---------------------------------------------------------------------------
def case_10_vqe_expectation() -> tuple[str, str, dict]:
    """VQE expectation with sign convention error + iden + local_*."""
    buggy = '''"""Estimate <ZZ> on a 2-qubit ansatz from measurement counts.

Uses an RY ansatz, measures both qubits in the Z basis, and converts
the bit-strings to the (+/-)1 eigenvalues of Z to estimate <ZZ>.
"""
import math
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import Aer, execute


def build_ry_ansatz(theta_0: float, theta_1: float) -> QuantumCircuit:
    """Apply RY(theta) to each qubit followed by an entangling CNOT."""
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.ry(theta_0, qr[0])
    qc.ry(theta_1, qr[1])
    qc.cx(qr[0], qr[1])
    qc.iden(qr[0])
    qc.iden(qr[1])
    qc.measure(qr, cr)
    return qc


def bitstring_to_zz_eigenvalue(bitstr: str) -> int:
    """Convert a 2-bit string to the eigenvalue of Z_0 Z_1.

    Z|0> = +|0> and Z|1> = -|1>, so ZZ has eigenvalue +1 when the two
    bits are equal and -1 when they differ.
    """
    bit0 = int(bitstr[-1])
    bit1 = int(bitstr[-2])
    # BUG: the eigenvalue mapping is inverted. Bit 0 should map to +1,
    # bit 1 should map to -1; the product is +1 for equal bits and -1
    # for different bits. Returning +1 for differing bits and -1 for
    # equal bits flips the sign of every measured expectation value.
    return -1 if bit0 == bit1 else +1


def measure_zz_expectation(theta_0: float, theta_1: float,
                           shots: int = 4096) -> float:
    """Sample <ZZ> on the ansatz prepared with the given angles."""
    qc = build_ry_ansatz(theta_0, theta_1)
    backend = Aer.get_backend("local_qasm_simulator")
    job = execute(qc, backend=backend, shots=shots)
    result = job.result()
    counts = result.get_counts(qc)
    expectation = sum(bitstring_to_zz_eigenvalue(b) * (n / shots)
                      for b, n in counts.items())
    return expectation


if __name__ == "__main__":
    val = measure_zz_expectation(theta_0=math.pi / 3,
                                 theta_1=math.pi / 4)
    print(f"<ZZ> estimate: {val:+.3f}")
'''
    fixed = '''"""Estimate <ZZ> on a 2-qubit ansatz from measurement counts.

Uses an RY ansatz, measures both qubits in the Z basis, and converts
the bit-strings to the (+/-)1 eigenvalues of Z to estimate <ZZ>.
"""
import math
from qiskit import (QuantumCircuit, QuantumRegister, ClassicalRegister,
                    transpile)
from qiskit_aer import Aer


def build_ry_ansatz(theta_0: float, theta_1: float) -> QuantumCircuit:
    """Apply RY(theta) to each qubit followed by an entangling CNOT."""
    qr = QuantumRegister(2, name="q")
    cr = ClassicalRegister(2, name="c")
    qc = QuantumCircuit(qr, cr)
    qc.ry(theta_0, qr[0])
    qc.ry(theta_1, qr[1])
    qc.cx(qr[0], qr[1])
    qc.id(qr[0])
    qc.id(qr[1])
    qc.measure(qr, cr)
    return qc


def bitstring_to_zz_eigenvalue(bitstr: str) -> int:
    """Convert a 2-bit string to the eigenvalue of Z_0 Z_1.

    Z|0> = +|0> and Z|1> = -|1>, so ZZ has eigenvalue +1 when the two
    bits are equal and -1 when they differ.
    """
    bit0 = int(bitstr[-1])
    bit1 = int(bitstr[-2])
    return +1 if bit0 == bit1 else -1


def measure_zz_expectation(theta_0: float, theta_1: float,
                           shots: int = 4096) -> float:
    """Sample <ZZ> on the ansatz prepared with the given angles."""
    qc = build_ry_ansatz(theta_0, theta_1)
    backend = Aer.get_backend("qasm_simulator")
    job = backend.run(transpile(qc, backend), shots=shots)
    result = job.result()
    counts = result.get_counts(qc)
    expectation = sum(bitstring_to_zz_eigenvalue(b) * (n / shots)
                      for b, n in counts.items())
    return expectation
'''
    return buggy, fixed, {
        "family": "syn_vqe_sign",
        "circuit": "<ZZ> expectation on RY ansatz",
        "summary": "Eigenvalue mapping inverted (+1 for unequal bits "
                   "instead of equal); every <ZZ> estimate has wrong sign. "
                   "Plus deprecated iden and local_qasm_simulator.",
        "n_qubits": 2,
        "expected_difficulty": "high for Pure-LLM (sign convention in a "
                               "function the model has to reason about).",
    }


# ---------------------------------------------------------------------------
ROSTER = [
    ("case_syn_06_grover_search",        case_06_grover_search),
    ("case_syn_07_phase_estimation",     case_07_phase_estimation),
    ("case_syn_08_qaoa_maxcut",          case_08_qaoa_maxcut),
    ("case_syn_09_chsh_test",            case_09_chsh_test),
    ("case_syn_10_vqe_expectation",      case_10_vqe_expectation),
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
    print(f"\nWrote {len(ROSTER)} new synthetic cases to {OUT_ROOT}")


if __name__ == "__main__":
    main()
