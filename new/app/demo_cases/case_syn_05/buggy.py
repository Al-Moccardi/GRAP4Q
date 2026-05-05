"""Inverse QFT on a 3-qubit register.

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
