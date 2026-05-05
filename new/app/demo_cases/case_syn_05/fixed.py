"""Inverse QFT on a 3-qubit register.

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
