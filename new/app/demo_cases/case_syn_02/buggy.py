"""Conditioned single-qubit rotation using a measurement outcome.

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
