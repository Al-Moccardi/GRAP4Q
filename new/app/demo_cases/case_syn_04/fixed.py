"""Multi-stage variational protocol for a 4-qubit problem.

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
