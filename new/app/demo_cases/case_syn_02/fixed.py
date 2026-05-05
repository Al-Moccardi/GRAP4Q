"""Conditioned single-qubit rotation using a measurement outcome.

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
