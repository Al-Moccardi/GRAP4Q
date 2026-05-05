"""Linear cluster state on a 4-qubit register.

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
